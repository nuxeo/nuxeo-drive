from nose.tools import assert_true
from nose.tools import assert_false
from nxdrive.synchronizer import name_match


def test_name_match():
    assert_true(name_match('File 1.txt', 'File 1.txt'))
    assert_true(name_match('File-1.txt', r'File\1.txt'))
    assert_true(name_match('File-1.txt', 'File*1.txt'))
    assert_true(name_match('File 1__1.txt', 'File 1.txt'))
    assert_true(name_match('File 1__2.txt', 'File 1.txt'))
    assert_true(name_match('File 1__103.txt', 'File 1.txt'))

    assert_false(name_match('File 2.txt', 'File 1.txt'))
    assert_false(name_match('File 2__103.txt', 'File 1.txt'))
    # We don't support deduplication for more than 999 conflicting
    # filenames in the same folder
    assert_false(name_match('File 1__1003.txt', 'File 1.txt'))
