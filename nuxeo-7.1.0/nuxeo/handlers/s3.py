# coding: utf-8
"""
The Amazon S3 upload handler.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Generator, List, Tuple

import boto3.session
from botocore.session import get_session
from botocore.client import BaseClient, Config
from botocore.credentials import DeferredRefreshableCredentials
from dateutil.tz import tzlocal

from .default import Uploader
from ..constants import UP_AMAZON_S3
from ..exceptions import UploadError
from ..utils import chunk_partition, log_chunk_details


logger = logging.getLogger(__name__)


class UploaderS3(Uploader):
    """Helper for uploads using Amazon S3 Direct Upload (single)."""

    __slots__ = ("bucket", "key", "s3_client", "_s3_config")

    def __init__(self, *args, **kwargs):
        # Allow to pass a custom S3 client (for tests)
        s3_client = kwargs.pop("s3_client", None)

        super().__init__(*args, **kwargs)

        # S3 client configuration
        s3_info = self.batch.extraInfo
        self.bucket = s3_info["bucket"]
        self.key = f"{s3_info['baseKey']}{self.batch.key or self.blob.name}"
        self._s3_config = Config(
            region_name=s3_info["region"],
            s3={
                "addressing_style": "path"
                if s3_info.get("usePathStyleAccess", False)
                else "auto",
                "use_accelerate_endpoint": s3_info.get("useS3Accelerate", False),
            },
        )
        self.s3_client = s3_client or self._create_s3_client(s3_info)

    def _create_s3_client(self, s3_info):
        # type: (Dict[str, Any]) -> BaseClient
        """Create the S3 client."""
        return boto3.Session().client(
            UP_AMAZON_S3,
            aws_access_key_id=s3_info["awsSecretKeyId"],
            aws_secret_access_key=s3_info["awsSecretAccessKey"],
            aws_session_token=s3_info["awsSessionToken"],
            endpoint_url=s3_info.get("endpoint") or None,
            config=self._s3_config,
        )

    def upload(self):
        # type: () -> None
        """Upload the file."""
        with self.blob as fd:
            try:
                # Note: we are using put_object() rather than upload_fileobj()
                # to be able to retrieve the ETag from the response. The latter
                # returns nothing and it would involve doing another HTTP call
                # just to get that information.
                response = self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=self.key,
                    Body=fd,
                    ContentType=self.headers["X-File-Type"],
                )
            except Exception as e:
                raise UploadError(self.blob.path, info=str(e))

            # Save the ETag for the batch.complete() call
            self.batch.etag = response["ETag"]

        self.blob.uploadedSize = self.blob.size
        setattr(self, "_completed", True)

        for callback in self.callback:
            callback(self)

        self._update_batch()


class ChunkUploaderS3(UploaderS3):
    """Helper for chunked uploads using Amazon S3 Direct Upload (multipart)."""

    __slots__ = ("_data_packs", "_max_parts", "_to_upload")

    chunked = True

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None

        # Allow to use a custom *MaxParts* value, used in .state() (for tests)
        # 0 <= MaxParts <= 2,147,483,647 (default is 1,000)
        self._max_parts = kwargs.pop("max_parts", 1000)

        super().__init__(*args, **kwargs)

        # Parts already sent
        self._data_packs = []

        self.chunk_count, self.blob.uploadedChunkIds = self.state()
        log_chunk_details(
            self.chunk_count,
            self.chunk_size,
            self.blob.uploadedChunkIds,
            self.blob.size,
        )

        self.blob.chunkCount = self.chunk_count
        self.blob.uploadedSize = min(
            self.blob.size, len(self.blob.uploadedChunkIds) * self.chunk_size
        )

        self._to_upload = []
        self._compute_chunks_left()

    def _create_s3_client(self, s3_info):
        # type: (Dict[str, Any]) -> BaseClient
        """Create the S3 client with automatic credentials renewal."""
        # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/resources.html#multithreading-and-multiprocessing
        # The session will be able to automatically refresh credentials
        creds = DeferredRefreshableCredentials(
            self._refresh_credentials,
            "sts-assume-role",
        )
        session = get_session()
        session._credentials = creds

        return boto3.Session(botocore_session=session).client(
            UP_AMAZON_S3,
            endpoint_url=s3_info.get("endpoint") or None,
            config=self._s3_config,
        )

    def _refresh_credentials(self):
        # type: () -> Dict[str, Any]
        """Method called automatically by boto3 to refresh tokens when needed."""
        data = self.service.refresh_token(
            self.batch, token_callback=self.token_callback
        )
        return {
            "access_key": data["awsSecretKeyId"],
            "secret_key": data["awsSecretAccessKey"],
            "token": data["awsSessionToken"],
            "expiry_time": datetime.fromtimestamp(
                data["expiration"] / 1000, tz=tzlocal()
            ).isoformat(),
        }

    def new(self):
        """
        Instantiate a new multipart upload.

        :return: the multipart upload ID
        """
        mpu = self.s3_client.create_multipart_upload(
            Bucket=self.bucket, Key=self.key, ContentType=self.headers["X-File-Type"]
        )
        self.batch.multiPartUploadId = mpu["UploadId"]
        return self.batch.multiPartUploadId

    def _state(self):
        # type: () -> List[int]
        """See .state()."""

        uploaded_chunks = []
        data_packs = []
        chunk_size = 0
        first = True

        # 0 <= PartNumberMarker <= 2,147,483,647
        part_number_marker = 0

        while "there are parts":
            info = self.s3_client.list_parts(
                Bucket=self.bucket,
                Key=self.key,
                UploadId=self.batch.multiPartUploadId,
                PartNumberMarker=part_number_marker,
                MaxParts=self._max_parts,
            )

            # Nothing was uploaded yet
            if "Parts" not in info:
                break

            for part in info["Parts"]:
                # Save the part size based on the first recieved part data
                if first:
                    chunk_size = part["Size"]
                    first = False

                index = part["PartNumber"]
                data_packs.append({"ETag": part["ETag"], "PartNumber": index})
                uploaded_chunks.append(index)

            # No more parts
            if not info["IsTruncated"]:
                break

            # TODO: part not yet tested/covered. Will be done with NXPY-147.
            # Next parts batch will start with that number
            part_number_marker = info["NextPartNumberMarker"]

        return chunk_size, uploaded_chunks, data_packs

    def state(self):
        # type: () -> Tuple[int, List]
        """
        Get the state of a multipart upload.

        If the blob upload has not begun yet, the server
        will return a 404 error, so we initialize the
        different values.
        If the blob upload is incomplete, we return the
        values the server sent us.

        :return: the chunk count and uploaded chunks
        """
        if self.batch.multiPartUploadId:

            self.chunk_size, uploaded_chunks, self._data_packs = self._state()
        else:
            # It's a new upload
            self.new()
            uploaded_chunks = []

        # *chunk_size* is overidden on purpose:
        # S3 has limitations and chunk size & count may be different from initial values
        chunk_count, self.chunk_size = chunk_partition(
            self.blob.size, self.chunk_size, handler=UP_AMAZON_S3
        )

        return chunk_count, uploaded_chunks

    def _compute_chunks_left(self):
        # type: () -> None
        """Compare the set of uploaded chunks with the final list."""
        if self.is_complete():
            return

        # S3 starts counting at 1
        to_upload = set(range(1, self.chunk_count + 1, 1)) - set(
            self.blob.uploadedChunkIds
        )
        self._to_upload = sorted(to_upload)

    def is_complete(self):
        # type: () -> bool
        """Return True when the upload is completely done."""
        return len(self.blob.uploadedChunkIds) == self.chunk_count

    def iter_upload(self):
        # type: () -> Generator
        """Upload a file in chunks.

        If the `Uploader` has callback(s), they are run after each chunk upload.
        The method will yield after the callbacks step. It yields the uploader
        itself since it contains all relevant data.
        """
        with self.blob as fd:
            while self._to_upload:
                # Get the index of a chunk to upload
                part_number = self._to_upload[0]

                # Seek to the right position (S3 starts counting at 1)
                position = (part_number - 1) * self.chunk_size
                fd.seek(position)

                # Read a chunk of data
                data = fd.read(self.chunk_size)
                data_len = len(data)

                try:
                    # Upload it
                    part = self.s3_client.upload_part(
                        UploadId=self.batch.multiPartUploadId,
                        Bucket=self.bucket,
                        Key=self.key,
                        PartNumber=part_number,
                        Body=data,
                        ContentLength=data_len,
                    )
                except Exception as e:
                    raise UploadError(self.blob.path, chunk=part_number, info=str(e))

                # Now that the part is uploaded, remove it from the list
                self._to_upload.pop(0)

                self._data_packs.append(
                    {"ETag": part["ETag"], "PartNumber": part_number}
                )
                self.blob.uploadedChunkIds.append(part_number)
                self.blob.uploadedSize += data_len

                # If the set of chunks to upload is empty, check whether
                # the server has received all of them.
                if not self._to_upload:
                    self._compute_chunks_left()

                # Call the callback(s), if any
                for callback in self.callback:
                    callback(self)

                # Yield to the upper scope
                yield self

        # Complete the upload on the S3 side
        response = self.s3_client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self.batch.multiPartUploadId,
            MultipartUpload={"Parts": self._data_packs},
        )

        # Save the ETag for the batch.complete() call
        self.batch.etag = response["ETag"]

        self._update_batch()

    def upload(self):
        # type: () -> None
        """Helper to upload the file in one-shot."""
        list(self.iter_upload())
