#!/usr/bin/env python3
"""Read a local RDS CA bundle and apply one ConfigMap; never deploy applications."""

import argparse
import json
from pathlib import Path
import ssl
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-file", type=Path, required=True, help="Path to global-bundle.pem")
    parser.add_argument("--context", default="twolevel-dev")
    parser.add_argument("--namespace", default="retailstore")
    parser.add_argument("--name", default="rds-ca", help="Must match databaseTLS.caConfigMapName")
    parser.add_argument("--dry-run", action="store_true", help="Validate against API server without saving")
    args = parser.parse_args()

    try:
        path = args.ca_file.expanduser().resolve(strict=True)
        pem = path.read_text(encoding="utf-8-sig")
        if "PRIVATE KEY" in pem:
            raise ValueError("Use a public CA bundle, not a private key")
        if "-----BEGIN CERTIFICATE-----" not in pem:
            raise ValueError("The CA file must contain PEM certificates")
        # Parse the exact content we will send; invalid/empty PEM fails before kubectl.
        ssl.create_default_context(cadata=pem)
        manifest = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": args.name, "namespace": args.namespace},
            "data": {"global-bundle.pem": pem},
        }
        command = ["kubectl", "--context", args.context, "apply", "-f", "-"]
        if args.dry_run:
            command.append("--dry-run=server")
        subprocess.run(command, input=json.dumps(manifest), text=True, check=True)
    except (OSError, ValueError, ssl.SSLError, subprocess.CalledProcessError) as exc:
        print(f"RDS CA ConfigMap failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
