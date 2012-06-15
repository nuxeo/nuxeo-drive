"""Uniform API to access both local and remote resource for synchronization."""

from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
import base64
import json
import logging as log
import mimetypes
import os
import random
import shutil
import time
import urllib2
import urllib


# Make the following an optional binding configuration
FILE_TYPE = 'File'
FOLDER_TYPE = 'Folder'


class Unauthorized(Exception):

    def __init__(self, server_url, user_id):
        self.server_url = server_url
        self.user_id = user_id

    def __str__(self):
        return ("'%s' is not authorized to access '%s' with"
                "the provided credentials" % (self.user_id, self.server_url))


class Info(object):
    """Data transfer object representing the state in one tree"""

    def __init__(self, root, path, uid, type, mtime, digest=None):
        self.root
        self.path = path
        self.uid = uid
        self.type = type
        self.mtime = mtime
        self.digest = digest

    def __repr__(self):
        return "Info(%r, %r, %r, %r, %r, %r)" % (
            self.root, self.path, self.uid, self.type, self.mtime,
            self.digest)

    def is_folderish(self):
        return self.type == 'folder'


# TODO: add support for the move operations

class LocalClient(object):
    """Client API implementation for the local file system"""

    def __init__(self, base_folder):
        self.base_folder = base_folder

    def authenticate(self):
        # TODO
        return True

    # Getters
    def get_info(self, ref):
        os_path = os.path.join(self.base_folder, ref)
        if not os.path.exists(os_path):
            return None
        if os.path.isdir(os_path):
            type = 'folder'
        else:
            type = 'file'
        stat_info = os.stat(os_path)
        mtime = datetime.fromtimestamp(stat_info.st_mtime)
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unixe inode at all.
        # uid = str(stat_info.st_ino)
        return Info(os_path[len(self.base_folder) + 1:], None, type, mtime)

    def get_content(self, ref):
        return open(os.path.join(self.base_folder, ref), "rb").read()

    def get_descendants(self, ref=None):
        if ref is None:
            os_path = self.base_folder
        else:
            os_path = os.path.join(self.base_folder, ref)
        result = []
        for root, dirs, files in os.walk(os_path):
            for dir in dirs:
                if not dir.startswith('.'):
                    descendant_ref = os.path.join(os_path, root, dir)
                    result.append(self.get_info(descendant_ref))
            for file in files:
                if not file.startswith('.'):
                    descendant_ref = os.path.join(os_path, root, file)
                    result.append(self.get_info(descendant_ref))
        return result

    def make_folder(self, parent, name):
        os.mkdir(os.path.join(self.base_folder, parent, name))

    def make_file(self, parent, name, content=None):
        with open(os.path.join(self.base_folder, parent, name), "wcb") as f:
            if content:
                f.write(content)

    def update(self, ref, content):
        with open(os.path.join(self.base_folder, ref), "wb") as f:
            f.write(content)

    def delete(self, ref):
        # TODO: support the OS trash?
        os_path = os.path.join(self.base_folder, ref)
        if os.path.isfile(os_path):
            os.unlink(os_path)
        elif os.path.isdir(os_path):
            shutil.rmtree(os_path)


class NuxeoClient(object):
    """Client for the Nuxeo Content Automation HTTP API"""

    def __init__(self, server_url, user_id, password,
                 base_folder=None, repo="default"):
        if not server_url.endswith('/'):
            server_url += '/'
        self.server_url = server_url
        self.user_id = user_id
        self.password = password
        self.base_folder = base_folder
        # TODO: actually use the repo info
        self.repo = repo

        self.auth = 'Basic %s' % base64.b64encode(
                self.user_id + ":" + self.password).strip()

        cookie_processor = urllib2.HTTPCookieProcessor()
        self.opener = urllib2.build_opener(cookie_processor)
        self.automation_url = server_url + 'site/automation/'

    def check_fetch_api(self):
        if not hasattr(self, 'operations'):
            self.fetch_api()

    def fetch_api(self):
        headers = {
            "Authorization": self.auth,
        }
        try:
            req = urllib2.Request(self.automation_url, headers=headers)
            response = json.loads(self.opener.open(req).read())
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id)
            else:
                raise e
        self.operations = {}
        for operation in response["operations"]:
            self.operations[operation['id']] = operation

    def authenticate(self):
        # Perform a cheap query to trigger authentication check
        try:
            self.fetch_api()
            return True
        except Unauthorized:
            return False

    def exists(self, ref):
        if ref.startswith('/'):
            results = self.query(
                "SELECT * FROM Document WHERE ecm:path = '%s' LIMIT 1" % ref)
        else:
            results = self.query(
                "SELECT * FROM Document WHERE ecm:uuid = '%s' LIMIT 1" % ref)
        return len(results[u'entries']) == 1

    #
    # Client API common with the FS API
    #

    def get_descendants(self, path=""):
        raise NotImplementedError()

    def get_state(self, path):
        raise NotImplementedError()

    def get_content(self, ref):
        return self.get_blob(ref)

    def make_folder(self, parent, name):
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

    #
    # Utilities
    #

    def get_full_path(self, path):
        if path != "":
            return self.base_folder + "/" + path
        else:
            return self.base_folder

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
        # RFC2231 (encoding extension in HTTP headers).
        quoted_filename = urllib.quote(filename.encode('utf-8'))
        blob_part.add_header("Content-Disposition",
                             "attachment;filename*=UTF-8''" + quoted_filename)

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
        req = urllib2.Request(self.automation_url + "Blob.Attach",
                              data, headers)
        try:
            resp = self.opener.open(req)
        except Exception, e:
            self._handle_error(e)
            raise e
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
        self.check_fetch_api()
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
