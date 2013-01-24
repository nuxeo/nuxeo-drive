"""Uniform API to access both local and remote resource for synchronization."""

from collections import namedtuple
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
import hashlib
import base64
import json
import mimetypes
import os
import random
import shutil
import time
import urllib2
from urllib import urlencode
import re
import sys
from nxdrive.logging_config import get_logger


log = get_logger(__name__)


# Make the following an optional binding configuration
FILE_TYPE = 'File'
FOLDER_TYPE = 'Folder'
DEDUPED_BASENAME_PATTERN = r'^(.*)__(\d{1,3})$'

BUFFER_SIZE = 1024 ** 2
MAX_CHILDREN = 1000

DEVICE_DESCRIPTIONS = {
    'linux2': 'Linux Desktop',
    'darwin': 'Mac OSX Desktop',
    'cygwin': 'Windows Desktop',
    'win32': 'Windows Desktop',
}


def safe_filename(name, replacement='-'):
    """Replace invalid character in candidate filename"""
    return re.sub(r'(/|\\|\*)', replacement, name)



class Unauthorized(Exception):

    def __init__(self, server_url, user_id, code=403):
        self.server_url = server_url
        self.user_id = user_id
        self.code = code

    def __str__(self):
        return ("'%s' is not authorized to access '%s' with"
                " the provided credentials" % (self.user_id, self.server_url))


class NotFound(Exception):
    pass


# Data transfer objects

class FileInfo(object):
    """Data Transfer Object for file info on the Local FS"""

    def __init__(self, root, path, folderish, last_modification_time,
                 digest_func='md5'):
        self.root = root  # the sync root folder local path
        self.path = path  # the truncated path (under the root)
        self.folderish = folderish  # True if a Folder

        # Last OS modification date of the file
        self.last_modification_time = last_modification_time

        # Function to use
        self._digest_func = digest_func.lower()

        # Precompute base name once and for all are it's often useful in
        # practice
        self.name = os.path.basename(path)

        self.filepath = os.path.join(
            root, path[1:].replace('/', os.path.sep))

    def get_digest(self):
        """Lazy computation of the digest"""
        if self.folderish:
            return None
        digester = getattr(hashlib, self._digest_func, None)
        if digester is None:
            raise ValueError('Unknow digest method: ' + self.digest_func)

        h = digester()
        with open(self.filepath, 'rb') as f:
            while True:
                buffer = f.read(BUFFER_SIZE)
                if buffer == '':
                    break
                h.update(buffer)
        return h.hexdigest()



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
])


class NuxeoDocumentInfo(BaseNuxeoDocumentInfo):
    """Data Transfer Object for doc info on the Remote Nuxeo repository"""

    def get_digest(self):
        """Eager retrieval of the digest"""
        return self.digest


# TODO: add support for the move operations

DEFAULT_IGNORED_PREFIXES = [
    '.',  # hidden Unix files
    '~$',  # Windows lock files
]

DEFAULT_IGNORED_SUFFIXES = [
    '~',  # editor buffers
    '.swp',  # vim swap files
    '.lock',  # some process use file locks
    '.LOCK',  # other locks
    '.part',  # partially downloaded files
]


class LocalClient(object):
    """Client API implementation for the local file system"""

    # TODO: initialize the prefixes and suffix with a dedicated Nuxeo
    # Automation operations fetched at controller init time.

    def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                 ignored_suffixes=None):
        if ignored_prefixes is not None:
            self.ignored_prefixes = ignored_prefixes
        else:
            self.ignored_prefixes = DEFAULT_IGNORED_PREFIXES

        if ignored_suffixes is not None:
            self.ignored_suffixes = ignored_suffixes
        else:
            self.ignored_suffixes = DEFAULT_IGNORED_SUFFIXES

        while len(base_folder) > 1 and base_folder.endswith(os.path.sep):
            base_folder = base_folder[:-1]
        self.base_folder = base_folder
        self._digest_func = digest_func

    # Getters
    def get_info(self, ref, raise_if_missing=True):
        os_path = self._abspath(ref)
        if not os.path.exists(os_path):
            if raise_if_missing:
                raise NotFound("Could not found file '%s' under '%s'" % (
                ref, self.base_folder))
            else:
                return None
        folderish = os.path.isdir(os_path)
        stat_info = os.stat(os_path)
        mtime = datetime.fromtimestamp(stat_info.st_mtime)
        path = '/' + os_path[len(self.base_folder) + 1:]
        path = path.replace(os.path.sep, '/')  # unix style path
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unixe inode at all.
        # uid = str(stat_info.st_ino)
        return FileInfo(self.base_folder, path, folderish, mtime,
                        digest_func=self._digest_func)

    def get_content(self, ref):
        return open(self._abspath(ref), "rb").read()

    def get_children_info(self, ref):
        os_path = self._abspath(ref)
        result = []
        children = os.listdir(os_path)
        children.sort()
        for child_name in children:
            ignore = False

            for suffix in self.ignored_suffixes:
                if child_name.endswith(suffix):
                    ignore = True
                    break

            for prefix in self.ignored_prefixes:
                if child_name.startswith(prefix):
                    ignore = True
                    break

            if not ignore:
                if ref == '/':
                    child_ref = ref + child_name
                else:
                    child_ref = ref + '/' + child_name
                try:
                    result.append(self.get_info(child_ref))
                except (OSError, NotFound):
                    # the child file has been deleted in the mean time or while
                    # reading some of its attributes
                    pass

        return result

    def make_folder(self, parent, name):
        os_path, name = self._abspath_deduped(parent, name)
        os.mkdir(os_path)
        if parent == "/":
            return "/" + name
        return parent + "/" + name

    def make_file(self, parent, name, content=None):
        os_path, name = self._abspath_deduped(parent, name)
        with open(os_path, "wb") as f:
            if content:
                f.write(content)
        if parent == "/":
            return "/" + name
        return parent + "/" + name

    def update_content(self, ref, content):
        with open(self._abspath(ref), "wb") as f:
            f.write(content)

    def delete(self, ref):
        # TODO: add support the OS trash?
        os_path = self._abspath(ref)
        if os.path.isfile(os_path):
            os.unlink(os_path)
        elif os.path.isdir(os_path):
            shutil.rmtree(os_path)

    def exists(self, ref):
        os_path = self._abspath(ref)
        return os.path.exists(os_path)

    def check_writable(self, ref):
        os_path = self._abspath(ref)
        return os.access(os_path, os.W_OK)

    def _abspath(self, ref):
        """Absolute path on the operating system"""
        if not ref.startswith('/'):
            raise ValueError("LocalClient expects ref starting with '/'")
        path_suffix = ref[1:].replace('/', os.path.sep)
        return os.path.abspath(os.path.join(self.base_folder, path_suffix))

    def _abspath_deduped(self, parent, orig_name):
        """Absolute path on the operating system with deduplicated names"""
        # make name safe by removing invalid chars
        name = safe_filename(orig_name)

        # decompose the name into actionable components
        name, suffix = os.path.splitext(name)

        for _ in range(1000):
            os_path = self._abspath(os.path.join(parent, name + suffix))
            if not os.path.exists(os_path):
                return os_path, name + suffix

            # the is a duplicated file, try to come with a new name
            m = re.match(DEDUPED_BASENAME_PATTERN, name)
            if m:
                short_name, increment = m.groups()
                name = "%s__%d" % (short_name, int(increment) + 1)
            else:
                name = name + '__1'

        raise ValueError("Failed to de-duplicate '%s' under '%s'" % (
            orig_name, parent))


class NuxeoClient(object):
    """Client for the Nuxeo Content Automation HTTP API"""

    _error = None

    # Parameters used when negotiating authentication token:

    application_name = 'Nuxeo Drive'

    permission = 'ReadWrite'

    def __init__(self, server_url, user_id, device_id,
                 password=None, token=None,
                 base_folder=None, repository="default",
                 ignored_prefixes=None, ignored_suffixes=None):
        if ignored_prefixes is not None:
            self.ignored_prefixes = ignored_prefixes
        else:
            self.ignored_prefixes = DEFAULT_IGNORED_PREFIXES

        if ignored_suffixes is not None:
            self.ignored_suffixes = ignored_suffixes
        else:
            self.ignored_suffixes = DEFAULT_IGNORED_SUFFIXES

        if not server_url.endswith('/'):
            server_url += '/'
        self.server_url = server_url
        self.base_folder = base_folder

        # TODO: actually use the repository info in the requests
        self.repository = repository

        self.user_id = user_id
        self.device_id = device_id
        self._update_auth(password=password, token=token)

        cookie_processor = urllib2.HTTPCookieProcessor()
        self.opener = urllib2.build_opener(cookie_processor)
        self.automation_url = server_url + 'site/automation/'

        self.fetch_api()

        # fetch the root folder ref
        if base_folder is not None:
            base_folder_doc = self.fetch(base_folder)
            self._base_folder_ref = base_folder_doc['uid']
            self._base_folder_path = base_folder_doc['path']
        else:
            self._base_folder_ref, self._base_folder_path = None, None

    def _update_auth(self, password=None, token=None):
        """Select the most appropriate authentication heads based on credentials"""
        if token is not None:
            self.auth = ('X-Authentication-Token', token)
        elif password is not None:
            basic_auth = 'Basic %s' % base64.b64encode(
                    self.user_id + ":" + password).strip()
            self.auth = ("Authorization", basic_auth)
        else:
            raise ValueError("Either password or token must be provided")

    def _get_common_headers(self):
        """Headers to include in every HTTP requests

        Includes the authentication heads (token based or basic auth if no
        token).

        Also include an application name header to make it possible for the
        server to compute access statistics for various client types (e.g.
        browser vs devices).

        """
        return {
            'X-Application-Name': self.application_name,
            self.auth[0]: self.auth[1],
        }

    def request_token(self, revoke=False):
        """Request and return a new token for the user"""

        parameters = {
            'deviceId': self.device_id,
            'applicationName': self.application_name,
            'permission': self.permission,
            'revoke': 'true' if revoke else 'false',
        }
        device_description = DEVICE_DESCRIPTIONS.get(sys.platform)
        if device_description:
            parameters['deviceDescription'] = device_description

        url = self.server_url + 'authentication/token?'
        url += urlencode(parameters)

        headers = self._get_common_headers()
        base_error_message = (
            "Failed not connect to Nuxeo Content Automation on server %r"
            " with user %r"
        ) % (self.server_url, self.user_id)
        try:
            log.trace("Calling '%s' with headers: %r", url, headers)
            req = urllib2.Request(url, headers=headers)
            token = self.opener.open(req).read()
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id, e.code)
            elif e.code == 404:
                # Token based auth is not supported by this server
                return None
            else:
                e.msg = base_error_message + ": HTTP error %d" % e.code
                raise e
        except Exception as e:
            if hasattr(e, 'msg'):
                e.msg = base_error_message + ": " + e.msg
            raise
        # Use the (potentially re-newed) token from now on
        if not revoke:
            self._update_auth(token=token)
        return token

    def revoke_token(self):
        self.request_token(revoke=True)

    def fetch_api(self):
        headers = self._get_common_headers()
        base_error_message = (
            "Failed not connect to Nuxeo Content Automation on server %r"
            " with user %r"
        ) % (self.server_url, self.user_id)
        try:
            req = urllib2.Request(self.automation_url, headers=headers)
            response = json.loads(self.opener.open(req).read())
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id, e.code)
            else:
                e.msg = base_error_message + ": HTTP error %d" % e.code
                raise e
        except Exception as e:
            if hasattr(e, 'msg'):
                e.msg = base_error_message + ": " + e.msg
            raise
        self.operations = {}
        for operation in response["operations"]:
            self.operations[operation['id']] = operation

    def is_addon_installed(self):
        return 'NuxeoDrive.GetRoots' in self.operations

    # Nuxeo Drive specific operations

    def get_repository_names(self):
        return self.execute("GetRepositories")[u'value']

    def get_roots(self):
        entries = self.execute("NuxeoDrive.GetRoots")[u'entries']
        return self._filtered_results(entries, fetch_parent_uid=False)

    def register_as_root(self, ref):
        ref = self._check_ref(ref)
        return self.execute("NuxeoDrive.SetSynchronization",
                             input="doc:" + ref, enable=True)

    def unregister_as_root(self, ref):
        ref = self._check_ref(ref)
        return self.execute("NuxeoDrive.SetSynchronization",
                             input="doc:" + ref, enable=False)

    #
    # Client API common with the FS API
    #

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

    def get_children_info(self, ref):
        ref = self._check_ref(ref)
        # TODO: make the list of document type to synchronize configurable or
        # maybe use a dedicated facet
        types = ['File', 'Workspace', 'Folder', 'SocialFolder']
        query = (
            "SELECT * FROM Document"
            "       WHERE ecm:parentId = '%s'"
            "       AND ecm:primaryType IN ('%s')"
            "       AND ecm:currentLifeCycleState != 'deleted'"
            "       ORDER BY dc:title, dc:created LIMIT %d"
        ) % (ref, "', '".join(types), MAX_CHILDREN)

        entries = self.query(query)[u'entries']
        if len(entries) == MAX_CHILDREN:
            # TODO: how to best handle this case? A warning and return an empty
            # list, a dedicated exception?
            raise RuntimeError("Folder %r on server %r has more than the"
                               "maximum number of children: %d" % (
                                   ref, self.server_url, MAX_CHILDREN))

        return self._filtered_results(entries)

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

    def get_info(self, ref, raise_if_missing=True, fetch_parent_uid=True,
                 use_trash=True):
        if not self.exists(ref, use_trash=use_trash):
            if raise_if_missing:
                raise NotFound("Could not find '%s' on '%s'" % (
                    self._check_ref(ref), self.server_url))
            return None
        return self._doc_to_info(self.fetch(self._check_ref(ref)),
                                 fetch_parent_uid=fetch_parent_uid)

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
        return NuxeoDocumentInfo(
            self._base_folder_ref, props['dc:title'], doc['uid'], parent_uid,
            doc['path'], folderish, last_update, digest, self.repository)

    def get_content(self, ref):
        ref = self._check_ref(ref)
        return self.get_blob(ref)

    def update_content(self, ref, content, name=None):
        if name is None:
            name = self.get_info(ref).name
        self.attach_blob(self._check_ref(ref), content, name)

    def _check_ref(self, ref):
        if self._base_folder_path is None:
            raise RuntimeError("Path handling is disabled on a remote client"
                               " with no base_folder")
        if ref.startswith('/') and self._base_folder_path != '/':
            ref = self._base_folder_path + ref
        return ref

    def make_folder(self, parent, name):
        # TODO: make it possible to configure context dependent:
        # - SocialFolder under SocialFolder or SocialWorkspace
        # - Folder under Folder or Workspace
        # This configuration should be provided by a special operation on the
        # server.
        doc = self.create(parent, FOLDER_TYPE, name=name,
                    properties={'dc:title': name})
        return doc[u'uid']

    def make_file(self, parent, name, content=None):
        doc = self.create(parent, FILE_TYPE, name=name,
                          properties={'dc:title': name})
        ref = doc[u'uid']
        if content is not None:
            self.attach_blob(ref, content, name)
        return ref

    def check_writable(self, ref):
        # TODO: which operation can be used to perform a permission check?
        return True

    def make_raise(self, error):
        """Make next calls to server raise the provided exception"""
        self._error = error

    #
    # Generic Automation features reused from nuxeolib
    #

    # Document category

    def create(self, ref, type, name=None, properties=None):
        return self.execute("Document.Create", input="doc:" + ref,
            type=type, name=name, properties=properties)

    def update(self, ref, properties=None):
        return self.execute("Document.Update", input="doc:" + ref,
            properties=properties)

    def set_property(self, ref, xpath, value):
        return self.execute("Document.SetProperty", input="doc:" + ref,
            xpath=xpath, value=value)

    def delete(self, ref, use_trash=True):
        input = "doc:" + self._check_ref(ref)
        if use_trash:
            try:
                return self.execute("Document.SetLifeCycle", input=input,
                                     value='delete')
            except urllib2.HTTPError as e:
                if e.code == 500:
                    return self.execute("Document.Delete", input=input)
                raise
        else:
            return self.execute("Document.Delete", input=input)

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
        return self.execute("Blob.Get", input="doc:" + ref)

    def attach_blob(self, ref, blob, filename, **params):
        container = MIMEMultipart("related",
                type="application/json+nxrequest",
                start="request")

        params['document'] = ref
        d = {'params': params}
        json_data = json.dumps(d)
        json_part = MIMEBase("application", "json+nxrequest")
        json_part.add_header("Content-ID", "request")
        json_part.set_payload(json_data)
        container.attach(json_part)

        ctype, encoding = mimetypes.guess_type(filename)
        if ctype:
            maintype, subtype = ctype.split('/', 1)
        else:
            maintype, subtype = "application", "binary"
        blob_part = MIMEBase(maintype, subtype)
        blob_part.add_header("Content-ID", "input")
        blob_part.add_header("Content-Transfer-Encoding", "binary")
        ascii_filename = filename.encode('ascii', 'ignore')
        #content_disposition = "attachment; filename=" + ascii_filename
        #quoted_filename = urllib.quote(filename.encode('utf-8'))
        #content_disposition += "; filename filename*=UTF-8''" \
        #    + quoted_filename
        #print content_disposition
        #blob_part.add_header("Content-Disposition:", content_disposition)

        # XXX: Use ASCCI safe version of the filename for now
        blob_part.add_header('Content-Disposition', 'attachment',
                             filename=ascii_filename)

        blob_part.set_payload(blob)
        container.attach(blob_part)

        # Create data by hand :(
        boundary = "====Part=%s=%s===" % (str(time.time()).replace('.', '='),
                                          random.randint(0, 1000000000))
        headers = {
            "Accept": "application/json+nxentity, */*",
            "Content-Type": ('multipart/related;boundary="%s";'
                             'type="application/json+nxrequest";'
                             'start="request"')
            % boundary,
        }
        headers.update(self._get_common_headers())
        data = (
            "--%s\r\n"
            "%s\r\n"
            "--%s\r\n"
            "%s\r\n"
            "--%s--"
        ) % (
            boundary,
            json_part.as_string(),
            boundary,
            blob_part.as_string(),
            boundary,
        )
        url = self.automation_url.encode('ascii') + "Blob.Attach"
        log.trace("Calling '%s' for file '%s'", url, filename)
        req = urllib2.Request(url, data, headers)
        try:
            resp = self.opener.open(req)
        except Exception as e:
            self._log_details(e)
            raise
        s = resp.read()
        return s

    def execute(self, command, input=None, **params):
        if self._error is not None:
            # Simulate a configurable (e.g. network or server) error for the
            # tests
            raise self._error

        self._check_params(command, input, params)
        headers = {
            "Content-Type": "application/json+nxrequest",
            "X-NXDocumentProperties": "*",
        }
        headers.update(self._get_common_headers())
        json_struct = {'params': {}}
        for k, v in params.items():
            if v is None:
                continue
            if k == 'properties':
                s = ""
                for propname, propvalue in v.items():
                    s += "%s=%s\n" % (propname, propvalue)
                json_struct['params'][k] = s.strip()
            else:
                json_struct['params'][k] = v

        if input:
            json_struct['input'] = input

        data = json.dumps(json_struct)

        url = self.automation_url + command
        log.trace("Calling '%s' with json payload: %r", url, data)
        req = urllib2.Request(url, data, headers)
        try:
            resp = self.opener.open(req)
        except Exception, e:
            self._log_details(e)
            raise

        info = resp.info()
        s = resp.read()

        content_type = info.get('content-type', '')
        if content_type.startswith("application/json"):
            log.trace("Response for '%s' with json payload: %r", url, s)
            return json.loads(s) if s else None
        else:
            log.trace("Response for '%s' with content-type: %r", url,
                      content_type)
            return s

    def _check_params(self, command, input, params):
        if command not in self.operations:
            raise ValueError("'%s' is not a registered operations." % command)
        method = self.operations[command]
        required_params = []
        other_params = []
        for param in method['params']:
            if param['required']:
                required_params.append(param['name'])
            else:
                other_params.append(param['name'])

        for param in params.keys():
            if (not param in required_params
                and not param in other_params):
                raise ValueError("Unexpected param '%s' for operation '%s"
                                 % (param, command))
        for param in required_params:
            if not param in params:
                raise ValueError(
                    "Missing required param '%s' for operation '%s'" % (
                        param, command))

        # TODO: add typechecking

    def _log_details(self, e):
        if hasattr(e, "fp"):
            detail = e.fp.read()
            try:
                exc = json.loads(detail)
                log.debug(exc['message'])
                log.debug(exc['stack'])
            except:
                # Error message should always be a JSON message,
                # but sometimes it's not
                log.debug(detail)

    def get_changes(self, last_sync_date=None, last_root_definitions=None):
        return self.execute(
            'NuxeoDrive.GetChangeSummary',
            lastSyncDate=last_sync_date,
            lastSyncActiveRootDefinitions=last_root_definitions)
