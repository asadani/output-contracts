import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_help_version_inspect_good_bad_and_invalid_contract(self):
        help_result = subprocess.run([sys.executable, "-m", "output_contracts", "--help"], cwd=REPO, text=True, capture_output=True)
        version = subprocess.run([sys.executable, "-m", "output_contracts", "--version"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertEqual(version.stdout.strip(), "output-contracts 0.1.0")
        inspected = subprocess.run([sys.executable, "-m", "output_contracts", "inspect", "fixtures/handoff-contract.json"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["required_headings"][0], "Summary")
        good = subprocess.run([sys.executable, "-m", "output_contracts", "validate", "fixtures/result-contract.json", "fixtures/result-good.json"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout)["valid"])
        heading_bad = subprocess.run([sys.executable, "-m", "output_contracts", "validate", "fixtures/handoff-contract.json", "fixtures/handoff-bad.md"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(heading_bad.returncode, 1)
        self.assertIn("heading_order", {v["kind"] for v in json.loads(heading_bad.stdout)["violations"]})
        heading_good = subprocess.run([sys.executable, "-m", "output_contracts", "validate", "fixtures/handoff-contract.json", "fixtures/handoff-good.md", "--format", "markdown"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(heading_good.returncode, 0, heading_good.stderr)
        self.assertIn("All configured structural checks passed", heading_good.stdout)
        bad = subprocess.run([sys.executable, "-m", "output_contracts", "validate", "fixtures/result-contract.json", "fixtures/result-bad.json", "--format", "markdown"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("field_type", bad.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "contract.json"
            invalid.write_text('{"schema_version": true}', encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "output_contracts", "validate", str(invalid), "fixtures/result-good.json"], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)
            huge_contract = Path(tmp) / "huge-contract.json"
            huge_contract.write_text('{"schema_version":1,"id":"c","description":"c","mode":"json","forbidden_patterns":[],"fields":[{"path":"/x","type":"number","minimum":1e999}]}', encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "output_contracts", "validate", str(huge_contract), "fixtures/result-good.json"], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)
            malformed_output = Path(tmp) / "output.json"
            malformed_output.write_text('{"x":NaN}', encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "output_contracts", "validate", "fixtures/result-contract.json", str(malformed_output)], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["violations"][0]["kind"], "invalid_json")
            huge_output = Path(tmp) / "huge.json"
            huge_output.write_text('{"nested":{"value":1e999}}', encoding="utf-8")
            root_only_contract = Path(tmp) / "root-contract.json"
            root_only_contract.write_text(json.dumps({"schema_version": 1, "id": "root", "description": "root", "mode": "json", "forbidden_patterns": [], "fields": []}), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "output_contracts", "validate", str(root_only_contract), str(huge_output)], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["violations"][0]["kind"], "invalid_json")

            contract_bytes = (REPO / "fixtures/result-contract.json").read_bytes()
            output_bytes = (REPO / "fixtures/result-good.json").read_bytes()
            source_contract = Path(tmp) / "same-contract.json"
            source_output = Path(tmp) / "same-output.json"
            source_contract.write_bytes(contract_bytes)
            source_output.write_bytes(output_bytes)
            alias = Path(tmp) / "output-alias.json"
            alias.symlink_to(source_output)
            for destination in (str(source_contract), str(alias)):
                result = subprocess.run([sys.executable, "-m", "output_contracts", "validate", str(source_contract), str(source_output), "--out", destination], cwd=REPO, text=True, capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(source_contract.read_bytes(), contract_bytes)
                self.assertEqual(source_output.read_bytes(), output_bytes)


if __name__ == "__main__":
    unittest.main()
