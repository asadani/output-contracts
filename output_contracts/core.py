"""Strict contract validation and deterministic structural checks."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


class ContractError(ValueError):
    """Expected invalid contract data."""


FIELD_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}
FIELD_KEYS = {"path", "type", "required", "equals", "enum", "min_length", "max_length", "minimum", "maximum"}
CONTRACT_COMMON = {"schema_version", "id", "description", "mode", "forbidden_patterns"}


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a nonempty string")
    return value


def _finite(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _strict_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number {token} is not allowed")
    return value


def _ensure_finite_json(value: Any, where: str = "contract") -> None:
    if type(value) is float and not math.isfinite(value):
        raise ContractError(f"{where} contains a non-finite number")
    if isinstance(value, dict):
        for key, item in value.items():
            _ensure_finite_json(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_finite_json(item, f"{where}[{index}]")


def _matches_type(value: Any, kind: str) -> bool:
    if kind == "null":
        return value is None
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return type(value) is int
    if kind == "number":
        return _finite(value)
    if kind == "string":
        return isinstance(value, str)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    return False


def _equal(a: Any, b: Any, allow_number_equivalence: bool) -> bool:
    if type(a) is not type(b):
        if allow_number_equivalence and _finite(a) and _finite(b):
            return a == b
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k], allow_number_equivalence) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_equal(x, y, allow_number_equivalence) for x, y in zip(a, b))
    return a == b


def _compatible(value: Any, kind: str, label: str) -> None:
    if not _matches_type(value, kind):
        raise ContractError(f"{label} is incompatible with field type {kind}")


def _validate_pointer(pointer: Any) -> list[str]:
    if not isinstance(pointer, str):
        raise ContractError("field path must be a JSON Pointer string")
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ContractError(f"invalid JSON Pointer {pointer!r}: must be empty or start with '/'")
    tokens = pointer[1:].split("/")
    decoded = []
    for token in tokens:
        if re.search(r"~(?![01])", token):
            raise ContractError(f"invalid JSON Pointer escape in {pointer!r}")
        token = token.replace("~1", "/").replace("~0", "~")
        if token == "-":
            raise ContractError("JSON Pointer array token '-' is not supported")
        decoded.append(token)
    return decoded


def _constraints(field: dict[str, Any]) -> None:
    kind = field["type"]
    if "required" in field and type(field["required"]) is not bool:
        raise ContractError(f"field {field['path']!r} required must be boolean")
    for key in ("min_length", "max_length"):
        if key in field:
            value = field[key]
            if type(value) is not int or value < 0:
                raise ContractError(f"field {field['path']!r} {key} must be a nonnegative integer")
            if kind not in {"string", "array", "object"}:
                raise ContractError(f"field {field['path']!r} {key} only applies to string, array, or object")
    if "min_length" in field and "max_length" in field and field["min_length"] > field["max_length"]:
        raise ContractError(f"field {field['path']!r} has inverted length bounds")
    for key in ("minimum", "maximum"):
        if key in field:
            value = field[key]
            if not _finite(value):
                raise ContractError(f"field {field['path']!r} {key} must be a finite number")
            if kind not in {"integer", "number"}:
                raise ContractError(f"field {field['path']!r} {key} only applies to integer or number")
    if "minimum" in field and "maximum" in field and field["minimum"] > field["maximum"]:
        raise ContractError(f"field {field['path']!r} has inverted numeric bounds")
    if "enum" in field:
        values = field["enum"]
        if not isinstance(values, list) or not values:
            raise ContractError(f"field {field['path']!r} enum must be a nonempty array")
        allow_numbers = kind == "number"
        for i, value in enumerate(values):
            _compatible(value, kind, f"field {field['path']!r} enum value {i}")
            if any(_equal(value, prior, allow_numbers) for prior in values[:i]):
                raise ContractError(f"field {field['path']!r} enum has duplicate values")
    if "equals" in field:
        _compatible(field["equals"], kind, f"field {field['path']!r} equals")
        if "enum" in field and not any(_equal(field["equals"], x, kind == "number") for x in field["enum"]):
            raise ContractError(f"field {field['path']!r} equals value is not in enum")
        value = field["equals"]
        if "min_length" in field and len(value) < field["min_length"]:
            raise ContractError(f"field {field['path']!r} equals value is below min_length")
        if "max_length" in field and len(value) > field["max_length"]:
            raise ContractError(f"field {field['path']!r} equals value exceeds max_length")
        if "minimum" in field and value < field["minimum"]:
            raise ContractError(f"field {field['path']!r} equals value is below minimum")
        if "maximum" in field and value > field["maximum"]:
            raise ContractError(f"field {field['path']!r} equals value exceeds maximum")


def load_contract(data: dict[str, Any]) -> dict[str, Any]:
    _ensure_finite_json(data)
    if not isinstance(data, dict):
        raise ContractError("contract must be a JSON object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ContractError("contract schema_version must be integer 1")
    mode = data.get("mode")
    if mode not in ("markdown", "json"):
        raise ContractError("contract mode must be markdown or json")
    allowed = CONTRACT_COMMON | ({"required_headings", "ordered", "allow_extra_headings"} if mode == "markdown" else {"fields", "allowed_root_keys"})
    unknown = set(data) - allowed
    if unknown:
        raise ContractError(f"unknown or mode-incompatible contract keys: {', '.join(sorted(unknown))}")
    _nonempty(data.get("id"), "contract id")
    _nonempty(data.get("description"), "contract description")
    patterns = data.get("forbidden_patterns")
    if not isinstance(patterns, list):
        raise ContractError("forbidden_patterns must be an array")
    pattern_ids = set()
    normalized_patterns = []
    for index, item in enumerate(patterns):
        if not isinstance(item, dict) or set(item) - {"id", "pattern", "ignore_case"}:
            raise ContractError(f"forbidden_patterns[{index}] has invalid keys or is not an object")
        pid = _nonempty(item.get("id"), f"forbidden_patterns[{index}].id")
        pattern = item.get("pattern")
        if not isinstance(pattern, str):
            raise ContractError(f"forbidden_patterns[{index}].pattern must be a string")
        if pid in pattern_ids:
            raise ContractError(f"duplicate forbidden pattern id: {pid}")
        pattern_ids.add(pid)
        ignore_case = item.get("ignore_case", False)
        if type(ignore_case) is not bool:
            raise ContractError(f"pattern {pid!r} ignore_case must be boolean")
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            raise ContractError(f"invalid regex for pattern {pid!r}: {exc}") from exc
        normalized_patterns.append({"id": pid, "pattern": pattern, "ignore_case": ignore_case, "_regex": regex})
    result = dict(data)
    result["forbidden_patterns"] = normalized_patterns
    if mode == "markdown":
        headings = data.get("required_headings")
        if not isinstance(headings, list):
            raise ContractError("required_headings must be an array")
        seen = set()
        for heading in headings:
            name = _nonempty(heading, "required heading")
            key = " ".join(name.strip().casefold().split())
            if key in seen:
                raise ContractError(f"duplicate required heading: {heading}")
            seen.add(key)
        for key, default in (("ordered", True), ("allow_extra_headings", True)):
            val = data.get(key, default)
            if type(val) is not bool:
                raise ContractError(f"{key} must be boolean")
            result[key] = val
    else:
        fields = data.get("fields")
        if not isinstance(fields, list):
            raise ContractError("fields must be an array")
        seen_paths = set()
        normalized_fields = []
        for index, raw_field in enumerate(fields):
            if not isinstance(raw_field, dict):
                raise ContractError(f"fields[{index}] must be an object")
            unknown_field = set(raw_field) - FIELD_KEYS
            if unknown_field:
                raise ContractError(f"fields[{index}] has unknown keys: {', '.join(sorted(unknown_field))}")
            field = dict(raw_field)
            field["path"] = _nonempty(field.get("path"), f"fields[{index}].path") if field.get("path") != "" else ""
            _validate_pointer(field["path"])
            if field["path"] in seen_paths:
                raise ContractError(f"duplicate field path: {field['path']!r}")
            seen_paths.add(field["path"])
            if not isinstance(field.get("type"), str) or field.get("type") not in FIELD_TYPES:
                raise ContractError(f"fields[{index}].type must be one of {', '.join(sorted(FIELD_TYPES))}")
            field.setdefault("required", True)
            _constraints(field)
            normalized_fields.append(field)
        result["fields"] = normalized_fields
        if "allowed_root_keys" in data:
            keys = data["allowed_root_keys"]
            if not isinstance(keys, list) or any(not isinstance(k, str) or not k for k in keys):
                raise ContractError("allowed_root_keys must be an array of nonempty strings")
            if len(set(keys)) != len(keys):
                raise ContractError("allowed_root_keys contains duplicates")
    return result


def extract_headings(text: str) -> list[dict[str, Any]]:
    headings = []
    for line_no, line in _visible_lines(text):
        match = re.match(r"^\s{0,3}(#{1,6})(?:[ \t]+|$)(.*)$", line)
        if not match:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        headings.append({"level": len(match.group(1)), "text": title, "normalized": " ".join(title.casefold().split()), "line": line_no})
    return headings


def _visible_lines(text: str):
    """Yield lines outside Markdown fences, honoring the opening run length."""
    opened: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if opened:
            if marker and marker.group(1)[0] == opened[0] and len(marker.group(1)) >= opened[1] and not marker.group(2).strip():
                opened = None
            continue
        if marker:
            opened = (marker.group(1)[0], len(marker.group(1)))
            continue
        yield number, line


def resolve_pointer(value: Any, pointer: str) -> tuple[bool, Any]:
    tokens = _validate_pointer(pointer)
    current = value
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if not re.fullmatch(r"0|[1-9]\d*", token):
                return False, None
            index = int(token)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def _excerpt(value: Any) -> dict[str, Any]:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        rendered = repr(value)
    truncated = len(rendered) > 120
    return {"type": "null" if value is None else "boolean" if type(value) is bool else "integer" if type(value) is int else "number" if type(value) is float else "string" if isinstance(value, str) else "array" if isinstance(value, list) else "object", "preview": rendered[:117] + "..." if truncated else rendered, "truncated": truncated}


def _violation(rule_id: str, kind: str, message: str, location: dict[str, Any], expected: Any = None, actual: Any = None, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"rule_id": rule_id, "kind": kind, "message": message, "location": location}
    if expected is not None:
        result["expected"] = expected
    if actual is not None:
        result["actual"] = actual
    result.update(extra)
    return result


def _check_patterns(contract: dict[str, Any], text: str) -> list[dict[str, Any]]:
    violations = []
    for pattern in contract["forbidden_patterns"]:
        regex = pattern["_regex"]
        matches = []
        total = 0
        for match in regex.finditer(text):
            total += 1
            if len(matches) < 100:
                matches.append(match)
        for match in matches:
            before = text[:match.start()]
            line = before.count("\n") + 1
            last_newline = before.rfind("\n")
            col = match.start() - last_newline
            literal = match.group(0)
            violations.append(_violation(pattern["id"], "forbidden_pattern", f"Forbidden pattern {pattern['id']!r} matched output text.",
                                          {"line": line, "column": col}, {"pattern": pattern["pattern"]},
                                          {"text": literal[:120], "truncated": len(literal) > 120}, match_count=total, truncated=total > 100))
    return violations


def _check_markdown(contract: dict[str, Any], text: str) -> list[dict[str, Any]]:
    headings = extract_headings(text)
    required = contract["required_headings"]
    required_norms = [" ".join(h.strip().casefold().split()) for h in required]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for heading in headings:
        by_name.setdefault(heading["normalized"], []).append(heading)
    violations = []
    for original, normalized in zip(required, required_norms):
        seen = by_name.get(normalized, [])
        if not seen:
            violations.append(_violation("required_headings", "missing_heading", f"Required heading {original!r} is missing.", {}, {"heading": original}))
        elif len(seen) > 1:
            violations.append(_violation("required_headings", "duplicate_heading", f"Required heading {original!r} appears more than once.",
                                          {"lines": [h["line"] for h in seen]}, {"heading": original}, {"count": len(seen)}))
    if contract["ordered"]:
        # Explain order using the actual textual sequence and configured sequence.
        seen_required: set[str] = set()
        actual_in_text = []
        actual_headings = []
        for heading in headings:
            name = heading["normalized"]
            if name in required_norms and name not in seen_required:
                actual_in_text.append(name)
                actual_headings.append(heading)
                seen_required.add(name)
        positions = [required_norms.index(name) for name in actual_in_text]
        if any(positions[i] > positions[i + 1] for i in range(len(positions) - 1)):
            violations.append(_violation("required_headings", "heading_order", "Required headings appear out of contract order.",
                                          {"lines": [h["line"] for h in actual_headings]},
                                          {"sequence": required}, {"sequence": [next(h["text"] for h in headings if h["normalized"] == name) for name in actual_in_text]}))
    if not contract["allow_extra_headings"]:
        allowed = set(required_norms)
        for heading in headings:
            if heading["normalized"] not in allowed:
                violations.append(_violation("required_headings", "unexpected_heading", f"Heading {heading['text']!r} is not allowed by this contract.",
                                              {"line": heading["line"]}, {"one of": required}, {"heading": heading["text"]}))
    return violations


def _check_json_fields(contract: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    violations = []
    if "allowed_root_keys" in contract:
        if not isinstance(value, dict):
            violations.append(_violation("allowed_root_keys", "root_type", "Allowed root keys requires a JSON object.", {"path": ""}, {"type": "object"}, _excerpt(value)))
        else:
            allowed = set(contract["allowed_root_keys"])
            for key in sorted(value.keys() - allowed):
                violations.append(_violation("allowed_root_keys", "unexpected_root_key", f"Unexpected root key {key!r}.", {"path": "/" + key.replace("~", "~0").replace("/", "~1")}, {"allowed": contract["allowed_root_keys"]}, {"key": key}))
    for field in contract["fields"]:
        path, kind = field["path"], field["type"]
        exists, actual = resolve_pointer(value, path)
        rule = "field:" + path
        if not exists:
            if field["required"]:
                violations.append(_violation(rule, "required_field", f"Required JSON field at {path or '<root>'} is absent.", {"path": path}, {"type": kind}))
            continue
        if not _matches_type(actual, kind):
            violations.append(_violation(rule, "field_type", f"JSON field at {path or '<root>'} has the wrong type.", {"path": path}, {"type": kind}, _excerpt(actual)))
            continue
        if "equals" in field and not _equal(actual, field["equals"], kind == "number"):
            violations.append(_violation(rule, "field_equals", f"JSON field at {path or '<root>'} does not equal its required value.", {"path": path}, {"equals": field["equals"]}, _excerpt(actual)))
        if "enum" in field and not any(_equal(actual, item, kind == "number") for item in field["enum"]):
            violations.append(_violation(rule, "field_enum", f"JSON field at {path or '<root>'} is not an allowed value.", {"path": path}, {"enum": field["enum"]}, _excerpt(actual)))
        if "min_length" in field or "max_length" in field:
            size = len(actual)
            if "min_length" in field and size < field["min_length"]:
                violations.append(_violation(rule, "min_length", f"JSON field at {path or '<root>'} is too short.", {"path": path}, {"min_length": field["min_length"]}, {"length": size}))
            if "max_length" in field and size > field["max_length"]:
                violations.append(_violation(rule, "max_length", f"JSON field at {path or '<root>'} is too long.", {"path": path}, {"max_length": field["max_length"]}, {"length": size}))
        if kind in {"integer", "number"}:
            if "minimum" in field and actual < field["minimum"]:
                violations.append(_violation(rule, "minimum", f"JSON field at {path or '<root>'} is below its minimum.", {"path": path}, {"minimum": field["minimum"]}, _excerpt(actual)))
            if "maximum" in field and actual > field["maximum"]:
                violations.append(_violation(rule, "maximum", f"JSON field at {path or '<root>'} exceeds its maximum.", {"path": path}, {"maximum": field["maximum"]}, _excerpt(actual)))
    return violations


def validate_output(contract: dict[str, Any], text: str) -> dict[str, Any]:
    normalized = load_contract(contract)
    if not isinstance(text, str):
        raise ContractError("output text must be a string")
    violations = _check_patterns(normalized, text)
    if normalized["mode"] == "markdown":
        violations.extend(_check_markdown(normalized, text))
    else:
        try:
            value = json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant, parse_float=_strict_float)
        except (json.JSONDecodeError, ValueError) as exc:
            line = getattr(exc, "lineno", text.count("\n") + 1)
            col = getattr(exc, "colno", 1)
            violations.append(_violation("json_syntax", "invalid_json", f"Output is not valid JSON: {exc}.", {"line": line, "column": col}))
        else:
            violations.extend(_check_json_fields(normalized, value))
    order = {p["id"]: i for i, p in enumerate(normalized["forbidden_patterns"])}
    base = len(order)
    if normalized["mode"] == "markdown":
        order["required_headings"] = base
    else:
        order.update({"field:" + f["path"]: base + i for i, f in enumerate(normalized["fields"])})
        if "allowed_root_keys" in normalized:
            order["allowed_root_keys"] = base + len(normalized["fields"])
    violations.sort(key=lambda v: (order.get(v["rule_id"], base + 1000), v["location"].get("line", 0),
                                   v["location"].get("column", 0), v["location"].get("path", ""), v["kind"]))
    limitations = ["Structural conformance checks do not establish truth, completeness, safety, or reasoning quality.",
                   "Forbidden regular expressions are trusted contract input and are not sandboxed."]
    if normalized["mode"] == "markdown":
        limitations.append("Heading checks recognize ATX headings outside fenced code blocks; Setext and HTML headings are ignored.")
        limitations.append("Forbidden patterns scan all output text, including fenced code blocks.")
    report = {"schema_version": 1, "contract_id": normalized["id"],
              "contract_sha256": hashlib.sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
              "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "mode": normalized["mode"],
              "valid": not violations, "checked_rules": [p["id"] for p in normalized["forbidden_patterns"]], "violations": violations,
              "limitations": limitations}
    if normalized["mode"] == "markdown":
        report["checked_rules"].append("required_headings")
    else:
        report["checked_rules"].extend("field:" + f["path"] for f in normalized["fields"])
        if "allowed_root_keys" in normalized:
            report["checked_rules"].append("allowed_root_keys")
    return report


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number {value} is not allowed")


def render_markdown(report: dict[str, Any]) -> str:
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 1 or not isinstance(report.get("violations"), list):
        raise ContractError("report must be a schema_version 1 report")
    lines = [f"# Validation: {'passed' if report.get('valid') else 'violations found'}", "",
             f"Contract: `{report.get('contract_id', '')}`", f"Mode: `{report.get('mode', '')}`",
             f"Output SHA-256: `{report.get('output_sha256', '')}`", ""]
    if report["violations"]:
        for item in report["violations"]:
            loc = item.get("location", {})
            if "path" in loc:
                location = f"JSON Pointer `{loc['path'] or '<root>'}`"
            elif "line" in loc:
                location = f"line {loc['line']}, column {loc['column']}"
            elif "lines" in loc:
                location = "lines " + ", ".join(str(x) for x in loc["lines"])
            else:
                location = "no source location"
            lines.extend((f"## {item['kind']} ({item['rule_id']})", "", f"{item['message']} Location: {location}."))
            if "expected" in item:
                lines.append("- Expected: `" + json.dumps(item["expected"], ensure_ascii=False, sort_keys=True) + "`")
            if "actual" in item:
                lines.append("- Observed: `" + json.dumps(item["actual"], ensure_ascii=False, sort_keys=True) + "`")
            if "match_count" in item:
                lines.append(f"- Matches: {item['match_count']} (display truncated: {str(item['truncated']).lower()})")
            lines.append("")
    else:
        lines.append("All configured structural checks passed. This does not certify the output's truth or quality.")
    lines.extend(("## Limitations", ""))
    lines.extend(f"- {text}" for text in report.get("limitations", []))
    return "\n".join(lines).rstrip() + "\n"

