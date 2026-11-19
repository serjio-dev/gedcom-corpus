#!/usr/bin/env python3
"""Download the inputs of external cases: files whose license does not allow committing them.

Usage: scripts/fetch-external.py [corpus-root]

external.json maps each such case to the URL of its input at a fixed commit and its SHA-256.
A file already present with that hash is kept; a download with another hash is an error. The
files land in cases/<id>/ under the name case.yaml gives (external.ged or external.gdz), which
.gitignore keeps out of commits. Only the Python standard library is used, so test suites in
any language can run it before the corpus.
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent)


def main() -> None:
    manifest = json.loads((ROOT / "external.json").read_text("utf-8"))
    fetched = 0
    for case, entry in manifest["cases"].items():
        target = ROOT / "cases" / case / entry["file"]
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]:
            continue
        with urllib.request.urlopen(entry["url"], timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            sys.exit(f"{case}: {entry['url']} does not have the SHA-256 in external.json")
        target.write_bytes(data)
        fetched += 1
    print(f"{len(manifest['cases'])} external input(s), {fetched} downloaded")


main()
