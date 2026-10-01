"""Regression tests for the QA report: sync icon never clears.

Nine repository nodes answered ``404 Unable to locate content`` on every
download attempt. The error reached the processor's catch-all handler, which
retries indefinitely because ``_postpone_pair()`` pins ``error_count`` to 1 and
``push_error()`` decides to give up from exactly that field. The affected pairs
therefore never left the syncing count and the tray icon span forever.
"""

from unittest.mock import Mock

import pytest
from alfresco.exceptions import NotFoundError as AlfrescoNotFoundError

from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.drive.exceptions import NotFound, ThreadInterrupt


@pytest.fixture
def engine():
    engine = Mock()
    engine.uid = "qa-uid"
    engine.dao = Mock()
    engine.local = Mock()
    engine.remote = Mock()
    engine.queue_manager = Mock()
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    return engine


@pytest.fixture
def pair():
    doc_pair = Mock()
    doc_pair.id = 42
    doc_pair.local_name = "broken.docx"
    doc_pair.remote_ref = "db31dce5-2469-4c68-8641-9becad64a756"
    doc_pair.pair_state = "remotely_created"
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
    processor._interact = Mock()
    processor._handle_doc_pair_sync = Mock(side_effect=error)
    processor._synchronize_remotely_created = Mock()

    with pytest.raises(ThreadInterrupt):
        processor._execute()

    return processor


def test_missing_remote_content_gives_up_instead_of_retrying(engine, pair):
    """The exact QA failure: 404 on the content endpoint."""
    error = AlfrescoNotFoundError(
        "[HTTP 404] 08280004 Unable to locate content for node ref "
        "workspace://SpacesStore/db31dce5-2469-4c68-8641-9becad64a756"
    )

    processor = _run_one_pair(engine, pair, error)

    processor.giveup_error.assert_called_once()
    assert processor.giveup_error.call_args.args[1] == "REMOTE_NOT_FOUND"
    # Must NOT take the retry-forever path.
    processor.increase_error.assert_not_called()


def test_missing_remote_content_clears_pending_transfers(engine, pair):
    error = AlfrescoNotFoundError("[HTTP 404] Unable to locate content")

    processor = _run_one_pair(engine, pair, error)

    processor.remove_void_transfers.assert_called_once_with(pair)


def test_drive_notfound_still_takes_the_silent_path(engine, pair):
    """The pre-existing nxdrive NotFound must keep its old behaviour."""
    processor = _run_one_pair(engine, pair, NotFound())

    processor.remove_void_transfers.assert_called_once_with(pair)
    processor.giveup_error.assert_not_called()
    processor.increase_error.assert_not_called()


def test_unrelated_error_still_uses_increase_error(engine, pair):
    """Genuinely transient failures must remain retryable."""
    processor = _run_one_pair(engine, pair, ValueError("something odd"))

    processor.increase_error.assert_called_once()
    assert processor.increase_error.call_args.args[1] == "UNKNOWN"
    processor.giveup_error.assert_not_called()


def test_giveup_error_crosses_the_queue_manager_threshold(engine, pair):
    """giveup_error must bypass the error_count=1 pin that causes the loop."""
    processor = AlfrescoProcessor(engine, Mock(return_value=None))

    processor.giveup_error(pair, "REMOTE_NOT_FOUND")

    # incr must exceed the threshold so push_error() actually gives up.
    kwargs = engine.dao.increase_error.call_args.kwargs
    assert kwargs["incr"] == 4
    engine.queue_manager.push_error.assert_called_once()
