# coding: utf-8
from _hashlib import HASH
import hashlib
import logging
import mimetypes
import sys
from packaging.version import Version
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from requests import Response

from . import constants
from .constants import UP_AMAZON_S3


logger = logging.getLogger(__name__)
WIN32_PATCHED_MIME_TYPES = {
    "image/pjpeg": "image/jpeg",
    "image/x-png": "image/png",
    "image/bmp": "image/x-ms-bmp",
    "audio/x-mpg": "audio/mpeg",
    "video/x-mpeg2a": "video/mpeg",
    "application/x-javascript": "application/javascript",
    "application/x-msexcel": "application/vnd.ms-excel",
    "application/x-mspowerpoint": "application/vnd.ms-powerpoint",
    "application/x-mspowerpoint.12": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def chunk_partition(file_size, desired_chunk_size, handler=""):
    # type: (int, int, Optional[str]) -> Tuple[int, int]
    """Determine the chunk count and chunk size from
    given *file_size* and *desired_chunk_size*.

    There may be boundaries depending of the given upload *handler*.

    :param file_size: the file size to upload (aka the blob)
    :param desired_chunk_size: the desired chunk size
    :param handler: the upload handler to use
    :return: a tuple of the chunk count and chunk size
    """

    chunk_size_min = 1
    chunk_count_max = None

    # Amazon S3 has some limitations
    if handler == UP_AMAZON_S3:
        chunk_size_min = 1024 * 1024 * 5  # 5 MiB
        chunk_count_max = 10000

    # Unsure to have the minimum valid chunk size
    chunk_size = max(chunk_size_min, desired_chunk_size)

    # Compute the number of chunks
    chunk_count = file_size // chunk_size + (file_size % chunk_size > 0)

    # If the chunks count exceeds the maximum chunks count ...
    if chunk_count_max and chunk_count > chunk_count_max:
        # ... In that case, the chunk count will define the chunk size
        return chunk_partition(
            file_size, file_size // (chunk_count_max - 1), handler=handler
        )

    return chunk_count, chunk_size


def cmp(a, b):
    if str(a) == "0":
        return 0 if str(b) == "0" else -1
    return 1 if str(b) == "0" else (a > b) - (a < b)


def get_digest_algorithm(digest):
    # type: (str) -> Optional[str]

    # Available algorithms
    digesters = {
        32: "md5",
        40: "sha1",
        56: "sha224",
        64: "sha256",
        96: "sha384",
        128: "sha512",
    }

    # Ensure the digest is hexadecimal
    try:
        int(digest, 16) >= 0
    except (TypeError, ValueError):
        return None

    return digesters.get(len(digest), None)


def get_digest_hash(algorithm):
    # type: (str) -> Optional[HASH]

    # Retrieve the hashlib function for the given digest, None if not found
    func = getattr(hashlib, algorithm, None)

    return func() if func else None


def get_digester(digest):
    # type: (str) -> Optional[HASH]
    """
    Get the digester corresponding to the given hash.

    To choose the digester used by the server, see
    https://doc.nuxeo.com/nxdoc/file-storage-configuration/#configuring-the-default-blobprovider

    :param digest: the hash
    :return: the digester function
    """

    algo = get_digest_algorithm(digest)
    func = get_digest_hash(algo) if algo else None

    if not func:
        logger.warning("No valid hash algorithm found for digest %r", digest)

    return func


def guess_mimetype(filename):
    # type: (str) -> str
    """Guess the mimetype of a given file."""
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        if sys.platform == "win32":
            # Patch bad Windows MIME types
            # See http://bugs.python.org/issue15207 and NXP-11660
            mime_type = WIN32_PATCHED_MIME_TYPES.get(mime_type, mime_type)
        return mime_type

    return "application/octet-stream"


def get_response_content(response, limit_size):
    # type: (Response, int) -> str
    """Log a server response."""
    # Do not use response.text as it will load the chardet module and its
    # heavy encoding detection mecanism. The server will only return UTF-8.
    # See https://stackoverflow.com/a/24656254/1117028 and NXPY-100.
    try:
        content = response.content.decode("utf-8", errors="replace")
        content_size = len(content)
        if content_size > limit_size:
            content = content[:limit_size]
            content = f"{content} [...] ({content_size - limit_size:,} bytes skipped)"
    except (MemoryError, OverflowError):
        # OverflowError: join() result is too long (in requests.models.content)
        # Still check for memory errors, this should never happen; or else,
        # it should be painless.
        headers = response.headers
        content_size = int(headers.get("content-length", 0))
        content = "<no enough memory ({content_size:,} bytes)>"

    return content


def json_helper(obj):
    # type: (Any) -> Dict[str, Any]
    return obj.to_json()


def log_chunk_details(chunk_count, chunk_size, uploaded_chunks, blob_size):
    # type: (int, int, List[int], int) -> None
    """Simple helper to log an chunked upload details about chunks data.

    :param chunk_count: the number of chunks
    :param chunk_size: the size of each chunks
    :param uploaded_chunks: the list of already uploaded chunks
    """
    if chunk_count <= 1 or logger.getEffectiveLevel() > logging.DEBUG:
        return

    uploaded_chunks_count = len(uploaded_chunks)
    uploaded_data_length = min(blob_size, chunk_size * uploaded_chunks_count)
    details = (
        f"Computed chunks count is {chunk_count:,}"
        f"; chunks size is {chunk_size:,} bytes"
        f"; uploaded chunks count is {uploaded_chunks_count:,}"
        f" => uploaded data so far is {uploaded_data_length:,} bytes."
    )
    logger.debug(details)


def log_response(response, *args, **kwargs):
    # type: (Response, Any, Any) -> Response
    """
    Log the server's response based on its content type.

    :param response: The server's response to handle
    :param limit_size: Maximum size to not overflow when printing raw content
    of the response
    """

    # No need to do more work if nobody will see it
    if logger.getEffectiveLevel() > logging.DEBUG:
        return response

    headers = response.headers
    content_type = headers.get("content-type", "application/octet-stream")
    content_size = int(headers.get("content-length", 0))
    chunked = headers.get("transfer-encoding", "") == "chunked"

    if response.status_code and response.status_code >= 400:
        # This is a request ending on an error
        content = get_response_content(response, constants.LOG_LIMIT_SIZE)
    if response.url.endswith("site/automation"):
        # This endpoint returns too many information and pollute logs.
        # Besides contents of this call are stored into the .operations attr.
        content = "<Automation details saved into the *operations* attr>"
    elif response.url.endswith("json/cmis"):
        # This endpoint returns too many information and pollute logs.
        # Besides contents of this call are stored into the .server_info attr.
        content = "<CMIS details saved into the *server_info* attr>"
    elif (
        not content_type.startswith("text")
        and "json" not in content_type
        and content_size
    ):
        # The Content-Type is a binary one, but it does not contain JSON data
        # Skipped binary types are everything but "text/xxx":
        #   https://www.iana.org/assignments/media-types/media-types.xhtml
        content = f"<binary data ({content_size:,} bytes)>"
    elif chunked or content_size > 0:
        # At this point, we should only have text data not bigger than *limit_size*.
        content = get_response_content(response, constants.LOG_LIMIT_SIZE)
    else:
        # response.content is empty when *void_op* is True,
        # meaning we do not want to get back what we sent
        # or the operation does not return anything by default
        content = "<no content>"

    logger.debug(
        f"Response from {response.url!r} [{response.status_code}]: {content!r}"
        f" with headers {headers!r}"
    )
    return response


@lru_cache(maxsize=128)
def version_compare(x, y):
    # type: (str, str) -> int
    # Handle None values
    if x == y == "0":
        return cmp(x, y)

    ret = (-1, 1)

    x_numbers = x.split(".")
    y_numbers = y.split(".")
    while x_numbers and y_numbers:
        x_part = x_numbers.pop(0)
        y_part = y_numbers.pop(0)

        # Handle hotfixes
        if "HF" in x_part:
            hf = x_part.replace("-HF", ".").split(".", 1)
            x_part = hf[0]
            x_numbers.append(hf[1])
        if "HF" in y_part:
            hf = y_part.replace("-HF", ".").split(".", 1)
            y_part = hf[0]
            y_numbers.append(hf[1])

        # Handle snapshots
        x_snapshot = "SNAPSHOT" in x_part
        y_snapshot = "SNAPSHOT" in y_part
        if not x_snapshot and y_snapshot:
            # y is snapshot, x is not
            x_number = int(x_part)
            y_number = int(y_part.replace("-SNAPSHOT", ""))
            return ret[y_number <= x_number]
        elif not y_snapshot and x_snapshot:
            # x is snapshot, y is not
            x_number = int(x_part.replace("-SNAPSHOT", ""))
            y_number = int(y_part)
            return ret[x_number > y_number]

        x_number = int(x_part.replace("-SNAPSHOT", ""))
        y_number = int(y_part.replace("-SNAPSHOT", ""))
        if x_number != y_number:
            return ret[x_number - y_number > 0]

    if x_numbers:
        return 1
    if y_numbers:
        return -1

    return 0


@lru_cache(maxsize=128)
def version_compare_client(x, y):
    # type: (str, str) -> int
    """Try to compare SemVer and fallback to version_compare on error."""

    # Ignore date based versions, they will be treated as normal versions
    if x is None:
        x = "0"
    if y is None:
        y = "0"

    if x and "-I" in x:
        x = x.split("-")[0]
    if y and "-I" in y:
        y = y.split("-")[0]

    try:
        return cmp(Version(x), Version(y))
    except Exception:
        return version_compare(x, y)


@lru_cache(maxsize=128)
def version_le(x, y):
    # type: (str, str) -> bool
    """x <= y"""
    return version_compare_client(x, y) <= 0


@lru_cache(maxsize=128)
def version_lt(x, y):
    # type: (str, str) -> bool
    """x < y"""
    return version_compare_client(x, y) < 0
