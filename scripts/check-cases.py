#!/usr/bin/env python3
"""Validate the corpus: schemas, file layout, licenses and input metadata.

Usage: scripts/check-cases.py [corpus-root]
Requires: pip install pyyaml jsonschema
"""

import json
import re
import sys
import zipfile
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent)
SCHEMAS = {
    name: Draft202012Validator(json.loads((ROOT / "schema" / f"{name}.schema.json").read_text("utf-8")))
    for name in ("case", "fingerprint", "losses", "ops")
}

errors: list[str] = []


def fail(case: str, message: str) -> None:
    errors.append(f"{case}: {message}")


def validate(case: str, schema: str, data: object, label: str) -> None:
    for error in SCHEMAS[schema].iter_errors(data):
        location = "/".join(str(p) for p in error.absolute_path) or "<root>"
        fail(case, f"{label} {location}: {error.message}")


def load_json(case: str, path: Path) -> object | None:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as e:
        fail(case, f"{path.name}: {e}")
        return None


def decode(raw: bytes) -> str:
    """Text of a GEDCOM file: UTF-16 by its BOM (5.5 output), otherwise UTF-8."""
    for bom, codec in ((b"\xfe\xff", "utf-16-be"), (b"\xff\xfe", "utf-16-le")):
        if raw.startswith(bom):
            return raw[len(bom):].decode(codec, "replace")
    return raw.decode("utf-8", "replace")


def line_ending(raw: bytes) -> str:
    crlf = raw.count(b"\r\n")
    cr = raw.count(b"\r") - crlf
    lf = raw.count(b"\n") - crlf
    kinds = [k for k, n in (("CRLF", crlf), ("CR", cr), ("LF", lf)) if n]
    return kinds[0] if len(kinds) == 1 else "mixed"


BOMS = {"UTF-8": b"\xef\xbb\xbf", "UTF-16LE": b"\xff\xfe", "UTF-16BE": b"\xfe\xff"}


def check_input(case: str, spec: dict, path: Path) -> None:
    if path.suffix == ".gdz":
        try:
            with zipfile.ZipFile(path) as archive:
                raw = archive.read("gedcom.ged")
        except (zipfile.BadZipFile, KeyError) as e:
            fail(case, f"input.gdz is not a GEDZIP archive with gedcom.ged: {e}")
            return
    elif path.suffix == ".ged":
        raw = path.read_bytes()
    else:
        return
    encoding = spec["encoding"]
    bom = BOMS.get(encoding, b"")
    has_bom = bool(bom) and raw.startswith(bom)
    if has_bom != spec.get("bom", False):
        fail(case, f"input BOM is {has_bom}, case.yaml says {spec.get('bom', False)}")
    body = raw[len(bom):] if has_bom else raw
    try:
        # Only line structure and ASCII tags are inspected, so latin-1 is enough for 8-bit encodings.
        text = body.decode(encoding.lower() if encoding.startswith("UTF-16") else "latin-1")
    except UnicodeDecodeError as e:
        fail(case, f"input is not valid {encoding}: {e}")
        return
    ending = line_ending(text.encode("utf-8"))
    if "lineEnding" in spec and ending != spec["lineEnding"]:
        fail(case, f"input line ending is {ending}, case.yaml says {spec['lineEnding']}")
    # Python's ^ and $ know only LF: CR (Mac) and CRLF line endings are made LF first.
    lines = text.replace("\r\n", "\n").replace("\r", "\n")
    gedc = re.search(r"^\s*1 GEDC\s*$\s*^\s*2 VERS (\S+)", lines, re.MULTILINE)
    match = gedc or re.search(r"^\s*2 VERS ([0-9.]+)", lines, re.MULTILINE)
    if match is None:
        if spec.get("versionDeclared", True):
            fail(case, "input has no HEAD.GEDC.VERS; set versionDeclared: false")
    elif match.group(1) != spec.get("declaredVersion", spec["version"]):
        fail(case, f"HEAD.GEDC.VERS is {match.group(1)}, case.yaml says {spec.get('declaredVersion', spec['version'])}")


def check_case(case_dir: Path) -> None:
    case = case_dir.name
    descriptor_path = case_dir / "case.yaml"
    if not descriptor_path.is_file():
        fail(case, "case.yaml is missing")
        return
    descriptor = yaml.safe_load(descriptor_path.read_text("utf-8"))
    validate(case, "case", descriptor, "case.yaml")
    if not isinstance(descriptor, dict) or not SCHEMAS["case"].is_valid(descriptor):
        return

    if descriptor["id"] != case:
        fail(case, f"id '{descriptor['id']}' does not match directory name")
    if descriptor["license"] != "Apache-2.0" and not (case_dir / "LICENSE").is_file():
        fail(case, f"license {descriptor['license']} requires a LICENSE file in the case directory")

    referenced = {"case.yaml", "LICENSE", descriptor["input"]["file"]}
    input_path = case_dir / descriptor["input"]["file"]
    if input_path.is_file():
        check_input(case, descriptor["input"], input_path)
    else:
        fail(case, f"{input_path.name} is missing")

    if "fingerprint" in descriptor["checks"]:
        referenced.add("fingerprint.json")
        data = load_json(case, case_dir / "fingerprint.json")
        if data is not None:
            validate(case, "fingerprint", data, "fingerprint.json")
            if isinstance(data, dict) and data.get("gedcomVersion") != descriptor["input"]["version"]:
                fail(case, "fingerprint.json gedcomVersion differs from input.version")

    for conversion in descriptor.get("convert", []):
        referenced.add(conversion["expected"])
        expected = case_dir / conversion["expected"]
        if not expected.is_file():
            fail(case, f"{conversion['expected']} is missing")
        elif not re.search(rf"^2 VERS {re.escape(conversion['to'])}$", decode(expected.read_bytes()).replace("\r\n", "\n").replace("\r", "\n"), re.MULTILINE):
            fail(case, f"{conversion['expected']} does not declare VERS {conversion['to']}")
        if "losses" in conversion:
            referenced.add(conversion["losses"])
            data = load_json(case, case_dir / conversion["losses"])
            if data is not None:
                validate(case, "losses", data, conversion["losses"])

    for reference in descriptor.get("references", []):
        target = ROOT / "cases" / reference["case"] / "case.yaml"
        if not target.is_file():
            fail(case, f"referenced case {reference['case']} does not exist")
        elif yaml.safe_load(target.read_text("utf-8"))["input"]["version"] != reference["to"]:
            fail(case, f"referenced case {reference['case']} is not version {reference['to']}")

    if "edit" in descriptor:
        edit = descriptor["edit"]
        referenced.update((edit["ops"], edit["expected"]))
        if not (case_dir / edit["expected"]).is_file():
            fail(case, f"{edit['expected']} is missing")
        data = load_json(case, case_dir / edit["ops"])
        if data is not None:
            validate(case, "ops", data, edit["ops"])

    for stray in sorted(p.name for p in case_dir.iterdir() if p.name not in referenced):
        fail(case, f"{stray} is not referenced by case.yaml")


cases = sorted(p for p in (ROOT / "cases").iterdir() if p.is_dir())
for case_dir in cases:
    check_case(case_dir)

if errors:
    print("\n".join(errors), file=sys.stderr)
    print(f"\n{len(errors)} problem(s) in {len(cases)} case(s)", file=sys.stderr)
    sys.exit(1)
print(f"{len(cases)} case(s) OK")
