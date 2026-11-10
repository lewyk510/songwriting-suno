"""Tests for scripts/lyric_lint.py (pinned contract).

CLI cases drive the real script through subprocess so exit codes are real:
0 = no actionable findings, 1 = cliche hit or repetition count above
--min-repeat, 2 = usage problem. Scheme/pair cases call analyze()
directly for precise assertions. The script must stay cwd-independent
(it resolves its sibling syllable_meter.py via __file__), which the
other-cwd cases pin down.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "lyric_lint.py"
sys.path.insert(0, str(SCRIPT.parent))

import lyric_lint  # noqa: E402


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


class RhymeSchemeTests(unittest.TestCase):
    # --- scheme 1: perfect rhymes -> AABB ---------------------------------
    def test_perfect_rhymes_aabb(self) -> None:
        res = lyric_lint.analyze(
            "[Verse]\nchasing the light\ninto the night\nthe road to home\nwe walk alone\n"
        )
        verse = res["groups"][1]
        self.assertEqual(verse["scheme"], "AABB")
        self.assertEqual(verse["perfect_pairs"], [[2, 3], [4, 5]])
        self.assertEqual(verse["near_pairs"], [])

    # --- scheme 2: same vowel, different coda -> near rhyme a' ------------
    def test_near_assonance_gets_prime_symbol(self) -> None:
        res = lyric_lint.analyze("[Verse]\ncity light\nsky so high\n")
        verse = res["groups"][1]
        self.assertEqual(verse["scheme"], "Aa'")
        self.assertEqual(verse["near_pairs"], [[2, 3]])
        self.assertEqual(verse["perfect_pairs"], [])
        self.assertEqual(verse["lines"][1]["symbol"], "a'")
        self.assertTrue(verse["lines"][1]["symbol"].endswith("'"))

    # --- scheme 3: perfect and near mixed, letters stay stable ------------
    def test_mixed_perfect_and_near(self) -> None:
        res = lyric_lint.analyze("[Verse]\ninto the night\nsky so high\ncity light\n")
        verse = res["groups"][1]
        self.assertEqual(verse["scheme"], "Aa'A")
        self.assertEqual(verse["perfect_pairs"], [[2, 4]])
        self.assertEqual(verse["near_pairs"], [[2, 3], [3, 4]])
        self.assertEqual(verse["near_desc"], ["(2,3), (3,4) vowel 'i'"])

    # --- scheme 4: no rhymable word -> '-' --------------------------------
    def test_no_rhymable_word_gets_dash(self) -> None:
        res = lyric_lint.analyze("[Verse]\n2024\nsky so high\n")
        verse = res["groups"][1]
        self.assertEqual(verse["lines"][0]["symbol"], "-")
        self.assertIsNone(verse["lines"][0]["rhyme_key"])

    # --- scheme 5: TAG_RE is the shared validate_structure.py convention ---
    def test_tag_re_matches_validate_structure_convention(self) -> None:
        self.assertEqual(lyric_lint.TAG_RE.pattern, r"^\s*\[([^\[\]]+)\]\s*$")

    # --- scheme 6: lines before the first tag form the preamble group ------
    def test_preamble_group(self) -> None:
        res = lyric_lint.analyze("just a stray line\n[Verse]\nla la la la\n")
        self.assertEqual(res["section_count"], 1)
        self.assertEqual(res["preamble_count"], 1)
        self.assertEqual(res["groups"][0]["tag"], "(preamble)")
        self.assertEqual(res["groups"][0]["line_count"], 1)

    # --- scheme 7: sections letter independently ---------------------------
    def test_sections_use_independent_letters(self) -> None:
        res = lyric_lint.analyze(
            "[Verse]\nsome day\nsome way\n[Verse 2]\nwe play\nwe say\n"
        )
        self.assertEqual(res["groups"][1]["scheme"], "AA")
        self.assertEqual(res["groups"][2]["scheme"], "AA")

    # --- scheme 8: the approximation disclaimer is pinned ------------------
    def test_docstring_disclaims_approximation(self) -> None:
        doc = (lyric_lint.__doc__ or "").lower()
        self.assertIn("approximat", doc)
        self.assertIn("not ground truth", doc)


class ClicheTests(unittest.TestCase):
    # --- cliche 1: hit -> exit 1 with line number --------------------------
    def test_cliche_hit_exit_1_with_line_number(self) -> None:
        proc = run_cli("--text", "[Verse]\nhello world\nyou got a broken heart\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("line 3: matched 'broken heart'", proc.stdout)

    # --- cliche 2: case-insensitive ----------------------------------------
    def test_cliche_case_insensitive(self) -> None:
        proc = run_cli("--text", "YOU GOT A BROKEN HEART\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("matched 'broken heart'", proc.stdout)

    # --- cliche 3: --no-cliche disables the scan ---------------------------
    def test_no_cliche_disables_scan(self) -> None:
        proc = run_cli("--text", "you got a broken heart\n", "--no-cliche")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("(scan disabled by --no-cliche)", proc.stdout)

    # --- cliche 4: tag lines are structure, not lyrics ---------------------
    def test_tags_are_not_scanned_for_cliches(self) -> None:
        proc = run_cli("--text", "[Chorus: broken heart]\nla la la\n")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("matched", proc.stdout)

    # --- cliche 5: the built-in list is documented and >= 25 entries -------
    def test_cliche_list_has_at_least_25_entries(self) -> None:
        self.assertGreaterEqual(len(lyric_lint.CLICHE_LIST), 25)
        for entry in lyric_lint.CLICHE_LIST:
            self.assertIsInstance(entry, str)
            self.assertTrue(entry.strip(), entry)


class RepetitionTests(unittest.TestCase):
    # --- repeat 1: 2x == chorus-normal, informational, exit 0 --------------
    def test_double_repeat_informational_exit_0(self) -> None:
        text = "[Chorus]\nla la la la\nother line here\nla la la la\n"
        proc = run_cli("--text", text)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("2x | informational", proc.stdout)

    # --- repeat 2: 3x is above --min-repeat 2 -> actionable, exit 1 --------
    def test_triple_repeat_actionable_exit_1(self) -> None:
        text = "[Chorus]\nla la la la\nother line here\nla la la la\nla la la la\n"
        proc = run_cli("--text", text)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("3x | above --min-repeat 2", proc.stdout)

    # --- repeat 3: lowering --min-repeat makes 2x actionable ---------------
    def test_min_repeat_lowers_threshold(self) -> None:
        text = "[Chorus]\nla la la la\nother line here\nla la la la\n"
        proc = run_cli("--text", text, "--min-repeat", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout)

    # --- repeat 4: normalization ignores case, punctuation, extra spaces ---
    def test_normalization_ignores_case_and_punctuation(self) -> None:
        text = "[Verse]\nLa La La La!\nnothing else here\nla  la la la\n"
        proc = run_cli("--text", text)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("2x | informational", proc.stdout)

    # --- repeat 5: section tags are not counted as repeated lyric lines ----
    def test_section_tags_not_counted_as_repeats(self) -> None:
        proc = run_cli("--text", "[Chorus]\nla la\n[Chorus]\nla la\n", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual([r["normalized"] for r in data["repeats"]], ["la la"])


class ExitCodeTests(unittest.TestCase):
    # --- exit 1: empty --text -> usage problem ------------------------------
    def test_empty_text_exit_2(self) -> None:
        proc = run_cli("--text", "")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())

    # --- exit 2: piped empty stdin -> usage problem -------------------------
    def test_no_input_exit_2(self) -> None:
        proc = run_cli(stdin="")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())

    # --- exit 2: --min-repeat below 1 ---------------------------------------
    def test_bad_min_repeat_exit_2(self) -> None:
        proc = run_cli("--min-repeat", "0", "--text", "la la\n")
        self.assertEqual(proc.returncode, 2)

    # --- exit 2: unreadable file --------------------------------------------
    def test_missing_file_exit_2(self) -> None:
        proc = run_cli("/nonexistent/lyrics/ghost.txt")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())

    # --- --warn-only forces exit 0 for findings ------------------------------
    def test_warn_only_forces_zero(self) -> None:
        proc = run_cli("--text", "you got a broken heart\n", "--warn-only")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Result: PASS (--warn-only", proc.stdout)

    # --- stdin is a valid input path -----------------------------------------
    def test_stdin_input(self) -> None:
        proc = run_cli(stdin="[Chorus]\nyou got a broken heart\n")
        self.assertEqual(proc.returncode, 1, proc.stdout)

    # --- cwd independence: file by absolute path, other cwd ------------------
    def test_file_positional_from_other_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lyric_file = tmp_path / "song.txt"
            lyric_file.write_text(
                "[Verse]\nchasing the light\ninto the night\n", encoding="utf-8"
            )
            proc = run_cli(str(lyric_file), cwd=tmp_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    # --- input precedence: positional file wins over --text ------------------
    def test_file_wins_over_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lyric_file = Path(tmp) / "clean.txt"
            lyric_file.write_text(
                "[Verse]\nchasing the light\ninto the night\n", encoding="utf-8"
            )
            proc = run_cli(str(lyric_file), "--text", "you got a broken heart\n")
            self.assertEqual(proc.returncode, 0, proc.stdout)


class JsonTests(unittest.TestCase):
    # --- json 1: pinned shape, same exit code as text mode ------------------
    def test_json_shape_and_exit_code(self) -> None:
        proc = run_cli(
            "--text", "[Verse]\nhello world\nyou got a broken heart\n", "--json"
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        data = json.loads(proc.stdout)  # stdout must be pure, valid JSON
        self.assertEqual(
            set(data),
            {
                "tool",
                "approximate",
                "min_repeat",
                "warn_only",
                "total_lines",
                "section_count",
                "preamble_count",
                "groups",
                "repeats",
                "cliche_matches",
                "cliche_scan_disabled",
                "tells",
                "actionable",
            },
        )
        self.assertTrue(data["approximate"])
        self.assertTrue(data["actionable"])
        self.assertFalse(data["warn_only"])
        self.assertEqual(data["min_repeat"], 2)
        self.assertEqual(data["total_lines"], 3)
        verse = data["groups"][1]
        self.assertEqual(
            set(verse),
            {
                "index",
                "tag",
                "line_count",
                "lines",
                "scheme",
                "perfect_pairs",
                "near_pairs",
                "near_desc",
                "syllables",
            },
        )
        self.assertEqual(verse["tag"], "Verse")
        self.assertEqual(
            set(verse["lines"][0]), {"n", "text", "symbol", "rhyme_key", "syllables"}
        )
        self.assertEqual(
            data["cliche_matches"],
            [{"line": 3, "text": "you got a broken heart", "cliche": "broken heart"}],
        )

    # --- json 2: clean run -> actionable false, exit 0 -----------------------
    def test_json_clean_run_actionable_false(self) -> None:
        proc = run_cli("--text", "[Verse]\nla la la la\n", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        data = json.loads(proc.stdout)
        self.assertFalse(data["actionable"])
        self.assertEqual(data["repeats"], [])
        self.assertEqual(data["cliche_matches"], [])


class SpreadTests(unittest.TestCase):
    # --- spread 1: min/max/median(3.5)/spread on a known pair ---------------
    def test_spread_values_and_half_median(self) -> None:
        res = lyric_lint.analyze("[Verse]\nla la la la la\nhello\n")
        self.assertEqual(
            res["groups"][1]["syllables"], {"min": 2, "max": 5, "median": 3.5, "spread": 3}
        )

    # --- spread 2: whole-number median (6, 8 -> 7) ---------------------------
    def test_spread_whole_median(self) -> None:
        res = lyric_lint.analyze(
            "[Verse]\nI drive until the streetlights end\nI whisper it again\n"
        )
        syl = res["groups"][1]["syllables"]
        self.assertEqual(syl["min"], 6)
        self.assertEqual(syl["max"], 8)
        self.assertEqual(syl["median"], 7)
        self.assertEqual(syl["spread"], 2)


class DeterminismTests(unittest.TestCase):
    # --- deterministic: identical input -> identical report ------------------
    def test_analyze_is_deterministic(self) -> None:
        text = (
            "[Verse]\ncity light\nsky so high\n[Chorus]\nla la la la\nla la la la\n"
        )
        self.assertEqual(lyric_lint.analyze(text), lyric_lint.analyze(text))


class MachineTellTests(unittest.TestCase):
    """Each tell rule: must-flag samples next to look-alike lines it must spare."""

    def tells(self, text: str) -> list[dict]:
        return lyric_lint.analyze(text)["tells"]

    def rules(self, text: str) -> list[str]:
        return [t["rule"] for t in self.tells(text)]

    def test_two_negation_frames_in_a_section_are_actionable(self) -> None:
        text = "[Chorus]\nI'm not broken, I'm just bruised\nI'm not over you, I'm just learning\n"
        res = lyric_lint.analyze(text)
        self.assertEqual([t["rule"] for t in res["tells"]], ["negation_frame"])
        self.assertEqual(res["tells"][0]["lines"], [2, 3])
        self.assertTrue(res["actionable"])

    def test_one_negation_frame_is_ordinary_writing(self) -> None:
        text = "[Verse]\nShe's not angry, but she won't say why\nthe kettle clicks off in the dark\n"
        res = lyric_lint.analyze(text)
        self.assertEqual(res["tells"], [])
        self.assertFalse(res["actionable"])

    def test_negation_frames_in_different_sections_do_not_add_up(self) -> None:
        text = (
            "[Verse]\nI'm not broken, I'm just bruised\n"
            "[Bridge]\nI'm not over you, I'm just learning\n"
        )
        self.assertEqual(self.rules(text), [])

    def test_repeating_one_negation_line_is_not_two_frames(self) -> None:
        text = "[Chorus]\nI'm not broken, I'm just bruised\nI'm not broken, I'm just bruised\n"
        self.assertEqual(self.rules(text), [])

    def test_plain_negation_without_the_turn_is_spared(self) -> None:
        text = "[Verse]\nI did not call, I did not write\nyou can't stay, the lease is up\n"
        self.assertEqual(self.rules(text), [])

    def test_first_person_turn_is_not_a_negation_frame(self) -> None:
        # "not X, I Y" is an ordinary human turn, not the but/just/only frame;
        # pins the contrast-word list against a stray alternation member.
        text = (
            "[Verse]\nI'm not here to fight, I came to dance\n"
            "I'm not trying to be cruel, I mean it kind\n"
        )
        self.assertEqual(self.rules(text), [])

    def test_imperative_negation_lookalike_is_spared(self) -> None:
        # Council round 1 (DeepSeek F1): "Don't X, just Y" has no pronoun
        # subject; density gating alone would still make two of these
        # actionable, so the frame requires a subject and these stay spare.
        text = "[Chorus]\nDon't look back, just drive\nDon't slow down, only forward\n"
        self.assertEqual(self.rules(text), [])

    def test_clause_initial_not_lookalike_is_spared(self) -> None:
        text = "[Verse]\nNot a sound, only rain\nNot a trace, just silence\n"
        self.assertEqual(self.rules(text), [])

    def test_negation_frame_accepts_dash_and_ellipsis_separators(self) -> None:
        em_dash = "[Verse]\nI'm not broken \u2014 just bruised\nI'm not angry \u2014 only late\n"
        hyphen = "[Verse]\nI'm not broken - just bruised\nI'm not angry - only late\n"
        ellipsis = "[Verse]\nI'm not broken... just bruised\nI'm not angry... only late\n"
        self.assertEqual(self.rules(em_dash), ["negation_frame"])
        self.assertEqual(self.rules(hyphen), ["negation_frame"])
        self.assertEqual(self.rules(ellipsis), ["negation_frame"])

    def test_preamble_and_untagged_lines_are_scanned_for_tells(self) -> None:
        # Council round 1 (Gemini): dropping the tags used to dodge the tell
        # rules entirely; untagged sheets and preamble lines are a
        # pseudo-section now.
        untagged = "I'm not broken, I'm just bruised\nI'm not over you, I'm just learning\n"
        self.assertEqual(self.rules(untagged), ["negation_frame"])
        preamble = (
            "I'm not broken, I'm just bruised\nI'm not over you, I'm just learning\n"
            "[Verse]\nthe kettle clicks off in the dark\n"
        )
        res = lyric_lint.analyze(preamble)
        self.assertEqual([t["rule"] for t in res["tells"]], ["negation_frame"])
        self.assertEqual(res["tells"][0]["tag"], "(preamble)")
        self.assertEqual(res["tells"][0]["section"], 0)

    def test_anaphora_run_is_advisory(self) -> None:
        text = (
            "[Bridge]\nMaybe love is just a season\nMaybe we were meant to break\n"
            "Maybe that's the lie I make\n"
        )
        res = lyric_lint.analyze(text)
        self.assertEqual([t["rule"] for t in res["tells"]], ["anaphora_run"])
        self.assertFalse(res["tells"][0]["actionable"])
        self.assertFalse(res["actionable"])

    def test_two_shared_openers_or_function_words_are_not_a_run(self) -> None:
        two = "[Bridge]\nMaybe love is just a season\nMaybe we were meant to break\nthe porch light stays on\n"
        function_words = "[Verse]\nI woke up late\nI missed the train\nI walked the bridge\n"
        third_person = "[Verse]\nShe woke up\nShe packed her bags\nShe left at dawn\n"
        self.assertEqual(self.rules(two), [])
        self.assertEqual(self.rules(function_words), [])
        self.assertEqual(self.rules(third_person), [])

    def test_cjk_openers_run_on_first_character(self) -> None:
        text = "[Verse]\n\u4f60\u8bf4\u7684\u8bdd\n\u4f60\u5199\u7684\u4fe1\n\u4f60\u7559\u7684\u706f\n"
        res = lyric_lint.analyze(text)
        self.assertEqual([t["rule"] for t in res["tells"]], ["anaphora_run"])
        self.assertFalse(res["tells"][0]["actionable"])

    def test_imagery_cluster_needs_four_distinct_words(self) -> None:
        four = "[Verse]\nNeon bleeding on the asphalt\nChrome and static in the rain\nMidnight on the wire\n"
        three = "[Verse]\nNeon sign above the laundromat\nThe chrome on the bumper peeled\nStatic on the radio\n"
        res = lyric_lint.analyze(four)
        self.assertEqual([t["rule"] for t in res["tells"]], ["imagery_cluster"])
        self.assertFalse(res["actionable"])
        self.assertEqual(self.rules(three), [])

    def test_imagery_singular_forms_count_too(self) -> None:
        # Council round 1 (Gemini): singular/plural inflection must not gate
        # the cluster ("shadow" is as stock as "shadows").
        text = (
            "[Verse]\nA shadow on the wall\nAn echo down the hall\n"
            "A whisper in the quiet\nA single ash falls down\n"
        )
        self.assertEqual(self.rules(text), ["imagery_cluster"])

    def test_repeated_imagery_word_counts_once(self) -> None:
        text = "[Verse]\nneon neon neon neon\nneon on the neon sign\n"
        self.assertEqual(self.rules(text), [])

    def test_actionable_tell_drives_exit_code_and_report(self) -> None:
        text = "[Chorus]\nI'm not broken, I'm just bruised\nI'm not over you, I'm just learning\n"
        proc = run_cli("--text", text)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("negation_frame | actionable | [Chorus]", proc.stdout)
        self.assertEqual(run_cli("--text", text, "--warn-only").returncode, 0)

    def test_binary_file_exits_2(self) -> None:
        # Council round 1 (GLM): a non-UTF8 sheet crashed with a traceback and
        # exit 1, which reads as "actionable findings"; usage errors exit 2.
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.txt"
            bad.write_bytes(b"\xff\xfe\x00not utf8")
            proc = run_cli(str(bad))
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("cannot read", proc.stderr)


class AddedClicheTests(unittest.TestCase):
    def hits(self, text: str) -> list[str]:
        return [m["cliche"] for m in lyric_lint.analyze(text)["cliche_matches"]]

    def test_contraction_phrase_matches_through_punctuation(self) -> None:
        self.assertEqual(self.hits("[Chorus]\nI won't back down, not now\n"), ["won't back down"])

    def test_heart_skips_inflections_match(self) -> None:
        # Council round 1 (GLM): word-boundary matching never hits the
        # inflected forms; both are listed.
        self.assertEqual(self.hits("[Chorus]\nmy heart skips a beat\n"), ["heart skips a beat"])
        self.assertEqual(self.hits("[Verse]\nmy heart skipped a beat\n"), ["heart skipped a beat"])

    def test_phrase_needs_whole_words(self) -> None:
        self.assertEqual(self.hits("[Verse]\nshe stole my heartbeat monitor\n"), [])

    def test_mandarin_stock_phrase_matches_inside_a_line(self) -> None:
        line = "\u601d\u5ff5\u50cf\u6f6e\u6c34\u4e00\u6837\u6d8c\u6765"
        self.assertEqual(self.hits(f"[Verse]\n{line}\n"), ["\u601d\u5ff5\u50cf\u6f6e\u6c34"])

    def test_mandarin_phrase_matches_across_a_sung_space(self) -> None:
        line = "\u6211\u60f3\u56de\u5bb6 \u56de\u5230 \u4f60\u8eab\u65c1"
        self.assertEqual(self.hits(f"[Chorus]\n{line}\n"), ["\u56de\u5230\u4f60\u8eab\u65c1"])

    def test_plain_mandarin_line_is_clean(self) -> None:
        line = "\u6211\u60f3\u56de\u5bb6\u62ff\u4ef6\u5916\u5957"
        self.assertEqual(self.hits(f"[Verse]\n{line}\n"), [])


class ContractionRhymeTests(unittest.TestCase):
    def test_contractions_rhyme_on_the_whole_word(self) -> None:
        res = lyric_lint.analyze("[Verse]\nI won't\nshe don't\n")
        self.assertEqual(res["groups"][1]["scheme"], "AA")
        self.assertEqual(lyric_lint.rhyme_key("I won\u2019t"), ("ont", "o"))


if __name__ == "__main__":
    unittest.main()
