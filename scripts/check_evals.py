#!/usr/bin/env python3
"""Structural checker for evals/evals.json (see scripts/check_freshness.py for the sibling CLI contract).

Validates the MACHINE-CONSUMED shape of the behavioral eval spec — never the
prose. For every eval case:

  - "id": non-empty string, unique across the file
  - "prompt": non-empty string
  - "expected_behavior": non-empty string
  - "success_criteria": non-empty list of non-empty strings
  - every path-like reference matching scripts/<name>.py or
    assets/<name>.<ext> inside expected_behavior or success_criteria must
    resolve to an existing file in the bundle

The "_note" key is ignored (top-level or per-eval). Any other unknown keys
are ignored too: this checker pins structure, not schema completeness.

Path references resolve against the skill root derived from THIS SCRIPT's
own location (parent of scripts/), not from the input file's location, so a
copy of evals.json elsewhere is still checked against this bundle's
scripts/ and assets/ — the same cwd-independent rule the sibling checkers
follow for their defaults.

Exit codes:
    0  no findings
    1  at least one structural finding
    2  usage error, file not readable, not valid JSON, or the top-level
       shape is unusable (not an object / "evals" missing, not a list, or empty)

Usage:
  python3 check_evals.py [file] [--json]     # default: <skill>/evals/evals.json
  cat evals.json | python3 check_evals.py -  # stdin via '-'
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

Finding = dict[str, str]

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = SKILL_ROOT / "evals" / "evals.json"

# scripts/<name>.py or assets/<name>.<ext>, name = path-safe chars/dots
PATH_RE = re.compile(r"\b(?:scripts/[\w./-]*\.py|assets/[\w./-]*\.[A-Za-z0-9]+)")


class EvalSpecError(Exception):
    """The spec file is missing, unreadable, or its top level is unusable."""


def load_spec(path: Path) -> dict[str, object]:
    """Read and parse the spec file (boundary parse; callers trust it)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvalSpecError(f"spec not readable: {path} ({exc})") from exc
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvalSpecError(f"spec is not valid JSON: {path} ({exc})") from exc
    if not isinstance(spec, dict):
        raise EvalSpecError(f"spec top level is not an object: {path}")
    return spec


def spec_evals(spec: dict[str, object]) -> list[object] | None:
    """The 'evals' list, or None when missing/not a list (unusable spec)."""
    evals = spec.get("evals")
    return evals if isinstance(evals, list) else None


def _string_findings(eval_id: str, field: str, value: object) -> list[Finding]:
    """One finding when `value` is not a non-empty string; else none."""
    if isinstance(value, str) and value.strip():
        return []
    return [{"id": eval_id, "field": field, "problem": "must be a non-empty string"}]


def _path_findings(eval_id: str, field: str, text: str) -> list[Finding]:
    """One finding per referenced scripts/* or assets/* path missing on disk."""
    findings: list[Finding] = []
    for ref in PATH_RE.findall(text):
        if (SKILL_ROOT / ref).exists():
            continue
        findings.append(
            {"id": eval_id, "field": field, "problem": f"referenced path does not exist: {ref}"}
        )
    return findings


def eval_findings(index: int, case: object, seen_ids: set[str]) -> list[Finding]:
    """All structural findings for one eval entry (never judges prose)."""
    findings: list[Finding] = []
    if not isinstance(case, dict):
        return [
            {
                "id": f"#{index}",
                "field": "(eval)",
                "problem": "entry is not an object",
            }
        ]
    eval_id = case.get("id")
    label = eval_id if isinstance(eval_id, str) and eval_id else f"#{index}"

    findings.extend(_string_findings(label, "id", eval_id))
    if isinstance(eval_id, str) and eval_id:
        if eval_id in seen_ids:
            findings.append(
                {"id": label, "field": "id", "problem": f"duplicate id: {eval_id}"}
            )
        else:
            seen_ids.add(eval_id)

    findings.extend(_string_findings(label, "prompt", case.get("prompt")))
    findings.extend(
        _string_findings(label, "expected_behavior", case.get("expected_behavior"))
    )

    criteria = case.get("success_criteria")
    if not isinstance(criteria, list) or not criteria:
        findings.append(
            {
                "id": label,
                "field": "success_criteria",
                "problem": "must be a non-empty list of non-empty strings",
            }
        )
    else:
        for pos, criterion in enumerate(criteria):
            findings.extend(
                _string_findings(label, f"success_criteria[{pos}]", criterion)
            )

    if isinstance(case.get("expected_behavior"), str):
        findings.extend(
            _path_findings(label, "expected_behavior", case["expected_behavior"])
        )
    if isinstance(criteria, list):
        for pos, criterion in enumerate(criteria):
            if isinstance(criterion, str):
                findings.extend(
                    _path_findings(label, f"success_criteria[{pos}]", criterion)
                )
    return findings


def all_findings(evals: list[object]) -> list[Finding]:
    """Every structural finding across the spec, in file order."""
    seen_ids: set[str] = set()
    findings: list[Finding] = []
    for index, case in enumerate(evals):
        findings.extend(eval_findings(index, case, seen_ids))
    return findings


def render(findings: list[Finding]) -> list[str]:
    """'id | field | problem' lines, one per finding."""
    return [f"{f['id']} | {f['field']} | {f['problem']}" for f in findings]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Structurally validate evals/evals.json (ids, fields, path references)."
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="path to evals.json (default: <skill>/evals/evals.json; '-' reads stdin)",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.file is not None and str(args.file) != "-":
        try:
            spec = load_spec(args.file)
        except EvalSpecError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    elif str(args.file) == "-":
        try:
            spec = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(f"ERROR: stdin is not valid JSON ({exc})", file=sys.stderr)
            return 2
        if not isinstance(spec, dict):
            print("ERROR: stdin top level is not an object", file=sys.stderr)
            return 2
    else:
        try:
            spec = load_spec(DEFAULT_FILE)
        except EvalSpecError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    evals = spec_evals(spec)
    if evals is None:
        print('ERROR: spec must have an "evals" list', file=sys.stderr)
        return 2
    if not evals:
        print('ERROR: spec "evals" list is empty (nothing to check)', file=sys.stderr)
        return 2

    findings = all_findings(evals)
    total = len(evals)
    exit_code = 1 if findings else 0

    if args.json:
        print(
            json.dumps(
                {
                    "evals": total,
                    "findings": findings,
                    "summary": {"evals": total, "findings": len(findings)},
                    "exit_code": exit_code,
                },
                indent=2,
            )
        )
        return exit_code

    for line in render(findings):
        print(line)
    print(f"{total} evals: {len(findings)} finding(s)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
