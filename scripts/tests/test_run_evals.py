"""Tests for scripts/run_evals.py (pinned contract).

CLI cases drive the real script through subprocess so exit codes are real:
0 = no FAIL (PASS and JUDGE allowed), 1 = at least one FAIL, 2 = usage error,
unknown case, unreadable input, or criterion drift. Artifacts are disposable
dirs under tempfile with the documented names (style_prompt.txt, lyrics.txt).

The negative probes pin the false-positive class the review panel found:
tag lines must never count as lyric content, comma/descriptor conjuncts are
really checked, the verse/chorus gap is counted here (validate only warns),
and malformed --evals / unreadable artifacts exit 2 instead of crashing.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "run_evals.py"
EVALS = Path(__file__).resolve().parent.parent.parent / "evals" / "evals.json"
sys.path.insert(0, str(SCRIPT.parent))

import run_evals  # noqa: E402

GOOD_STYLE = "city-pop, melancholic, 92 BPM, retro synth, female vocal\nEXCLUDE: EDM, harsh vocals\n"
GOOD_LYRICS = (
    "[Verse 1]\n"
    "\u8def\u706f\u4e0b\u7684\u65e7\u7ad9\u53f0\n"
    "\u96e8\u58f0\u76d6\u8fc7\u544a\u522b\n"
    "[Chorus]\n"
    "one more night before the train\n"
    "I leave the city in the rain\n"
)

WEDDING_STYLE = "acoustic ballad, fingerpicked guitar, 72 BPM, warm\nEXCLUDE: electronic drums, autotune\n"
WEDDING_LYRICS = (
    "[Verse 1]\nwe kept your room the way it was\nthe porch light on at ten\n"
    "[Chorus]\ncarry our name into the light\nwe will be standing right behind\n"
)
TRAP_STYLE = "dark trap, 808 bass, 140 BPM, menacing\nEXCLUDE: acoustic guitar\n"
TRAP_LYRICS = (
    "[Verse 1]\nI count the seconds till the sun\nno sleep until the work is done\n"
    "[Hook]\nrun it up\nrun it up\n"
    "[Verse 2]\nthey said the door was never mine\n"
    "[Hook]\nrun it up\nrun it up\n"
    "[Chorus]\nrun it up\n"
)
TEMPLATE = Path(__file__).resolve().parent.parent.parent / "assets" / "song-template.md"


def write_song(
    artifacts: Path,
    log_row: str = "| 1 | chorus trimmed | singability | kept |",
    drop: str = "",
    blank: str = "",
    reverse: bool = False,
) -> None:
    """song.md with the template's own H2 headings, each given real content.

    drop = heading to leave out; blank = heading left with only a placeholder;
    reverse = emit the headings in reverse order.
    """
    heads = [
        line[3:].strip()
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    ]
    if reverse:
        heads.reverse()
    parts = ["# Song Draft: porch light"]
    for head in heads:
        if head == drop:
            continue
        if head == blank:
            body = "<to be written>"
        elif head == "Iteration log":
            body = "| # | Change | Why | Result |\n|---|--------|-----|--------|\n" + log_row
        else:
            body = f"real content for {head}"
        parts.append(f"## {head}\n{body}")
    (artifacts / "song.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def make_artifacts(
    root: Path,
    style: str = GOOD_STYLE,
    lyrics: str = GOOD_LYRICS,
    case: str = "art",
) -> Path:
    artifacts = root / case
    artifacts.mkdir()
    (artifacts / "style_prompt.txt").write_text(style, encoding="utf-8")
    (artifacts / "lyrics.txt").write_text(lyrics, encoding="utf-8")
    return artifacts


class HappyPathTests(unittest.TestCase):
    def test_citypop_good_artifacts_pass_machine_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp))
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("3 PASS, 0 FAIL, 2 JUDGE", res.stdout)
        self.assertIn("PASS   #1", res.stdout)
        self.assertIn("JUDGE  #4", res.stdout)
        self.assertIn("JUDGE  #5", res.stdout)
        self.assertIn("-> ", res.stdout)  # PASS/JUDGE details are printed in text mode

    def test_json_mode_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp))
            res = run_cli(
                "--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts), "--json"
            )
        self.assertEqual(res.returncode, 0)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["case"], "citypop-bilingual-leaving-home")
        self.assertEqual(payload["summary"], {"passed": 3, "failed": 0, "judge": 2})
        self.assertEqual(payload["exit_code"], 0)

    def test_judge_only_case_exits_0_without_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "empty"
            artifacts.mkdir()
            res = run_cli("--case", "learn-route-teach-me", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 PASS, 0 FAIL, 4 JUDGE", res.stdout)

    def test_kpop_balanced_sheet_passes(self) -> None:
        style = "k-pop, dance pop, 128 BPM, bright synths, girl group\nEXCLUDE: (none)\n"
        lyrics = (
            "[Verse 1]\nfirst line of the verse\nsecond line of the verse\n"
            "[Chorus]\nchant it out now\n\ub2e4\uc2dc \ud55c \ubc88 now\n"
            "[Instrumental Break (dance break)]\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style, lyrics=lyrics)
            res = run_cli("--case", "kpop-girlgroup-debut", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("4 PASS, 0 FAIL, 1 JUDGE", res.stdout)

    def test_lofi_sheet_passes(self) -> None:
        style = "lo-fi, chill, mellow, soft piano, 80 BPM\nEXCLUDE: (none)\n"
        lyrics = (
            "[Verse]\nmurmured words under the static\n"
            "[Chorus]\nstudy till the morning light\n"
            "[Instrumental Break]\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style, lyrics=lyrics)
            res = run_cli("--case", "lofi-study-instrumental", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("3 PASS, 0 FAIL, 2 JUDGE", res.stdout)

    def test_wedding_sheet_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=WEDDING_STYLE, lyrics=WEDDING_LYRICS)
            res = run_cli("--case", "wedding-acoustic-ballad", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("3 PASS, 0 FAIL, 2 JUDGE", res.stdout)

    def test_trap_sheet_with_song_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=TRAP_STYLE, lyrics=TRAP_LYRICS)
            write_song(artifacts, log_row="| 1 | verse 1 to 8-syllable lines | meter | kept |")
            res = run_cli("--case", "trap-motivation-tight-meter", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("4 PASS, 0 FAIL, 1 JUDGE", res.stdout)

    def test_worked_example_with_song_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp))
            write_song(artifacts)
            res = run_cli("--case", "worked-example-as-model", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("3 PASS, 0 FAIL, 2 JUDGE", res.stdout)

    def test_unrecorded_song_goes_to_judge_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp))
            res = run_cli(
                "--case", "worked-example-as-model", "--dir", str(artifacts), "--json"
            )
        self.assertEqual(res.returncode, 0, res.stdout)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["summary"], {"passed": 1, "failed": 0, "judge": 4})
        self.assertIn("song.md not recorded", payload["results"][2]["detail"])

    def test_coverage_counts_registry_against_spec(self) -> None:
        res = run_cli("--coverage", "--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        data = json.loads(EVALS.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["summary"]["criteria"],
            sum(len(c["success_criteria"]) for c in data["evals"]),
        )
        self.assertEqual(
            payload["summary"]["machine"],
            sum(len(checks) for checks in run_evals.CHECKS.values()),
        )
        self.assertEqual(payload["summary"]["cases"], len(data["evals"]))
        # Literal pins: the derived checks above cannot catch a registry
        # entry silently disappearing (council round 1 finding).
        self.assertEqual(payload["summary"]["machine"], 23)
        self.assertEqual(payload["summary"]["criteria"], 84)
        self.assertEqual(payload["summary"]["cases_with_checks"], 7)
        self.assertEqual(payload["summary"]["cases"], 19)

    def test_lowercase_tags_pass(self) -> None:
        lyrics = (
            "[verse 1]\n"
            "\u8def\u706f\u4e0b\u7684\u65e7\u7ad9\u53f0\n"
            "[chorus]\n"
            "one more night in the rain\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("3 PASS, 0 FAIL, 2 JUDGE", res.stdout)
        self.assertIn("JUDGE  #4", res.stdout)


class FalsePositiveProbeTests(unittest.TestCase):
    def test_chinese_only_criterion_stays_judge_bilingual_check_kept(self) -> None:
        # #4 carries the "metered as 1 unit" process conjunct, so the registry
        # leaves it JUDGE; the bilingual check itself stays pinned in
        # DirectCheckTests.test_bilingual_requires_both_languages.
        lyrics = "[Verse 1]\n\u8def\u706f\u4e0b\u7684\u65e7\u7ad9\u53f0\n[Chorus]\n\u96e8\u58f0\u76d6\u8fc7\u544a\u522b\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("JUDGE  #4", res.stdout)

    def test_commaless_style_fails_single_string_criterion(self) -> None:
        style = "city pop melancholic 92 BPM retro synth female vocal\nEXCLUDE: EDM\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #1", res.stdout)
        self.assertIn("not comma-separated", res.stdout)

    def test_kpop_verse_chorus_gap_fails_balance(self) -> None:
        style = "k-pop, dance pop, 128 BPM\nEXCLUDE: (none)\n"
        lyrics = (
            "[Verse 1]\none line\n[Verse 2]\none line\n[Verse 3]\none line\n"
            "[Chorus]\nchant it out\n"
            "[Instrumental Break (dance break)]\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style, lyrics=lyrics)
            res = run_cli("--case", "kpop-girlgroup-debut", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #2", res.stdout)
        self.assertIn("gap 2", res.stdout)

    def test_lofi_loud_style_fails_descriptor_criterion(self) -> None:
        style = "heavy metal, screaming vocals, blast beats, 140 BPM\nEXCLUDE: (none)\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style)
            res = run_cli("--case", "lofi-study-instrumental", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #3", res.stdout)
        self.assertIn("banned tag", res.stdout)

    def test_wedding_style_without_ballad_descriptors_fails(self) -> None:
        style = "synthwave, 72 BPM, neon\nEXCLUDE: (none)\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style)
            res = run_cli("--case", "wedding-acoustic-ballad", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #1", res.stdout)


class NewCheckProbeTests(unittest.TestCase):
    """Each added check has a must-FAIL case next to its happy path."""

    def grade(self, case: str, artifacts: Path) -> dict[int, dict[str, str]]:
        res = run_cli("--case", case, "--dir", str(artifacts), "--json")
        self.assertIn(res.returncode, (0, 1), res.stderr)
        return {r["index"]: r for r in json.loads(res.stdout)["results"]}

    def test_wedding_exclude_missing_autotune_fails(self) -> None:
        style = WEDDING_STYLE.replace(", autotune", "")
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style, lyrics=WEDDING_LYRICS)
            got = self.grade("wedding-acoustic-ballad", artifacts)
        self.assertEqual(got[2]["verdict"], "FAIL")
        self.assertIn("autotune", got[2]["detail"])

    def test_wedding_meter_criterion_stays_judge(self) -> None:
        # "(syllable_meter.py output shown)" is a transcript conjunct: the
        # registry leaves #3 JUDGE instead of PASS-certifying the whole
        # sentence (same call as worked-example #2). The check itself stays
        # pinned in DirectCheckTests.test_section_meter_range.
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=WEDDING_STYLE, lyrics=WEDDING_LYRICS)
            got = self.grade("wedding-acoustic-ballad", artifacts)
        self.assertEqual(got[3]["verdict"], "JUDGE")

    def test_wedding_verse_chorus_gap_fails(self) -> None:
        lyrics = WEDDING_LYRICS + "[Verse 2]\none more line\n[Verse 3]\nand another line\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=WEDDING_STYLE, lyrics=lyrics)
            got = self.grade("wedding-acoustic-ballad", artifacts)
        self.assertEqual(got[4]["verdict"], "FAIL")
        self.assertIn("gap 2", got[4]["detail"])

    def test_trap_meter_criterion_stays_judge(self) -> None:
        # The prompt never fixes a syllable count ("verses should feel
        # relentless"), so pinning 8 here would invent a spec; #2 stays
        # JUDGE. The meter check itself stays pinned in DirectCheckTests.
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=TRAP_STYLE, lyrics=TRAP_LYRICS)
            got = self.grade("trap-motivation-tight-meter", artifacts)
        self.assertEqual(got[2]["verdict"], "JUDGE")

    def test_trap_full_chorus_beside_short_hook_passes(self) -> None:
        lyrics = TRAP_LYRICS.replace(
            "[Chorus]\nrun it up\n",
            "[Chorus]\nfirst chorus line\nsecond one here\nthird one here\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=TRAP_STYLE, lyrics=lyrics)
            got = self.grade("trap-motivation-tight-meter", artifacts)
        self.assertEqual(got[3]["verdict"], "PASS", got[3]["detail"])

    def test_trap_hook_with_three_distinct_lines_fails(self) -> None:
        lyrics = TRAP_LYRICS.replace("[Hook]\nrun it up\nrun it up\n", "[Hook]\nrun it up\nstack it\nflip it\n")
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=TRAP_STYLE, lyrics=lyrics)
            got = self.grade("trap-motivation-tight-meter", artifacts)
        self.assertEqual(got[3]["verdict"], "FAIL")
        self.assertIn("3 distinct lines", got[3]["detail"])

    def test_trap_hook_sung_once_fails(self) -> None:
        lyrics = "[Verse 1]\nI count the seconds till the sun\n[Chorus]\nrun it up\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=TRAP_STYLE, lyrics=lyrics)
            got = self.grade("trap-motivation-tight-meter", artifacts)
        self.assertEqual(got[3]["verdict"], "FAIL")
        self.assertIn("fewer than 2 times", got[3]["detail"])

    def test_trap_iteration_log_without_meter_revision_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=TRAP_STYLE, lyrics=TRAP_LYRICS)
            write_song(artifacts, log_row="| 1 | darker pads | mood | kept |")
            got = self.grade("trap-motivation-tight-meter", artifacts)
        self.assertEqual(got[5]["verdict"], "FAIL")

    def test_kpop_long_chant_line_fails(self) -> None:
        lyrics = (
            "[Verse 1]\nfirst line of the verse\n"
            "[Chorus]\nthis chant line keeps going far too long\n\ub2e4\uc2dc now\n"
            "[Instrumental Break (dance break)]\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            got = self.grade("kpop-girlgroup-debut", artifacts)
        self.assertEqual(got[3]["verdict"], "FAIL")
        self.assertIn("outside 1-6 units", got[3]["detail"])

    def test_kpop_hook_bilingual_criterion_stays_judge(self) -> None:
        # "CJK lines metered per character if used" is a process conjunct:
        # #4 stays JUDGE; the bilingual-sections check itself is pinned in
        # DirectCheckTests.test_hook_bilingual_requires_both_languages.
        lyrics = (
            "[Verse 1]\n\ub2e4\uc2dc \ud55c \ubc88\n"
            "[Chorus]\nchant it out now\n"
            "[Instrumental Break (dance break)]\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            got = self.grade("kpop-girlgroup-debut", artifacts)
        self.assertEqual(got[4]["verdict"], "JUDGE")

    def test_lone_latin_interjection_is_not_a_second_language(self) -> None:
        lyrics = "[Verse 1]\n\u8def\u706f\u4e0b\u7684\u65e7\u7ad9\u53f0\n[Chorus]\n\u96e8\u58f0\u76d6\u8fc7\u544a\u522b (hey)\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            ok, detail = run_evals.check_bilingual(artifacts)
        self.assertFalse(ok)
        self.assertIn("tags excluded", detail)

    def test_lofi_vocal_direction_must_mention_the_murmur(self) -> None:
        style = "lo-fi, chill, mellow, soft piano, 80 BPM\nEXCLUDE: (none)\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plain = make_artifacts(root, style=style, case="plain")
            write_song(plain)
            murmur = make_artifacts(root, style=style, case="murmur")
            write_song(murmur)
            song = murmur / "song.md"
            song.write_text(
                song.read_text(encoding="utf-8").replace(
                    "real content for Vocal direction", "one murmured phrase, low in the mix"
                ),
                encoding="utf-8",
            )
            got_plain = self.grade("lofi-study-instrumental", plain)
            got_murmur = self.grade("lofi-study-instrumental", murmur)
        self.assertEqual(got_plain[5]["verdict"], "FAIL")
        self.assertEqual(got_murmur[5]["verdict"], "PASS")

    def test_coverage_reports_unknown_registry_case_next_to_drift(self) -> None:
        data = json.loads(EVALS.read_text(encoding="utf-8"))
        data["evals"] = [c for c in data["evals"] if c["id"] != "kpop-girlgroup-debut"]
        case = data["evals"][0]
        case["success_criteria"][0] = "reworded"
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "evals.json"
            other.write_text(json.dumps(data), encoding="utf-8")
            res = run_cli("--coverage", "--evals", str(other))
        self.assertEqual(res.returncode, 2)
        self.assertIn("criterion drift", res.stderr)
        self.assertIn("unknown case 'kpop-girlgroup-debut'", res.stderr)

    def test_check_all_fail_beats_unrecorded_artifact(self) -> None:
        fail = lambda _dir: (False, "broken")  # noqa: E731
        unrecorded = lambda _dir: (None, "not recorded")  # noqa: E731
        passed = lambda _dir: (True, "fine")  # noqa: E731
        here = Path(".")
        self.assertIs(run_evals.check_all(unrecorded, fail)(here)[0], False)
        self.assertIs(run_evals.check_all(passed, unrecorded)(here)[0], None)
        self.assertIs(run_evals.check_all(passed, passed)(here)[0], True)

    def test_template_heading_missing_or_reordered_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = make_artifacts(root, case="missing")
            write_song(missing, drop="Production notes")
            reordered = make_artifacts(root, case="reordered")
            write_song(reordered, reverse=True)
            got_missing = self.grade("build-default-unaffected", missing)
            got_reordered = self.grade("build-default-unaffected", reordered)
        self.assertEqual(got_missing[3]["verdict"], "FAIL")
        self.assertIn("Production notes", got_missing[3]["detail"])
        self.assertEqual(got_reordered[3]["verdict"], "FAIL")
        self.assertIn("out of template order", got_reordered[3]["detail"])

    def test_placeholder_only_section_is_not_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blank = make_artifacts(root, case="blank")
            write_song(blank, blank="Concept")
            full = make_artifacts(root, case="full")
            write_song(full)
            got_blank = self.grade("citypop-bilingual-leaving-home", blank)
            got_full = self.grade("citypop-bilingual-leaving-home", full)
        self.assertEqual(got_blank[5]["verdict"], "FAIL")
        self.assertIn("Concept", got_blank[5]["detail"])
        self.assertEqual(got_full[5]["verdict"], "PASS")

    def test_template_placeholder_log_row_is_not_an_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp))
            write_song(artifacts, log_row="| 1 | <e.g. chorus to 8-syllable lines> | <why> | <kept> |")
            got = self.grade("worked-example-as-model", artifacts)
        self.assertEqual(got[4]["verdict"], "FAIL")
        self.assertIn("no filled entry", got[4]["detail"])


class FailureTests(unittest.TestCase):
    def test_overlong_style_fails_criterion_1(self) -> None:
        style = "x" * 250 + "\nEXCLUDE: EDM\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #1", res.stdout)
        self.assertIn("chars > 200", res.stdout)

    def test_empty_exclude_value_fails(self) -> None:
        style = GOOD_STYLE.splitlines()[0] + "\nEXCLUDE:\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("EXCLUDE line has no value", res.stdout)

    def test_missing_artifacts_fail_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp) / "empty"
            artifacts.mkdir()
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("artifact missing: style_prompt.txt", res.stdout)
        self.assertIn("artifact missing: lyrics.txt", res.stdout)

    def test_bad_lyrics_fail_validate_criterion(self) -> None:
        lyrics = "[Verse]\nonly a verse, no chorus, and far too long a line\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #3", res.stdout)
        self.assertIn("ERROR:", res.stdout)

    def test_missing_bilingual_stays_judge_on_criterion_4(self) -> None:
        # #4's "metered as 1 unit" conjunct keeps the whole criterion with
        # the judge; the bilingual check itself is pinned in DirectCheckTests.
        lyrics = "[Verse]\nenglish only lines here\n[Chorus]\nstill only english words\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("JUDGE  #4", res.stdout)


class UsageErrorTests(unittest.TestCase):
    def test_unknown_case_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cli("--case", "no-such-case", "--dir", tmp)
        self.assertEqual(res.returncode, 2)
        self.assertIn("unknown case", res.stderr)

    def test_no_case_without_coverage_exits_2(self) -> None:
        res = run_cli("--dir", "/tmp")
        self.assertEqual(res.returncode, 2)
        self.assertIn("--case and --dir are required", res.stderr)

    def test_missing_dir_exits_2(self) -> None:
        res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", "/no/such/dir")
        self.assertEqual(res.returncode, 2)
        self.assertIn("artifacts dir not found", res.stderr)

    def test_evals_top_level_list_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "evals.json"
            other.write_text("[]", encoding="utf-8")
            artifacts = make_artifacts(root)
            res = run_cli(
                "--case", "citypop-bilingual-leaving-home",
                "--dir", str(artifacts), "--evals", str(other),
            )
        self.assertEqual(res.returncode, 2)
        self.assertIn("invalid evals file", res.stderr)

    def test_non_utf8_artifact_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = make_artifacts(root)
            (artifacts / "style_prompt.txt").write_bytes(b"\xff\xfe\x00bad")
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 2)
        self.assertIn("unreadable artifact", res.stderr)

    def test_empty_criteria_exits_2(self) -> None:
        data = {"evals": [{"id": "empty-case", "prompt": "p", "success_criteria": []}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "evals.json"
            other.write_text(json.dumps(data), encoding="utf-8")
            artifacts = make_artifacts(root)
            res = run_cli(
                "--case", "empty-case", "--dir", str(artifacts), "--evals", str(other),
            )
        self.assertEqual(res.returncode, 2)
        self.assertIn("no success_criteria", res.stderr)


class DriftGuardTests(unittest.TestCase):
    def test_reworded_criterion_exits_2(self) -> None:
        data = json.loads(EVALS.read_text(encoding="utf-8"))
        case = next(c for c in data["evals"] if c["id"] == "citypop-bilingual-leaving-home")
        case["success_criteria"][0] = case["success_criteria"][0].replace(
            "single comma-separated string", "one comma-separated string"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "evals.json"
            other.write_text(json.dumps(data), encoding="utf-8")
            artifacts = make_artifacts(root)
            res = run_cli(
                "--case", "citypop-bilingual-leaving-home",
                "--dir", str(artifacts), "--evals", str(other),
            )
        self.assertEqual(res.returncode, 2)
        self.assertIn("criterion drift", res.stderr)

    def test_registry_sweep_no_drift_against_repo_spec(self) -> None:
        for case_id in run_evals.CHECKS:
            with tempfile.TemporaryDirectory() as tmp:
                artifacts = Path(tmp) / "empty"
                artifacts.mkdir()
                res = run_cli("--case", case_id, "--dir", str(artifacts))
            # 1 = required artifacts missing; 0 = the case only has checks on
            # the optional song.md, which go to the judge when unrecorded.
            self.assertIn(res.returncode, (0, 1), f"{case_id}: {res.stdout}{res.stderr}")
            self.assertNotIn("drift", res.stderr, case_id)

    def test_registry_ids_are_real_cases(self) -> None:
        data = json.loads(EVALS.read_text(encoding="utf-8"))
        ids = {c["id"] for c in data["evals"]}
        self.assertTrue(set(run_evals.CHECKS) <= ids)


class DirectCheckTests(unittest.TestCase):
    """Pass/fail pins for check helpers the registry no longer reaches
    (their criteria carry transcript conjuncts and stay JUDGE), plus the
    check_tag case-insensitivity contract."""

    def test_bilingual_requires_both_languages(self) -> None:
        bad_lyrics = (
            "[Verse 1]\n\u8def\u706f\u4e0b\u7684\u65e7\u7ad9\u53f0\n"
            "[Chorus]\n\u96e8\u58f0\u76d6\u8fc7\u544a\u522b\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = make_artifacts(root)
            bad_root = root / "b"
            bad_root.mkdir()
            bad = make_artifacts(bad_root, case="bad", lyrics=bad_lyrics)
            self.assertTrue(run_evals.check_bilingual(good)[0])
            ok, detail = run_evals.check_bilingual(bad)
        self.assertFalse(ok)
        self.assertIn("tags excluded", detail)

    def test_hook_bilingual_requires_both_languages(self) -> None:
        bad_lyrics = (
            "[Verse 1]\n\ub2e4\uc2dc \ud55c \ubc88\n"
            "[Chorus]\nchant it out now\n"
            "[Instrumental Break (dance break)]\n"
        )
        good_lyrics = (
            "[Verse 1]\nfirst line of the verse\n"
            "[Chorus]\nchant it out now\n\ub2e4\uc2dc \ud55c \ubc88 now\n"
            "[Instrumental Break (dance break)]\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = make_artifacts(root, case="bad", lyrics=bad_lyrics)
            good = make_artifacts(root, case="good", lyrics=good_lyrics)
            ok_bad, detail = run_evals.check_bilingual_sections(("chorus", "hook"))(bad)
            ok_good = run_evals.check_bilingual_sections(("chorus", "hook"))(good)[0]
        self.assertFalse(ok_bad)
        self.assertIn("CJK=False", detail)
        self.assertTrue(ok_good)

    def test_section_meter_range(self) -> None:
        long_line = WEDDING_LYRICS.replace(
            "carry our name into the light",
            "carry our family name into the morning light together",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = make_artifacts(root, case="bad", style=WEDDING_STYLE, lyrics=long_line)
            no_chorus_root = root / "c"
            no_chorus_root.mkdir()
            no_chorus = make_artifacts(
                no_chorus_root, style=WEDDING_STYLE,
                lyrics="[Verse 1]\nwe kept your room the way it was\n",
            )
            ok, detail = run_evals.check_section_meter(("chorus",), 6, 8)(bad)
            no_chorus_ok = run_evals.check_section_meter(("chorus",), 6, 8)(no_chorus)[0]
        self.assertFalse(ok)
        self.assertIn("outside 6-8 units", detail)
        self.assertFalse(no_chorus_ok)

    def test_section_meter_first_only_ignores_later_sections(self) -> None:
        loose_verse_two = TRAP_LYRICS.replace(
            "they said the door was never mine", "they said no"
        )
        bad_verse_one = TRAP_LYRICS.replace(
            "I count the seconds till the sun", "I count the hours"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ok_artifacts = make_artifacts(root, case="ok", style=TRAP_STYLE, lyrics=loose_verse_two)
            bad_root = root / "b"
            bad_root.mkdir()
            bad_artifacts = make_artifacts(bad_root, style=TRAP_STYLE, lyrics=bad_verse_one)
            ok, detail = run_evals.check_section_meter(("verse",), 8, 8, first_only=True)(ok_artifacts)
            bad_ok, bad_detail = run_evals.check_section_meter(("verse",), 8, 8, first_only=True)(bad_artifacts)
        self.assertTrue(ok, detail)
        self.assertFalse(bad_ok)
        self.assertIn("outside 8 units", bad_detail)

    def test_check_tag_contains_is_case_insensitive(self) -> None:
        lyrics = "[Verse 1]\none line\n[Instrumental Break (dance break)]\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            ok, detail = run_evals.check_tag(contains="Dance")(artifacts)
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
