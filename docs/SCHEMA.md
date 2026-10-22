# Output Contracts format

Contract files are UTF-8 JSON with `schema_version: 1`. Unknown keys and keys belonging to the other mode are rejected so misspelled rules cannot silently pass. IDs are nonempty strings. `forbidden_patterns` is an ordered array of `{id, pattern, ignore_case?}` records; rule IDs are unique. Patterns are Python regular expressions over the entire original output text, including code fences. A rule emits up to 100 located violations and records the total match count and whether display was truncated.

## Markdown mode

Use `mode: "markdown"`, `required_headings: [...]`, optional `ordered` (default `true`), and `allow_extra_headings` (default `true`). Required heading names are nonempty and unique after case folding and whitespace normalization. The checker recognizes ATX headings with one through six `#` markers outside backtick or tilde fences and strips optional closing hashes. Missing and duplicate headings are independent violations. When ordered, first occurrences must follow contract order. Extra headings are only reported when `allow_extra_headings` is false. Heading depth is not constrained. Setext, HTML, and bold text are not headings.

## JSON mode

Use `mode: "json"`, an ordered `fields` array, and optional `allowed_root_keys`. Each field has an RFC 6901 JSON Pointer `path` (empty string addresses the root), `type` (`string`, `integer`, `number`, `boolean`, `object`, `array`, or `null`), and optional constraints. `required` defaults to true. Optional missing fields skip their other constraints. JSON object keys must be unique. Non-finite numbers are rejected. Array indexes use canonical nonnegative decimal strings; `-` is unsupported.

`equals` and `enum` use recursive JSON comparison. Boolean values never equal numbers. `1` and `1.0` can compare equal for `number` fields, while integer fields accept only JSON integers. `min_length` and `max_length` apply to strings, arrays, and objects. `minimum` and `maximum` apply to integers and finite numbers. `allowed_root_keys` checks only the top-level object.

Reports contain schema version, contract ID and fingerprint, output fingerprint, mode, validity, checked rules, located violations, and limitations. An invalid JSON output is a completed validation violation (`invalid_json`); an unreadable output or invalid contract is an operational/input error.
