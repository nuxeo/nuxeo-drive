# coding: utf-8
from typing import Any, Dict, List, Optional

from requests.exceptions import RetryError


class NuxeoError(Exception):
    """Mother class for all exceptions."""


class BadQuery(NuxeoError):
    """
    Exception thrown either by an operation failure:
        - when the command is not valid
        - on unexpected parameter
        - on missing required parameter
        - when a parameter has not the required type
    Or by any requests to the server with invalid data.
    """


class CorruptedFile(NuxeoError):
    """Exception thrown when digests of a downloaded blob are different."""

    def __init__(self, filename, server_digest, local_digest):
        # type: (str, str, str) -> None
        self.filename = filename
        self.server_digest = server_digest
        self.local_digest = local_digest

    def __repr__(self):
        # type: () -> str
        return (
            f"CorruptedFile {self.filename!r}: server digest is {self.server_digest!r},"
            f" local digest is {self.local_digest!r}"
        )

    def __str__(self):
        # type: () -> str
        return repr(self)


class HTTPError(RetryError, NuxeoError):
    """Exception thrown when the server returns an error."""

    _valid_properties = {"status": -1, "message": None, "stacktrace": None}

    def __init__(self, **kwargs):
        # type: (Any) -> None
        for key, default in HTTPError._valid_properties.items():
            if key == "status":
                # Use the subclass value, if defined
                value = getattr(self, key, kwargs.get(key, default))
            else:
                value = kwargs.get(key, default)

            setattr(self, key, value)

    def __repr__(self):
        # type: () -> str
        return "%s(%d), error: %r, server trace: %r" % (
            type(self).__name__,
            self.status,
            self.message,
            self.stacktrace,
        )

    def __str__(self):
        # type: () -> str
        return repr(self)

    @classmethod
    def parse(cls, json):
        # type: (Dict[str, Any]) -> HTTPError
        """Parse a JSON object into a model instance."""
        model = cls()

        for key, val in json.items():
            if key in cls._valid_properties:
                setattr(model, key, val)
        return model


class Conflict(HTTPError):
    """Exception thrown when the HTTPError code is 409."""

    status = 409


class Forbidden(HTTPError):
    """Exception thrown when the HTTPError code is 403."""

    status = 403


class InvalidBatch(NuxeoError):
    """Exception thrown when accessing inexistant or deleted batches."""


class InvalidUploadHandler(NuxeoError):
    """Exception thrown when trying to upload a blob using an invalid handler."""

    def __init__(self, handler, handlers):
        # type: (str, List[str]) -> None
        self.handler = handler
        self.handlers = tuple(handlers)

    def __repr__(self):
        # type: () -> str
        return f"{type(self).__name__}: the upload handler {self.handler!r} is not one of {self.handlers}."

    def __str__(self):
        # type: () -> str
        return repr(self)


class OAuth2Error(HTTPError):
    """Exception thrown when an OAuth2 error happens."""

    status = 400

    def __init__(self, error):
        # type: (str) -> None
        self.message = error
        self.stacktrace = None


class OngoingRequestError(Conflict):
    """Exception thrown when doing an idempotent call that is already being processed."""

    def __init__(self, request_uid):
        # type: (str) -> None
        self.request_uid = request_uid

    def __repr__(self):
        # type: () -> str
        return (
            f"{type(self).__name__}: a request with the idempotency key"
            f" {self.request_uid!r} is already being processed."
        )

    def __str__(self):
        # type: () -> str
        return repr(self)


class Unauthorized(HTTPError):
    """Exception thrown when the HTTPError code is 401."""

    status = 401


class UnavailableConvertor(NuxeoError):
    """
    Exception thrown when a converter is registered but not
    available right now (e.g. not installed on the server).

    :param options: options passed to the conversion request
    """

    def __init__(self, options):
        # type: (Dict[str, Any]) -> None
        self.options = options
        self.message = str(self)

    def __repr__(self):
        # type: () -> str
        return f"UnavailableConvertor: conversion with options {self.options!r} is not available"

    def __str__(self):
        # type: () -> str
        return repr(self)


class NotRegisteredConvertor(NuxeoError):
    """
    Exception thrown when a converter is not registered.

    :param options: options passed to the conversion request
    """

    def __init__(self, options):
        # type: (Dict[str, Any]) -> None
        self.options = options
        self.message = str(self)

    def __repr__(self):
        # type: () -> str
        return f"ConvertorNotRegistered: conversion with options {self.options!r} can not be done"

    def __str__(self):
        # type: () -> str
        return repr(self)


class UnavailableBogusConvertor(NuxeoError):
    """
    Exception thrown when a converter is registered but not
    available right now (e.g. not installed on the server)
    or when a converter is not registered
    and an Internal Server Error is thrown instead of actual error message.

    :param error_message: actual error message
    :param converter_name: name of the converter if available else empty string
    """

    def __init__(self, error_message, converter_name):
        # type: (str, str) -> None
        self.error_message = error_message
        self.converter_name = converter_name
        self.message = str(self)

    def __repr__(self):
        # type: () -> str
        msg = (
            "Internal Server Error or Converter "
            + self.converter_name
            + " is not registered or "
            + "UnavailableConvertor: conversion with options or Unsupported Operation"
        )
        return msg

    def __str__(self):
        # type: () -> str
        return repr(self)


class UploadError(NuxeoError):
    """
    Exception thrown when an upload fails even after retries.
    """

    def __init__(self, name, chunk=None, info=None):
        # type: (str, Optional[int], Optional[str]) -> None
        self.name = name
        self.chunk = chunk
        self.info = info

    def __repr__(self):
        # type: () -> str
        err = f"UploadError: unable to upload file {self.name!r}"
        if self.chunk:
            err += f" (failed at chunk {self.chunk})"
        if self.info:
            err += f" (source: {self.info})"
        return err

    def __str__(self):
        # type: () -> str
        return repr(self)
