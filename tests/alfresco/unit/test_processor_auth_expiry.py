#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""QA report: the log floods with "Unhandled error" once the OAuth session ends.

Every processor shares the remote's auth object. Once the refresh token is
gone, every request fails at once with ``AuthenticationError``, which used to
reach the catch-all handler: the pair was retried forever and each processor
went on to fail on the next one, until the remote watcher's next poll flagged
the credentials and stopped the engine.
"""

from unittest.mock import Mock, call

import pytest
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import OAuth2Error

from nxdrive.alfresco.auth.refresh import RefreshingOAuth2Auth
from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.drive.exceptions import ThreadInterrupt


@pytest.fixture
def engine():
    engine = Mock()
    engine.uid = "qa-uid"
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    return engine


def _pair(row_id):
    doc_pair = Mock()
    doc_pair.id = row_id
    doc_pair.local_name = f"doc-{row_id}.docx"
    doc_pair.pair_state = "remotely_created"
    doc_pair.size = 0
    return doc_pair


def _run(engine, pairs, error):
    """Run the processor loop over *pairs*, each handler raising *error*."""
    items = iter(pairs)

    def _next(*_, **__):
        return next(items, None)

    processor = AlfrescoProcessor(engine, _next)
    processor._get_next_doc_pair = Mock(side_effect=lambda item: item)
    processor.check_pair_state = Mock(return_value=True)
    processor.increase_error = Mock()
    processor.giveup_error = Mock()
    processor._handle_doc_pair_sync = Mock(side_effect=error)
    processor._synchronize_remotely_created = Mock()
    processor.dao = engine.dao
    return processor


def test_the_qa_error_is_raised_as_an_authentication_error():
    """What the SDK raises once the refresh token is gone (the QA trace)."""
    auth = RefreshingOAuth2Auth.from_token(
        access_token="expired",
        refresh_token=None,
        expires_in=1,  # Inside the refresh skew: already treated as expired.
        token_url="https://idp.example.com/token",
        client_id="drive",
    )

    with pytest.raises(AlfrescoAuthError, match="grant_type"):
        auth._ensure_token()


@pytest.mark.parametrize(
    "error", [AlfrescoAuthError("expired"), OAuth2Error("refresh rejected")]
)
def test_expired_credentials_stop_the_processor(engine, error):
    pair = _pair(1)
    processor = _run(engine, [pair], error)

    with pytest.raises(ThreadInterrupt):
        processor._execute()

    engine.set_invalid_credentials.assert_called_once()
    assert "re-login" in engine.set_invalid_credentials.call_args.kwargs["reason"]
    # Kept for after the re-login, without recording any error.
    engine.queue_manager.push.assert_called_once_with(pair)
    processor.increase_error.assert_not_called()
    processor.giveup_error.assert_not_called()
    engine.queue_manager.push_error.assert_not_called()


def test_one_failure_per_processor_instead_of_a_flood(engine):
    pairs = [_pair(1), _pair(2), _pair(3)]
    processor = _run(engine, pairs, AlfrescoAuthError("expired"))

    with pytest.raises(ThreadInterrupt):
        processor._execute()

    processor._handle_doc_pair_sync.assert_called_once()
    engine.queue_manager.push.assert_called_once_with(pairs[0])


def test_credentials_are_flagged_before_the_pair_is_queued_again(engine):
    """So the engine stops before the re-queued pair can start a processor."""
    processor = _run(engine, [_pair(1)], AlfrescoAuthError("expired"))
    order = Mock()
    order.attach_mock(engine.set_invalid_credentials, "flag")
    order.attach_mock(engine.queue_manager.push, "push")

    with pytest.raises(ThreadInterrupt):
        processor._execute()

    assert [c[0] for c in order.mock_calls] == ["flag", "push"]


def test_the_pair_lock_is_still_released(engine):
    processor = _run(engine, [_pair(1)], AlfrescoAuthError("expired"))
    processor.thread_id = 1234

    with pytest.raises(ThreadInterrupt):
        processor._execute()

    assert engine.dao.release_state.call_args_list == [call(1234)]


def test_other_errors_still_take_the_retry_path(engine):
    processor = _run(engine, [_pair(1)], ValueError("something odd"))

    processor._execute()

    engine.set_invalid_credentials.assert_not_called()
    processor.increase_error.assert_called_once()
    assert processor.increase_error.call_args.args[1] == "UNKNOWN"
