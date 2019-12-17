import logging

from nxdrive.constants import MAX_LOG_DISPLAYED
from nxdrive.logging_config import CustomMemoryHandler


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
