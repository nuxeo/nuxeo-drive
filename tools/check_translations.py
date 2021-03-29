"""
This script allows the user to check the project translations files and print on the standard
output the differences between the reference translation file and the others files.

This tool accepts only json files as parameters.
"""

import json
import re
import sys
from pathlib import Path
from typing import List

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def print_results(errors: List[str], warnings: List[str]) -> int:
    """Print warnings and errors found during the check"""
    if warnings:
        print("=== List of obsolete translations found ===")
        for warning in warnings:
            print(warning)

    if not errors:
        return EXIT_SUCCESS

    print("=== List of translations errors found ===")
    for error in errors:
        print(error)

    return EXIT_FAILURE


def find_errors_in_tested_file(
    reference_translation: dict,
    translation: dict,
    file: Path,
) -> List[str]:
    """Iterate through the tested translation file keys and compare values with the reference file"""
    matcher = re.compile(r"%[1-9]")

    errors = []
    for key, sentence in reference_translation.items():
        if key not in translation:
            print(f"{file} {key!r} : Missing key declaration.")
            continue
        reference_sentence_arguments = matcher.findall(sentence)
        tested_sentence_arguments = matcher.findall(translation[key])

        if sorted(reference_sentence_arguments) != sorted(tested_sentence_arguments):
            errors.append(f"{file} {key!r} : Wrong number of arguments.")
    return errors


def run_check(translations_folder: str) -> int:
    """Iterate through the translations files folder"""

    # List of translation key that are considered obsolete (not in reference anymore)
    warnings = []

    # List of translation key where the value does not contain the same arguments (count and name) than the reference
    errors = []

    translations = Path(translations_folder)
    reference_file = translations / "i18n.json"
    reference_translation = json.loads(reference_file.read_text(encoding="utf-8"))

    for file in translations.glob("i18n-*.json"):
        translation = json.loads(file.read_text(encoding="utf-8"))
        warnings += [
            f"{file} {key!r} : Seems to be an obsolete key."
            for key in set(translation).difference(set(reference_translation))
        ]

        errors += find_errors_in_tested_file(
            reference_translation,
            translation,
            file,
        )

    return print_results(errors, warnings)


if __name__ == "__main__":
    """
    Check translations files for anomalies.
    Take the translations files folder path as an argument.
    """
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/translations/folder")
        sys.exit(EXIT_FAILURE)
    sys.exit(run_check(sys.argv[1]))
