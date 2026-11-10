"""Tests for scripts/check_freshness.py and scripts/format_style_prompt.py (pinned contract).

Every check_freshness case drives the real script through subprocess so exit
codes are real. Fixtures are disposable skill trees under tempfile:
<tmp>/skill/ with assets/freshness.json and references/ files. All runs pass
--registry explicitly so the suite never depends on the real skill's assets
directory. format_style_prompt cases drive that script via subprocess too.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check_freshness.py"
FORMAT_SCRIPT = Path(__file__).resolve().parent.parent / "format_style_prompt.py"

TIERS = {
    "high": {"warn_days": 30, "stale_days": 60},
    "medium": {"warn_days": 90, "stale_days": 180},
    "low": {"warn_days": 365, "stale_days": 730},
}


def entry(
    volatility: str, days_ago: int, sources: list[str] | None = None
) -> dict:
    """A registry entry whose last_verified is exactly `days_ago` days back."""
    return {
        "volatility": volatility,
        "last_verified": (date.today() - timedelta(days=days_ago)).isoformat(),
        "sources": ["https://example.com/source"] if sources is None else sources,
        "notes": "test entry",
    }


class SkillFixture:
    """Disposable skill tree: <root>/skill/{assets/freshness.json, references/}."""

    def __init__(self, root: Path) -> None:
        self.skill = root / "skill"
        self.registry_path = self.skill / "assets" / "freshness.json"

    def write_registry(
        self, entries: dict, *, schema: int = 1, create_entries: bool = True
    ) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry = {
            "schema": schema,
            "updated": date.today().isoformat(),
            "tiers": TIERS,
            "entries": entries,
        }
        self.registry_path.write_text(json.dumps(registry), encoding="utf-8")
        if create_entries:
            for rel_path in entries:
                target = self.skill / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("placeholder\n", encoding="utf-8")

    def write_raw_registry(self, text: str) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(text, encoding="utf-8")

    def add_file(self, rel_path: str) -> None:
        target = self.skill / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# doc\n", encoding="utf-8")

    def run(
        self, *extra_args: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess:
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--registry",
            str(self.registry_path),
            *extra_args,
        ]
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=None if cwd is None else str(cwd)
        )


class CheckFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SCRIPT.is_file(), f"script missing: {SCRIPT}")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.fx = SkillFixture(Path(tmp.name))

    # --- case 1: fresh registry -> exit 0, all OK -------------------------
    def test_fresh_registry_exits_zero_all_ok(self) -> None:
        self.fx.write_registry({"references/a.md": entry("high", 0)})
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("references/a.md", proc.stdout)
        self.assertIn("1 entries: 1 OK, 0 warning, 0 stale", proc.stdout)

    # --- case 2: high tier, 70 days -> STALE, exit 1 ----------------------
    def test_high_tier_70_days_is_stale_exit_1(self) -> None:
        self.fx.write_registry({"references/a.md": entry("high", 70)})
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        stale_rows = [
            line for line in proc.stdout.splitlines() if line.startswith("STALE")
        ]
        self.assertEqual(len(stale_rows), 1, proc.stdout)
        self.assertIn("references/a.md", stale_rows[0])

    # --- case 3: medium tier, 120 days (90 < age <= 180) -> WARNING, exit 0
    def test_medium_tier_120_days_is_warning_exit_0(self) -> None:
        self.fx.write_registry({"references/a.md": entry("medium", 120)})
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        warning_rows = [
            line for line in proc.stdout.splitlines() if line.startswith("WARNING")
        ]
        self.assertEqual(len(warning_rows), 1, proc.stdout)
        self.assertIn("references/a.md", warning_rows[0])
        self.assertNotIn("STALE", proc.stdout)

    # --- case 4: low tier, 400 days -> WARNING (stale only past 730) ------
    def test_low_tier_400_days_is_warning_not_stale(self) -> None:
        self.fx.write_registry({"references/a.md": entry("low", 400)})
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        warning_rows = [
            line for line in proc.stdout.splitlines() if line.startswith("WARNING")
        ]
        self.assertEqual(len(warning_rows), 1, proc.stdout)
        self.assertNotIn("STALE", proc.stdout)
        self.assertIn("1 entries: 0 OK, 1 warning, 0 stale", proc.stdout)

    # --- case 5: registry path missing -> exit 2 ---------------------------
    def test_missing_registry_exits_2(self) -> None:
        proc = self.fx.run()  # registry file is never written
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip(), "expected an error message on stderr")

    # --- case 6: malformed JSON -> exit 2 ----------------------------------
    def test_malformed_json_exits_2(self) -> None:
        self.fx.write_raw_registry("{definitely not json")
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())

    # --- case 7: unknown schema (schema:2) -> exit 2 -----------------------
    def test_unknown_schema_exits_2(self) -> None:
        self.fx.write_registry({"references/a.md": entry("high", 0)}, schema=2)
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("schema", proc.stderr.lower())

    # --- case 8: entry path not on disk -> exit 2 --------------------------
    def test_missing_entry_file_exits_2(self) -> None:
        self.fx.write_registry(
            {"references/ghost.md": entry("high", 0)}, create_entries=False
        )
        proc = self.fx.run()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ghost.md", proc.stderr)

    # --- case 9: --json parses, pinned keys, summary counts ----------------
    def test_json_output_has_pinned_shape_and_counts(self) -> None:
        self.fx.write_registry(
            {
                "references/ok.md": entry("high", 0),
                "references/warn.md": entry("medium", 120),
                "references/stale.md": entry("high", 70),
            }
        )
        proc = self.fx.run("--json")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        data = json.loads(proc.stdout)  # stdout must be pure, valid JSON
        self.assertEqual(
            set(data),
            {"schema", "updated", "checked_date", "entries", "summary", "exit_code"},
        )
        self.assertEqual(data["exit_code"], 1)
        self.assertEqual(
            data["summary"],
            {
                "ok": 1,
                "warning": 1,
                "stale": 1,
                "unregistered": [],
                "bad_sources": [],
            },
        )
        by_path = {row["path"]: row for row in data["entries"]}
        self.assertEqual(by_path["references/ok.md"]["status"], "OK")
        self.assertEqual(by_path["references/ok.md"]["age_days"], 0)
        self.assertEqual(by_path["references/warn.md"]["status"], "WARNING")
        self.assertEqual(by_path["references/stale.md"]["status"], "STALE")
        for row in data["entries"]:
            self.assertEqual(
                set(row),
                {
                    "path",
                    "volatility",
                    "last_verified",
                    "age_days",
                    "status",
                    "sources",
                },
            )
            self.assertEqual(row["sources"], ["https://example.com/source"])

    # --- case 10: --stale-only hides OK rows, keeps summary ----------------
    def test_stale_only_hides_ok_rows(self) -> None:
        self.fx.write_registry(
            {
                "references/ok.md": entry("high", 0),
                "references/stale.md": entry("high", 70),
            }
        )
        proc = self.fx.run("--stale-only")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertNotIn("references/ok.md", proc.stdout)
        self.assertIn("references/stale.md", proc.stdout)
        self.assertIn("2 entries: 1 OK, 0 warning, 1 stale", proc.stdout)

    # --- case 11: --check-coverage flags unregistered references/*.md ------
    def test_check_coverage_flags_unregistered_reference(self) -> None:
        self.fx.write_registry({"references/known.md": entry("medium", 10)})
        self.fx.add_file("references/foo.md")
        proc = self.fx.run("--check-coverage")
        self.assertEqual(proc.returncode, 1, proc.stdout)  # coverage alone -> exit 1
        unregistered = [
            line
            for line in proc.stdout.splitlines()
            if line.startswith("UNREGISTERED:")
        ]
        self.assertEqual(len(unregistered), 1, proc.stdout)
        self.assertIn("references/foo.md", unregistered[0])
        self.assertNotIn("UNREGISTERED: references/known.md", proc.stdout)

    # --- case 12: same result from a different cwd -------------------------
    def test_runs_from_a_different_cwd(self) -> None:
        self.fx.write_registry({"references/a.md": entry("high", 0)})
        proc = self.fx.run(cwd=self.fx.skill.parent)  # tempdir, not the skill root
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("1 entries: 1 OK, 0 warning, 0 stale", proc.stdout)

    # --- case 13: --check-sources accepts well-formed sources --------------
    def test_check_sources_accepts_well_formed_urls(self) -> None:
        self.fx.write_registry(
            {
                "references/a.md": entry(
                    "high",
                    0,
                    sources=[
                        "https://help.suno.com/en/articles/123",
                        "https://example.com/source",
                        "http://sub.example.org:8080/guide?x=1#top",
                    ],
                )
            }
        )
        proc = self.fx.run("--check-sources", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(data["summary"]["bad_sources"], [])
        self.assertNotIn("BAD-SOURCE", proc.stdout)

    # --- case 14: --check-sources flags a glued-on host ---------------------
    def test_check_sources_flags_glued_host(self) -> None:
        glued = "https://www.example.orgPooja"
        self.fx.write_registry(
            {
                "references/a.md": entry(
                    "high", 70, sources=["https://example.com/ok", glued]
                )
            }
        )
        proc = self.fx.run("--check-sources")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        bad = [line for line in proc.stdout.splitlines() if line.startswith("BAD-SOURCE")]
        self.assertEqual(len(bad), 1, proc.stdout)
        self.assertIn(f"BAD-SOURCE: references/a.md :: {glued} :: ", bad[0])

    # --- case 15: --check-sources flags an ellipsis URL ---------------------
    def test_check_sources_flags_ellipsis_url(self) -> None:
        for ellipsis_url in ("https://help.suno.com/…", "https://help.suno.com/..."):
            with self.subTest(ellipsis_url=ellipsis_url):
                self.fx.write_registry(
                    {"references/a.md": entry("high", 0, sources=[ellipsis_url])}
                )
                proc = self.fx.run("--check-sources", "--json")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                data = json.loads(proc.stdout)
                self.assertEqual(len(data["summary"]["bad_sources"]), 1, proc.stdout)
                finding = data["summary"]["bad_sources"][0]
                self.assertEqual(finding["source"], ellipsis_url)
                self.assertIn("ellipsis", finding["reason"])

    # --- case 16: default run (no flags) must NOT report bad sources --------
    def test_without_source_flags_glued_url_is_not_reported(self) -> None:
        self.fx.write_registry(
            {"references/a.md": entry("high", 0, sources=["https://www.example.orgPooja"])}
        )
        proc = self.fx.run()  # no --check-sources: legacy behavior preserved
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("BAD-SOURCE", proc.stdout)

    # --- case 17: --check-coverage implies --check-sources -------------------
    def test_check_coverage_implies_check_sources(self) -> None:
        glued = "https://www.example.orgPooja"
        self.fx.write_registry(
            {"references/a.md": entry("medium", 10, sources=[glued])}
        )
        proc = self.fx.run("--check-coverage")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertNotIn("UNREGISTERED:", proc.stdout)  # coverage is clean...
        bad = [line for line in proc.stdout.splitlines() if line.startswith("BAD-SOURCE")]
        self.assertEqual(len(bad), 1, proc.stdout)  # ...only sources flagged it
        self.assertIn(f"BAD-SOURCE: references/a.md :: {glued} :: ", bad[0])


class FormatStylePromptLimitTests(unittest.TestCase):
    def run_format(
        self, *extra_args: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(FORMAT_SCRIPT), *extra_args]
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=None if cwd is None else str(cwd)
        )

    def test_non_positive_tempo_exits_2(self) -> None:
        for tempo in ("0", "-5"):
            proc = self.run_format("--genre", "pop", f"--tempo={tempo}")
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertIn("must be a positive integer", proc.stderr)

    def test_default_limit_is_200_with_matching_warning(self) -> None:
        long_tag = "x" * 250
        proc = self.run_format("--genre", long_tag)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(
            proc.stderr.startswith("WARNING: style prompt exceeded 200 chars;"),
            proc.stderr,
        )
        self.assertLessEqual(len(proc.stdout.splitlines()[0]), 200)

    def test_limit_widens_budget_no_warning(self) -> None:
        long_tag = "x" * 250
        proc = self.run_format("--genre", long_tag, "--limit", "500")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertIn("x" * 250, proc.stdout)

    def test_limit_narrows_budget_warning_mentions_limit(self) -> None:
        long_tag = "x" * 250
        proc = self.run_format("--genre", long_tag, "--limit", "50")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(
            proc.stderr.startswith("WARNING: style prompt exceeded 50 chars;"),
            proc.stderr,
        )
        self.assertLessEqual(len(proc.stdout.splitlines()[0]), 50)

    def test_limit_rejects_non_positive_and_non_integer(self) -> None:
        for bad_value in ("0", "-3", "abc"):
            with self.subTest(limit=bad_value):
                proc = self.run_format("--genre", "synth-pop", "--limit", bad_value)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertNotIn("exceeded", proc.stderr)
        proc = self.run_format("--genre", "synth-pop", "--limit", "0")
        self.assertIn("positive integer", proc.stderr)


if __name__ == "__main__":
    unittest.main()
