import os
import sys

import xattr

if __name__ == "__main__":
    if len(sys.argv) > 1:
        folder = sys.argv[1]
        if not os.path.isdir(folder):
            print("The argument must be an existing folder")
            sys.exit(0)
    else:
        folder = "."
    txt = xattr.getxattr(os.path.join(folder, "Icon\r"), xattr.XATTR_RESOURCEFORK_NAME)
    with open("Icon.dat", "wb") as out:
        out.write(txt)
