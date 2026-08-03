"""Unit tests for nxdrive.drive.exceptions module."""

from pathlib import Path
from unittest.mock import Mock

from nxdrive.drive.exceptions import (
    DocumentAlreadyLocked,
    DriveError,
    EngineInitError,
    InvalidSSLCertificate,
    MissingClientSSLCertificate,
    MissingXattrSupport,
    RemoteConflict,
    RemoteHTTPError,
    RemoteOAuth2Error,
    RemoteOngoingRequestError,
    RemoteUnauthorized,
)


class TestDriveError:
    def test_is_exception(self):
        assert issubclass(DriveError, Exception)


class TestRemoteHTTPError:
    def test_stores_status_and_message(self):
        err = RemoteHTTPError(status=404, message="Not Found")
        assert err.status == 404
        assert err.message == "Not Found"

    def test_repr(self):
        err = RemoteHTTPError(status=500, message="Server Error")
        assert "500" in repr(err)
        assert "Server Error" in repr(err)

    def test_str_same_as_repr(self):
        err = RemoteHTTPError(status=403, message="Forbidden")
        assert str(err) == repr(err)


class TestRemoteUnauthorized:
    def test_status_is_401(self):
        err = RemoteUnauthorized(message="bad token")
        assert err.status == 401
        assert err.message == "bad token"


class TestRemoteOAuth2Error:
    def test_status_is_400(self):
        err = RemoteOAuth2Error(message="invalid_grant")
        assert err.status == 400


class TestRemoteOngoingRequestError:
    def test_stores_request_uid(self):
        err = RemoteOngoingRequestError(request_uid="req-123")
        assert err.request_uid == "req-123"


class TestRemoteConflict:
    def test_is_remote_error(self):
        from nxdrive.drive.exceptions import RemoteError

        assert issubclass(RemoteConflict, RemoteError)


class TestDocumentAlreadyLocked:
    def test_stores_username(self):
        err = DocumentAlreadyLocked("john")
        assert err.username == "john"

    def test_repr(self):
        err = DocumentAlreadyLocked("jane")
        assert "jane" in repr(err)
        assert str(err) == repr(err)


class TestEngineInitError:
    def test_stores_engine(self):
        engine = Mock()
        err = EngineInitError(engine)
        assert err.engine is engine

    def test_repr(self):
        engine = Mock()
        err = EngineInitError(engine)
        assert "Engine initialization error" in repr(err)


class TestInvalidSSLCertificate:
    def test_repr(self):
        err = InvalidSSLCertificate()
        assert "Invalid SSL certificate" in repr(err)
        assert "ca-bundle" in str(err)


class TestMissingClientSSLCertificate:
    def test_repr(self):
        err = MissingClientSSLCertificate()
        assert "cert-file" in str(err)


class TestMissingXattrSupport:
    def test_stores_path(self):
        err = MissingXattrSupport(Path("/mnt/fat32"))
        assert err.path == Path("/mnt/fat32")
