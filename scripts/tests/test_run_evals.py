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
        self.assertIn("4 PASS, 0 FAIL, 1 JUDGE", res.stdout)
        self.assertIn("PASS   #1", res.stdout)
        self.assertIn("PASS   #4", res.stdout)
        self.assertIn("JUDGE  #5", res.stdout)

    def test_json_mode_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp))
            res = run_cli(
                "--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts), "--json"
            )
        self.assertEqual(res.returncode, 0)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["case"], "citypop-bilingual-leaving-home")
        self.assertEqual(payload["summary"], {"passed": 4, "failed": 0, "judge": 1})
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
            "[Chorus]\nchant it out now\nchant it louder now\n"
            "[Instrumental Break (dance break)]\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), style=style, lyrics=lyrics)
            res = run_cli("--case", "kpop-girlgroup-debut", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("3 PASS, 0 FAIL, 2 JUDGE", res.stdout)

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

    def test_wedding_and_trap_style_checks_pass(self) -> None:
        wedding = "acoustic ballad, fingerpicked guitar, 72 BPM, warm\nEXCLUDE: (none)\n"
        trap = "dark trap, 808 bass, 140 BPM, menacing\nEXCLUDE: autotune\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            w = make_artifacts(root, style=wedding, case="w")
            t = make_artifacts(root, style=trap, case="t")
            res_w = run_cli("--case", "wedding-acoustic-ballad", "--dir", str(w))
            res_t = run_cli("--case", "trap-motivation-tight-meter", "--dir", str(t))
        self.assertEqual(res_w.returncode, 0, res_w.stdout)
        self.assertIn("1 PASS, 0 FAIL, 4 JUDGE", res_w.stdout)
        self.assertEqual(res_t.returncode, 0, res_t.stdout)
        self.assertIn("2 PASS, 0 FAIL, 3 JUDGE", res_t.stdout)

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
        self.assertIn("4 PASS, 0 FAIL, 1 JUDGE", res.stdout)


class FalsePositiveProbeTests(unittest.TestCase):
    def test_chinese_only_lyrics_with_english_tags_fail_bilingual(self) -> None:
        lyrics = "[Verse 1]\n\u8def\u706f\u4e0b\u7684\u65e7\u7ad9\u53f0\n[Chorus]\n\u96e8\u58f0\u76d6\u8fc7\u544a\u522b\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #4", res.stdout)
        self.assertIn("tags excluded", res.stdout)

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

    def test_missing_bilingual_fails_criterion_4(self) -> None:
        lyrics = "[Verse]\nenglish only lines here\n[Chorus]\nstill only english words\n"
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = make_artifacts(Path(tmp), lyrics=lyrics)
            res = run_cli("--case", "citypop-bilingual-leaving-home", "--dir", str(artifacts))
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL   #4", res.stdout)


class UsageErrorTests(unittest.TestCase):
    def test_unknown_case_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cli("--case", "no-such-case", "--dir", tmp)
        self.assertEqual(res.returncode, 2)
        self.assertIn("unknown case", res.stderr)

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
            self.assertEqual(res.returncode, 1, f"{case_id}: {res.stdout}{res.stderr}")
            self.assertNotIn("drift", res.stderr, case_id)

    def test_registry_ids_are_real_cases(self) -> None:
        data = json.loads(EVALS.read_text(encoding="utf-8"))
        ids = {c["id"] for c in data["evals"]}
        self.assertTrue(set(run_evals.CHECKS) <= ids)


if __name__ == "__main__":
    unittest.main()
