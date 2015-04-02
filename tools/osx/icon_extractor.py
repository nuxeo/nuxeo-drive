import os
import base64
import xattr
import sys

if __name__ == "__main__":
	if len(sys.argv) > 1:
		folder = sys.argv[1]
		if not os.path.exists(folder) or not os.path.isdir(folder):
			print "The argument must be an existing folder"
			sys.exit(0)
	else:
		folder = "."
	str = xattr.getxattr(os.path.join(folder,'Icon\r'), xattr.XATTR_RESOURCEFORK_NAME)
	out = open('Icon.dat', 'wb')
	out.write(str)
