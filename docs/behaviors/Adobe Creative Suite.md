# Adobe Creative Suite: Photoshop

The following is a recipe based on a real world example on how we tried to understand how Photoshop is working with a opened files.
For this scenario, we are on Windows 10 with the username Alice.

1. First, install `watchmedo`.
2. Create the folder `C:\Users\Alice\tests`.
3. Open Photoshop and save a test file, let's say `test.psd`, inside that folder.
4. Go to that folder and execute this code in a console:
    ```batch
    C:\Users\Alice\tests> watchmedo log --recursive .
    ```
5. Then, open `test.psd` with Photoshop.
6. Observe the console output when doing different actions.

## Opening

When opening the file, nothing is logged. This is problematic as for now we have no way to know that `test.psd` is being edited in Photoshop.

## Saving

When saving changes, we can see (I removed useless data):

```batch
on_created(event=<FileCreatedEvent: src_path='.\\ps9985.tmp'>)
on_modified(event=<FileModifiedEvent: src_path='.\\ps9985.tmp'>)
on_modified(event=<FileModifiedEvent: src_path='.\\ps9985.tmp'>)
on_deleted(event=<FileDeletedEvent: src_path='.\\test.psd'>)
on_moved(event=<FileMovedEvent: src_path='.\\ps9985.tmp', dest_path='.\\test.psd'>)
on_modified(event=<FileModifiedEvent: src_path='.\\test.psd'>)
```

What we can understand is that Photoshop is:

1. Creating a temporary file `ps9985.tmp` with the updated content of `test.psd`.
2. Deleting `test.psd`.
3. Moving `ps9985.tmp` to `test.psd`.

### Opened Files

We have another way to detect opened files. We use this Python code (inspired from [autolocker.py](https://github.com/nuxeo/nuxeo-drive/blob/349d195f2337dd730f43a2d99bb0d2239dbeef87/nxdrive/autolocker.py#L115)):

```python
from contextlib import suppress
from typing import Iterator, Tuple
import psutil


def get_open_files() -> Iterator[Tuple[int, str]]:
    """
    Get all opened files on the OS.
    :return: Generator of (PID, file path).
    """
    for proc in psutil.process_iter():
        with suppress(psutil.Error, OSError):
            for handler in proc.open_files():
                with suppress(PermissionError):
                    yield proc.pid, handler.path.lower()


for pid, path in get_open_files():
    # XXX: This is here you can change what you are looking for
    if (
        "photoshop" in path
        and not "required" in path
        and not "web-cache-temp" in path
    ):
        print(pid, file)
```

Calling this script will output:

```batch
6872 C:\Program Files\Adobe\Adobe Photoshop CC 2018\TypeLibrary.tlb
6872 C:\Users\Alice\AppData\Roaming\Adobe\Adobe Photoshop CC 2018\logs\debug.log
6872 C:\Users\Alice\AppData\Local\Temp\Photoshop Temp1893966872
```

The interesting thing is `C:\Users\Alice\AppData\Local\Temp\Photoshop Temp1893966872`, which is a 163 Mo file!
For information, `test.psd` is only 456Ko ...

That file is protected and cannot be accessed outside Photoshop. Making a copy will result in an empty file.

Now, can we do try something else with that? Let's try!

#### Parsing the Debug File

In the opened files, there was a `debug.log`:

```batch
C:\Users\Alice\AppData\Roaming\Adobe\Adobe Photoshop CC 2018\logs\debug.log
```

But this file is empty.

#### Marking the File

We can use xattr (extended attributes) to mark the original file and see if we find the marker in the temporary file too.

We will use this Python code (inspired from [local_client.py](https://github.com/nuxeo/nuxeo-drive/blob/master/nxdrive/client/local_client.py#L331)):

```python
def set_xattr(path : str, marker: str, value: bytes) -> None:
    """
    Add a marker into extended attributes.
    """
    path_alt = f"{path}:{marker}"
    with open(path_alt, "wb") as f:
        f.write(value)

def read_xattr(path : str, marker: str) -> bytes:
    """
    Read a marker from extended attributes.
    """
    path_alt = f"{path}:{marker}"
    try:
        with open(path_alt, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return b""
```

Then we mark the original file:

```python
set_xattr(r"C:\Users\Alice\test\test.psd", "marker", b"found me!")
```

And change the `XXX` part of the previous script to include the check:

```python
for pid, path in get_open_files():
    # XXX: This is here you can change what you are looking for
    if (
        "photoshop" in path
        and not "web-cache-temp" in path
        and "temp" in path
    ):
        print(pid, path)
        print("xattr marker:", read_xattr(path, "marker"))
```

The output will be, sadly:

```batch
7620 c:\users\window~1\appdata\local\temp\photoshop temp2608567620
xattr marker: b''
```

The marker is empty, meaning this does not work.

## Ideas

### Idea 1

In the Photoshop settings, we can set a log file where actions are written.

The file content look like:

```log
2019-02-01 17:50:17    D�but de la session Photoshop
2019-02-01 17:50:21    Fichier test.psd ouvert
2019-02-01 17:50:51    Fichier test.psd ferm�
2019-02-01 17:50:51    Fin de la session Photoshop
```

But I only see many cons:

1) We are asking the user to do something.
2) If we do that, we need the user to save the file in a folder we define (into `$HOME/.nuxeo-drive/apps/` for example). For that, the user must show hidden files, which may be a painful task.
3) The log file is localised (and it seems there are encoding issues on Windows, which will harden the task).
4) If we decide to write a custom log parser for Photoshop, we will have to do that for others apps, which is a non desirable amount of work (not speaking about the log format changes in several apps versions).

### Idea 2

A naive approach would be to check that `get_open_files()` returns a path ending with `r"Photoshop Temp\d+"`.
But this implies a lot of trouble:

1) If another picture is already open in Photoshop when doing the Direct Edit on another document, we will have 2 temporary files. Which one is the good one?
2) If Photoshtop failed to open the Direct Edit'ing document, but there already is another file opened, we will ses a temporary file but it will not be the good one.
3) If there is several Direct Edit on multiple files, how to know which temporary file belongs to which document?

And most probably a lot of issues I cannot imagine right now.
So, this does not work either.

### Idea 3

We could use the Photoshop Scripting API. I uses COM objects on Windows and AppleScript on macOS.

I read that we can setup a `Notifer` that will call a function on specified a event.

This is a non working POC for Windows (requires the `pywin32` module):

```python
from win32com.client import Dispatch, GetActiveObject


app = GetActiveObject("Photoshop.Application")

# Ensure the Notifier is enabled
app.notifiersEnabled = True

# Call the function 'on_open_event()' when any document is opened.
# This is not work for documents opened via another script.
def on_open_event(*args, **kwargs):
    print(args, kwargs)

def on_close_event(*args, **kwargs):
    print(args, kwargs)

app.notifiers.add("Opn ", on_open_event)
app.notifiers.add("Cls ", on_close_event)

while True:
    pass
```

Reference manuals are [here](https://www.adobe.com/devnet/photoshop/scripting.html).

## Solution

The final idea was the good one: use the Photoshop Scripting API (COM objects on Windows and AppleScript on macOS).

After a long search in the sparse documentation and a lot of bad snippets found on Internet, this is the so *simple* working script:

```python
from win32com.client import GetActiveObject


app = GetActiveObject("Photoshop.Application")
for doc in app.Application.Documents:
    print(doc.FullName)
```

And for macOS, using AppleScript:

```python
from ScriptingBridge import SBApplication


app = SBApplication.applicationWithBundleIdentifier_("com.adobe.Photoshop")
for doc in app.documents():
    print(doc.filePath().path())
```

Both codes will output the list of opened files.
