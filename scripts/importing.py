"""Helpers shared by the import scripts: what an imported GEDCOM file is (encoding, BOM, declared
CHAR and version, line ending), for the `input` of its case.yaml."""

import re
import sys

CHAR_TO_ENCODING = {"UTF-8": "UTF-8", "ASCII": "ASCII", "ANSEL": "ANSEL"}


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
