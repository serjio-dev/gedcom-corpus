#!/usr/bin/env python3
"""Import the GEDCOM 7.0 test files of gedcom.io into cases/gio-* as external cases.

Usage:
    git clone https://github.com/FamilySearch/GEDCOM.io.git /tmp/GEDCOM.io
    scripts/import-gedcomio.py /tmp/GEDCOM.io

FamilySearch/GEDCOM.io gives no license, so the files are not committed: each case gets a
case.yaml with `license: NOASSERTION`, and external.json the URL at the clone's commit and the
SHA-256 that scripts/fetch-external.py downloads and checks. Every `testfiles/gedcom70/*.ged` and
`*.gdz` becomes a case (gio-<name>, gio-<name>-gdz); the unpacked archives (`maximal70/`) are
the .gdz cases. Checks: read and roundtrip-preserve, plus roundtrip-stream for .ged files.
Re-running the script replaces all gio-* cases; checks and expectations added by hand are kept
for files whose bytes are unchanged upstream, and dropped with a warning otherwise.
Requires: pip install pyyaml
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

from importing import describe_input

REPO = "FamilySearch/GEDCOM.io"
DIRECTORY = "testfiles/gedcom70"
ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"
MANIFEST = ROOT / "external.json"
BASE_CHECKS = ("read", "roundtrip-preserve", "roundtrip-stream")


def case_id(path: Path) -> str:
    return "gio-" + re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") + ("-gdz" if path.suffix == ".gdz" else "")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    source = Path(sys.argv[1]).resolve()
    commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    manifest = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.is_file() else {"cases": {}}
    old_hashes = {cid: entry["sha256"] for cid, entry in manifest["cases"].items()}

    kept = {}
    for old in CASES.glob("gio-*"):
        descriptor = yaml.safe_load((old / "case.yaml").read_text("utf-8"))
        extra = [c for c in descriptor["checks"] if c not in BASE_CHECKS]
        if extra or "expect" in descriptor:
            kept[old.name] = (old_hashes.get(old.name), extra, descriptor.get("expect"))
        shutil.rmtree(old)
        manifest["cases"].pop(old.name, None)

    paths = sorted(p for p in (source / DIRECTORY).iterdir() if p.suffix in (".ged", ".gdz"))
    for path in paths:
        cid = case_id(path)
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        gedcom = zipfile.ZipFile(path).read("gedcom.ged") if path.suffix == ".gdz" else raw
        spec = describe_input(gedcom, "7")
        spec["file"] = "external" + path.suffix
        upstream = f"{DIRECTORY}/{path.name}"
        descriptor = {
            "id": cid,
            "description": f"gedcom.io test file {path.name}, fetched by scripts/fetch-external.py (no license given, not committed).",
            "source": {"origin": "gedcom.io", "url": f"https://github.com/{REPO}/blob/{commit}/{upstream}", "commit": commit, "path": upstream},
            "license": "NOASSERTION",
            "fictional": True,
            "milestone": "0.6",
            "tags": ["gedcom.io"],
            "input": {"file": spec.pop("file"), **spec},
            "checks": list(BASE_CHECKS if path.suffix == ".ged" else BASE_CHECKS[:2]),
        }
        if cid in kept:
            old_hash, extra, expect = kept.pop(cid)
            if old_hash == sha256:
                descriptor["checks"] += extra
                if expect is not None:
                    descriptor["expect"] = expect
            else:
                print(f"{cid}: input changed upstream, checks {extra} and expect dropped; review them", file=sys.stderr)
        target = CASES / cid
        target.mkdir()
        (target / "case.yaml").write_text(yaml.safe_dump(descriptor, allow_unicode=True, sort_keys=False, width=200), "utf-8")
        manifest["cases"][cid] = {
            "file": descriptor["input"]["file"],
            "url": f"https://raw.githubusercontent.com/{REPO}/{commit}/{upstream}",
            "sha256": sha256,
        }
        print(f"{cid}: {spec['version']} {spec['encoding']}")

    for cid in kept:
        print(f"{cid}: removed upstream, its checks and expect are gone", file=sys.stderr)
    manifest["cases"] = dict(sorted(manifest["cases"].items()))
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    print(f"imported {len(paths)} files from {REPO} @ {commit[:12]}; run scripts/fetch-external.py")


main()
