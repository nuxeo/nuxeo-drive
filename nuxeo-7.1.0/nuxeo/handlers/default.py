# coding: utf-8
"""
The default upload handler.
"""
from typing import TYPE_CHECKING, Any, Callable, Generator, Tuple, Union
from urllib.parse import quote

from ..models import Batch, Blob, BufferBlob, FileBlob
from ..utils import log_chunk_details

if TYPE_CHECKING:
    from ..uploads import API

ActualBlob = Union[BufferBlob, FileBlob]


class Uploader(object):
    """ Helper for uploads """

    __slots__ = (
        "batch",
        "blob",
        "callback",
        "chunk_count",
        "chunk_size",
        "token_callback",
        "headers",
        "path",
        "service",
        "_completed",
        "_timeout",
    )

    chunked = False

    def __init__(
        self, service, batch, blob, chunk_size, callback=None, token_callback=None
    ):
        # type: ("API", Batch, ActualBlob, int, Union[Callable, Tuple[Callable]], Callable) -> None
        self.service = service
        self.batch = batch
        self.blob = blob
        self.chunk_size = chunk_size
        self.headers = service.headers.copy()

        # Several callbacks are accepted
        if callback and isinstance(callback, (tuple, list, set)):
            self.callback = tuple(cb for cb in callback if callable(cb))
        else:
            self.callback = tuple([callback] if callable(callback) else [])

        # Callback triggered after having renewed token
        self.token_callback = token_callback

        self.blob.uploadType = "chunked" if self.chunked else "normal"
        self.chunk_count = 1
        self.path = f"{self.batch.batchId}/{self.batch.upload_idx}"
        self.headers.update(
            {
                "Cache-Control": "no-cache",
                "X-File-Name": quote(self.blob.name),
                "X-File-Size": str(self.blob.size),
                "X-File-Type": self.blob.mimetype,
                "Content-Length": str(self.blob.size),
                "Content-Type": self.blob.mimetype,
            }
        )

        self._timeout = None

    def __repr__(self):
        # type: () -> str
        return (
            f"<{type(self).__name__} is_complete={self.is_complete()!r},"
            f" chunked={self.chunked!r}, chunk_size={self.chunk_size!r},"
            f" batch={self.batch!r}, blob={self.blob!r}>"
        )

    def __str__(self):
        # type: () -> str
        return repr(self)

    def is_complete(self):
        # type: () -> bool
        """Return True when the upload is completely done."""
        return getattr(self, "_completed", False)

    def process(self, response):
        # type: (Blob) -> None
        self.blob.fileIdx = response.fileIdx
        self.blob.uploadedSize = int(response.uploadedSize)

    def timeout(self, chunk_size):
        # type: (int) -> float
        """Compute a timeout that allowes to handle big chunks."""
        if self._timeout is not None:
            # Used in tests
            return self._timeout

        return max(60.0, 60.0 * chunk_size / 1024 / 1024)
        #          |     |
        #          └-----|--- 1 minute is the minimum
        #                |
        #                └--- (chunk size reduced to 1 MiB) in minutes
        #                      ╚==> if chunk size is  5 MiB:  5 minutes
        #                      ╚==> if chunk size is 10 MiB: 10 minutes
        #                      ╚==> if chunk size is 20 MiB: 20 minutes

    def upload(self):
        # type: () -> None
        """ Upload the file. """
        with self.blob as src:
            data = src if self.blob.size else None
            timeout = self.timeout(self.chunk_size)

            self.process(
                self.service.send_data(
                    self.blob.name,
                    data,
                    self.path,
                    self.chunked,
                    0,
                    self.headers,
                    timeout=timeout,
                )
            )

            setattr(self, "_completed", True)

            for callback in self.callback:
                callback(self)
        self._update_batch()

    def _update_batch(self):
        # type: () -> None
        """ Add the uploaded blob info to the batch. """
        if self.is_complete():
            # All the parts have been uploaded, update the attributes
            self.blob.batchId = self.batch.uid
            self.batch.blobs[self.batch.upload_idx] = self.blob
            self.batch.upload_idx += 1


class ChunkUploader(Uploader):
    """ Helper for chunked uploads """

    __slots__ = ("_to_upload",)

    chunked = True

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)

        self.chunk_count, self.blob.uploadedChunkIds = self.service.state(
            self.path, self.blob, chunk_size=self.chunk_size
        )
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

        self.headers.update(
            {"X-Upload-Type": "chunked", "X-Upload-Chunk-Count": str(self.chunk_count)}
        )

        self._to_upload = []
        self._compute_chunks_left()

    def _compute_chunks_left(self):
        # type: () -> None
        """ Compare the set of uploaded chunks with the final list. """
        if self.is_complete():
            return

        to_upload = set(range(self.chunk_count)) - set(self.blob.uploadedChunkIds)
        self._to_upload = sorted(to_upload)

    def is_complete(self):
        # type: () -> bool
        """Return True when the upload is completely done."""
        return len(self.blob.uploadedChunkIds) == self.chunk_count

    def iter_upload(self):
        # type: () -> Generator
        """
        Get a generator to upload the file.

        If the `Uploader` has callback(s), they are run after each chunk upload.
        The method will yield after the callbacks step. It yields the uploader
        itself since it contains all relevant data.
        """
        with self.blob as src:
            timeout = self.timeout(self.chunk_size)

            while self._to_upload:
                # Get the index of a chunk to upload
                index = self._to_upload[0]

                # Seek to the right position
                src.seek(index * self.chunk_size)

                # Read a chunk of data
                data = src.read(self.chunk_size)
                data_len = len(data)

                # Upload it
                self.process(
                    self.service.send_data(
                        self.blob.name,
                        data,
                        self.path,
                        self.chunked,
                        index,
                        self.headers,
                        data_len=data_len,
                        timeout=timeout,
                    )
                )

                # Now that the part is uploaded, remove it from the list
                self._to_upload.pop(0)

                # keep track of the uploaded data size so far
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

        self._update_batch()

    def process(self, response):
        # type: (Blob) -> None
        self.blob.fileIdx = response.fileIdx
        self.blob.uploadedChunkIds = [int(i) for i in response.uploadedChunkIds]

    def upload(self):
        # type: () -> None
        """Helper to upload the file in one-shot."""
        list(self.iter_upload())
