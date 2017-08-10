# coding: utf-8
import hashlib
import sys

FILE_BUFFER_SIZE = 4096


def get_digest(file_path, digest_func='md5'):
    digester = getattr(hashlib, digest_func, None)
    if digester is None:
        raise ValueError('Unknow digest method: ' + digest_func)

    h = digester()
    with open(file_path, 'rb') as f:
        while True:
            buffer_ = f.read(FILE_BUFFER_SIZE)
            if buffer_ == '':
                break
            h.update(buffer_)
    return h.hexdigest()

if __name__ == "__main__":
    file_path = sys.argv[1]
    print 'Digest of %s = %s' % (file_path, get_digest(file_path))

