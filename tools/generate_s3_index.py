"""
Generate index.html pages for the software-channel S3 bucket.

Produces:
  - <output>/index.html                 : root page with links to each folder
                                          and to `versions.yml`.
  - <output>/<folder>/index.html        : per-folder page listing files with
                                          name, last-modified date, and size.

Object listing is done via `aws s3api list-objects-v2` (no extra Python
dependencies beyond the standard library are required).
"""

import argparse
import html
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def _human_size(num_bytes):
    """Return a human-readable size string for `num_bytes`."""

    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"


def _list_folder(bucket, prefix):
    """List objects directly under `prefix` (single level, no sub-folders)."""

    if prefix and not prefix.endswith("/"):
        prefix += "/"

    cmd = [
        "aws",
        "s3api",
        "list-objects-v2",
        "--bucket",
        bucket,
        "--prefix",
        prefix,
        "--delimiter",
        "/",
        "--output",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        # A missing prefix is not an error: return an empty list.
        if "NoSuchKey" in stderr or "NoSuchBucket" in stderr:
            return []
        print(f">>> aws s3api list-objects-v2 failed: {stderr}", file=sys.stderr)
        return []

    payload = proc.stdout.strip()
    if not payload:
        return []

    data = json.loads(payload)
    contents = data.get("Contents") or []

    files = []
    for obj in contents:
        key = obj.get("Key", "")
        # Skip the folder placeholder and any nested index.html we uploaded.
        name = key[len(prefix) :]
        if not name or name.endswith("/") or name == "index.html":
            continue
        files.append(
            {
                "name": name,
                "size": obj.get("Size", 0),
                "last_modified": obj.get("LastModified", ""),
            }
        )

    files.sort(key=lambda f: f["name"].lower())
    return files


def _format_date(raw):
    """Format an ISO-8601 timestamp coming from the AWS CLI."""

    if not raw:
        return ""
    try:
        # AWS CLI emits e.g. "2025-07-30T12:34:56+00:00".
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return raw


def _write(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f">>> wrote {path}")


def _page(title, body):
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{html.escape(title)}</title>\n"
        "  <style>\n"
        "    body { font-family: -apple-system, Segoe UI, Roboto, sans-serif;"
        " margin: 2rem; color: #222; }\n"
        "    h1 { border-bottom: 1px solid #ddd; padding-bottom: .5rem; }\n"
        "    table { border-collapse: collapse; width: 100%; }\n"
        "    th, td { text-align: left; padding: .4rem .8rem;"
        " border-bottom: 1px solid #eee; }\n"
        "    th { background: #f6f8fa; }\n"
        "    a { color: #0366d6; text-decoration: none; }\n"
        "    a:hover { text-decoration: underline; }\n"
        "    ul { list-style: none; padding: 0; }\n"
        "    li { padding: .3rem 0; }\n"
        f"    footer {{ margin-top: 2rem; color: #888; font-size: .85rem; }}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{html.escape(title)}</h1>\n"
        f"{body}\n"
        f"  <footer>Generated on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</footer>\n"
        "</body>\n"
        "</html>\n"
    )


def _render_root(root_url, prefix, folders, extra_files):
    items = []
    for folder in folders:
        href = f"{root_url}/{prefix}{folder}/"
        items.append(
            f'    <li>&#128193; <a href="{html.escape(href)}">'
            f"{html.escape(folder)}/</a></li>"
        )
    for name in extra_files:
        href = f"{root_url}/{prefix}{name}"
        items.append(
            f'    <li>&#128196; <a href="{html.escape(href)}">'
            f"{html.escape(name)}</a></li>"
        )

    body = "  <ul>\n" + "\n".join(items) + "\n  </ul>"
    return _page("Alfresco Drive – Software Channel", body)


def _render_folder(folder, root_url, prefix, files):
    rows = []
    for entry in files:
        href = f"{root_url}/{prefix}{folder}/{entry['name']}"
        rows.append(
            "      <tr>"
            f'<td><a href="{html.escape(href)}">'
            f"{html.escape(entry['name'])}</a></td>"
            f"<td>{html.escape(_format_date(entry['last_modified']))}</td>"
            f"<td>{html.escape(_human_size(entry['size']))}</td>"
            "</tr>"
        )

    parent = f"{root_url}/{prefix}"
    if not rows:
        table = "  <p><em>No files.</em></p>"
    else:
        table = (
            "  <table>\n"
            "    <thead>\n"
            "      <tr><th>Name</th><th>Last modified</th><th>Size</th></tr>\n"
            "    </thead>\n"
            "    <tbody>\n" + "\n".join(rows) + "\n    </tbody>\n"
            "  </table>"
        )

    body = (
        f'  <p><a href="{html.escape(parent)}">&#8592; Back to root</a></p>\n' + table
    )
    return _page(f"Alfresco Drive – {folder}", body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument(
        "--prefix",
        default="alfresco/drive-updates/",
        help="S3 key prefix (must end with '/').",
    )
    parser.add_argument("--root-url", required=True, help="Public base URL.")
    parser.add_argument(
        "--folders",
        nargs="+",
        default=["alpha", "beta", "release"],
        help="Folders to link from the root index.html.",
    )
    parser.add_argument(
        "--update-folders",
        nargs="*",
        default=None,
        help=(
            "Subset of --folders whose per-folder index.html should be"
            " (re)generated. Defaults to all of --folders."
        ),
    )
    parser.add_argument(
        "--extra-files",
        nargs="*",
        default=["versions.yml"],
        help="Files at the root of the prefix to link from the index.",
    )
    parser.add_argument(
        "--output-dir",
        default="index_pages",
        help="Local directory where index.html files are written.",
    )
    args = parser.parse_args()

    prefix = args.prefix
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    root_url = args.root_url.rstrip("/")

    _write(
        os.path.join(args.output_dir, "index.html"),
        _render_root(root_url, prefix, args.folders, args.extra_files),
    )

    update_folders = args.update_folders
    if update_folders is None:
        update_folders = args.folders

    unknown = [f for f in update_folders if f not in args.folders]
    if unknown:
        print(
            f">>> --update-folders contains folders not in --folders: {unknown}",
            file=sys.stderr,
        )
        sys.exit(2)

    for folder in update_folders:
        files = _list_folder(args.bucket, f"{prefix}{folder}")
        _write(
            os.path.join(args.output_dir, folder, "index.html"),
            _render_folder(folder, root_url, prefix, files),
        )


if __name__ == "__main__":
    main()
