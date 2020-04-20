# Application Behavior Analysis

We are using [watchmedo](https://github.com/gorakhargosh/watchdog/#shell-utilities) to check and try to understand how a given software is managing files.
This is crucial to be able to find a pattern to identify documents to lock/unlock on the server when using Direct Edit.

The following is some guidelines (we are on Windows 10 with the username Alice and trying to analyse Photoshop):

1. First, install `watchmedo`.
2. Create the folder `C:\Users\Alice\tests`.
3. Open Photoshop and save a test file, let's say `test.psd`, inside that folder.
4. Go to that folder and execute this code in a console:
    ```batch
    C:\Users\Alice\tests> watchmedo log --recursive .
    ```
5. Then, open `test.psd` with Photoshop.
6. Observe the console output when doing different actions.

You can find valuable information in the different anaylsed behaviors in that folder.
