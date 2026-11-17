#!/usr/bin/env python3
"""Build the input.gdz of the GEDZIP cases, byte for byte the same on every run.

The archives are binary, so their content lives here: run this script after changing it,
and commit the archives it writes. Entries have a fixed date (1 January 2000) and no extra
fields; gedcom.ged is the first entry.
"""

import zipfile
from pathlib import Path

CASES = Path(__file__).resolve().parent.parent / "cases"
DATE = (2000, 1, 1, 0, 0, 0)

MEDIA_GED = (
    "0 HEAD\n1 GEDC\n2 VERS 7.0\n"
    "0 @I1@ INDI\n1 NAME Анна /Коваль/\n1 OBJE @M1@\n1 OBJE @M2@\n"
    "0 @M1@ OBJE\n1 FILE photos/anna.jpg\n2 FORM image/jpeg\n2 TITL Анна, 1921\n"
    "0 @M2@ OBJE\n1 FILE docs/birth%20record.txt\n2 FORM text/plain\n"
    "1 FILE https://example.com/anna.jpg\n2 FORM image/jpeg\n"
    "0 @M3@ OBJE\n1 FILE photos/missing.png\n2 FORM image/png\n"
    "0 TRLR\n"
)

UNSAFE_GED = "0 HEAD\n1 GEDC\n2 VERS 7.0\n0 @M1@ OBJE\n1 FILE ok.txt\n2 FORM text/plain\n0 TRLR\n"


def entry(archive: zipfile.ZipFile, name: str, data: bytes, deflate: bool = True, mode: int = 0o100644) -> None:
    info = zipfile.ZipInfo(name, DATE)
    info.compress_type = zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED
    info.external_attr = mode << 16
    info.create_system = 3  # Unix, so that the mode is read
    archive.writestr(info, data)


def build(case: str, entries: list[tuple]) -> None:
    with zipfile.ZipFile(CASES / case / "input.gdz", "w") as archive:
        for args in entries:
            entry(archive, *args)


build("gedzip-media-70", [
    ("gedcom.ged", MEDIA_GED.encode("utf-8")),
    # A JPEG header is enough: the content is not read, only found.
    ("photos/anna.jpg", b"\xff\xd8\xff\xe0" + bytes(60), False),
    ("docs/birth record.txt", "Метрична книга, 1921\n".encode("utf-8")),
])

build("gedzip-unsafe-entries-70", [
    ("gedcom.ged", UNSAFE_GED.encode("utf-8")),
    ("ok.txt", b"fine\n"),
    ("../outside.txt", b"zip-slip\n"),
    ("/etc/absolute.txt", b"absolute\n"),
    ("dir\\backslash.txt", b"backslash\n"),
    ("C:/drive.txt", b"drive\n"),
    ("link.txt", b"/etc/passwd", True, 0o120777),
])
