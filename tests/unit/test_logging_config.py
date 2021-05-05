import logging

from nxdrive.constants import MAX_LOG_DISPLAYED
from nxdrive.logging_config import CustomMemoryHandler, configure


def test_custom_memory_handler():
    """Test the custom memory logger internal buffer."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    memory_handler = CustomMemoryHandler()
    memory_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(memory_handler)

    # Log a lot of lines, more than the capacity of the logger
    for n in range(MAX_LOG_DISPLAYED * 2):
        root_logger.debug(f"Line n° {n:,}")

        # Ensure the logger buffer never exceeds its maximum capacity
        assert len(memory_handler.buffer) <= MAX_LOG_DISPLAYED

    # Can't get logs with negative size
    buffer = memory_handler.get_buffer(-42)
    assert len(buffer) == 0

    # Can't get logs with zero size
    buffer = memory_handler.get_buffer(0)
    assert len(buffer) == 0

    # Get logs for at least MAX_LOG_DISPLAYED size
    buffer = memory_handler.get_buffer(MAX_LOG_DISPLAYED)
    assert len(buffer) == MAX_LOG_DISPLAYED
    assert buffer[0].message == "Line n° 50,000"
    assert buffer[-1].message == "Line n° 99,999"

    # Get logs for more than MAX_LOG_DISPLAYED size
    buffer = memory_handler.get_buffer(MAX_LOG_DISPLAYED + 42)
    assert len(buffer) == MAX_LOG_DISPLAYED
    assert buffer[0].message == "Line n° 50,000"
    assert buffer[-1].message == "Line n° 99,999"

    # Get logs for 42 last records
    buffer = memory_handler.get_buffer(42)
    assert len(buffer) == 42
    assert buffer[0].message == "Line n° 99,958"
    assert buffer[-1].message == "Line n° 99,999"


def test_force_configure(tmp_path):
    """Check that logging handlers are well freed when forcing configuration."""
    log_file1 = tmp_path / "log1.log"
    log_file2 = tmp_path / "log2.log"

    configure(log_filename=log_file1)  # For coverage ...
    configure(log_filename=log_file1, force_configure=True)
    logging.warning("a line")
    assert log_file1.is_file()
    assert not log_file2.is_file()

    log1_size = log_file1.stat().st_size
    configure(log_filename=log_file2, force_configure=True)
    logging.warning("another line")
    assert log_file1.stat().st_size == log1_size
    assert log_file2.is_file()
