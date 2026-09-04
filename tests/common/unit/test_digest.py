"""Unit tests for nxdrive.drive.digest module."""

from nxdrive.drive.digest import (
    get_digest_algorithm,
    get_digest_hash,
    guess_mimetype,
    version_compare,
    version_compare_client,
    version_le,
    version_lt,
)


class TestGetDigestAlgorithm:
    def test_md5(self):
        digest = "d41d8cd98f00b204e9800998ecf8427e"  # 32 chars
        assert get_digest_algorithm(digest) == "md5"

    def test_sha1(self):
        digest = "da39a3ee5e6b4b0d3255bfef95601890afd80709"  # 40 chars
        assert get_digest_algorithm(digest) == "sha1"

    def test_sha256(self):
        digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert get_digest_algorithm(digest) == "sha256"

    def test_unknown_length(self):
        assert get_digest_algorithm("abc") is None

    def test_non_hex_string(self):
        assert get_digest_algorithm("not-a-hex-string!!") is None

    def test_none_input(self):
        assert get_digest_algorithm(None) is None

    def test_empty_string(self):
        assert get_digest_algorithm("") is None


class TestGetDigestHash:
    def test_md5(self):
        h = get_digest_hash("md5")
        assert h is not None
        assert h.name == "md5"

    def test_sha256(self):
        h = get_digest_hash("sha256")
        assert h is not None
        assert h.name == "sha256"

    def test_unknown_algorithm(self):
        assert get_digest_hash("nonexistent_algo") is None


class TestVersionCompare:
    def test_equal(self):
        assert version_compare("1.0.0", "1.0.0") == 0

    def test_less_than(self):
        assert version_compare("1.0.0", "2.0.0") == -1

    def test_greater_than(self):
        assert version_compare("2.0.0", "1.0.0") == 1

    def test_minor_version(self):
        assert version_compare("1.1.0", "1.2.0") == -1

    def test_patch_version(self):
        assert version_compare("1.0.1", "1.0.2") == -1

    def test_snapshot_less_than_release(self):
        assert version_compare("1.0-SNAPSHOT", "1.0") == -1

    def test_hotfix(self):
        assert version_compare("1.0-HF01", "1.0-HF02") == -1

    def test_extra_parts(self):
        assert version_compare("1.0.0.1", "1.0.0") == 1

    def test_both_zero(self):
        assert version_compare("0", "0") == 0


class TestVersionCompareClient:
    def test_semver(self):
        assert version_compare_client("7.0.0", "8.0.0") == -1

    def test_with_suffix(self):
        assert version_compare_client("7.0.0-I123", "7.0.0-I124") == 0

    def test_none_x(self):
        assert version_compare_client(None, "1.0.0") == -1

    def test_none_y(self):
        assert version_compare_client("1.0.0", None) == 1


class TestVersionLt:
    def test_true(self):
        assert version_lt("1.0.0", "2.0.0") is True

    def test_false(self):
        assert version_lt("2.0.0", "1.0.0") is False

    def test_equal(self):
        assert version_lt("1.0.0", "1.0.0") is False


class TestVersionLe:
    def test_less(self):
        assert version_le("1.0.0", "2.0.0") is True

    def test_equal(self):
        assert version_le("1.0.0", "1.0.0") is True

    def test_greater(self):
        assert version_le("2.0.0", "1.0.0") is False


class TestGuessMimetype:
    def test_python_file(self):
        assert guess_mimetype("script.py") == "text/x-python"

    def test_pdf(self):
        assert guess_mimetype("document.pdf") == "application/pdf"

    def test_unknown_extension(self):
        assert guess_mimetype("file.xyz123unknown") == "application/octet-stream"

    def test_no_extension(self):
        assert guess_mimetype("README") == "application/octet-stream"

    def test_html(self):
        assert guess_mimetype("page.html") == "text/html"
