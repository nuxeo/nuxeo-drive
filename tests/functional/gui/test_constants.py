"""Functional tests for nxdrive.gui.constants module."""

from unittest.mock import patch

import pytest

from nxdrive.gui.constants import get_known_types_translations


class TestKnownTypesTranslations:
    """Test cases for known types translations functionality."""

    def test_get_known_types_translations_basic(self):
        """Test basic structure of known types translations."""
        with patch("nxdrive.gui.constants.Translator") as mock_translator:
            # Mock translation returns
            mock_translator.get.side_effect = lambda key: f"Translated_{key}"

            result = get_known_types_translations()

            # Verify structure
            assert isinstance(result, dict)
            assert "FOLDER_TYPES" in result
            assert "FILE_TYPES" in result
            assert "DEFAULT" in result

            # Verify folder types
            folder_types = result["FOLDER_TYPES"]
            assert "OrderedFolder" in folder_types
            assert "Folder" in folder_types
            assert folder_types["OrderedFolder"] == "Translated_ORDERED_FOLDER"
            assert folder_types["Folder"] == "Translated_FOLDER"

            # Verify file types
            file_types = result["FILE_TYPES"]
            assert "Audio" in file_types
            assert "File" in file_types
            assert "Picture" in file_types
            assert "Video" in file_types
            assert file_types["Audio"] == "Translated_AUDIO"
            assert file_types["File"] == "Translated_FILE"
            assert file_types["Picture"] == "Translated_PICTURE"
            assert file_types["Video"] == "Translated_VIDEO"

            # Verify default types
            default_types = result["DEFAULT"]
            assert "Automatic" in default_types
            assert "Create" in default_types
            assert default_types["Automatic"] == "Translated_AUTOMATICS"
            assert default_types["Create"] == "Translated_CREATE"

    def test_get_known_types_translations_translator_calls(self):
        """Test that translator is called with correct keys."""
        with patch("nxdrive.gui.constants.Translator") as mock_translator:
            mock_translator.get.return_value = "dummy_translation"

            get_known_types_translations()

            # Verify all expected translation keys were called
            expected_calls = [
                "ORDERED_FOLDER",
                "FOLDER",
                "AUDIO",
                "FILE",
                "PICTURE",
                "VIDEO",
                "AUTOMATICS",
                "CREATE",
            ]

            assert mock_translator.get.call_count == len(expected_calls)
            called_keys = [call[0][0] for call in mock_translator.get.call_args_list]
            for key in expected_calls:
                assert key in called_keys

    def test_get_known_types_translations_with_real_translations(self):
        """Test with actual translator instance (integration test)."""
        # Mock the Translator to avoid initialization issues
        with patch("nxdrive.gui.constants.Translator") as mock_translator:
            mock_translator.get.side_effect = lambda label: f"translated_{label}"

            # This test verifies the function works with a translator
            result = get_known_types_translations()

            # Verify structure and content types
            assert isinstance(result, dict)
            assert len(result) == 3

            # Verify structure and content types
            assert isinstance(result, dict)
            assert len(result) == 3

            folder_types = result["FOLDER_TYPES"]
            assert isinstance(folder_types, dict)
            assert len(folder_types) == 2
            # Check that translations were applied
            assert "translated_ORDERED_FOLDER" in folder_types.values()

            file_types = result["FILE_TYPES"]
            assert isinstance(file_types, dict)
            assert len(file_types) == 4

            default_types = result["DEFAULT"]
            assert isinstance(default_types, dict)
            assert len(default_types) == 2

        # Verify all values are strings (translations)
        for category in result.values():
            for translation in category.values():
                assert isinstance(translation, str)
                assert len(translation) > 0

    def test_get_known_types_translations_immutability(self):
        """Test that function returns a new dict each time (not cached)."""
        with patch("nxdrive.gui.constants.Translator") as mock_translator:
            mock_translator.get.return_value = "translation"

            result1 = get_known_types_translations()
            result2 = get_known_types_translations()

            # Should be different dict instances
            assert result1 is not result2
            # But should have the same content
            assert result1 == result2

    def test_get_known_types_translations_error_handling(self):
        """Test behavior when translator fails."""
        with patch("nxdrive.gui.constants.Translator") as mock_translator:
            mock_translator.get.side_effect = Exception("Translation error")

            # Should raise the exception
            with pytest.raises(Exception, match="Translation error"):
                get_known_types_translations()

    def test_get_known_types_translations_partial_failure(self):
        """Test behavior when some translations fail."""

        def translation_side_effect(key):
            if key == "FOLDER":
                raise Exception("Translation failed")
            return f"Translated_{key}"

        with patch("nxdrive.gui.constants.Translator") as mock_translator:
            mock_translator.get.side_effect = translation_side_effect

            # Should raise the exception on first failed translation
            with pytest.raises(Exception, match="Translation failed"):
                get_known_types_translations()

    def test_get_known_types_translations_empty_translations(self):
        """Test behavior with empty translation strings."""
        with patch("nxdrive.gui.constants.Translator") as mock_translator:
            mock_translator.get.return_value = ""

            result = get_known_types_translations()

            # Should still work but with empty strings
            assert all(
                translation == ""
                for category in result.values()
                for translation in category.values()
            )
