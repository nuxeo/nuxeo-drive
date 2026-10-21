#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Regression tests: sync freezes during an SSO re-authentication.

The Alfresco SDK converts every ``requests`` transport failure into its own
``alfresco.exceptions.NetworkError``, which does *not* inherit from the
``requests`` classes listed in ``CONNECTION_ERROR``. A read timeout therefore
escaped the processor's connection handler and reached the catch-all, which
calls ``increase_error()`` and abandons the pair once ``Options.max_errors``
(3) is reached -- sync then looks frozen until a restart.

The same hole swallowed ``AuthenticationError``: the processor never called
``set_invalid_credentials()``, so an expired SSO token produced three silent
failures instead of a re-login prompt.
"""

from unittest.mock import Mock

import pytest
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import NetworkError as AlfrescoNetworkError
from alfresco.exceptions import OAuth2Error
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout

from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.drive.constants import CONNECTION_ERROR
from nxdrive.drive.exceptions import ThreadInterrupt

#: The exact failure reported from production, verbatim from the log.
READ_TIMEOUT = AlfrescoNetworkError(
    "PUT https://acs-11756.envalfresco.com/alfresco/api/-default-/public/"
    "alfresco/versions/1/nodes/009a1521-9688-42b3-9a15-21968842b3e5/content: "
    "HTTPSConnectionPool(host='acs-11756.envalfresco.com', port=443): "
    "Read timed out. (read timeout=60)"
)


@pytest.fixture
def engine():
    engine = Mock()
    engine.uid = "sso-uid"
    engine.dao = Mock()
    engine.local = Mock()
    engine.remote = Mock()
    engine.queue_manager = Mock()
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    return engine


@pytest.fixture
def pair():
    doc_pair = Mock()
    doc_pair.id = 7
    doc_pair.local_name = "report.docx"
    doc_pair.remote_ref = "009a1521-9688-42b3-9a15-21968842b3e5"
    doc_pair.pair_state = "locally_resolved"
    doc_pair.version = 1
    doc_pair.size = 0
    return doc_pair


def _run_one_pair(engine, doc_pair, error):
    """Drive a single iteration of the processor loop, raising *error*."""
    items = iter([doc_pair])

    def _next(*args, **kwargs):
        try:
            return next(items)
        except StopIteration:
            raise ThreadInterrupt() from None

    processor = AlfrescoProcessor(engine, _next)
    processor._get_next_doc_pair = Mock(return_value=doc_pair)
    processor.check_pair_state = Mock(return_value=True)
    processor.remove_void_transfers = Mock()
    processor.increase_error = Mock()
    processor.giveup_error = Mock()
    processor._postpone_pair = Mock()
    processor._interact = Mock()
    processor._handle_doc_pair_sync = Mock(side_effect=error)
    processor._synchronize_locally_resolved = Mock()

    with pytest.raises(ThreadInterrupt):
        processor._execute()

    return processor


class TestTheSdkWrapsTransportErrors:
    """Why the connection handler was being skipped."""

    def test_the_sdk_error_is_not_a_requests_error(self):
        assert not issubclass(AlfrescoNetworkError, CONNECTION_ERROR)

    def test_an_expired_token_is_not_a_requests_error_either(self):
        assert not issubclass(AlfrescoAuthError, CONNECTION_ERROR)

    def test_an_oauth_failure_is_an_authentication_failure(self):
        """Guards the inheritance the invalid-credentials branch relies on.

        ``_execute`` catches ``AuthenticationError`` only. That covers
        ``OAuth2Error`` solely because the SDK makes it a subclass. Should a
        future release reparent it, OAuth refreshes would quietly fall through
        to the catch-all and start consuming the pair's error budget again
        instead of prompting for a re-login -- fail here instead.
        """
        assert issubclass(OAuth2Error, AlfrescoAuthError)


class TestANetworkTimeoutIsRetriedForever:
    """A blip must never consume the pair's error budget."""

    def test_the_production_read_timeout_is_postponed(self, engine, pair):
        processor = _run_one_pair(engine, pair, READ_TIMEOUT)

        processor._postpone_pair.assert_called_once()
        assert processor._postpone_pair.call_args.args[1] == "CONNECTION_ERROR"

    def test_the_pair_is_never_given_up_on(self, engine, pair):
        processor = _run_one_pair(engine, pair, READ_TIMEOUT)

        processor.increase_error.assert_not_called()
        processor.giveup_error.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            ReadTimeout("read timed out"),
            RequestsConnectionError("connection aborted"),
        ],
    )
    def test_plain_requests_errors_still_work(self, engine, pair, error):
        """The pre-existing behaviour must not regress."""
        processor = _run_one_pair(engine, pair, error)

        processor._postpone_pair.assert_called_once()
        assert processor._postpone_pair.call_args.args[1] == "CONNECTION_ERROR"
        processor.increase_error.assert_not_called()


class TestAnExpiredSsoTokenAsksForALogin:
    """An auth failure must raise the re-login prompt, not burn retries."""

    @pytest.mark.parametrize(
        "error",
        [
            AlfrescoAuthError("[HTTP 401] Authentication failed"),
            OAuth2Error("token refresh rejected"),
        ],
    )
    def test_credentials_are_flagged_as_invalid(self, engine, pair, error):
        processor = _run_one_pair(engine, pair, error)

        engine.set_invalid_credentials.assert_called_once()
        assert engine.set_invalid_credentials.call_args.kwargs["reason"]
        # Not a "network blip" and not an "unknown" failure.
        processor.increase_error.assert_not_called()
        processor.giveup_error.assert_not_called()

    def test_the_pair_stays_retryable_for_after_the_re_login(self, engine, pair):
        error = AlfrescoAuthError("[HTTP 401] Authentication failed")

        processor = _run_one_pair(engine, pair, error)

        processor._postpone_pair.assert_called_once()
        assert processor._postpone_pair.call_args.args[1] == "INVALID_CREDENTIALS"

    def test_the_abandoned_transfer_is_cleaned_up(self, engine, pair):
        error = AlfrescoAuthError("[HTTP 401] Authentication failed")

        processor = _run_one_pair(engine, pair, error)

        processor.remove_void_transfers.assert_called_once_with(pair)


class TestGenuineFailuresAreStillErrors:
    """The widened handlers must not swallow real bugs."""

    def test_an_unexpected_error_still_counts(self, engine, pair):
        processor = _run_one_pair(engine, pair, ValueError("boom"))

        processor.increase_error.assert_called_once()
        assert processor.increase_error.call_args.args[1] == "UNKNOWN"
        engine.set_invalid_credentials.assert_not_called()
