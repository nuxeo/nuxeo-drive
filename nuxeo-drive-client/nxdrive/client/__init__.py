from nxdrive.client.common import NotFound
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.client.remote_document_client import NuxeoDocumentInfo
from nxdrive.client.local_client import DEDUPED_BASENAME_PATTERN
from nxdrive.client.local_client import safe_filename
from nxdrive.client.local_client import LocalClient
from nxdrive.client.remote_document_client import RemoteDocumentClient

# TODO: backward compatibility with old remote client name, to be removed
NuxeoClient = RemoteDocumentClient
