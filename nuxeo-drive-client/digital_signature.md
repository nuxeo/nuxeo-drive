# How to sign Nuxeo Drive as a Mac OS X and Windows application

## OS X

We've resumed the main steps in this documentation. Please follow Apple's nice [Code Signing Guide](https://developer.apple.com/library/mac/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html#//apple_ref/doc/uid/TP40005929-CH4-SW2) for a complete explanation.

### Obtaining a signing identity

To sign code, you need a code signing identity, which is a private key plus a digital certificate. 

#### Trusted certificate, required for the released application

Such a certificate is needed to pass the system validation.

- Get a Developer ID certificate from Apple (99$ / year).

- Import the certificate to the build machine's keychain:

    1. In Keychain Access (available in `/Applications/Utilities`), choose File > Import Items.

    2. Choose a destination keychain for the identity.

    3. Choose the certificate file.

    4. Click Open.

#### Self-signed certificate, for tests only!

Such a certificate will not pass the system verification.

For test purpose you can use a self-signed certificate made by OS X's Certificate Assistant:

1. Open Applications > Utilities > Keychain Access.

2. From the Keychain Access menu, choose Certificate Assistant > Create a Certificate.

3. Follow the steps.

### Info.plist file

You need to include an `Info.plist` file in your application bundle, typically in `Nuxeo Drive.app/Contents`. It will be used by the system to determine the code's designated requirement.

It must at least have the `CFBundleIdentifier` and `CFBundleName` keys. In the case of Nuxeo Drive we use the following values:

    CFBundleIdentifier: org.nuxeo.drive
    CFBundleName: NuxeoDrive

### Signing the code

You should sign every executable in your product, including applications, tools, hidden helper tools, utilities and so forth.

Your final signing must be done **after you are done building your product, including any post-processing and assembly of bundle resources**.
Code signing detects any change to your program after signing, so if you make any changes at all after signing, your code will be rejected when an attempt is made to verify it.
Sign your code before you package the product for delivery, typically before creating the .dmg file.

Use the `codesign` command line tool to sign your application.

To sign the code located at `<code-path>`, using the signing identity `<identity>`, use the following command:

    codesign -s <identity> <code-path> -v

- The `<code-path>` value may be a bundle folder or a specific code binary.

- The identity can be named with any (case sensitive) substring of the certificate's common name attribute, as long as the substring is unique throughout your keychains.

- `-v` option is for verbose

In the case of Nuxeo Drive:
   
    codesign -s "Nuxeo Drive" nuxeo-drive/dist/Nuxeo\ Drive.app -v

This should output something like:

    nuxeo-drive/dist/Nuxeo Drive.app: signed bundle with Mach-O thin (x86_64) [org.nuxeo.drive]

### Verifying the code

To verify the signature on a signed binary or application bundle, use the `-v` option with no other options:

    codesign -v nuxeo-drive/dist/Nuxeo\ Drive.app

This checks that the code at `<code-path>` is actually signed, that the signature is valid, that all the sealed components are unaltered, and that the whole thing passes some basic consistency checks.

To get more details, add a `-v` option:

    codesign -vv nuxeo-drive/dist/Nuxeo\ Drive.app

This should output something like:

    nuxeo-drive/dist/Nuxeo Drive.app: valid on disk
    nuxeo-drive/dist/Nuxeo Drive.app: satisfies its Designated Requirement

### Getting information about code signatures

    codesign -d nuxeo-drive/dist/Nuxeo\ Drive.app

This should output something like:

    Executable=nuxeo-drive/dist/Nuxeo\ Drive.app/Contents/MacOS/Nuxeo Drive

To get more details, add more `-v` options:

    codesign -d -vvv nuxeo-drive/dist/Nuxeo\ Drive.app

This should output something like:

    Executable=nuxeo-drive/dist/Nuxeo\ Drive.app/Contents/MacOS/Nuxeo Drive
    Identifier=org.nuxeo.drive
    Format=bundle with Mach-O thin (x86_64)
    CodeDirectory v=20100 size=284 flags=0x0(none) hashes=8+3 location=embedded
    Hash type=sha1 size=20
    CDHash=0d5ca767f76730c66105d57aa5bb51629291e954
    Signature size=1506
    Authority=Nuxeo Drive
    Signed Time=24 janv. 2014 12:44:02
    Info.plist entries=23
    Sealed Resources rules=4 files=264
    Internal requirements count=1 size=92

### Test code signing using the spctl tool

    spctl --assess --type execute nuxeo-drive/dist/Nuxeo\ Drive.app

If your application or package signature is valid, this tools exits silently with an exit status of 0. (Type `echo $?` to display the exit status of the last command.)
If the signature is invalid, this tool prints an error message and exit with a nonzero exit status.

For more detailed information about why the assessment failed, you can add the `--verbose` flag:

    spctl --assess nuxeo-drive/dist/Nuxeo\ Drive.app --verbose

In case of success this should output something like:

    nuxeo-drive/dist/Nuxeo Drive.app: accepted
    source=No matching Rule

To see everything the system has to say about an assessment, pass the `--raw` option. With this flag, the spctl tool prints a detailed assessment as a property list.

    spctl --assess nuxeo-drive/dist/Nuxeo\ Drive.app --raw

Finally, `spctl` allows you to enable or disable the security assessment policy subsystem.
By default, assessment is turned off, which means that missing or invalid code signatures do not prevent an application from launching.
However, it is strongly recommended that you test your application with assessment enabled to ensure that your application works correctly.

To enable or disable assessment, issue one of the following commands.

    sudo spctl --master-enable   # enables assessment
    
    sudo spctl --master-disable  # disables assessment
    
    spctl --status               # shows whether assessment is enabl

## Windows

We've resumed the main steps in this documentation, mostly inspired from this excellent [stackoverflow post](http://stackoverflow.com/questions/84847/how-do-i-create-a-self-signed-certificate-for-code-signing-on-windows).
For for more theoretical explanations, see Microsoft's [Introduction to Code Signing](http://msdn.microsoft.com/en-us/library/ie/ms537361%28v=vs.85%29.aspx).

### Requirements

In order to sign your code, verify code signature and eventually create a self-signed certificate you need to install the latest version of the [.NET Framework](http://www.microsoft.com/fr-fr/download/details.aspx?id=30653)
and the [Windows SDK](http://msdn.microsoft.com/en-us/windowsserver/bb980924.aspx).

Add the `Bin` folder of the Windows SDK to the `PATH` environment variable (typically `C:\Program Files\Microsoft SDKs\Windows\v7.1\Bin`) to be able to execute its programs from the command line.

Note that you might have some trouble installing the Windows SDK if you have one or more versions of `Microsoft Visual C++` installed,
in which case you should uninstall them all before installing the Windows SDK.

### Obtaining a signing identity

#### Trusted certificate, required for the released application

You can get one from a certification authority.

#### Self-signed certificate, for tests only!

You can use the [MakeCert](http://msdn.microsoft.com/en-us/library/aa386968\(v=vs.85\).aspx) tool provided by the Windows SDK to create such a certificate.

- Create a self-signed Certificate Authority (CA)

        makecert -r -pe -ss CA -sr CurrentUser -n "CN=Nuxeo Drive CA, OU=Security,O=Nuxeo,E=ataillefer@nuxeo.com" -a sha256 -cy authority -sky signature -sv NuxeoDriveCA.pvk NuxeoDriveCA.cer

    You then need to create a Private Key Password and enter this password.  
    This will create the `NuxeoDriveCA.pvk` and `NuxeoDriveCA.cer` files and a "Nuxeo Drive CA" entry in the `Intermediate Certification Authorities`.

- Import the CA certificate into the Windows Root certificate store

        certutil -user -addstore Root NuxeoDriveCA.cer

    This will create a "Nuxeo Drive CA" entry in the `Trusted Root Certification Authorities`.

- Create a code-signing (SPC) certificate

        makecert -pe -n "CN=Nuxeo Drive SPC, OU=Security,O=Nuxeo,E=ataillefer@nuxeo.com" -a sha256 -cy end -sky signature -ic NuxeoDriveCA.cer -iv NuxeoDriveCA.pvk -sv NuxeoDriveSPC.pvk NuxeoDriveSPC.cer

    You then need to create a Private Key Password and enter this password.  
    This will create the `NuxeoDriveSPC.pvk` and `NuxeoDriveSPC.cer` files.

- Convert the certificate and key into a PFX file

        pvk2pfx -pvk NuxeoDriveSPC.pvk -spc NuxeoDriveSPC.cer -pfx NuxeoDriveSPC.pfx -po nuxeo

    `nuxeo` is the passphrase.  
    You then need to create a Private Key Password and enter this password.  
    This will create the `NuxeoDriveSPC.pfx` file.

- Import the code-signing certificate into the certificate store

    Run `certmgr.msc` and import `NuxeoDriveSPC.pfx` into the `Trusted Root Certification Authorites`. Check everything except "Enable strong  private key protection" and keep default options.  
    This will create a "Nuxeo Drive SPC" entry in the `Trusted Root Certification Authorites`.

### Signing the code

Use the [SignTool](http://msdn.microsoft.com/en-us/library/aa387764%28v=vs.85%29.aspx) tool provided by the Windows SDK to sign your application.

    signtool sign /v /s Root /n "Nuxeo Drive SPC" /d "Nuxeo Drive" /t http://timestamp.verisign.com/scripts/timstamp.dll dist\nuxeo-drive-1.3.0127-win32.msi

- `/v` verbose

- `/s Root` name of the certificate store

- `/n "Nuxeo Drive SPC"` subject name of the signing certificate

- `/d "Nuxeo Drive"` signed content description, used as the msi program name

- `/t http://timestamp.verisign.com/scripts/timstamp.dll` URL of the timestamp server

This should output something like:

    The following certificate was selected:
        Issued to: Nuxeo Drive SPC
        Issued by: Nuxeo Drive CA
        Expires:   Sun Jan 01 00:59:59 2040
        SHA1 hash: 786E8629AFEDA34379B6B1C7EB37D4A7AD3B268B

    Done Adding Additional Store
    Successfully signed and timestamped: dist\nuxeo-drive-1.3.0127-win32.msi

    Number of files successfully Signed: 1
    Number of warnings: 0
    Number of errors: 0

### Verifying the code

    signtool verify /v /pa dist\nuxeo-drive-1.3.0127-win32.msi

This should output something like:

    Verifying: dist\nuxeo-drive-1.3.0127-win32.msi
    Hash of file (sha1): 1F8C2CD99880DAE90F149294323D4F4B2AD8E859

    Signing Certificate Chain:
        Issued to: Nuxeo Drive CA
        Issued by: Nuxeo Drive CA
        Expires:   Sun Jan 01 00:59:59 2040
        SHA1 hash: 83C630745010A41AEF906D586EAE5164FDDB191C

            Issued to: Nuxeo Drive SPC
            Issued by: Nuxeo Drive CA
            Expires:   Sun Jan 01 00:59:59 2040
            SHA1 hash: 786E8629AFEDA34379B6B1C7EB37D4A7AD3B268B

    The signature is timestamped: Tue Jan 28 14:52:34 2014
    Timestamp Verified by:
        Issued to: Thawte Timestamping CA
        Issued by: Thawte Timestamping CA
        Expires:   Fri Jan 01 00:59:59 2021
        SHA1 hash: BE36A4562FB2EE05DBB3D32323ADF445084ED656

            Issued to: Symantec Time Stamping Services CA - G2
            Issued by: Thawte Timestamping CA
            Expires:   Thu Dec 31 00:59:59 2020
            SHA1 hash: 6C07453FFDDA08B83707C09B82FB3D15F35336B1

                Issued to: Symantec Time Stamping Services Signer - G4
                Issued by: Symantec Time Stamping Services CA - G2
                Expires:   Wed Dec 30 00:59:59 2020
                SHA1 hash: 65439929B67973EB192D6FF243E6767ADF0834E4

    Successfully verified: dist\nuxeo-drive-1.3.0127-win32.msi

    Number of files successfully Verified: 1
    Number of warnings: 0
    Number of errors: 0
