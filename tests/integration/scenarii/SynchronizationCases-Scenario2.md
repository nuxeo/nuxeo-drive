# Drive not uploading renamed file from shared folder

Related issue: https://jira.nuxeo.com/browse/NXDRIVE-646

## Scenario to reproduce

* Server side: user 1 create the structure and give Read permissions to user2
> Folder01
>> File01.txt
>> SubFolder01 - “Aerial09.jpg”
>> SubFolder02 - “Cosmos05.jpg”

<img src="/docs/Pictures/Scenario2-Pic1.png" width="300"/>

* Connect user2 on drive client and synchronize “Folder01” folder

<img src="/docs/Pictures/Scenario2-Pic2.png" width="300"/>

* Quit Drive

* Server side: user1 change permissions from “Read” to “Write” permissions for user2

* Client side, User2 goes to the drive synchronized local folder. Rename “File01.txt” to “File01_renamed.txt” and delete the file “Aerial09.jpg” in Subfolder01

<img src="/docs/Pictures/Scenario2-Pic3.png" width="300"/>

* Then user2 restarts Drive

## Current Results

* File01_renamed.txt is sync with the server with the renamed label

* Aerial09.jpg remains server side but doesn't reappear client side

<img src="/docs/Pictures/Scenario2-Pic4.png" width="300"/>


## Expected Results

Aerial09.jpg should be deleted server-side
