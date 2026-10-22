from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import ContractError, load_contract, render_markdown, validate_output


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ContractError(f"non-finite JSON constant {value} is not allowed")


def _strict_float(token: str) -> float:
    import math
    value = float(token)
    if not math.isfinite(value):
        raise ContractError(f"non-finite JSON number {token} is not allowed")
    return value


def _json_file(path: str) -> Any:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"cannot read UTF-8 file {path}: {exc}") from exc
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_strict_float)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def _output_text(path: str) -> str:
    try:
        return Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"cannot read UTF-8 output {path}: {exc}") from exc


def _write(path: str | None, content: str) -> None:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)


def _refuse_input_overwrite(output_path: str, input_paths: list[str]) -> None:
    destination = Path(output_path).resolve(strict=False)
    for input_path in input_paths:
        source = Path(input_path).resolve(strict=True)
        if destination == source:
            raise ContractError(f"--out resolves to an input file and would overwrite it: {input_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="output-contracts", description="Validate outputs against explicit structural contracts.")
    parser.add_argument("--version", action="version", version=f"output-contracts {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("validate", help="validate one output against a contract")
    p.add_argument("contract")
    p.add_argument("output")
    p.add_argument("--format", choices=("json", "markdown"), default="json")
    p.add_argument("--out")
    p = commands.add_parser("inspect", help="show the normalized rules in a contract")
    p.add_argument("contract")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raw_contract = _json_file(args.contract)
        contract = load_contract(raw_contract)
        if args.command == "inspect":
            result = {"schema_version": 1, "id": contract["id"], "description": contract["description"], "mode": contract["mode"],
                      "forbidden_patterns": [{"id": p["id"], "pattern": p["pattern"], "ignore_case": p["ignore_case"]} for p in contract["forbidden_patterns"]]}
            if contract["mode"] == "markdown":
                result.update(required_headings=contract["required_headings"], ordered=contract["ordered"], allow_extra_headings=contract["allow_extra_headings"])
            else:
                result["fields"] = [{k: v for k, v in f.items() if k != "_regex"} for f in contract["fields"]]
                if "allowed_root_keys" in contract:
                    result["allowed_root_keys"] = contract["allowed_root_keys"]
            _write(None, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            return 0
        text = _output_text(args.output)
        report = validate_output(raw_contract, text)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.format == "json" else render_markdown(report)
        if args.out:
            _refuse_input_overwrite(args.out, [args.contract, args.output])
        _write(args.out, rendered)
        return 0 if report["valid"] else 1
    except (ContractError, OSError, ValueError) as exc:
        print(f"output-contracts: error: {exc}", file=sys.stderr)
        return 2

