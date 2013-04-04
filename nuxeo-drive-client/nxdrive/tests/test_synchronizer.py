from nose.tools import assert_true
from nose.tools import assert_false
from nose.tools import assert_equals
from nxdrive.synchronizer import name_match
from nxdrive.synchronizer import jaccard_index


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


def test_jaccard_index():
    assert_equals(jaccard_index(set(), set()), 1.)
    assert_equals(jaccard_index(set(), ()), 1.)

    assert_equals(jaccard_index(set(['a']), set(['a'])), 1.)
    assert_equals(jaccard_index(set(['a']), ['a']), 1.)
    assert_equals(jaccard_index(set(['a']), ('a',)), 1.)

    assert_equals(jaccard_index(set(['a']), ['b']), 0.)
    assert_equals(jaccard_index(set(['a', 'b']), ['b']), .5)
    assert_equals(jaccard_index(set(['a', 'b']), ['a']), .5)
    assert_equals(jaccard_index(set(['a', 'b']), []), 0.)

    assert_equals(jaccard_index(set(['b']), ['a', 'b']), .5)
    assert_equals(jaccard_index(set(['a']), ['a', 'b']), .5)
    assert_equals(jaccard_index(set([]), ['a', 'b']), 0.)

    assert_equals(jaccard_index(set(['a', 'b', 'c']), ['b', 'd', 'e']), .2)
    assert_equals(jaccard_index(set(['a', 'b', 'c']), ['b', 'c', 'e']), .5)
