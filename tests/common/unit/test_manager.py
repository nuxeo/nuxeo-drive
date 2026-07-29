import os
import re
from unittest.mock import Mock
from uuid import uuid4


def test_send_sync_status(manager, engine):
    """This method is to test weather drive need to send sync status
    or not based on which directory user is currently watching.
    Is it drive local_folder e.g "/Users/test/Nuxeo Drive" or watching
    some other folder like Downloads, Applications etc.
    """
    tmp_path = os.path.expandvars("C:\\test\\%username%\\Downloads")
    manager.engines = {f"{uuid4()}": engine}
    manager.osi.send_content_sync_status = Mock()
    engine.dao.get_local_children = Mock()

    manager.send_sync_status(manager, tmp_path)

    # No need to send status as user is watching Downloads folder
    assert not re.search(f"{str(engine.local_folder)}/", f"{str(tmp_path)}/")
