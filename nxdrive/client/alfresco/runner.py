from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .client import AlfrescoClient, AlfrescoClientError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal Alfresco client runner")
    parser.add_argument("--url", default=os.getenv("ALFRESCO_URL", ""), required=False)
    parser.add_argument("--username", default=os.getenv("ALFRESCO_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("ALFRESCO_PASSWORD", ""))
    parser.add_argument("--token", default=os.getenv("ALFRESCO_TOKEN", ""))
    parser.add_argument(
        "--no-verify", action="store_true", help="Disable TLS certificate checks"
    )
    parser.add_argument("--timeout", type=int, default=30)

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="Authenticate and print bearer token")

    list_cmd = sub.add_parser("list", help="List children nodes")
    list_cmd.add_argument("--parent-id", default="-root-")

    get_cmd = sub.add_parser("get", help="Get one node")
    get_cmd.add_argument("node_id")

    upload_cmd = sub.add_parser("upload", help="Upload a file")
    upload_cmd.add_argument("parent_id")
    upload_cmd.add_argument("file_path", type=Path)
    upload_cmd.add_argument("--name", default="")
    upload_cmd.add_argument("--no-auto-rename", action="store_true")

    delete_cmd = sub.add_parser("delete", help="Delete one node")
    delete_cmd.add_argument("node_id")
    delete_cmd.add_argument("--permanent", action="store_true")

    return parser


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    args = build_parser().parse_args()
    if not args.url:
        print("Missing --url (or ALFRESCO_URL)")
        return 2

    client = AlfrescoClient(
        args.url,
        username=args.username,
        password=args.password,
        token=args.token,
        verify=not args.no_verify,
        timeout=args.timeout,
    )

    try:
        if args.command == "auth":
            _print_json({"token": client.authenticate()})
        elif args.command == "list":
            _print_json(client.list_nodes(args.parent_id))
        elif args.command == "get":
            _print_json(client.get_node(args.node_id))
        elif args.command == "upload":
            _print_json(
                client.upload_file(
                    args.parent_id,
                    args.file_path,
                    name=args.name,
                    auto_rename=not args.no_auto_rename,
                )
            )
        elif args.command == "delete":
            client.delete_node(args.node_id, permanent=args.permanent)
            _print_json({"deleted": args.node_id, "permanent": args.permanent})
        else:
            print(f"Unsupported command: {args.command}")
            return 2
    except AlfrescoClientError as exc:
        _print_json(
            {
                "error": str(exc),
                "status_code": exc.status_code,
                "payload": exc.payload,
            }
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
