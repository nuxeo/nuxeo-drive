"""Uniform API to access both local and remote resource for synchronization."""

from collections import namedtuple
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
import hashlib
import base64
import json
import logging as log
import mimetypes
import os
import random
import shutil
import time
import urllib2
import re


# Make the following an optional binding configuration
FILE_TYPE = 'File'
FOLDER_TYPE = 'Folder'

BUFFER_SIZE = 1024 ** 2
MAX_CHILDREN = 1000


def safe_filename(name, replacement='-'):
    """Replace invalid character in candidate filename"""
    return re.sub(r'(/|\\)', replacement, name)


class Unauthorized(Exception):

    def __init__(self, server_url, user_id):
        self.server_url = server_url
        self.user_id = user_id

    def __str__(self):
        return ("'%s' is not authorized to access '%s' with"
                "the provided credentials" % (self.user_id, self.server_url))


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

    # TODO: initialize the prefixes and sufffix with a dedicated Nuxeo
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
        return os.path.join(parent, name)

    def make_file(self, parent, name, content=None):
        os_path, name = self._abspath_deduped(parent, name)
        with open(os_path, "wcb") as f:
            if content:
                f.write(content)
        return os.path.join(parent, name)

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
        if "." in name:
            name, extension = name.rsplit('.', 1)
            suffix = "." + extension
        else:
            name, suffix = name, ""

        for _ in range(1000):
            os_path = self._abspath(os.path.join(parent, name + suffix))
            if not os.path.exists(os_path):
                return os_path, name + suffix

            # the is a duplicated file, try to come with a new name
            m = re.match(r'(.*)__(\d)', name)
            if m:
                short_name, increment = m.groups()
                name = "%s__%d" % (short_name, int(increment) + 1)
            else:
                name = name + '__1'

        raise ValueError("Failed to de-duplicate '%s' under '%s'" % (
            orig_name, parent))


class NuxeoClient(object):
    """Client for the Nuxeo Content Automation HTTP API"""

    def __init__(self, server_url, user_id, password,
                 base_folder='/', repository="default",
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
        self.user_id = user_id
        self.password = password
        self.base_folder = base_folder

        # TODO: actually use the repository info
        self.repository = repository

        self.auth = 'Basic %s' % base64.b64encode(
                self.user_id + ":" + self.password).strip()

        cookie_processor = urllib2.HTTPCookieProcessor()
        self.opener = urllib2.build_opener(cookie_processor)
        self.automation_url = server_url + 'site/automation/'

        self.fetch_api()

        # fetch the root folder ref
        base_folder = base_folder if not None else '/'
        self._base_folder_ref = self.fetch(base_folder)['uid']
        self._base_folder_path = self.fetch(base_folder)['path']

    def fetch_api(self):
        headers = {
            "Authorization": self.auth,
        }
        base_error_message = (
            "Failed not connect to Nuxeo Content Automation on server %r"
            " with user %r"
        ) % (self.server_url, self.user_id)
        try:
            req = urllib2.Request(self.automation_url, headers=headers)
            response = json.loads(self.opener.open(req).read())
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id)
            else:
                raise IOError(base_error_message + ": HTTP error %d" % e.code)
        except Exception as e:
            raise IOError(base_error_message + ": " + e)
        self.operations = {}
        for operation in response["operations"]:
            self.operations[operation['id']] = operation

    #
    # Client API common with the FS API
    #

    def exists(self, ref):
        ref = self._check_ref(ref)
        if ref.startswith('/'):
            results = self.query(
                "SELECT * FROM Document WHERE ecm:path = '%s' LIMIT 1" % ref)
        else:
            results = self.query(
                "SELECT * FROM Document WHERE ecm:uuid = '%s' LIMIT 1" % ref)
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

        results = self.query(query)[u'entries']
        if len(results) == MAX_CHILDREN:
            # TODO: how to best handle this case? A warning and return an empty
            # list, a dedicated exception?
            raise RuntimeError("Folder %r on server %r has more than the"
                               "maximum number of children: %d" % (
                                   ref, self.server_url, MAX_CHILDREN))

        # Filter out filenames that would be ignored by the file system client
        # so as to be consistent.
        filtered = []
        for info in [self._doc_to_info(d) for d in results]:
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

    def get_info(self, ref, raise_if_missing=True):
        ref = self._check_ref(ref)
        if not self.exists(ref):
            if raise_if_missing:
                raise NotFound("Could not find '%s' on '%s'" % (
                    ref, self.server_url))
            return None
        return self._doc_to_info(self.fetch(ref))

    def _doc_to_info(self, doc):
        """Convert Automation document description to NuxeoDocumentInfo"""
        props = doc['properties']
        folderish = 'Folderish' in doc['facets']
        last_update = datetime.strptime(doc['lastModified'],
                                        "%Y-%m-%dT%H:%M:%S.%fZ")

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
        parent_uid = self.fetch(os.path.dirname(doc['path']))['uid']
        return NuxeoDocumentInfo(
            self._base_folder_ref, props['dc:title'], doc['uid'], parent_uid,
            doc['path'], folderish, last_update, digest)

    def get_content(self, ref):
        ref = self._check_ref(ref)
        return self.get_blob(ref)

    def update_content(self, ref, content, name=None):
        ref = self._check_ref(ref)
        if name is None:
            name = self.get_info(ref).name
        self.attach_blob(ref, content, name)

    def _check_ref(self, ref):
        if (ref.startswith('/')
            and not ref.startswith(self._base_folder_path + '/')):
            ref = os.path.join(self._base_folder_path, ref[1:])
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

    #
    # Generic Automation features reused from nuxeolib
    #

    # Document category

    def create(self, ref, type, name=None, properties=None):
        return self._execute("Document.Create", input="doc:" + ref,
            type=type, name=name, properties=properties)

    def update(self, ref, properties=None):
        return self._execute("Document.Update", input="doc:" + ref,
            properties=properties)

    def set_property(self, ref, xpath, value):
        return self._execute("Document.SetProperty", input="doc:" + ref,
            xpath=xpath, value=value)

    def delete(self, ref):
        ref = self._check_ref(ref)
        return self._execute("Document.Delete", input="doc:" + ref)

    def get_children(self, ref):
        return self._execute("Document.GetChildren", input="doc:" + ref)

    def get_parent(self, ref):
        return self._execute("Document.GetParent", input="doc:" + ref)

    def lock(self, ref):
        return self._execute("Document.Lock", input="doc:" + ref)

    def unlock(self, ref):
        return self._execute("Document.Unlock", input="doc:" + ref)

    def move(self, ref, target, name=None):
        return self._execute("Document.Move", input="doc:" + ref,
            target=target, name=name)

    def copy(self, ref, target, name=None):
        return self._execute("Document.Copy", input="doc:" + ref,
            target=target, name=name)

    # These ones are special: no 'input' parameter

    def fetch(self, ref):
        return self._execute("Document.Fetch", value=ref)

    def query(self, query, language=None):
        return self._execute("Document.Query", query=query, language=language)

    # Blob category

    def get_blob(self, ref):
        return self._execute("Blob.Get", input="doc:" + ref)

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
            "Authorization": self.auth,
            "Content-Type": ('multipart/related;boundary="%s";'
                             'type="application/json+nxrequest";'
                             'start="request"')
            % boundary,
        }
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
        req = urllib2.Request(url, data, headers)
        #try:
        resp = self.opener.open(req)
        #except Exception as e:
        #    self._handle_error(e)
        #    raise e
        s = resp.read()
        return s

    def _execute(self, command, input=None, **params):
        self._check_params(command, input, params)
        headers = {
            "Content-Type": "application/json+nxrequest",
            "Authorization": self.auth,
            "X-NXDocumentProperties": "*",
        }
        d = {}
        if params:
            d['params'] = {}
            for k, v in params.items():
                if v is None:
                    continue
                if k == 'properties':
                    s = ""
                    for propname, propvalue in v.items():
                        s += "%s=%s\n" % (propname, propvalue)
                    d['params'][k] = s.strip()
                else:
                    d['params'][k] = v
        if input:
            d['input'] = input
        if d:
            data = json.dumps(d)
        else:
            data = None

        req = urllib2.Request(self.automation_url + command, data, headers)
        try:
            resp = self.opener.open(req)
        except Exception, e:
            self._handle_error(e)
            raise

        info = resp.info()
        s = resp.read()

        if info.get('content-type', '').startswith("application/json"):
            return json.loads(s) if s else None
        else:
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

    def _handle_error(self, e):
        log.error(e)
        if hasattr(e, "fp"):
            detail = e.fp.read()
            try:
                exc = json.loads(detail)
                log.error(exc['message'])
                log.error(exc['stack'])
            except:
                # Error message should always be a JSON message,
                # but sometimes it's not
                log.error(detail)
