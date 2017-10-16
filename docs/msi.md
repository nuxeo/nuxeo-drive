# MSI Customization

On Windows you can customize Nuxeo Drive installation by passing custom arguments.

## Mandatory arguments

Note: You cannot use one of these arguments without the other, they are complementary.

- `TARGETURL`:  The URL of the Nuxeo server.
- `TARGETUSERNAME`: The username of the user who will be using Nuxeo Drive.

## Optionnal arguments

- `TARGETPASSWORD`: The password of the user who will be using Nuxeo Drive.
If you don't specify it then it will be asked to the user when Nuxeo Drive is started.
- `TARGETDRIVEFOLDER`: The path to the user synchronisation folder that will be created.
Path must include the Nuxeo Drive folder.

## Examples

Install quietly Nuxeo Drive in `C:\NDrive`:

    msiexec /i nuxeo-drive.msi /qn /quiet TARGETDIR="C:\NDrive"

Install Nuxeo Drive et configure the Nuxeo server to `http://localhost:8080/nuxeo` with the username `username`:

    msiexec /i nuxeo-drive.msi TARGETURL="http://localhost:8080/nuxeo" TARGETUSERNAME="username"

The same as above, but add the username password's:

    msiexec /i nuxeo-drive.msi TARGETURL="http://localhost:8080/nuxeo" TARGETUSERNAME="username" TARGETPASSWORD="password"

A full installation, useful for large automatic deployments:

    msiexec /i nuxeo-drive.msi /qn /quiet TARGETDIR="C:\NDrive" TARGETDRIVEFOLDER="%USERPROFILE%\Documents\Nuxeo Drive" TARGETURL="http://localhost:8080/nuxeo" TARGETUSERNAME="foo"

Even if `username` is wrong, it will permit de customize the Nuxeo server on all clients. The users will be asked to enter their username and password on the first connection.