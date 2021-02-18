from nxdrive.constants import TransferStatus
from nxdrive.manager import Manager
from nxdrive.objects import Session
from nxdrive.session_csv import SessionCsv


def test_csv_generation(tmp):
    session = Session(
        uid=2,
        remote_path="/default-domain/UserWorkspaces/Administrator/test_csv",
        remote_ref="08716a45-7154-4c2a-939c-bb70a7a2805e",
        status=TransferStatus.DONE,
        uploaded_items=10,
        total_items=10,
        engine="f513f5b371cc11eb85d008002733076e",
        created_on="2021-02-18 15:15:38",
        completed_on="2021-02-18 15:15:39",
        description="icons-svg (+9)",
        planned_items=10,
    )
    with Manager(tmp()) as manager:
        session_csv = SessionCsv(manager, session)

        assert session_csv.output_file.name == "session_2021-02-18_15-15-39.csv"
        assert session_csv.output_tmp.name == "session_2021-02-18_15-15-39.tmp"

        session_csv.create_tmp()
        assert session_csv.output_tmp.is_file()
        assert not session_csv.output_file.is_file()

        session_csv.store_data(
            [
                {
                    "path": "/default-domain/UserWorkspaces/Administrator/test_csv/toto.txt",
                    "properties": {"dc:title": "Toto file"},
                    "type": "File",
                }
            ]
        )
        assert not session_csv.output_tmp.is_file()
        assert session_csv.output_file.is_file()
