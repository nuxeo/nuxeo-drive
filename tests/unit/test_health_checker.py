import logging
import threading
import time

from nxdrive.commandline import HealthCheck


def test_no_crash(tmp_path):
    file = tmp_path / "crash.state"
    assert not file.is_file()

    with HealthCheck(folder=tmp_path):
        pass
    assert not file.is_file()


def test_crash(caplog, tmp_path):
    def thread(folder):
        with HealthCheck(folder=folder):
            while True:
                time.sleep(0.1)

    file = tmp_path / "crash.state"
    assert not file.is_file()

    # Mimic a crash, it must escape HealthCheck.__exit__() brutally
    th = threading.Thread(target=thread, args=(tmp_path,))
    th.start()
    time.sleep(1)

    assert file.is_file()
    th.join(timeout=1)
    assert file.is_file()
    file.write_text("Some\n\ntraceback\ninside")

    # Mimic app restart and check logs
    with caplog.at_level(logging.WARNING):
        caplog.clear()
        with HealthCheck(folder=tmp_path):
            pass
    assert not file.is_file()
    lines = [record.getMessage() for record in caplog.records]
    assert lines[0].startswith("It seems the application crashed")
    assert lines[1] == "Crash trace:\nSome\n\ntraceback\ninside"


def test_crash_invalid_data_in_traces(caplog, tmp_path):
    file = tmp_path / "crash.state"

    # Try to generate a badly encoded file
    file.write_text("Some\n\ninsane\n𝔘𝔫𝔦𝔠𝔬𝔡𝔢\ntraceback", encoding="utf-16")

    with caplog.at_level(logging.WARNING):
        caplog.clear()
        with HealthCheck(folder=tmp_path):
            pass
    assert not file.is_file()

    lines = [record.getMessage() for record in caplog.records]
    assert lines[0].startswith("It seems the application crashed")
    assert lines[1].startswith("Crash trace:")
    assert "\x00a" in lines[1]
