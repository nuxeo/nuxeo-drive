# Drive is not uploading the local renamed folder to server

Related issue: https://jira.nuxeo.com/browse/NXDRIVE-647

## Scenario to reproduce

* Server side: user1 create a “Folder1” with 2 pictures inside

* Client side: user1 synchronizes “Folder1”


<img src="/docs/Pictures/Scenario3-Pic1.png" width="300"/>

* Quit Drive

* Server side: rename “Folder1” by “Folder1-ServerName”

<img src="/docs/Pictures/Scenario3-Pic2.png" width="300"/>

* Client side: rename “Folder1” by “Folder1LocalRename”

<img src="/docs/Pictures/Scenario3-Pic3.png" width="300"/>

* Client side: restart Drive

## Current Results

* Server side: “Folder1LocalRename” is uploaded (and no more “Folder1-ServerName”)

<img src="/docs/Pictures/Scenario3-Pic4.png" width="300"/>

* Client side: “Folder1-ServerName” is downloaded (and no more “Folder1LocalRename”)

<img src="/docs/Pictures/Scenario3-Pic6.png" width="300"/>


## Expected Results

This looks like a conflict situation on the folder. Ideally, I would say that conflict is handled client side in the conflict management UI, letting the user the choice to either apply server name or keep client name and update server. Just by renaming, not deleting the folder and re-downloading.
