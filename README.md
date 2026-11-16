# gedcom-corpus

Language-neutral test corpus for GEDCOM readers, writers, validators and converters.
It holds data only — inputs, expected outputs, loss reports and semantic fingerprints —
so any implementation in any language can run the same cases. It is the conformance
suite of [Korin](https://github.com/serjio-dev/korin-php), but nothing here depends on it.

Every person in the corpus is invented. Real trees of living people are never accepted.

## Layout

```
cases/<id>/
├── case.yaml               what the case is and what it checks   (schema/case.schema.json)
├── input.ged | input.gdz   the input, byte-exact
├── fingerprint.json        semantic content of the input         (schema/fingerprint.schema.json)
├── expected.<ver>.ged      output of converting to <ver>
├── losses.<ver>.json       loss report of that conversion        (schema/losses.schema.json)
├── ops.json                edit operations                       (schema/ops.schema.json)
├── expected.ged            output after applying ops.json
└── LICENSE                 only when the case is not Apache-2.0
```

Only files referenced from `case.yaml` may be present.

## Checks

| Check | Passes when |
| --- | --- |
| `read` | The input parses; `expect.recordCount` and `expect.diagnostics` match |
| `roundtrip-preserve` | Writing the unmodified document in preserve mode reproduces `input` byte for byte |
| `roundtrip-normalize` | Normalized output has the same fingerprint as the input |
| `roundtrip-stream` | Reading record by record and writing each record in preserve mode reproduces `input` byte for byte |
| `fingerprint` | The fingerprint of the parsed input equals `fingerprint.json` |
| `validate` | Diagnostics of the version's validator equal `expect.diagnostics` |
| `convert` | For each `convert[]` entry, output equals `expected.<ver>.ged`, validates cleanly, and the loss report matches `losses.<ver>.json` by `code`, `path`, `storedAs` |
| `convert-stream` | Streaming conversion with constant memory gives the same output and loss report as `convert`, byte for byte. Requires `convert` |
| `edit` | Applying `ops.json` and writing in `edit.writeMode` gives `expected.ged` |

Diagnostics without `code` are matched by severity and path until codes are assigned.
Codes are those of Korin's [diagnostics reference](https://github.com/serjio-dev/korin-php/blob/main/docs/diagnostics.md);
`validate` expects the reader's diagnostics too, since a validator reports both.

## Fingerprint

A canonical JSON form of a document's meaning, used to compare documents that differ in bytes:

- records and substructures in document order;
- values in Unicode NFC, after joining `CONC`/`CONT` (`CONT` becomes `\n`) and removing `@@` escaping;
- a cross-reference value is stored as `pointer`, any other value as `value`;
- `TRLR` and the volatile `HEAD` substructures `DATE`, `SOUR`, `CHAR`, `GEDC` are omitted.

Fingerprints are compared only within one GEDCOM version.

## Paths

Used in `ops.json` and loss reports:

```
HEAD/GEDC/VERS
@I1@/NAME[0]/SURN[0]
```

The first segment is `HEAD` or a record xref. Each next segment is a tag with an optional
0-based index among siblings with that tag; without an index the tag must be unique among
its siblings. In `ops.json` each path is resolved after the previous operation.

Paths in diagnostics and loss reports use the canonical form: an index appears only when
the tag repeats among its siblings (`@I1@/NAME[1]`, but `@I1@/FAMC` for a single `FAMC`).

## Imported cases

`cases/g7c-*` come from [gedcom7code/test-files](https://github.com/gedcom7code/test-files)
(Unlicense), pinned to the commit recorded in each `case.yaml`. To refresh them:

```bash
git clone https://github.com/gedcom7code/test-files.git /tmp/test-files
python scripts/import-gedcom7code.py /tmp/test-files
```

Upstream pairs a 5.5.1 file in `5/` with a 7.0 file of the same name in `7/`. The 7.0 file is
one valid conversion, not the only one, so the pair is linked through `references` and
compared semantically, never byte for byte. Fingerprints, expected diagnostics and
conversions for imported cases are added by hand after review; the import script keeps them as
long as the upstream file is unchanged. The `convert` golden file of a 5.5.1 case
(`expected.7.0.ged`) follows the spec's output conventions; where the upstream 7.0 file is
exactly that conversion, the golden file is a copy of it. Otherwise they differ where the
upstream converter drops data (SUBN, `@#…@` in text) or orders new records differently.

Every imported case has the `validate` check except `g7c-5-date-all`: it combines every
date form with every calendar written without its `@#D…@` escape (`JULIAN 1401`) and with
one-digit dual years (`1401/8`), so most of its 2,917 dates are invalid 5.5.1 by design and an
expected list would not test anything the smaller date cases do not.

## Contributing a case

1. Create `cases/<id>/` with a lowercase, hyphenated `id`.
2. Add the input and `case.yaml`; set `fictional: true` and a license. Files with an
   unclear license are not committed — they are fetched by a script instead.
3. Run the checks:

   ```bash
   pip install pyyaml jsonschema
   python scripts/check-cases.py
   ```

`.ged` and `.gdz` files are `binary` in `.gitattributes`, so Git never rewrites their line endings.

## Versioning

SemVer tags. A new case is a minor release; changing the expected result of an existing
case is a major release.

## License

Apache-2.0, except cases that carry their own `LICENSE`.
GEDCOM is a trademark of Intellectual Reserve, Inc. This project is not affiliated with or
endorsed by FamilySearch.
