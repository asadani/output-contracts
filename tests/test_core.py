import json
import unittest

from output_contracts.core import (ContractError, extract_headings,
                                   load_contract, resolve_pointer,
                                   validate_output)


def markdown_contract(**changes):
    value = {"schema_version": 1, "id": "m", "description": "markdown", "mode": "markdown",
             "forbidden_patterns": [{"id": "ban", "pattern": "bad", "ignore_case": True}],
             "required_headings": ["Summary", "Evidence", "Unresolved questions", "Next steps"]}
    value.update(changes)
    return value


def json_contract(**changes):
    value = {"schema_version": 1, "id": "j", "description": "json", "mode": "json", "forbidden_patterns": [],
             "fields": [{"path": "/result/count", "type": "integer", "minimum": 0},
                        {"path": "/result/status", "type": "string", "enum": ["ok", "failed"]}]}
    value.update(changes)
    return value


class ContractCoreTests(unittest.TestCase):
    def test_headings_fences_order_duplicates_missing_extra_and_pattern_locations(self):
        text = "# Next steps\n\n# Summary ##\n\n```md\n# Evidence\n```\n# Evidence\nBAD and bad\n# Extra\n"
        headings = extract_headings(text)
        self.assertEqual([h["text"] for h in headings], ["Next steps", "Summary", "Evidence", "Extra"])
        contract = markdown_contract(allow_extra_headings=False)
        report = validate_output(contract, text)
        kinds = [v["kind"] for v in report["violations"]]
        self.assertIn("heading_order", kinds)
        self.assertIn("missing_heading", kinds)
        self.assertIn("unexpected_heading", kinds)
        self.assertEqual(sum(v["kind"] == "forbidden_pattern" for v in report["violations"]), 2)
        first = next(v for v in report["violations"] if v["kind"] == "forbidden_pattern")
        self.assertEqual(first["location"], {"line": 9, "column": 1})

    def test_duplicate_heading_and_order_switch(self):
        text = "# Summary\n# Evidence\n# Evidence\n# Unresolved questions\n# Next steps\n"
        report = validate_output(markdown_contract(ordered=False), text)
        kinds = [v["kind"] for v in report["violations"]]
        self.assertIn("duplicate_heading", kinds)
        self.assertNotIn("heading_order", kinds)
        self.assertTrue(any(v["kind"] == "duplicate_heading" and v["location"]["lines"] == [2, 3] for v in report["violations"]))
        duplicate_at_end = validate_output(markdown_contract(), "# Summary\n# Evidence\n# Unresolved questions\n# Next steps\n# Summary\n")
        self.assertNotIn("heading_order", {v["kind"] for v in duplicate_at_end["violations"]})

    def test_long_fence_is_not_closed_by_shorter_run(self):
        headings = extract_headings("````md\n# Hidden\n```\n# Still hidden\n````\n# Visible\n")
        self.assertEqual([h["text"] for h in headings], ["Visible"])

    def test_pointer_escapes_arrays_and_root_scalars(self):
        value = {"a/b": {"~key": ["x", 7]}}
        self.assertEqual(resolve_pointer(value, "/a~1b/~0key/1"), (True, 7))
        self.assertEqual(resolve_pointer(value, "/a~1b/~0key/01"), (False, None))
        self.assertEqual(resolve_pointer(5, ""), (True, 5))
        with self.assertRaises(ContractError):
            resolve_pointer(value, "/a~2b")
        with self.assertRaises(ContractError):
            load_contract(json_contract(fields=[{"path": "/x/-", "type": "string"}]))

    def test_field_types_enum_bounds_required_null_and_boolean_distinction(self):
        contract = json_contract(fields=[
            {"path": "/count", "type": "integer", "minimum": 0},
            {"path": "/floatCount", "type": "integer", "required": False},
            {"path": "/must", "type": "boolean", "required": True},
            {"path": "/nil", "type": "null", "required": True},
            {"path": "/status", "type": "string", "enum": ["ok", "failed"]},
            {"path": "/numbers", "type": "number", "enum": [1, 2.0]}
        ])
        report = validate_output(contract, '{"count": true, "nil": null, "status": "ok", "numbers": 1.0}')
        self.assertEqual([v["kind"] for v in report["violations"]], ["field_type", "required_field"])
        report = validate_output(contract, '{"count": 1, "must": true, "nil": null, "status": "ok", "numbers": 1}')
        self.assertTrue(report["valid"])

    def test_json_syntax_duplicate_keys_nan_and_pointer_contract_errors(self):
        c = json_contract(fields=[])
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{'):
            report = validate_output(c, text)
            self.assertEqual([v["kind"] for v in report["violations"]], ["invalid_json"])
        root_only = json_contract(fields=[])
        self.assertEqual(validate_output(root_only, '{"nested":{"value":1e999}}')["violations"][0]["kind"], "invalid_json")
        with self.assertRaises(ContractError):
            load_contract(json_contract(fields=[{"path": "/x", "type": "number", "minimum": float("inf")}]))
        for path in ("bad", "/x~2y"):
            with self.assertRaises(ContractError):
                load_contract(json_contract(fields=[{"path": path, "type": "string"}]))

    def test_contract_rejects_versions_unhashable_enum_and_incompatible_rules(self):
        for version in (True, 1.0, "1"):
            with self.assertRaises(ContractError):
                load_contract(markdown_contract(schema_version=version))
        with self.assertRaises(ContractError):
            load_contract(json_contract(fields=[{"path": "/x", "type": ["integer"]}]))
        with self.assertRaises(ContractError):
            load_contract(json_contract(fields=[{"path": "/x", "type": "string", "enum": [["not a string"]]}]))
        with self.assertRaises(ContractError):
            load_contract(json_contract(fields=[{"path": "/x", "type": "integer", "minimum": 5, "maximum": 1}]))

    def test_forbidden_match_display_cap_and_repeatability(self):
        contract = {"schema_version": 1, "id": "p", "description": "cap", "mode": "markdown", "forbidden_patterns": [{"id": "x", "pattern": "x"}], "required_headings": []}
        text = "x " * 105
        report = validate_output(contract, text)
        self.assertEqual(len(report["violations"]), 100)
        self.assertEqual(report["violations"][0]["match_count"], 105)
        self.assertTrue(report["violations"][0]["truncated"])
        self.assertEqual(report, validate_output(contract, text))
        empty_pattern = dict(contract, forbidden_patterns=[{"id": "empty", "pattern": ""}])
        zero_width = validate_output(empty_pattern, "abc")
        self.assertEqual(len(zero_width["violations"]), 4)


if __name__ == "__main__":
    unittest.main()
