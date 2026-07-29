"""
1. Connect Drive in 2 PC's with same account (Drive-01, Drive-02)
2. Drive-01: Create a Folder "Folder01" and upload 20 files into it
3. Drive-02: Wait for folder and files to sync in 2nd PC (Drive-02)
4. Drive-01: Create a folder "878" in folder "Folder01" and move all the files
    into folder "878"
5. Drive-02: Wait for files to sync in Drive-02

Expected result: In Drive-02, all files should move into folder "878"

Stack:

sqlite Updating remote state for row=<DocPair> with info=...
sqlite Increasing version to 1 for pair <DocPair>
remote_watcher Unexpected error
Traceback (most recent call last):
  File "remote_watcher.py", line 487, in _handle_changes
    self._update_remote_states()
  File "remote_watcher.py", line 699, in _update_remote_states
    force_update=lock_update)
  File "sqlite.py", line 1401, in update_remote_state
    row.remote_state, row.pair_state, row.id))
  File "sqlite.py", line 65, in execute
    obj = super().execute(*args, **kwargs)
IntegrityError: UNIQUE constraint failed:
                States.remote_ref, States.remote_parent_ref

---

Understanding:

When the client 1 created the 878 folder and then moved all files into it, the
client 2 received unordered events.  Still on the client 2, 878 was created if
needed by one of its children: 1st error of duplicate type when the folder
creation event was handled later.

Another error was the remote creation twice of a given document because of the
previous error. We found then in the database 2 rows with the same remote_ref
but different remote_parent_ref (as one was under "/Folder01" and the other
into "/Folder01/878". Later when doing the move, it failed with the previous
traceback.

With the fix, we now have a clean database without any errors and all events
are well taken into account.
"""

from itertools import product

from .common import TwoUsersTest


class Test(TwoUsersTest):
    def test_nxdrive_1033(self):
        local1, local2 = self.local_1, self.local_2
        self.engine_1.start()
        self.engine_2.start()
        self.wait_sync(wait_for_async=True)

        # Create documents
        files = [f"test_file_{i + 1}.odt" for i in range(20)]
        srcname = "Folder 01"
        folder = local1.make_folder("/", srcname)
        srcname = f"/{srcname}"
        for filename in files:
            local1.make_file(srcname, filename, content=filename.encode("utf-8"))

        # Checks
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)
        for local, filename in product((local1, local2), files):
            assert local.exists(f"{srcname}/{filename}")

        # Step 4
        dstname = "8 78"
        dst = local1.make_folder(srcname, dstname)
        dstname = f"/{dstname}"
        for child in local1.get_children_info(folder):
            if not child.folderish:
                local1.move(child.path, dst)

        # Checks
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True, timeout=180)

        for local in {local1, local2}:
            assert len(local.get_children_info("/")) == 1
            assert len(local.get_children_info(srcname)) == 1
            assert len(local.get_children_info(srcname + dstname)) == len(files)

        for dao in {self.engine_1.dao, self.engine_2.dao}:
            assert not dao.get_errors(limit=0)
            assert not dao.get_filters()
            assert not dao.get_unsynchronizeds()

        for dao in {self.engine_1.dao, self.engine_2.dao}:
            assert not dao.get_errors(limit=0)
            assert not dao.get_filters()
            assert not dao.get_unsynchronizeds()

        for remote in (self.remote_document_client_1, self.remote_document_client_2):
            # '/'
            children = remote.get_children_info(self.workspace)
            assert len(children) == 1

            # srcname
            children = remote.get_children_info(children[0].uid)
            assert len(children) == 1

            # srcname + dstname
            children = remote.get_children_info(children[0].uid)
            assert len(children) == len(files)
