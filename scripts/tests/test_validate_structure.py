"""Tests for scripts/validate_structure.py (pinned contract).

CLI cases drive the real script through subprocess so exit codes are real:
0 = PASS (warnings allowed), 1 = structure errors (missing [Chorus] or an
empty non-instrumental section), 2 = usage problem. Pure helpers
(parse_sections, is_chorus, is_instrumental, TAG_RE) are called directly
where their behavior is the contract. Input modes: positional file or
stdin only -- this CLI offers no --text and no --json, which the
usage-error cases pin deliberately.
"""

import os
import pty
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "validate_structure.py"
sys.path.insert(0, str(SCRIPT.parent))

import validate_structure  # noqa: E402


def run_cli(
    *args: str, cwd: Path | None = None, stdin: str | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        input=stdin,
        cwd=None if cwd is None else str(cwd),
    )


class ValidSheetTests(unittest.TestCase):
    # --- pass 1: valid sheet via stdin -> exit 0, PASS, no findings ----------
    def test_valid_sheet_stdin_exits_0_pass(self) -> None:
        proc = run_cli(stdin="[Verse]\nline one\n[Chorus]\nbig hook\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Sections found: 2", proc.stdout)
        self.assertIn("Result: PASS", proc.stdout)
        self.assertNotIn("ERROR", proc.stdout)
        self.assertNotIn("WARNING", proc.stdout)

    # --- pass 2: positional file, other cwd (cwd-independence pin) -----------
    def test_positional_file_from_other_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sheet = tmp_path / "song.txt"
            sheet.write_text(
                "[Verse]\nline one\n[Chorus]\nbig hook\n", encoding="utf-8"
            )
            proc = run_cli(str(sheet), cwd=tmp_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Result: PASS", proc.stdout)


class ChorusPresenceTests(unittest.TestCase):
    # --- chorus 1: no chorus anywhere -> exit 1 with the pinned error --------
    def test_missing_chorus_exit_1(self) -> None:
        proc = run_cli(stdin="[Verse]\nonly verse lyrics\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn(
            "ERROR: no [Chorus] section found (at least one is required)", proc.stdout
        )
        self.assertIn("Result: FAIL (structure errors)", proc.stdout)

    # --- chorus 2: [Pre-Chorus] does not satisfy chorus presence -------------
    def test_pre_chorus_is_not_a_chorus(self) -> None:
        proc = run_cli(stdin="[Verse]\nv\n[Pre-Chorus]\np\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("no [Chorus] section found", proc.stdout)

    # --- chorus 3: numbered [Chorus 2] counts as a chorus --------------------
    def test_numbered_chorus_counts(self) -> None:
        proc = run_cli(stdin="[Chorus 2]\nbig hook\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Result: PASS", proc.stdout)


class EmptySectionTests(unittest.TestCase):
    # --- empty 1: sung section with no lines under it -> exit 1 --------------
    def test_empty_sung_section_exit_1(self) -> None:
        proc = run_cli(stdin="[Verse]\n[Chorus]\nbig hook\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn(
            "ERROR: section [Verse] is empty (no lyric lines under it)", proc.stdout
        )

    # --- empty 2: blank lines under a tag do not count as lyrics -------------
    def test_blank_lines_do_not_count_as_lyrics(self) -> None:
        proc = run_cli(stdin="[Verse]\n\n\n[Chorus]\nbig hook\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("section [Verse] is empty", proc.stdout)

    # --- empty 3: instrumental sections are allowed to be empty --------------
    def test_instrumental_empty_section_allowed(self) -> None:
        proc = run_cli(stdin="[Verse]\nv\n[Chorus]\nc\n[Instrumental Break]\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(
            "[Instrumental Break] - 0 line(s) (instrumental)", proc.stdout
        )
        self.assertNotIn("is empty", proc.stdout)

    # --- empty 4: several findings are all reported, single exit 1 -----------
    def test_multiple_errors_all_reported(self) -> None:
        proc = run_cli(stdin="[Verse]\n")  # empty verse AND no chorus
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertEqual(proc.stdout.count("ERROR:"), 2, proc.stdout)


class WarningTests(unittest.TestCase):
    # --- warn 1: verse/chorus counts differ by > 1 -> warning, exit 0 --------
    def test_verse_chorus_imbalance_warns_exit_0(self) -> None:
        text = "[Verse]\nv1\n[Verse 2]\nv2\n[Verse 3]\nv3\n[Chorus]\nc1\n"
        proc = run_cli(stdin=text)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(
            "WARNING: 3 [Verse] vs 1 [Chorus]: counts differ by more than 1",
            proc.stdout,
        )
        self.assertIn("Result: PASS", proc.stdout)

    # --- warn 2: a difference of exactly 1 stays silent -----------------------
    def test_verse_chorus_diff_of_one_no_warning(self) -> None:
        text = "[Verse]\nv1\n[Verse 2]\nv2\n[Chorus]\nc1\n"
        proc = run_cli(stdin=text)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("WARNING", proc.stdout)

    # --- warn 3: stray lines before the first tag -> warning, exit 0 ----------
    def test_preamble_lines_warn_exit_0(self) -> None:
        proc = run_cli(stdin="stray opening line\n[Verse]\nv\n[Chorus]\nc\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(
            "WARNING: 1 lyric line(s) appear before the first section tag",
            proc.stdout,
        )
        self.assertIn("Lyric lines: 3", proc.stdout)  # preamble counts as a lyric line


class ReportShapeTests(unittest.TestCase):
    # --- shape 1: per-section listing and the 3.5s/line estimate -------------
    def test_section_listing_and_estimated_length(self) -> None:
        proc = run_cli(
            stdin="[Verse]\nline one\nline two\n[Chorus]\nbig hook\nbig hook again\n"
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Sections found: 2", proc.stdout)
        self.assertIn("[Verse] - 2 line(s)", proc.stdout)
        self.assertIn("[Chorus] - 2 line(s)", proc.stdout)
        self.assertIn(
            "Lyric lines: 4 | Estimated length @3.5s/line: 14s (~0:14)", proc.stdout
        )

    # --- shape 2: the estimate rolls over into minutes ------------------------
    def test_estimate_rolls_over_minutes(self) -> None:
        text = "[Verse]\n" + "v\n" * 10 + "[Chorus]\n" + "c\n" * 10
        proc = run_cli(stdin=text)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(
            "Lyric lines: 20 | Estimated length @3.5s/line: 70s (~1:10)", proc.stdout
        )


class UsageErrorTests(unittest.TestCase):
    # --- usage 1: unknown flag -> argparse exit 2 ------------------------------
    def test_unknown_flag_exit_2(self) -> None:
        proc = run_cli("--json", stdin="[Verse]\nv\n[Chorus]\nc\n")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized arguments", proc.stderr)

    # --- usage 2: --text is NOT an input mode of this CLI ---------------------
    def test_text_flag_not_supported_exit_2(self) -> None:
        proc = run_cli("--text", "[Verse]\nv\n[Chorus]\nc\n")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())

    # --- usage 3: no file and stdin is a tty -> exit 2 -------------------------
    def test_no_input_on_tty_exit_2(self) -> None:
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            stdin=slave,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("no input: pass a file or pipe lyrics via stdin", proc.stderr)

    # --- usage 5: unreadable file is a usage error, not "structure errors" ----
    def test_missing_file_exit_2(self) -> None:
        proc = run_cli("/no/such/lyrics.txt")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("cannot read /no/such/lyrics.txt", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    # --- usage 4: empty piped stdin is validated (no chorus), not exit 2 ------
    def test_empty_stdin_is_no_chorus_failure(self) -> None:
        proc = run_cli(stdin="")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("no [Chorus] section found", proc.stdout)


class ParseSectionsTests(unittest.TestCase):
    # --- parse 1: splits preamble, tags, and per-section lines -----------------
    def test_splits_preamble_tags_and_lines(self) -> None:
        sections, preamble = validate_structure.parse_sections(
            ["stray", "[Verse]", "v1", "", "[Chorus]", "c1"]
        )
        self.assertEqual(preamble, ["stray"])
        self.assertEqual([s["tag"] for s in sections], ["Verse", "Chorus"])
        self.assertEqual(sections[0]["lines"], ["v1", ""])
        self.assertEqual(sections[1]["lines"], ["c1"])

    # --- parse 2: blank preamble lines are dropped ------------------------------
    def test_blank_preamble_lines_dropped(self) -> None:
        sections, preamble = validate_structure.parse_sections(
            ["", "   ", "stray", "[Verse]", "v"]
        )
        self.assertEqual(preamble, ["stray"])

    # --- parse 3: a tag owns the whole line -- trailing text is a lyric line ----
    def test_tag_must_own_the_whole_line(self) -> None:
        sections, preamble = validate_structure.parse_sections(["[Chorus] words"])
        self.assertEqual(sections, [])
        self.assertEqual(preamble, ["[Chorus] words"])


class TagClassifierTests(unittest.TestCase):
    # --- classify 1: chorus semantics = prefix, case-insensitive ----------------
    def test_is_chorus_prefix_semantics(self) -> None:
        cases = [("Chorus", True), ("chorus 2", True), ("Pre-Chorus", False), ("Bridge", False)]
        for tag, expected in cases:
            with self.subTest(tag=tag):
                self.assertEqual(validate_structure.is_chorus(tag), expected)

    # --- classify 2: instrumental matches anywhere in the tag, any case ---------
    def test_is_instrumental_case_insensitive(self) -> None:
        cases = [
            ("Instrumental Break", True),
            ("instrumental solo", True),
            ("Break", False),
        ]
        for tag, expected in cases:
            with self.subTest(tag=tag):
                self.assertEqual(validate_structure.is_instrumental(tag), expected)

    # --- classify 3: TAG_RE is the shared lyric_lint convention ------------------
    def test_tag_re_matches_lyric_lint_convention(self) -> None:
        self.assertEqual(validate_structure.TAG_RE.pattern, r"^\s*\[([^\[\]]+)\]\s*$")


if __name__ == "__main__":
    unittest.main()
