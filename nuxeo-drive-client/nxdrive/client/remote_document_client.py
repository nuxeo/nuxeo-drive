"""API to access remote Nuxeo documents for synchronization."""

import unicodedata
from collections import namedtuple
from datetime import datetime
import os
import urllib2
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME
from nxdrive.client.common import safe_filename
from nxdrive.logging_config import get_logger
from nxdrive.client.common import NotFound
from nxdrive.client.base_automation_client import BaseAutomationClient


log = get_logger(__name__)


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
    'state', # Nuxeo lifecycle state
    'has_blob', # If this doc has blob
    'filename' # Filename of document
])


class NuxeoDocumentInfo(BaseNuxeoDocumentInfo):
    """Data Transfer Object for doc info on the Remote Nuxeo repository"""

    # Consistency with the local client API
    def get_digest(self):
        return self.digest


class RemoteDocumentClient(BaseAutomationClient):
    """Nuxeo document oriented Automation client

    Uses Automation standard document API. Deprecated in NuxeDrive
    since now using FileSystemItem API.
    Kept here for tests and later extraction of a generic API.
    """

    # Override constructor to initialize base folder
    # which is specific to RemoteDocumentClient
    def __init__(self, server_url, user_id, device_id, client_version,
                 proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository=DEFAULT_REPOSITORY_NAME,
                 ignored_prefixes=None, ignored_suffixes=None,
                 base_folder=None, timeout=20, blob_timeout=None,
                 cookie_jar=None, upload_tmp_dir=None, check_suspended=None):
        super(RemoteDocumentClient, self).__init__(
            server_url, user_id, device_id, client_version,
            proxies=proxies, proxy_exceptions=proxy_exceptions,
            password=password, token=token, repository=repository,
            ignored_prefixes=ignored_prefixes,
            ignored_suffixes=ignored_suffixes,
            timeout=timeout, blob_timeout=blob_timeout,
            cookie_jar=cookie_jar, upload_tmp_dir=upload_tmp_dir,
            check_suspended=check_suspended)

        # fetch the root folder ref
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
                    self._check_ref(ref), self.server_url))
            return None
        return self._doc_to_info(self.fetch(self._check_ref(ref)),
                                 fetch_parent_uid=fetch_parent_uid)

    def get_content(self, ref):
        """Download and return the binary content of a document

        Beware that the content is loaded in memory.
        """
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
        self.execute_with_blob_streaming("Blob.Attach", file_path,
                                         filename=filename, document=ref,
                                         mime_type=mime_type)
        return ref

    def update_content(self, ref, content, filename=None):
        """Update a document with the given content

        Creates a temporary file from the content then streams it.
        """
        if filename is None:
            filename = self.get_info(ref).name
        self.attach_blob(self._check_ref(ref), content, filename)

    def stream_update(self, ref, file_path, filename=None, mime_type=None, apply_versioning_policy=False):
        """Update a document by streaming the file with the given path"""
        ref = self._check_ref(ref)
        op_name = 'NuxeoDrive.AttachBlob' if self.is_nuxeo_drive_attach_blob() else 'Blob.Attach'
        params = {'document': ref}
        if self.is_nuxeo_drive_attach_blob():
            params.update({'applyVersioningPolicy': apply_versioning_policy})
        self.execute_with_blob_streaming(op_name, file_path, filename=filename, mime_type=mime_type, **params)

    def delete(self, ref, use_trash=True):
        op_input = "doc:" + self._check_ref(ref)
        if use_trash:
            try:
                return self.execute("Document.SetLifeCycle", op_input=op_input,
                                     value='delete')
            except urllib2.HTTPError as e:
                if e.code == 500:
                    return self.execute("Document.Delete", op_input=op_input)
                raise
        else:
            return self.execute("Document.Delete", op_input=op_input)

    def undelete(self, ref):
        op_input = "doc:" + self._check_ref(ref)
        return self.execute("Document.SetLifeCycle", op_input=op_input,
                            value='undelete')

    def delete_content(self, ref, xpath=None):
        return self.delete_blob(self._check_ref(ref), xpath=xpath)

    def exists(self, ref, use_trash=True, include_versions=False):
        ref = self._check_ref(ref)
        id_prop = 'ecm:path' if ref.startswith('/') else 'ecm:uuid'
        if use_trash:
            lifecyle_pred = "AND ecm:currentLifeCycleState != 'deleted'"
        else:
            lifecyle_pred = ""
        if include_versions:
            version_pred = ""
        else:
            version_pred = "AND ecm:isCheckedInVersion = 0"

        query = ("SELECT * FROM Document WHERE %s = '%s' %s %s"
                 " LIMIT 1") % (
            id_prop, ref, lifecyle_pred, version_pred)
        results = self.query(query)
        return len(results[u'entries']) == 1

    def check_writable(self, ref):
        # TODO: which operation can be used to perform a permission check?
        return True

    def _check_ref(self, ref):
        if ref.startswith('/'):
            # This is a path ref (else an id ref)
            if self._base_folder_path is not None:
                if self._base_folder_path.endswith('/'):
                    ref = self._base_folder_path + ref[1:]
                else:
                    ref = self._base_folder_path + ref
        return ref

    def _doc_to_info(self, doc, fetch_parent_uid=True, parent_uid=None):
        """Convert Automation document description to NuxeoDocumentInfo"""
        props = doc['properties']
        name = props['dc:title']
        filename = None
        folderish = 'Folderish' in doc['facets']
        try:
            last_update = datetime.strptime(doc['lastModified'],
                                            "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            # no millisecond?
            last_update = datetime.strptime(doc['lastModified'],
                                            "%Y-%m-%dT%H:%M:%SZ")
        lastContributor = props['dc:lastContributor']

        # TODO: support other main files
        has_blob = False
        if folderish:
            digestAlgorithm = None
            digest = None
        else:
            blob = props.get('file:content')
            if blob is None:
                note = props.get('note:note')
                if note is None:
                    digestAlgorithm = None
                    digest = None
                else:
                    import hashlib
                    m = hashlib.md5()
                    m.update(note.encode('utf-8'))
                    digest = m.hexdigest()
                    digestAlgorithm = 'md5'
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
                digestAlgorithm = blob.get('digestAlgorithm')
                if digestAlgorithm is not None:
                    digestAlgorithm = digestAlgorithm.lower().replace('-', '')
                digest = blob.get('digest')
                filename = blob.get('name')

        # XXX: we need another roundtrip just to fetch the parent uid...
        if parent_uid is None and fetch_parent_uid:
            parent_uid = self.fetch(os.path.dirname(doc['path']))['uid']

        # Normalize using NFC to make the tests more intuitive
        if 'uid:major_version' in props and 'uid:minor_version' in props:
            version = str(props['uid:major_version']) + "." + str(props['uid:minor_version'])
        else:
            version = None
        if name is not None:
            name = unicodedata.normalize('NFC', name)
        return NuxeoDocumentInfo(
            self._base_folder_ref, name, doc['uid'], parent_uid,
            doc['path'], folderish, last_update, lastContributor,
            digestAlgorithm, digest, self.repository, doc['type'], version, doc['state'], has_blob, filename)

    def _filtered_results(self, entries, fetch_parent_uid=True,
                          parent_uid=None):
        # Filter out filenames that would be ignored by the file system client
        # so as to be consistent.
        filtered = []
        for info in [self._doc_to_info(d, fetch_parent_uid=fetch_parent_uid,
                                       parent_uid=parent_uid)
                     for d in entries]:
            ignore = False

            for suffix in self.ignored_suffixes:
                if info.name.endswith(suffix):
                    ignore = True
                    break

            for prefix in self.ignored_prefixes:
                if info.name.startswith(prefix):
                    ignore = True
                    break

            if not ignore:
                filtered.append(info)

        return filtered

    #
    # Generic Automation features reused from nuxeolib
    #

    # Document category

    def create(self, ref, doc_type, name=None, properties=None):
        name = safe_filename(name)
        return self.execute("Document.Create", op_input="doc:" + ref,
            type=doc_type, name=name, properties=properties)

    def update(self, ref, properties=None):
        return self.execute("Document.Update", op_input="doc:" + ref,
            properties=properties)

    def set_property(self, ref, xpath, value):
        return self.execute("Document.SetProperty", op_input="doc:" + ref,
            xpath=xpath, value=value)

    def get_children(self, ref):
        return self.execute("Document.GetChildren", op_input="doc:" + ref)

    def get_parent(self, ref):
        return self.execute("Document.GetParent", op_input="doc:" + ref)

    def lock(self, ref):
        return self.execute("Document.Lock", op_input="doc:" + self._check_ref(ref))

    def unlock(self, ref):
        return self.execute("Document.Unlock", op_input="doc:" + self._check_ref(ref))

    def move(self, ref, target, name=None):
        return self.execute("Document.Move",
                            op_input="doc:" + self._check_ref(ref),
                            target=self._check_ref(target), name=name)

    def copy(self, ref, target, name=None):
        return self.execute("Document.Copy",
                            op_input="doc:" + self._check_ref(ref),
                            target=self._check_ref(target), name=name)

    def create_version(self, ref, increment='None'):
        doc = self.execute("Document.CreateVersion",
                            op_input="doc:" + self._check_ref(ref),
                            increment=increment)
        return doc['uid']

    def get_versions(self, ref):
        extra_headers = {'X-NXfetch.document': 'versionLabel'}
        versions = self.execute("Document.GetVersions",
                            op_input="doc:" + self._check_ref(ref), extra_headers=extra_headers)
        return [(v['uid'], v['versionLabel']) for v in versions['entries']]

    def restore_version(self, version):
        doc = self.execute("Document.RestoreVersion",
                            op_input="doc:" + self._check_ref(version))
        return doc['uid']

    def block_inheritance(self, ref, overwrite=True):
        op_input = "doc:" + self._check_ref(ref)
        self.execute("Document.SetACE",
            op_input=op_input,
            user="Administrator",
            permission="Everything",
            overwrite=overwrite)
        self.execute("Document.SetACE",
            op_input=op_input,
            user="Everyone",
            permission="Everything",
            grant="false",
            overwrite=False)

    # These ones are special: no 'op_input' parameter

    def fetch(self, ref):
        try:
            return self.execute("Document.Fetch", value=ref)
        except urllib2.HTTPError as e:
            if e.code == 404:
                raise NotFound("Failed to fetch document %r on server %r" % (
                    ref, self.server_url))
            raise e

    def query(self, query, language=None):
        return self.execute("Document.Query", query=query, language=language)

    # Blob category
    def get_blob(self, ref, file_out=None):
        if isinstance(ref, NuxeoDocumentInfo):
            doc_id = ref.uid
            if not ref.has_blob and ref.doc_type == "Note":
                doc = self.fetch(doc_id)
                content = doc['properties'].get('note:note')
                if file_out is not None:
                    if content is not None:
                        encoded_content = content.encode('utf-8')
                    with open(file_out, 'wb') as f:
                        f.write(encoded_content)
                return content
        else:
            doc_id = ref
        return self.execute("Blob.Get", op_input="doc:" + doc_id,
                            timeout=self.blob_timeout, file_out=file_out)

    def attach_blob(self, ref, blob, filename):
        file_path = self.make_tmp_file(blob)
        try:
            return self.execute_with_blob_streaming("Blob.Attach", file_path, filename=filename, document=ref)
        finally:
            os.remove(file_path)

    def delete_blob(self, ref, xpath=None):
        return self.execute("Blob.Remove", op_input="doc:" + ref, xpath=xpath)

    #
    # Nuxeo Drive specific operations
    #

    def get_repository_names(self):
        return self.execute("GetRepositories")[u'value']

    def get_roots(self):
        entries = self.execute("NuxeoDrive.GetRoots")[u'entries']
        return self._filtered_results(entries, fetch_parent_uid=False)

    def register_as_root(self, ref):
        ref = self._check_ref(ref)
        self.execute("NuxeoDrive.SetSynchronization", op_input="doc:" + ref,
                     enable=True)
        return True

    def unregister_as_root(self, ref):
        ref = self._check_ref(ref)
        self.execute("NuxeoDrive.SetSynchronization", op_input="doc:" + ref,
                     enable=False)
        return True

    def make_file_in_user_workspace(self, content, filename):
        """Stream the given content as a document in the user workspace"""
        file_path = self.make_tmp_file(content)
        try:
            return self.execute_with_blob_streaming("UserWorkspace.CreateDocumentFromBlob", file_path,
                                                    filename=filename)
        finally:
            os.remove(file_path)

    def activate_profile(self, profile):
        self.execute("NuxeoDrive.SetActiveFactories", profile=profile)

    def deactivate_profile(self, profile):
        self.execute("NuxeoDrive.SetActiveFactories", profile=profile,
                     enable=False)

    def get_update_info(self):
        return self.execute("NuxeoDrive.GetClientUpdateInfo")

    def add_to_locally_edited_collection(self, ref):
        doc = self.execute("NuxeoDrive.AddToLocallyEditedCollection",
                           op_input="doc:" + self._check_ref(ref))
        return doc['uid']

    def get_collection_members(self, ref):
        docs = self.execute("Collection.GetDocumentsFromCollection",
                           op_input="doc:" + self._check_ref(ref))
        return [doc['uid'] for doc in docs['entries']]
