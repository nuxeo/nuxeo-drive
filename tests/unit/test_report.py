from logging import getLogger

from nxdrive.manager import Manager
from nxdrive.report import Report


def test_logs(tmp):
    log = getLogger(__name__)

    with Manager(tmp()) as manager:
        log.info("Strange encoding \xe8 \xe9")

        # Crafted problematic logRecord
        try:
            raise ValueError("[Mock] folder/\xeatre ou ne pas \xeatre.odt")
        except ValueError as e:
            log.exception("Oups!")
            log.exception(repr(e))
            log.exception(str(e))
            log.exception(e)

        # Test raw report (calling the Report class manually)
        report = Report(manager)
        report.generate()
        path = report.get_path()
        assert path.is_file()
        assert path.suffix == ".zip"

        # Test the report managed by the Manager
        path_managed = manager.generate_report()
        assert path_managed.is_file()
        assert path_managed.suffix == ".zip"
