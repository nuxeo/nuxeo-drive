# How to sign Nuxeo Drive as a Mac OS X and Windows application

## OS X

We've resumed the main steps in this documentation. Please follow Apple's nice [Code Signing Guide](https://developer.apple.com/library/mac/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html#//apple_ref/doc/uid/TP40005929-CH4-SW2) for a complete explanation.

### Obtaining a signing identity

To sign code, you need a code signing identity, which is a private key plus a digital certificate. 

#### For the build machine

- Get a Developer ID certificate from Apple (99$ / year).

- Import the certificate to the build machine's keychain:

    1. In Keychain Access (available in `/Applications/Utilities`), choose File > Import Items.

    2. Choose a destination keychain for the identity.

    3. Choose the certificate file.

    4. Click Open.

#### For tests (only!)

Use a self-signed certificate made by OS X's Certificate Assistant:

1. Open Applications > Utilities > Keychain Access.

2. From the Keychain Access menu, choose Certificate Assistant > Create a Certificate.

3. Follow the steps.

Such a certificate will not pass the system verification.

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

### Test code signing using the spctl Tool

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