import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REMOTE = REPO / "nxdrive/client/remote_client.py"
ALF = REPO / "nxdrive/client/alfresco_remote.py"


def class_def(path: Path, name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise RuntimeError(f"class not found: {name}")


def public_members(cls: ast.ClassDef) -> dict[str, tuple[tuple[str, ...], str, str]]:
    out: dict[str, tuple[tuple[str, ...], str, str]] = {}
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            decorators = tuple(ast.unparse(d) for d in node.decorator_list)
            args = ast.unparse(node.args)
            ret = ast.unparse(node.returns) if node.returns else ""
            out[node.name] = (decorators, args, ret)
    return out


def init_sig(cls: ast.ClassDef) -> tuple[str, str]:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            return ast.unparse(node.args), ast.unparse(node.returns)
    raise RuntimeError("__init__ not found")


remote_cls = class_def(REMOTE, "Remote")
alf_cls = class_def(ALF, "AlfrescoRemote")

remote = public_members(remote_cls)
alf = public_members(alf_cls)

print("missing:", sorted(set(remote) - set(alf)))
print("extra:", sorted(set(alf) - set(remote)))

common = sorted(set(remote) & set(alf))
mismatches = [name for name in common if remote[name] != alf[name]]
print("mismatch_count:", len(mismatches))
if mismatches:
    first = mismatches[0]
    print("first:", first)
    print("remote:", remote[first])
    print("alf:", alf[first])

remote_init = init_sig(remote_cls)
alf_init = init_sig(alf_cls)
print("init_equal:", remote_init == alf_init)
if remote_init != alf_init:
    print("remote_init:", remote_init)
    print("alf_init:", alf_init)
