#!/usr/bin/env python3
"""Import gedcom7code/test-files into cases/g7c-*.

Usage:
    git clone https://github.com/gedcom7code/test-files.git /tmp/test-files
    scripts/import-gedcom7code.py /tmp/test-files

Every upstream file becomes its own case (g7c-5-<name>, g7c-7-<name>) checked for
read and roundtrip-preserve. A 5/ file and the 7/ file with the same name are linked
through `references`: upstream's 7.0 file is one valid conversion, not the only one,
so the pair is compared semantically. Re-running the script replaces all g7c-* cases;
checks and expectations added by hand (`checks` beyond the two above, `expect`, `convert`
with its expected files) are kept for files whose bytes are unchanged upstream, and dropped
with a warning otherwise.
Requires: pip install pyyaml
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = "https://github.com/gedcom7code/test-files"
ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"

CHAR_TO_ENCODING = {"UTF-8": "UTF-8", "ASCII": "ASCII", "ANSEL": "ANSEL"}


def case_id(major: str, name: str) -> str:
    return f"g7c-{major}-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def line_ending(text: str) -> str:
    crlf = text.count("\r\n")
    cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf
    kinds = [k for k, n in (("CRLF", crlf), ("CR", cr), ("LF", lf)) if n]
    return kinds[0] if len(kinds) == 1 else "mixed"


def describe_input(raw: bytes, major: str) -> dict:
    """Work out real encoding, BOM, declared CHAR, version and line ending of a file."""
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding, bom = "UTF-8", True
    elif raw.startswith(b"\xff\xfe"):
        encoding, bom = "UTF-16LE", True
    elif raw.startswith(b"\xfe\xff"):
        encoding, bom = "UTF-16BE", True
    elif raw[:2] == b"0\x00":
        encoding, bom = "UTF-16LE", False
    elif raw[:2] == b"\x000":
        encoding, bom = "UTF-16BE", False
    else:
        encoding, bom = None, False

    if encoding is None:
        text = raw.decode("latin-1")
    else:
        text = raw[(3 if encoding == "UTF-8" else 2) if bom else 0:].decode(encoding.lower())

    char = re.search(r"^1 CHAR (.+?)\r?$", text, re.MULTILINE)
    declared = char.group(1).strip() if char else None
    if encoding is None:
        if all(b < 0x80 for b in raw):
            encoding = CHAR_TO_ENCODING.get(declared or "", "ASCII")
        else:
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                sys.exit(f"cannot determine encoding; add the case by hand (CHAR {declared})")
            encoding = "UTF-8"

    spec: dict = {"file": "input.ged"}
    vers = re.search(r"^2 VERS ([0-9.]+)", text, re.MULTILINE)
    spec["version"] = vers.group(1) if vers else ("5.5.1" if major == "5" else "7.0")
    if not vers:
        spec["versionDeclared"] = False
    spec["encoding"] = encoding
    expected_char = {"UTF-8": "UTF-8", "ASCII": "ASCII", "ANSEL": "ANSEL", "UTF-16LE": "UNICODE", "UTF-16BE": "UNICODE"}
    if declared is not None and declared != expected_char.get(encoding):
        spec["declaredChar"] = declared
    if bom:
        spec["bom"] = True
    spec["lineEnding"] = line_ending(text)
    return spec


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    source = Path(sys.argv[1]).resolve()
    commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    license_text = (source / "LICENSE").read_text("utf-8")

    kept = {}
    for old in CASES.glob("g7c-*"):
        descriptor = yaml.safe_load((old / "case.yaml").read_text("utf-8"))
        extra = [c for c in descriptor["checks"] if c not in ("read", "roundtrip-preserve")]
        convert = descriptor.get("convert")
        if extra or "expect" in descriptor or convert:
            golden = {}
            for entry in convert or []:
                for key in ("expected", "losses"):
                    if key in entry:
                        golden[entry[key]] = (old / entry[key]).read_bytes()
            kept[old.name] = ((old / "input.ged").read_bytes(), extra, descriptor.get("expect"), convert, golden)
        shutil.rmtree(old)

    files = {major: sorted((source / major).glob("*.ged")) for major in ("5", "7")}
    names = {major: {f.stem for f in fs} for major, fs in files.items()}
    for major, paths in files.items():
        other = "7" if major == "5" else "5"
        for path in paths:
            cid = case_id(major, path.stem)
            spec = describe_input(path.read_bytes(), major)
            descriptor = {
                "id": cid,
                "description": f"Imported from gedcom7code/test-files {major}/{path.name}.",
                "source": {"origin": "gedcom7code", "url": f"{REPO}/blob/{commit}/{major}/{path.name}", "commit": commit, "path": f"{major}/{path.name}"},
                "license": "Unlicense",
                "fictional": True,
                "milestone": "0.1",
                "tags": ["gedcom7code"],
                "input": spec,
                "checks": ["read", "roundtrip-preserve"],
            }
            if major == "5" and path.stem in names[other]:
                descriptor["references"] = [{"to": "7.0", "case": case_id(other, path.stem)}]
            golden = {}
            if cid in kept:
                raw, extra, expect, convert, golden = kept.pop(cid)
                if raw == path.read_bytes():
                    descriptor["checks"] += extra
                    if expect is not None:
                        descriptor["expect"] = expect
                    if convert:
                        descriptor["convert"] = convert
                else:
                    golden = {}
                    print(f"{cid}: input changed upstream, checks {extra}, expect and convert dropped; review them", file=sys.stderr)

            target = CASES / cid
            target.mkdir()
            for name, data in golden.items():
                (target / name).write_bytes(data)
            shutil.copyfile(path, target / "input.ged")
            (target / "LICENSE").write_text(license_text, "utf-8")
            (target / "case.yaml").write_text(yaml.safe_dump(descriptor, allow_unicode=True, sort_keys=False, width=200), "utf-8")
            print(f"{cid}: {spec['version']} {spec['encoding']}" + (f" (CHAR {spec['declaredChar']})" if "declaredChar" in spec else ""))

    for cid in kept:
        print(f"{cid}: removed upstream, its checks, expect and convert are gone", file=sys.stderr)
    print(f"imported {sum(len(p) for p in files.values())} files from {REPO} @ {commit[:12]}")


main()
