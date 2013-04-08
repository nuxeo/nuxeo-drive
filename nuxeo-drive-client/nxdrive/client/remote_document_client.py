"""API to access remote Nuxeo documents for synchronization."""

import unicodedata
from collections import namedtuple
from datetime import datetime
import hashlib
import os
import urllib2
from nxdrive.client.common import safe_filename
from nxdrive.logging_config import get_logger
from nxdrive.client.common import NotFound
from nxdrive.client.base_automation_client import BaseAutomationClient


log = get_logger(__name__)


# Make the following an optional binding configuration

FILE_TYPE = 'File'
FOLDER_TYPE = 'Folder'
DEFAULT_TYPES = ('File', 'Workspace', 'Folder', 'SocialFolder')


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
    'digest',  # digest of the document
    'repository',  # server repository name
    'doc_type',  # Nuxeo document type
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
    def __init__(self, server_url, user_id, device_id,
                 password=None, token=None, repository="default",
                 ignored_prefixes=None, ignored_suffixes=None,
                 base_folder=None, timeout=10, blob_timeout=None):
        super(RemoteDocumentClient, self).__init__(
            server_url, user_id, device_id, password, token, repository,
            ignored_prefixes, ignored_suffixes, timeout=timeout,
            blob_timeout=blob_timeout)

        # fetch the root folder ref
        self.base_folder = base_folder
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
                 use_trash=True):
        if not self.exists(ref, use_trash=use_trash):
            if raise_if_missing:
                raise NotFound("Could not find '%s' on '%s'" % (
                    self._check_ref(ref), self.server_url))
            return None
        return self._doc_to_info(self.fetch(self._check_ref(ref)),
                                 fetch_parent_uid=fetch_parent_uid)

    def get_content(self, ref):
        ref = self._check_ref(ref)
        return self.get_blob(ref)

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
        parent = self._check_ref(parent)
        doc = self.create(parent, FILE_TYPE, name=name,
                          properties={'dc:title': name})
        ref = doc[u'uid']
        if content is not None:
            self.attach_blob(ref, content, name)
        return ref

    def update_content(self, ref, content, name=None):
        if name is None:
            name = self.get_info(ref).name
        self.attach_blob(self._check_ref(ref), content, name)

    def delete(self, ref, use_trash=True):
        op_input = "doc:" + self._check_ref(ref)
        if use_trash:
            try:
                return self.execute("Document.SetLifeCycle", input=op_input,
                                     value='delete')
            except urllib2.HTTPError as e:
                if e.code == 500:
                    return self.execute("Document.Delete", input=op_input)
                raise
        else:
            return self.execute("Document.Delete", input=op_input)

    def exists(self, ref, use_trash=True):
        ref = self._check_ref(ref)
        id_prop = 'ecm:path' if ref.startswith('/') else 'ecm:uuid'
        if use_trash:
            lifecyle_pred = " AND ecm:currentLifeCycleState != 'deleted'"
        else:
            lifecyle_pred = ""

        query = ("SELECT * FROM Document WHERE %s = '%s' %s"
                 " AND ecm:isCheckedInVersion = 0 LIMIT 1") % (
            id_prop, ref, lifecyle_pred)
        results = self.query(query)
        return len(results[u'entries']) == 1

    def check_writable(self, ref):
        # TODO: which operation can be used to perform a permission check?
        return True

    def _check_ref(self, ref):
        if ref.startswith('/'):
            if self._base_folder_path is None:
                raise RuntimeError("Path handling is disabled on a remote"
                                   " client with no base_folder parameter:"
                                   " use idref instead")
            elif self._base_folder_path.endswith('/'):
                ref = self._base_folder_path + ref[1:]
            else:
                ref = self._base_folder_path + ref
        return ref

    def _doc_to_info(self, doc, fetch_parent_uid=True, parent_uid=None):
        """Convert Automation document description to NuxeoDocumentInfo"""
        props = doc['properties']
        folderish = 'Folderish' in doc['facets']
        try:
            last_update = datetime.strptime(doc['lastModified'],
                                            "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            # no millisecond?
            last_update = datetime.strptime(doc['lastModified'],
                                            "%Y-%m-%dT%H:%M:%SZ")

        # TODO: support other main files
        if folderish:
            digest = None
        else:
            blob = props.get('file:content')
            if blob is None:
                # Be consistent with empty files on the local filesystem
                # TODO: find a way to introspect which hash function to use
                # from the repository configuration
                digest = hashlib.md5().hexdigest()
            else:
                digest = blob.get('digest')

        # XXX: we need another roundtrip just to fetch the parent uid...
        if parent_uid is None and fetch_parent_uid:
            parent_uid = self.fetch(os.path.dirname(doc['path']))['uid']

        # Normalize using NFKC to make the tests more intuitive
        name = props['dc:title']
        if name is not None:
            name = unicodedata.normalize('NFKC', name)
        return NuxeoDocumentInfo(
            self._base_folder_ref, name, doc['uid'], parent_uid,
            doc['path'], folderish, last_update, digest, self.repository,
            doc['type'])

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
        return self.execute("Document.Create", input="doc:" + ref,
            type=doc_type, name=name, properties=properties)

    def update(self, ref, properties=None):
        return self.execute("Document.Update", input="doc:" + ref,
            properties=properties)

    def set_property(self, ref, xpath, value):
        return self.execute("Document.SetProperty", input="doc:" + ref,
            xpath=xpath, value=value)

    def get_children(self, ref):
        return self.execute("Document.GetChildren", input="doc:" + ref)

    def get_parent(self, ref):
        return self.execute("Document.GetParent", input="doc:" + ref)

    def lock(self, ref):
        return self.execute("Document.Lock", input="doc:" + ref)

    def unlock(self, ref):
        return self.execute("Document.Unlock", input="doc:" + ref)

    def move(self, ref, target, name=None):
        return self.execute("Document.Move", input="doc:" + ref,
            target=target, name=name)

    def copy(self, ref, target, name=None):
        return self.execute("Document.Copy", input="doc:" + ref,
            target=target, name=name)

    # These ones are special: no 'input' parameter

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

    def get_blob(self, ref):
        return self.execute("Blob.Get", input="doc:" + ref,
                            timeout=self.blob_timeout)

    def attach_blob(self, ref, blob, filename, **params):
        return self.execute_with_blob("Blob.Attach",
            blob, filename, document=ref)

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
        self.execute("NuxeoDrive.SetSynchronization", input="doc:" + ref,
                     enable=True)
        return True

    def unregister_as_root(self, ref):
        ref = self._check_ref(ref)
        self.execute("NuxeoDrive.SetSynchronization", input="doc:" + ref,
                     enable=False)
        return True
