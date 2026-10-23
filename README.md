<p align="center">
  <img src="assets/logo.svg" alt="Output Contracts — Define the shape. Check the output." width="400" height="160">
</p>

# Output Contracts

Output Contracts checks whether Markdown headings, forbidden text patterns, and declared JSON fields follow an explicit contract. It produces located violations and a useful exit status. A passing result means only that the configured structural rules passed.

## Quickstart

Run from this repository with Python 3.11 or newer:

```sh
set -eu
if python -m output_contracts validate fixtures/handoff-contract.json fixtures/handoff-bad.md --format json --out /tmp/output-contracts-handoff.json; then
  echo "Expected handoff violations" >&2; exit 1
else
  code=$?
  test "$code" -eq 1
fi
python -c 'import json; d=json.load(open("/tmp/output-contracts-handoff.json")); print("Violations:", ", ".join(v["kind"] for v in d["violations"]))'
python -m output_contracts validate fixtures/result-contract.json fixtures/result-good.json --format markdown --out /tmp/output-contracts-good.md
python -m output_contracts inspect fixtures/handoff-contract.json
```

The handoff report shows missing and out-of-order sections plus the forbidden completion claim. The good JSON fixture exits `0`. The adverse JSON fixture returns `1` because `true` is not an integer count and `items` is empty:

```sh
if python -m output_contracts validate fixtures/result-contract.json fixtures/result-bad.json; then
  echo "Expected JSON field violations" >&2; exit 1
else
  code=$?
  test "$code" -eq 1
fi
```

`validate` exits `0` when all configured rules pass, `1` when validation completes with violations (including invalid output JSON), and `2` for an invalid contract, unreadable input, or invalid command arguments. JSON reports go to stdout by default; use `--format markdown` for a readable report and `--out` to save either format. `inspect` validates and prints a normalized contract summary. See `python -m output_contracts --help` for command details.

## Rule boundaries

Markdown heading extraction recognizes ATX `#` through `######` headings outside fenced code blocks. It ignores Setext headings, HTML headings, and bold text. Forbidden patterns scan the whole output, including code blocks. JSON mode uses RFC 6901 pointers and exact declared types; `true` does not satisfy `integer`, and null is distinct from a missing field.

Contracts are declarative and do not execute code. Regexes come from trusted contract authors and are not sandboxed or guaranteed to have linear runtime. The validator does not establish truth, completeness of evidence, safety, or reasoning quality. A clean report means only that the listed structural checks passed.

See [the complete format reference](docs/SCHEMA.md). Run the standard-library tests with:

```sh
python -m unittest discover -s tests -v
```

See [verification coverage](docs/VERIFICATION.md) and [the design plan](docs/PLAN.md) for tested behavior and remaining limits.
