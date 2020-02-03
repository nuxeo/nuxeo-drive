#Drive not uploading files from shared folder

related issue: https://jira.nuxeo.com/browse/NXDRIVE-645

## Scenario to reproduce

* Create user1 and user2

* Server: user1 create a folder, add a file in it “NatGeo01.jpg” and give write permissions to user2

<img src="/docs/Pictures/Scenario1-Pic1.png" width="300"/>

* Connect user2 on drive client and synchronize “testshared” folder

<img src="/docs/Pictures/Scenario1-Pic2.png" width="300"/>

* Quit Drive

* User2 goes to the drive synchronized local folder. Create a new folder “Finished” and add a new file inside “Aerial04.jpg”

<img src="/docs/Pictures/Scenario1-Pic3.png" width="300"/>

* Server side: user1 renames folder “final” in “Finished”

* Then client side, User2 restarts Drive


## Current Results

* Folder “Finished” created by user2 is not uploaded server side, neither the “Aerial04.jpg”. No updates serverside

<img src="/docs/Pictures/Scenario1-Pic4.png" width="300"/>

* Locally:
“Finished” folder created by user2 remains the same
Previous local “final” folder is renamed “Finished__1”

<img src="/docs/Pictures/Scenario1-Pic5.png" width="300"/>

* Drive client has an error for the “Aerial04.jpg” document

<img src="/docs/Pictures/Scenario1-Pic6.png" width="300"/>

## Expected Results

Rename with __ ( the option exists now ) and put the folder in conflict with option to merge it.
(“Aerial04.jpg” is waiting for parent’s conflict resolution).
