# coding: utf-8
""" API to access remote Nuxeo documents for synchronization. """

import datetime
import os
import unicodedata
from collections import namedtuple
from logging import getLogger

from dateutil import parser
from nuxeo.exceptions import HTTPError

from nxdrive.utils import make_tmp_file
from .common import NotFound, safe_filename
from .nuxeo_client import BaseNuxeo
from ..options import Options

log = getLogger(__name__)


# Make the following an optional binding configuration

FILE_TYPE = 'File'
FOLDER_TYPE = 'Folder'
DEFAULT_TYPES = ('File', 'Note', 'Workspace', 'Folder')


MAX_CHILDREN = 1000

# Data transfer objects

BaseNuxeoDocumentInfo = namedtuple('NuxeoDocumentInfo', [
    'root',  # ref of the document that serves as sync root
    'name',  # title of the document (not guaranteed to be locally unique)
    'uid',   # ref of the document
    'parent_uid',  # ref of the parent document
    'path',  # remote path (useful for ordering)
    'folderish',  # True is can host child documents
    'last_modification_time',  # last update time
    'last_contributor',  # last contributor
    'digest_algorithm',  # digest algorithm of the document's blob
    'digest',  # digest of the document's blob
    'repository',  # server repository name
    'doc_type',  # Nuxeo document type
    'version',  # Nuxeo version
    'state',  # Nuxeo lifecycle state
    'has_blob',  # If this doc has blob
    'filename',  # Filename of document
    'lock_owner',  # lock owner
    'lock_created',  # lock creation time
    'permissions',  # permissions
])


class NuxeoDocumentInfo(BaseNuxeoDocumentInfo):
    """Data Transfer Object for doc info on the Remote Nuxeo repository"""

    # Consistency with the local client API
    def get_digest(self):
        return self.digest


class RemoteDocumentClient(BaseNuxeo):
    """Nuxeo document oriented Automation client

    Uses Automation standard document API. Deprecated in NuxeDrive
    since now using FileSystemItem API.
    Kept here for tests and later extraction of a generic API.
    """

    # Override constructor to initialize base folder
    # which is specific to RemoteDocumentClient
    def __init__(self, *args, **kwargs):
        base_folder = kwargs.pop('base_folder', None)
        super(RemoteDocumentClient, self).__init__(*args, **kwargs)
        self.set_base_folder(base_folder)

    def set_base_folder(self, base_folder):
        if base_folder is not None:
            base_folder_doc = self.fetch(base_folder)
            self._base_folder_ref = base_folder_doc['uid']
            self._base_folder_path = base_folder_doc['path']
        else:
            self._base_folder_ref, self._base_folder_path = None, None

    #
    # API common with the local client API
    #
    def get_info(self, ref, raise_if_missing=True, fetch_parent_uid=True,
                 use_trash=True, include_versions=False):
        if not self.exists(ref, use_trash=use_trash,
                           include_versions=include_versions):
            if raise_if_missing:
                raise NotFound("Could not find '%s' on '%s'" % (
                    self._check_ref(ref), self.client.host))
            return None
        return self.doc_to_info(self.fetch(self._check_ref(ref)),
                                fetch_parent_uid=fetch_parent_uid)

    def get_content(self, ref):
        """
        Download and return the binary content of a document
        Beware that the content is loaded in memory.
        """

        if not isinstance(ref, NuxeoDocumentInfo):
            ref = self._check_ref(ref)
        return self.get_blob(ref)

    # TODO: allow getting content by streaming the response to an output file
    # See RemoteFileSystemClient.stream_content

    def get_children_info(self, ref, types=DEFAULT_TYPES, limit=MAX_CHILDREN):
        ref = self._check_ref(ref)
        query = (
            "SELECT * FROM Document"
            "       WHERE ecm:parentId = '%s'"
            "       AND ecm:primaryType IN ('%s')"
            "       AND ecm:currentLifeCycleState != 'deleted'"
            "       AND ecm:isVersion = 0"
            "       ORDER BY dc:title, dc:created LIMIT %d"
        ) % (ref, "', '".join(types), limit)

        entries = self.query(query)[u'entries']
        if len(entries) == MAX_CHILDREN:
            # TODO: how to best handle this case? A warning and return an empty
            # list, a dedicated exception?
            raise RuntimeError("Folder %r on server %r has more than the"
                               "maximum number of children: %d" % (
                                   ref, self.server_url, MAX_CHILDREN))

        return self._filtered_results(entries)

    def make_folder(self, parent, name, doc_type=FOLDER_TYPE):
        # TODO: make it possible to configure context dependent:
        # - SocialFolder under SocialFolder or SocialWorkspace
        # - Folder under Folder or Workspace
        # This configuration should be provided by a special operation on the
        # server.
        parent = self._check_ref(parent)
        doc = self.create(parent, doc_type, name=name,
                    properties={'dc:title': name})
        return doc[u'uid']

    def make_file(self, parent, name, content=None, doc_type=FILE_TYPE):
        """Create a document of the given type with the given name and content

        Creates a temporary file from the content then streams it.
        """
        parent = self._check_ref(parent)
        properties = {'dc:title': name}
        if doc_type is 'Note' and content is not None:
            properties['note:note'] = content
        doc = self.create(parent, doc_type, name=name, properties=properties)
        ref = doc[u'uid']
        if doc_type is not 'Note' and content is not None:
            self.attach_blob(ref, content, name)
        return ref

    def stream_file(self, parent, name, file_path, filename=None,
                    mime_type=None, doc_type=FILE_TYPE):
        """Create a document by streaming the file with the given path"""
        ref = self.make_file(parent, name, doc_type=doc_type)
        self.upload(
            file_path, filename=filename, mime_type=mime_type,
            command='Blob.Attach', document=ref)
        return ref

    def update_content(self, ref, content, filename=None):
        """Update a document with the given content

        Creates a temporary file from the content then streams it.
        """
        if filename is None:
            filename = self.get_info(ref).name
        self.attach_blob(self._check_ref(ref), content, filename)

    def stream_update(
        self,
        ref,
        file_path,
        filename=None,
        mime_type=None,
        apply_versioning_policy=False,
    ):
        """Update a document by streaming the file with the given path"""
        ref = self._check_ref(ref)
        op_name = ('NuxeoDrive.AttachBlob'
                   if self.is_nuxeo_drive_attach_blob()
                   else 'Blob.Attach')
        params = {'document': ref}
        if self.is_nuxeo_drive_attach_blob():
            params.update({'applyVersioningPolicy': apply_versioning_policy})
        self.upload(
            file_path, filename=filename, mime_type=mime_type,
            command=op_name, **params)

    def delete(self, ref, use_trash=True):
        input_obj = 'doc:' + self._check_ref(ref)
        if use_trash:
            try:
                # We need more stability in the Trash behavior before
                # we can use it instead of the SetLifeCycle operation
                # if version_lt(Options.server_version, '10.1'):
                return self.operations.execute(command='Document.SetLifeCycle',
                                               input_obj=input_obj,
                                               value='delete')
                # else:
                #    return self.operations.execute(command='Document.Trash', input_obj=input_obj)
            except HTTPError as e:
                if e.status != 500:
                    raise
        return self.operations.execute(command='Document.Delete',
                                       input_obj=input_obj)

    def undelete(self, uid):
        input_obj = 'doc:' + uid
        # We need more stability in the Trash behavior before
        # we can use it instead of the SetLifeCycle operation
        # if version_lt(Options.server_version, '10.1'):
        return self.operations.execute(command='Document.SetLifeCycle',
                                       input_obj=input_obj, value='undelete')
        # else:
        #    return self.operations.execute(command='Document.Untrash', input_obj=input_obj)

    def delete_content(self, ref, xpath=None):
        return self.delete_blob(self._check_ref(ref), xpath=xpath)

    def exists(self, ref, use_trash=True, include_versions=False):
        # type: (unicode, bool, bool) -> bool
        """
        Check if a document exists on the server.

        :param ref: Document reference (UID).
        :param use_trash: Filter documents inside the trash.
        :param include_versions:
        :rtype: bool
        """
        ref = self._check_ref(ref)
        id_prop = 'ecm:path' if ref.startswith('/') else 'ecm:uuid'
        if use_trash:
            lifecyle_pred = "AND ecm:currentLifeCycleState != 'deleted'"
        else:
            lifecyle_pred = ""
        if include_versions:
            version_pred = ""
        else:
            version_pred = "AND ecm:isVersion = 0"

        query = ("SELECT * FROM Document WHERE %s = '%s' %s %s"
                 " LIMIT 1") % (
            id_prop, ref, lifecyle_pred, version_pred)
        results = self.query(query)
        return len(results[u'entries']) == 1

    def _check_ref(self, ref):
        if ref.startswith('/') and self._base_folder_path is not None:
            # This is a path ref (else an id ref)
            if self._base_folder_path.endswith('/'):
                ref = self._base_folder_path + ref[1:]
            else:
                ref = self._base_folder_path + ref
        return ref

    def doc_to_info(self, doc, fetch_parent_uid=True, parent_uid=None):
        """Convert Automation document description to NuxeoDocumentInfo"""
        props = doc['properties']
        name = props['dc:title']
        filename = None
        folderish = 'Folderish' in doc['facets']
        try:
            last_update = datetime.datetime.strptime(
                doc['lastModified'], '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            # no millisecond?
            last_update = datetime.datetime.strptime(
                doc['lastModified'], '%Y-%m-%dT%H:%M:%SZ')
        last_contributor = props['dc:lastContributor']

        # TODO: support other main files
        has_blob = False
        if folderish:
            digest_algorithm = None
            digest = None
        else:
            blob = props.get('file:content')
            if blob is None:
                note = props.get('note:note')
                if note is None:
                    digest_algorithm = None
                    digest = None
                else:
                    import hashlib
                    m = hashlib.md5()
                    m.update(note.encode('utf-8'))
                    digest = m.hexdigest()
                    digest_algorithm = 'md5'
                    ext = '.txt'
                    mime_type = props.get('note:mime_type')
                    if mime_type == 'text/html':
                        ext = '.html'
                    elif mime_type == 'text/xml':
                        ext = '.xml'
                    elif mime_type == 'text/x-web-markdown':
                        ext = '.md'
                    if not name.endswith(ext):
                        filename = name + ext
                    else:
                        filename = name
            else:
                has_blob = True
                digest_algorithm = blob.get('digestAlgorithm')
                if digest_algorithm is not None:
                    digest_algorithm = digest_algorithm.lower().replace('-', '')
                digest = blob.get('digest')
                filename = blob.get('name')

        # Lock info
        lock_owner = doc.get('lockOwner')
        lock_created = doc.get('lockCreated')
        if lock_created is not None:
            lock_created = parser.parse(lock_created)

        # Permissions
        permissions = doc.get('contextParameters', {}).get('permissions', None)

        # XXX: we need another roundtrip just to fetch the parent uid...
        if parent_uid is None and fetch_parent_uid:
            parent_uid = self.fetch(os.path.dirname(doc['path']))['uid']

        # Normalize using NFC to make the tests more intuitive
        if 'uid:major_version' in props and 'uid:minor_version' in props:
            version = (str(props['uid:major_version'])
                       + '.'
                       + str(props['uid:minor_version']))
        else:
            version = None
        if name is not None:
            name = unicodedata.normalize('NFC', name)
        return NuxeoDocumentInfo(
            self._base_folder_ref, name, doc['uid'], parent_uid,
            doc['path'], folderish, last_update, last_contributor,
            digest_algorithm, digest, self.client.repository, doc['type'],
            version, doc['state'], has_blob, filename,
            lock_owner, lock_created, permissions)

    def _filtered_results(self, entries, fetch_parent_uid=True,
                          parent_uid=None):
        # Filter out filenames that would be ignored by the file system client
        # so as to be consistent.
        filtered = []
        for info in [self.doc_to_info(d, fetch_parent_uid=fetch_parent_uid,
                                      parent_uid=parent_uid)
                     for d in entries]:

            name = info.name.lower()
            if (name.endswith(Options.ignored_suffixes)
                    or name.startswith(Options.ignored_prefixes)):
                continue

            filtered.append(info)

        return filtered

    #
    # Generic Automation features reused from nuxeolib
    #

    # Document category

    def create(self, ref, doc_type, name=None, properties=None):
        name = safe_filename(name)
        return self.operations.execute(
            command='Document.Create', input_obj='doc:' + ref,
            type=doc_type, name=name, properties=properties)

    def update(self, ref, properties=None):
        return self.operations.execute(
            command='Document.Update', input_obj='doc:' + ref,
            properties=properties)

    def get_children(self, ref):
        return self.operations.execute(
            command='Document.GetChildren', input_obj='doc:' + ref)

    def is_locked(self, ref):
        data = self.fetch(ref, extra_headers={'fetch-document': 'lock'})
        return 'lockCreated' in data

    def lock(self, ref):
        return self.operations.execute(
            command='Document.Lock', input_obj='doc:' + self._check_ref(ref))

    def unlock(self, ref):
        return self.operations.execute(
            command='Document.Unlock', input_obj='doc:' + self._check_ref(ref))

    def create_user(self, user_name, **kwargs):
        return self.operations.execute(
            command='User.CreateOrUpdate', username=user_name, **kwargs)

    def move(self, ref, target, name=None):
        return self.operations.execute(
            command='Document.Move', input_obj='doc:' + self._check_ref(ref),
            target=self._check_ref(target), name=name)

    def copy(self, ref, target, name=None):
        return self.operations.execute(
            command='Document.Copy', input_obj='doc:' + self._check_ref(ref),
            target=self._check_ref(target), name=name)

    def create_version(self, ref, increment='None'):
        doc = self.operations.execute(
            command='Document.CreateVersion',
            input_obj='doc:' + self._check_ref(ref), increment=increment)
        return doc['uid']

    def get_versions(self, ref):
        headers = {'X-NXfetch.document': 'versionLabel'}
        versions = self.operations.execute(command='Document.GetVersions',
            input_obj='doc:' + self._check_ref(ref), headers=headers)
        return [(v['uid'], v['versionLabel']) for v in versions['entries']]

    def restore_version(self, version):
        doc = self.operations.execute(
            command='Document.RestoreVersion',
            input_obj='doc:' + self._check_ref(version))
        return doc['uid']

    def block_inheritance(self, ref, overwrite=True):
        input_obj = 'doc:' + self._check_ref(ref)
        self.operations.execute(
            command='Document.SetACE',
            input_obj=input_obj,
            user='Administrator',
            permission='Everything',
            overwrite=overwrite)
        self.operations.execute(
            command='Document.SetACE',
            input_obj=input_obj,
            user='Everyone',
            permission='Everything',
            grant='false',
            overwrite=False)

    # These ones are special: no 'input_obj' parameter

    def fetch(self, ref, **kwargs):
        try:
            return self.operations.execute(
                command='Document.Fetch', value=ref, **kwargs)
        except HTTPError as e:
            if e.status == 404:
                raise NotFound('Failed to fetch document %r on server %r' % (
                    ref, self.client.host))
            raise e

    def query(self, query, language=None):
        return self.operations.execute(
            command='Document.Query', query=query, language=language)

    # Blob category
    def get_blob(self, ref, file_out=None):
        if isinstance(ref, NuxeoDocumentInfo):
            doc_id = ref.uid
            if not ref.has_blob and ref.doc_type == 'Note':
                doc = self.fetch(doc_id)
                content = doc['properties'].get('note:note')
                if file_out is not None and content is not None:
                    with open(file_out, 'wb') as f:
                        f.write(content.encode('utf-8'))
                return content
        else:
            doc_id = ref
        return self.operations.execute(
            command='Blob.Get', input_obj='doc:' + doc_id, json=False,
            timeout=self.blob_timeout, file_out=file_out)

    def attach_blob(self, ref, blob, filename):
        file_path = make_tmp_file(self.upload_tmp_dir, blob)
        try:
            return self.upload(
                file_path, filename=filename, command='Blob.Attach',
                document=ref)
        finally:
            os.remove(file_path)

    def delete_blob(self, ref, xpath=None):
        return self.operations.execute(
            command='Blob.Remove', input_obj='doc:' + ref, xpath=xpath)

    def log_on_server(self, message, level='WARN'):
        """ Log the current test server side.  Helpful for debugging. """
        return self.operations.execute(
            command='Log', message=message, level=level.lower())

    #
    # Nuxeo Drive specific operations
    #
    def get_roots(self):
        res = self.operations.execute(command='NuxeoDrive.GetRoots')
        return self._filtered_results(res['entries'], fetch_parent_uid=False)

    def get_update_info(self):
        return self.operations.execute(
            command='NuxeoDrive.GetClientUpdateInfo')

    def register_as_root(self, ref):
        self.operations.execute(
            command='NuxeoDrive.SetSynchronization',
            input_obj='doc:' + self._check_ref(ref), enable=True)
        return True

    def unregister_as_root(self, ref):
        self.operations.execute(
            command='NuxeoDrive.SetSynchronization',
            input_obj='doc:' + self._check_ref(ref), enable=False)
        return True
