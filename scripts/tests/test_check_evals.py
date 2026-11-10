"""Tests for scripts/check_evals.py (pinned contract).

Every case drives the real script through subprocess so exit codes are real.
Fixtures are disposable copies under tempfile; each copy is written to
<tmp>/evals.json and passed positionally. Path-reference cases rely on the
checker resolving refs against the real bundle (script-location rule), so a
valid fixture cites existing bundle files and a broken one cites
scripts/foo.py, which never exists.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check_evals.py"

VALID_EVAL = {
    "id": "sample-eval",
    "prompt": "write a song about the sea",
    "expected_behavior": "Build the style prompt with scripts/format_style_prompt.py.",
    "success_criteria": [
        "Style prompt is a single line under 200 chars",
        "Template filled per assets/song-template.md",
    ],
}


def spec(evals: list[object]) -> dict[str, object]:
    return {"_note": "fixture", "evals": evals}


class EvalFixture:
    """Disposable spec copy: <root>/evals.json, run via positional path."""

    def __init__(self, root: Path) -> None:
        self.path = root / "evals.json"

    def write(self, data: dict[str, object]) -> None:
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def write_raw(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    def run(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.path), *extra_args],
            capture_output=True,
            text=True,
        )


class CheckEvalsTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.fx = EvalFixture(Path(tmp.name))

    def run_with(
        self, evals: list[object], *extra_args: str
    ) -> subprocess.CompletedProcess[str]:
        self.fx.write(spec(evals))
        return self.fx.run(*extra_args)

    # --- valid spec -> exit 0 ------------------------------------------------
    def test_valid_spec_exits_zero(self) -> None:
        proc = self.run_with([VALID_EVAL, {**VALID_EVAL, "id": "another-eval"}])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    # --- duplicate id -> exit 1 ----------------------------------------------
    def test_duplicate_id_exits_1(self) -> None:
        proc = self.run_with([VALID_EVAL, {**VALID_EVAL, "id": VALID_EVAL["id"]}])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("duplicate id: sample-eval", proc.stdout)

    # --- empty success_criteria -> exit 1 ------------------------------------
    def test_empty_success_criteria_exits_1(self) -> None:
        broken = {**VALID_EVAL, "success_criteria": []}
        proc = self.run_with([broken])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("success_criteria", proc.stdout)

    # --- non-string success_criteria entry -> exit 1 --------------------------
    def test_non_string_success_criteria_entry_exits_1(self) -> None:
        broken = {**VALID_EVAL, "success_criteria": ["ok criterion", 42]}
        proc = self.run_with([broken])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("success_criteria[1]", proc.stdout)

    # --- referenced scripts/foo.py missing -> exit 1 ---------------------------
    def test_missing_referenced_script_exits_1(self) -> None:
        broken = {
            **VALID_EVAL,
            "expected_behavior": "Run scripts/foo.py on the lyrics.",
        }
        proc = self.run_with([broken])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("scripts/foo.py", proc.stdout)

    # --- malformed JSON -> exit 2 ---------------------------------------------
    def test_malformed_json_exits_2(self) -> None:
        self.fx.write_raw("{definitely not json")
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip(), "expected an error message on stderr")

    # --- --json parses and names the offending id ------------------------------
    def test_json_output_parses_and_names_offending_id(self) -> None:
        proc = self.run_with(
            [VALID_EVAL, {**VALID_EVAL, "id": VALID_EVAL["id"]}], "--json"
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        data = json.loads(proc.stdout)  # stdout must be pure, valid JSON
        self.assertEqual(data["exit_code"], 1)
        self.assertGreaterEqual(len(data["findings"]), 1)
        self.assertTrue(
            any(f["id"] == "sample-eval" and f["field"] == "id" for f in data["findings"]),
            data["findings"],
        )

    def test_empty_evals_list_exits_2(self) -> None:
        self.fx.write(spec([]))
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("list is empty", proc.stderr)


if __name__ == "__main__":
    unittest.main()
