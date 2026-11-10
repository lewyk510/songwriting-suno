"""Tests for scripts/syllable_meter.py (pinned contract).

Every case drives the real script through subprocess so exit codes are real:
0 = all lines match --expect (or no --expect given), 1 = at least one line
misses the expected meter, 2 = usage problem (bad --expect / --lang value,
or no non-blank lyric lines). Word-level counting cases call the stable
syllables_en()/count_line() internals directly (lyric_lint.py imports this
module the same way). Input precedence pinned here: --text wins over the
positional file, which wins over stdin (note: lyric_lint.py is the other
way round -- each script pins its own real order). CJK characters count as
exactly 1 unit each under --lang auto/cjk and are ignored by --lang en.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "syllable_meter.py"
sys.path.insert(0, str(SCRIPT.parent))

import syllable_meter  # noqa: E402


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


class WordSyllableTests(unittest.TestCase):
    """Direct pins on the English heuristic (stable internal, min 1)."""

    # --- word 1: basic vowel-group counts ----------------------------------
    def test_basic_word_counts(self) -> None:
        counts = {w: syllable_meter.syllables_en(w) for w in
                  ("hello", "world", "tonight", "city", "into", "chasing")}
        self.assertEqual(
            counts, {"hello": 2, "world": 1, "tonight": 2, "city": 2,
                     "into": 2, "chasing": 2}
        )

    # --- word 2: silent trailing 'e' is subtracted --------------------------
    def test_silent_trailing_e_subtracted(self) -> None:
        self.assertEqual(syllable_meter.syllables_en("time"), 1)
        self.assertEqual(syllable_meter.syllables_en("cake"), 1)

    # --- word 3: -le/-ee/-ie endings keep their trailing 'e' ----------------
    def test_kept_e_endings_not_subtracted(self) -> None:
        self.assertEqual(syllable_meter.syllables_en("smile"), 2)  # -le kept
        self.assertEqual(syllable_meter.syllables_en("movie"), 2)  # -ie kept
        self.assertEqual(syllable_meter.syllables_en("free"), 1)   # -ee kept

    # --- word 4: count floors at 1, even with no vowel group ---------------
    def test_min_count_is_one(self) -> None:
        for word in ("rhythm", "hmm", "a", "y"):
            with self.subTest(word=word):
                self.assertEqual(syllable_meter.syllables_en(word), 1)


class EnglishLineTests(unittest.TestCase):
    """Per-line totals through the CLI, no --expect."""

    # --- line 1: single line via --text, exact row format -------------------
    def test_single_line_row_format(self) -> None:
        proc = run_cli("--text", "Hello world tonight")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  1 |  5 | Hello world tonight\n")

    # --- line 2: two lines via stdin ----------------------------------------
    def test_stdin_input_mode(self) -> None:
        proc = run_cli(stdin="Hello world tonight\nI feel the city light\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout,
            "  1 |  5 | Hello world tonight\n  2 |  6 | I feel the city light\n",
        )

    # --- line 3: blank lines skipped, counted lines renumbered --------------
    def test_blank_lines_skipped_and_renumbered(self) -> None:
        proc = run_cli(stdin="hello  \n\n\nworld\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  1 |  2 | hello\n  2 |  1 | world\n")

    # --- line 4: positional file works from another cwd (cwd-independent) ---
    def test_positional_file_from_other_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lyric_file = tmp_path / "song.txt"
            lyric_file.write_text(
                "chasing the light\ninto the night\n", encoding="utf-8"
            )
            proc = run_cli(str(lyric_file), cwd=tmp_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                proc.stdout, "  1 |  4 | chasing the light\n  2 |  4 | into the night\n"
            )

    # --- line 5: input precedence --text beats the positional file ---------
    def test_text_wins_over_positional_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lyric_file = Path(tmp) / "song.txt"
            lyric_file.write_text("into the night\n", encoding="utf-8")
            proc = run_cli(str(lyric_file), "--text", "you got a broken heart")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, "  1 |  6 | you got a broken heart\n")

    # --- line 6: --text splits lines on the literal two-char '\n' -----------
    def test_text_literal_backslash_n_splits_lines(self) -> None:
        proc = run_cli("--text", "Hello world tonight\\nI feel the city light")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("  1 |  5 | Hello world tonight\n", proc.stdout)
        self.assertIn("  2 |  6 | I feel the city light\n", proc.stdout)


class ExpectTests(unittest.TestCase):
    """--expect N,N meter checking drives the exit code."""

    # --- expect 1: all lines match -> exit 0 with PASS rows ------------------
    def test_expect_match_exit_0(self) -> None:
        proc = run_cli("--text", "Hello world tonight\\nI am here now",
                       "--expect", "5,4")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(
            proc.stdout,
            "  1 |  5/5   | PASS | Hello world tonight\n"
            "  2 |  4/4   | PASS | I am here now\n"
            "Summary: 2/2 lines match expected meter.\n",
        )

    # --- expect 2: mismatch on line 2 -> exit 1 (docstring example) ---------
    def test_expect_mismatch_exit_1(self) -> None:
        proc = run_cli("--expect", "5,5",
                       stdin="Hello world tonight\nI feel the city light\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("  2 |  6/5   | FAIL | I feel the city light", proc.stdout)
        self.assertIn("Summary: 1/2 lines match expected meter.", proc.stdout)

    # --- expect 3: fewer lines than expected counts -> exit 1 ----------------
    def test_expect_fewer_lines_than_expected_exit_1(self) -> None:
        proc = run_cli("--text", "Hello world tonight", "--expect", "5,5")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("  2 |  0/5   | FAIL | (input has no line 2)", proc.stdout)
        self.assertIn("Summary: 1/2 lines match expected meter.", proc.stdout)

    # --- expect 4: more lines than expected counts -> exit 1 -----------------
    def test_expect_more_lines_than_expected_exit_1(self) -> None:
        proc = run_cli("--text", "I am here now\\nla la", "--expect", "4")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("  2 |  2/-   | FAIL | la la", proc.stdout)
        self.assertIn("Summary: 1/2 lines match expected meter.", proc.stdout)

    # --- expect 5: non-integer --expect -> usage error, exit 2 ---------------
    def test_expect_bad_value_exit_2(self) -> None:
        proc = run_cli("--text", "hello", "--expect", "5,x")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--expect must be comma-separated", proc.stderr)


class CjkTests(unittest.TestCase):
    """CJK characters count as exactly 1 unit each (auto/cjk), 0 in en mode."""

    # --- cjk 1: auto mode detects Hanzi and prints the banner ----------------
    def test_cjk_auto_counts_each_char(self) -> None:
        proc = run_cli("--text", "夜色温柔")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout,
            "CJK mode: each CJK character counts as 1 syllable unit.\n"
            "  1 |  4 | 夜色温柔 (+4 CJK chars)\n",
        )

    # --- cjk 2: mixed line adds CJK chars to the English total ---------------
    def test_cjk_auto_mixed_line(self) -> None:
        proc = run_cli("--text", "hello 夜")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CJK mode: each CJK character counts as 1 syllable unit.",
                      proc.stdout)
        self.assertIn("  1 |  3 | hello 夜 (+1 CJK chars)", proc.stdout)

    # --- cjk 3: kana and Hangul count too (not just Hanzi) -------------------
    def test_cjk_kana_and_hangul_counted(self) -> None:
        proc = run_cli("--text", "ありがとう 안녕")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("  1 |  7 | ありがとう 안녕 (+7 CJK chars)", proc.stdout)

    # --- cjk 4: --lang en ignores CJK chars in the total, no banner ----------
    def test_lang_en_ignores_cjk(self) -> None:
        proc = run_cli("--lang", "en", "--text", "夜色温柔 hello")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("CJK mode:", proc.stdout)
        self.assertIn("  1 |  2 | 夜色温柔 hello (+4 CJK chars)", proc.stdout)

    # --- cjk 5: --lang cjk forces the banner even on pure-ASCII lines -------
    def test_lang_cjk_banner_on_ascii_only(self) -> None:
        proc = run_cli("--lang", "cjk", "--text", "hello world")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout,
            "CJK mode: each CJK character counts as 1 syllable unit.\n"
            "  1 |  3 | hello world\n",
        )

    # --- cjk 6: CJK meter check against --expect -> exit 0 -------------------
    def test_cjk_expect_match_exit_0(self) -> None:
        proc = run_cli("--text", "夜色温柔", "--expect", "4")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("  1 |  4/4   | PASS | 夜色温柔", proc.stdout)
        self.assertIn("Summary: 1/1 lines match expected meter.", proc.stdout)


class UsageErrorTests(unittest.TestCase):
    """Usage problems exit 2 with a message on stderr."""

    # --- usage 1: empty stdin -> no lyric lines -------------------------------
    def test_empty_stdin_exit_2(self) -> None:
        proc = run_cli(stdin="")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("No non-blank lyric lines found.", proc.stderr)

    # --- usage 2: --text with only whitespace -> no lyric lines --------------
    def test_blank_only_text_exit_2(self) -> None:
        proc = run_cli("--text", "  \n \n")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("No non-blank lyric lines found.", proc.stderr)

    # --- usage 3: invalid --lang choice ---------------------------------------
    def test_bad_lang_choice_exit_2(self) -> None:
        proc = run_cli("--lang", "xyz", "--text", "hello")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid choice", proc.stderr)

    # --- usage 4: unreadable file is a usage error, not a finding -------------
    def test_missing_file_exit_2(self) -> None:
        proc = run_cli("/no/such/lyrics.txt")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("cannot read /no/such/lyrics.txt", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class ContractionTests(unittest.TestCase):
    def test_contraction_is_one_word(self) -> None:
        for word, want in (("won't", 1), ("I'm", 1), ("don't", 1), ("they're", 1),
                           ("coffee's", 2), ("won\u2019t", 1)):
            self.assertEqual(syllable_meter.syllables_en(word), want, word)

    def test_consonant_nt_keeps_its_syllable(self) -> None:
        for word, want in (("didn't", 2), ("couldn't", 2), ("wasn't", 2)):
            self.assertEqual(syllable_meter.syllables_en(word), want, word)

    def test_line_with_contractions(self) -> None:
        self.assertEqual(syllable_meter.count_line("I won't go", "auto")[0], 3)
        self.assertEqual(syllable_meter.count_line("I'm home", "auto")[0], 2)


if __name__ == "__main__":
    unittest.main()
