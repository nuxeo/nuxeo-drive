import json
import os
import re
import sys
from typing import List

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def print_results(errors: List[str], warnings: List[str]) -> int:
    if len(warnings) < 0:
        print("=== translations check warnings ===")
        [print(elem) for elem in warnings]
    if len(errors) == 0:
        return EXIT_SUCCESS
    print("=== translations check errors ===")
    [print(elem) for elem in errors]
    return EXIT_FAILURE


def find_errors_in_tested_file(
    reference_translation_dict: dict,
    tested_translation_dict: dict,
    translation_file_path: str,
) -> List[str]:
    matcher = re.compile(r"%[1-9]")

    errors = []
    for key, sentence in reference_translation_dict.items():
        if key not in tested_translation_dict:
            continue
        reference_sentence_arguments = matcher.findall(sentence)
        tested_sentence_arguments = matcher.findall(tested_translation_dict[key])

        if sorted(reference_sentence_arguments) != sorted(tested_sentence_arguments):
            errors.append(f"{translation_file_path} {key!r}")
    return errors


def run_check(translations_folder: str) -> int:
    warnings = []
    errors = []

    with open(
        os.path.join(translations_folder, "i18n.json"), "r"
    ) as reference_translation_file:
        reference_translation_dict = json.load(reference_translation_file)
    translations_files_list = [
        os.path.join(translations_folder, translation_file)
        for translation_file in os.listdir(translations_folder)
        if os.path.isfile(os.path.join(translations_folder, translation_file))
        and translation_file.startswith("i18n-")
    ]

    for translation_file_path in translations_files_list:
        with open(translation_file_path, "r") as translation_file:
            tested_translation_dict = json.load(translation_file)

        warnings += [
            f"{translation_file_path} {key!r}"
            for key in set(tested_translation_dict).difference(
                set(reference_translation_dict)
            )
        ]

        errors += find_errors_in_tested_file(
            reference_translation_dict, tested_translation_dict, translation_file_path
        )

    return print_results(errors, warnings)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/translations/folder")
        sys.exit(EXIT_FAILURE)
    sys.exit(run_check(sys.argv[1]))
