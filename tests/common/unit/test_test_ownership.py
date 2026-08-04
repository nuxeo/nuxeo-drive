"""Guard test ownership boundaries between shared and backend suites."""

import ast
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("relative_root", "forbidden_prefixes"),
    [
        ("common", ("nxdrive.nuxeo", "nxdrive.alfresco")),
        ("nuxeo", ("nxdrive.alfresco",)),
        ("alfresco", ("nxdrive.nuxeo",)),
    ],
)
def test_backend_implementation_tests_live_in_their_own_tree(
    relative_root: str, forbidden_prefixes: tuple[str, ...]
) -> None:
    """Reject backend imports and patch targets from the wrong test tree."""
    violations: list[str] = []
    root = TESTS_ROOT / relative_root

    for test_file in sorted(root.rglob("test_*.py")):
        if test_file == Path(__file__):
            continue

        tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=test_file)
        for node in ast.walk(tree):
            references: list[str] = []
            if isinstance(node, ast.Import):
                references.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                references.append(node.module or "")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Patch targets are fully qualified strings. Restrict this to
                # strings beginning with a backend module so documentation
                # mentioning another backend remains valid.
                references.append(node.value.strip())

            for reference in references:
                if reference.startswith(forbidden_prefixes):
                    path = test_file.relative_to(TESTS_ROOT.parent)
                    violations.append(f"{path}:{node.lineno}: {reference!r}")

    assert not violations, "Backend test ownership violations:\n" + "\n".join(
        violations
    )
