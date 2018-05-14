# coding: utf-8
import logging
import os

from nuxeo.exceptions import HTTPError

from nxdrive.client import NuxeoDocumentInfo, Remote, safe_filename
from nxdrive.logging_config import configure
from nxdrive.utils import make_tmp_file

FILE_TYPE = 'File'
FOLDER_TYPE = 'Folder'
DEFAULT_TYPES = ('File', 'Note', 'Workspace', 'Folder')


def configure_logger():
    formatter = logging.Formatter(
        '%(thread)-4d %(module)-16s %(levelname).1s %(message)s')
    configure(console_level='TRACE',
              command_name='test',
              force_configure=True,
              formatter=formatter)


# Configure test logger
configure_logger()
log = logging.getLogger(__name__)


class RemoteTest(Remote):

    _download_remote_error = None
    _upload_remote_error = None
    _server_error = None
    raise_on = None

    def __init__(self, *args, **kwargs):
        super(RemoteTest, self).__init__(*args, **kwargs)
        self.exec_fn = self.operations.execute
        self.operations.execute = self.execute

    def download(self, *args, **kwargs):
        self._raise(self._download_remote_error, *args, **kwargs)
        return super(RemoteTest, self).download(*args, **kwargs)

    def upload(self, *args, **kwargs):
        self._raise(self._upload_remote_error, *args, **kwargs)
        return super(RemoteTest, self).upload(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self._raise(self._server_error, *args, **kwargs)
        return self.exec_fn(*args, **kwargs)

    def make_download_raise(self, error):
        """ Make next calls to do_get() raise the provided exception. """
        self._download_remote_error = error

    def make_upload_raise(self, error):
        """ Make next calls to upload() raise the provided exception. """
        self._upload_remote_error = error

    def make_server_call_raise(self, error):
        """ Make next calls to the server raise the provided exception. """
        self._server_error = error

    def _raise(self, exc, *args, **kwargs):
        """ Make the next calls raise `exc` if `raise_on()` allowed it. """

        if exc:
            if not callable(self.raise_on):
                raise exc
            if self.raise_on(*args, **kwargs):
                raise exc

    def reset_errors(self):
        """ Remove custom errors. """

        self._download_remote_error = None
        self._upload_remote_error = None
        self._server_error = None
        self.raise_on = None

    def activate_profile(self, profile):
        self.operations.execute(
            command='NuxeoDrive.SetActiveFactories', profile=profile)

    def deactivate_profile(self, profile):
        self.operations.execute(
            command='NuxeoDrive.SetActiveFactories', profile=profile,
            enable=False)

    def mass_import(self, target_path, nb_nodes, nb_threads=12):
        tx_timeout = 3600
        url = 'site/randomImporter/run'
        params = {
            'targetPath': target_path,
            'batchSize': 50,
            'nbThreads': nb_threads,
            'interactive': 'true',
            'fileSizeKB': 1,
            'nbNodes': nb_nodes,
            'nonUniform': 'true',
            'transactionTimeout': tx_timeout
        }
        headers = {'Nuxeo-Transaction-Timeout': str(tx_timeout)}

        log.info('Calling random mass importer on %s with %d threads '
                 'and %d nodes', target_path, nb_threads, nb_nodes)

        self.client.request('GET', url, params=params, headers=headers,
                            timeout=tx_timeout)

    def wait_for_async_and_es_indexing(self):
        """ Use for test_volume only. """

        tx_timeout = 3600
        headers = {'Nuxeo-Transaction-Timeout': str(tx_timeout)}
        self.operations.execute(
            command='Elasticsearch.WaitForIndexing', timeout=tx_timeout,
            headers=headers, timeoutSecond=tx_timeout, refresh=True)

    def result_set_query(self, query):
        return self.operations.execute(
            command='Repository.ResultSetQuery', query=query)

    def log_on_server(self, message, level='WARN'):
        """ Log the current test server side.  Helpful for debugging. """
        return self.operations.execute(
            command='Log', message=message, level=level.lower())

    def wait(self):
        if self.is_elasticsearch_audit():
            self.operations.execute(
                command='NuxeoDrive.WaitForElasticsearchCompletion')
        else:
            # Backward compatibility with JPA audit implementation,
            # in which case we are also backward compatible
            # with date based resolution
            self.operations.execute(
                command='NuxeoDrive.WaitForAsyncCompletion')


class DocRemote(RemoteTest):

    def create(self, ref, doc_type, name=None, properties=None):
        name = safe_filename(name)
        return self.operations.execute(
            command='Document.Create', input_obj='doc:' + ref,
            type=doc_type, name=name, properties=properties)

    def make_folder(self, parent, name, doc_type=FOLDER_TYPE):
        # type (str, str, str) -> str
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

    def make_file_in_user_workspace(self, content, filename):
        """Stream the given content as a document in the user workspace"""
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            return self.upload(file_path, filename=filename,
                               command='UserWorkspace.CreateDocumentFromBlob')
        finally:
            os.remove(file_path)

    def stream_file(self, parent, name, file_path, filename=None,
                    mime_type=None, doc_type=FILE_TYPE):
        """Create a document by streaming the file with the given path"""
        ref = self.make_file(parent, name, doc_type=doc_type)
        self.upload(
            file_path, filename=filename, mime_type=mime_type,
            command='Blob.Attach', document=ref)
        return ref

    def attach_blob(self, ref, blob, filename):
        file_path = make_tmp_file(self.upload_tmp_dir, blob)
        try:
            return self.upload(
                file_path, filename=filename, command='Blob.Attach',
                document=ref)
        finally:
            os.remove(file_path)

    def get_content(self, ref):
        """
        Download and return the binary content of a document
        Beware that the content is loaded in memory.
        """

        if not isinstance(ref, NuxeoDocumentInfo):
            ref = self._check_ref(ref)
        return self.get_blob(ref)

    def update_content(self, ref, content, filename=None):
        """Update a document with the given content

        Creates a temporary file from the content then streams it.
        """
        if filename is None:
            filename = self.get_info(ref).name
        self.attach_blob(self._check_ref(ref), content, filename)

    def move(self, ref, target, name=None):
        return self.operations.execute(
            command='Document.Move', input_obj='doc:' + self._check_ref(ref),
            target=self._check_ref(target), name=name)

    def update(self, ref, properties=None):
        return self.operations.execute(
            command='Document.Update', input_obj='doc:' + ref,
            properties=properties)

    def copy(self, ref, target, name=None):
        return self.operations.execute(
            command='Document.Copy', input_obj='doc:' + self._check_ref(ref),
            target=self._check_ref(target), name=name)

    def delete(self, ref, use_trash=True):
        input_obj = 'doc:' + self._check_ref(ref)
        if use_trash:
            try:
                # We need more stability in the Trash behavior before
                # we can use it instead of the SetLifeCycle operation
                # if version_lt(self.client.server_version, '10.1'):
                return self.operations.execute(command='Document.SetLifeCycle',
                                               input_obj=input_obj,
                                               value='delete')
                # else:
                #    return self.operations.execute(command='Document.Trash',
                #                                   input_obj=input_obj)
            except HTTPError as e:
                if e.status != 500:
                    raise
        return self.operations.execute(command='Document.Delete',
                                       input_obj=input_obj)

    def undelete(self, uid):
        input_obj = 'doc:' + uid
        # We need more stability in the Trash behavior before
        # we can use it instead of the SetLifeCycle operation
        # if version_lt(self.client.server_version, '10.1'):
        return self.operations.execute(command='Document.SetLifeCycle',
                                       input_obj=input_obj, value='undelete')
        # else:
        #    return self.operations.execute(command='Document.Untrash',
        #                                   input_obj=input_obj)

    def delete_content(self, ref, xpath=None):
        return self.delete_blob(self._check_ref(ref), xpath=xpath)

    def delete_blob(self, ref, xpath=None):
        return self.operations.execute(
            command='Blob.Remove', input_obj='doc:' + ref, xpath=xpath)

    def is_locked(self, ref):
        data = self.fetch(ref, headers={'fetch-document': 'lock'})
        return 'lockCreated' in data

    def get_repository_names(self):
        return self.operations.execute(command='GetRepositories')[u'value']

    def get_versions(self, ref):
        headers = {'X-NXfetch.document': 'versionLabel'}
        versions = self.operations.execute(command='Document.GetVersions',
            input_obj='doc:' + self._check_ref(ref), headers=headers)
        return [(v['uid'], v['versionLabel']) for v in versions['entries']]

    def create_version(self, ref, increment='None'):
        doc = self.operations.execute(
            command='Document.CreateVersion',
            input_obj='doc:' + self._check_ref(ref), increment=increment)
        return doc['uid']

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
