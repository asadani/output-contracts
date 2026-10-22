# Output Contracts v0.1 implementation plan

## User job and CLI

Validate a UTF-8 Markdown or JSON output against a declarative contract, emit located violations, and return a useful automation exit code.

```sh
python -m output_contracts validate fixtures/handoff-contract.json fixtures/handoff-bad.md --format json --out violations.json
python -m output_contracts validate fixtures/result-contract.json fixtures/result-good.json --format markdown --out validation.md
python -m output_contracts inspect fixtures/handoff-contract.json
```

`validate` exits 0 when all configured rules pass, 1 for completed validation with violations (including invalid output JSON), and 2 for invalid contract, unreadable input, or invalid CLI arguments. `inspect` validates a contract and prints a short normalized description of its rules. No repair, retries, or output mutation.

## Common contract structure

`{schema_version:1,id,description,mode:"markdown"|"json",forbidden_patterns:[{id,pattern,ignore_case:false}],...}`. Contract IDs and rule IDs are nonempty. Pattern IDs unique; regexes compile at contract load using Python `re`, with only optional IGNORECASE. Patterns operate on the original output text in both modes and produce one violation per match, located by character offset and 1-based line/column. Cap displayed matches at 100 per rule, retain total match count and truncation flag. Zero-width matches are allowed but bounded in displayed output. These are author-supplied trusted regexes; do not claim regex sandboxing or linear execution time.

Reject unknown contract keys and mode-incompatible options so misspelled rules do not silently pass. Validate all rule types and constraints before reading results as conforming.

## Markdown rules

Additional fields: `required_headings:[string]`, `ordered:boolean` default true, `allow_extra_headings:boolean` default true. Required heading names are unique, nonempty, normalized by stripping outer whitespace and casefolding. Recognize ATX `#` through `######` headings outside fenced code blocks; strip optional closing hashes. Do not treat Setext, HTML, or bold lines as headings. Disclose this grammar.

Each required heading must appear exactly once; missing gives `missing_heading`, multiple gives `duplicate_heading` with all line locations. If ordered, first occurrences of present required headings must follow contract order; report `heading_order` with the expected sequence and actual sequence. Missing sections still receive independent missing findings. Extra headings are allowed unless explicitly forbidden; then each unmatched heading is `unexpected_heading`. Heading depth is not constrained in v0.1. Forbidden patterns still apply inside code blocks because their contract scope is whole output text; document this difference from heading extraction.

## JSON field rules

Additional fields: `fields:[{path,type,required:true,equals?,enum?,min_length?,max_length?,minimum?,maximum?}]`, optional `allowed_root_keys:[string]`. `path` is an RFC 6901 JSON Pointer: empty string addresses the root; `/result/count` traverses object keys; array indexes use canonical nonnegative integer strings, no `-`. Decode `~0` and `~1`; reject invalid escapes. Duplicate field paths fail contract validation.

`type` is `string|integer|number|boolean|object|array|null`. Booleans never satisfy integer/number. Numbers must be finite; reject NaN/Infinity JSON constants. JSON decoding rejects duplicate object keys rather than discarding earlier values. An absent required path gives `required_field`; an absent optional path skips its other constraints; wrong type gives `field_type` and skips incompatible checks for that field. Null is a present value, not a missing field. Root-level scalar values are valid if compatible with the declared root constraints.

`equals` and `enum` use strict recursive JSON equality that distinguishes bool from numeric values. `1` and `1.0` may compare numerically equal only for number-typed constraints; integer type already rejects float input. Enum must be nonempty with no duplicate strictly equal values, all compatible with the declared type. `equals` must be compatible with type and enum when both supplied. `min_length/max_length` apply to strings/arrays/objects, nonnegative integers; `minimum/maximum` apply to integer/number. Reject inverted bounds and incompatible constraints at load. `allowed_root_keys` requires output object; unexpected top-level keys are violations. No recursive extra-key policy is implied.

## Report and API

Report: `{schema_version:1,contract_id,contract_sha256,output_sha256,mode,valid,checked_rules,violations:[{rule_id,kind,message,location:{line?,column?,path?},expected?,actual?}],limitations:[...]}`. Syntax-invalid output JSON gives `invalid_json` with decoder location. Missing heading has an empty location plus expected name; do not invent a source line. JSON field violations use pointers; no approximate source line needed. Stable order follows contract rule order then source location. Do not render entire large/private values when a short type/value excerpt suffices; mark truncated excerpts.

- `load_contract(data: dict) -> dict` validates and returns normalized contract.
- `extract_headings(text: str) -> list[dict]`
- `resolve_pointer(value: object, pointer: str) -> tuple[bool, object]`
- `validate_output(contract: dict, text: str) -> dict`
- `render_markdown(report: dict) -> str`

CLI adds original-byte hashes. A valid result must say “All configured structural checks passed,” not “correct,” “safe,” or “verified answer.” Markdown reports cite each rule, location, expected constraint, and observed violation.

## Fixtures and acceptance tests

1. Handoff contract requires Summary, Evidence, Unresolved questions, and Next steps in order and forbids a configured unsupported-completion phrase. Bad output violates missing/order/pattern rules; good output passes. Code-fenced heading examples do not count as headings.
2. Duplicate required headings, optional extras, forbidden extras, case-normalized headings, closing hashes, and missing plus misordered headings produce precise independent outcomes.
3. JSON fixture validates string ID, exact `status` enum, integer count bounds, array minimum length, and forbidden top-level key. Test boolean-as-integer, float-as-integer, null versus absent, optional missing field, and correct values.
4. JSON pointers correctly handle slash/tilde keys and array indexes. Unknown path, malformed pointer, duplicate field path, duplicate output object key, NaN, malformed JSON, and invalid contract constraint fail with the documented distinction between exits 1 and 2.
5. Pattern matches retain exact line/column, escaped text, bounded excerpts, and total counts after truncation. Invalid regex is a contract error.
6. CLI good/bad examples verify exits, machine-readable stdout, and JSON/Markdown reports. Repeated identical validation is deterministic.

## Non-goals and milestone

Required: two modes, strict contract validation, located violations, exact JSON typing, reports, fixtures/tests. Deferred: JSON Schema compatibility, arbitrary executable assertions, semantic grading, automated output repair, model APIs, template generation, remote validation. Keep the schema small enough that its behavior is fully explained in the README.

Build contract validation, then the two validators, then CLI/report. Done means structural mistakes fail predictably with the responsible rule and location, while a compliant fixture passes without any claim about truth.
