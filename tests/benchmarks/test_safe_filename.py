"""
The current implementation used in Drive is str.replace().
If is not the most efficient for small ASCII-only filenames,
but it is the best when there are non-ASCII characters.
"""
import pytest

FILENAMES = [
    ("nom-valide.sh", "nom-valide.sh"),
    ("Ça, c'est un nom de fichié (2).odt", "Ça, c'est un nom de fichié (2).odt"),
    ("東京スカイツリー.jpg", "東京スカイツリー.jpg"),
    ("Наксео Драйв.exe", "Наксео Драйв.exe"),
    ('a/b\\c*d:e<f>g?h"i|j.doc', "a-b-c-d-e-f-g-h-i-j.doc"),
    ("F" * 250 + "?.pdf", "F" * 250 + "-.pdf"),
]


@pytest.mark.parametrize("fname, fname_expected", FILENAMES)
def test_re_sub(fname, fname_expected, benchmark):
    from re import compile, sub

    pattern = compile(r'([/:"|*<>?\\])')
    assert benchmark(lambda: sub(pattern, "-", fname)) == fname_expected


@pytest.mark.parametrize("fname, fname_expected", FILENAMES)
def test_str_translate(fname, fname_expected, benchmark):
    repmap = {ord(c): "-" for c in '/:"|*<>?\\'}
    assert benchmark(lambda: fname.translate(repmap)) == fname_expected


@pytest.mark.parametrize("fname, fname_expected", FILENAMES)
def test_str_replace(fname, fname_expected, benchmark):
    assert (
        benchmark(
            lambda: (
                fname.replace("/", "-")
                .replace(":", "-")
                .replace('"', "-")
                .replace("|", "-")
                .replace("*", "-")
                .replace("<", "-")
                .replace(">", "-")
                .replace("?", "-")
                .replace("\\", "-")
            )
        )
        == fname_expected
    )
