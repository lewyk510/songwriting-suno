#!/usr/bin/env python3
"""Selftest for the whole songwriting-suno skill bundle.

One cwd-independent command that proves the bundle still works after any
self-update: script help responses, unit tests, freshness coverage, the
lyric tools on built-in fixtures, and JSON sanity of the asset files.

All paths are resolved from this script's own location (skill root =
parent of scripts/), so it runs from any working directory. Runs no network;
its only writes are throwaway directories (the install smoke destination and
the eval-runner artifacts) that the checks delete again — check failures are
evidence, never auto-fixed.

Checks (in order):
  1. help        every scripts/*.py CLI except selftest.py answers --help
                 with exit code 0 and a usage: line; modules without a CLI
                 (source_check.py) are SKIPped; scripts are auto-discovered
                 with Path.glob so future scripts are covered automatically
  2. unittest    python3 -m unittest discover over scripts/tests (and any
                 nested tests/ dir) — all tests must pass
  3. freshness   check_freshness.py --check-coverage exits 0
  4. evals       check_evals.py exits 0 on the repo's evals/evals.json
                 (structural contract: ids, fields, path references)
  5. runner      run_evals.py grades the built-in citypop artifact fixture
                 and must report 4 PASS / 0 FAIL (machine-checkable criteria
                 only; the rest is JUDGE)
  6. structure   validate_structure.py exits 0 on the built-in fixture
                 '[Verse]\nline one\n[Chorus]\nbig hook\n'
  7. meter       syllable_meter.py --expect 5,6 exits 0 on the built-in
                 fixture 'Hello world tonight\nI feel the city light\n'
  8. lyric_lint  lyric_lint.py exits 1 on a built-in cliche fixture
                 ('reach for the stars' / 'dance in the rain'), proving the
                 linter is wired end to end; SKIP if the script is absent
  9. json        evals/evals.json, assets/freshness.json and
                 assets/persona-presets.json each parse with json.load
 10. install     install.sh installs the bundle into a throwaway directory
                 with the payload present and repo-dev artifacts (.git,
                 .github, .gitignore, AGENTS.md) absent; SKIP without bash

Exit codes:
    0  no FAIL verdicts (SKIP allowed)
    1  at least one check FAILED
    2  usage error (argparse)

Usage:
  python3 selftest.py [--verbose] [--json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
Verdict = str  # one of PASS/FAIL/SKIP; kept a plain str alias for json output

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent

LYRIC_LINT = "lyric_lint.py"
STRUCTURE_FIXTURE = "[Verse]\nline one\n[Chorus]\nbig hook\n"
METER_FIXTURE = "Hello world tonight\nI feel the city light\n"
JSON_PATHS = (
    "evals/evals.json",
    "assets/freshness.json",
    "assets/persona-presets.json",
)
INSTALL_PAYLOAD = (
    "SKILL.md",
    "scripts/selftest.py",
    "references/00-index.md",
    "assets/freshness.json",
    "evals/evals.json",
)
INSTALL_ARTIFACTS = (
    ".git",
    ".github",
    ".gitignore",
    "AGENTS.md",
    "scripts/AGENTS.md",
    "scripts/__pycache__",
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One verified property of the bundle; verdict in {PASS, FAIL, SKIP}."""

    name: str
    verdict: Verdict
    detail: str


def run_tool(
    args: list[str], stdin_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with captured output; never raises on nonzero exit."""
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        input=stdin_text,
    )


def describe(proc: subprocess.CompletedProcess[str]) -> str:
    first = (proc.stdout or proc.stderr).strip().splitlines()
    head = first[0][:80] if first else "(no output)"
    return f"exit={proc.returncode} | {head}"


NO_CLI = {"selftest.py", "source_check.py"}


def check_help(script: Path) -> CheckResult | None:
    """Check 1: one CLI answers --help with usage text; None = not a target."""
    if script.name == "selftest.py":
        return None
    if script.name == "source_check.py":
        return CheckResult("help:source_check.py", SKIP, "module, not a CLI")
    proc = run_tool([str(script), "--help"])
    ok = proc.returncode == 0 and "usage:" in (proc.stdout or "")
    return CheckResult(f"help:{script.name}", PASS if ok else FAIL, describe(proc))


def script_help_checks() -> list[CheckResult]:
    return [r for r in map(check_help, sorted(SCRIPTS_DIR.glob("*.py"))) if r]


def tests_dirs() -> list[Path]:
    """scripts/tests itself plus any tests/ dir one level below scripts/."""
    candidates = {SCRIPTS_DIR / "tests"}
    candidates.update(SCRIPTS_DIR.glob("*/tests"))
    return sorted(d for d in candidates if d.is_dir())


def check_unittest(tests_dir: Path) -> CheckResult:
    """Check 2: unittest discovery over one tests dir (start == top-level
    so test modules import without scripts/tests/__init__.py)."""
    rel = tests_dir.relative_to(SCRIPTS_DIR).as_posix()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(tests_dir),
            "-t",
            str(tests_dir),
        ],
        capture_output=True,
        text=True,
    )
    verdict = PASS if proc.returncode == 0 else FAIL
    return CheckResult(f"unittest:{rel}", verdict, describe(proc))


def check_freshness_coverage() -> CheckResult:
    """Check 3: the freshness registry covers every references/*.md."""
    proc = run_tool(
        [str(SCRIPTS_DIR / "check_freshness.py"), "--check-coverage"]
    )
    verdict = PASS if proc.returncode == 0 else FAIL
    return CheckResult("freshness:coverage", verdict, describe(proc))


def check_evals_structure() -> CheckResult:
    """Check 8: evals/evals.json satisfies the structural contract."""
    proc = run_tool([str(SCRIPTS_DIR / "check_evals.py")])
    verdict = PASS if proc.returncode == 0 else FAIL
    return CheckResult("evals:structure", verdict, describe(proc))


def check_evals_runner() -> CheckResult:
    """Check 5: run_evals.py grades built-in artifacts, 4 PASS / 0 FAIL."""
    with tempfile.TemporaryDirectory(prefix="swsuno-eval-runner-") as tmp:
        artifacts = Path(tmp) / "art"
        artifacts.mkdir()
        (artifacts / "style_prompt.txt").write_text(
            "city-pop, melancholic, 92 BPM, retro synth, female vocal\nEXCLUDE: EDM\n",
            encoding="utf-8",
        )
        (artifacts / "lyrics.txt").write_text(
            "[Verse 1]\n\u8def\u706f\u4e0b\u7684\u65e7\u7ad9\u53f0\n[Chorus]\none more night in the rain\n",
            encoding="utf-8",
        )
        proc = run_tool(
            [
                str(SCRIPTS_DIR / "run_evals.py"),
                "--case",
                "citypop-bilingual-leaving-home",
                "--dir",
                str(artifacts),
                "--json",
            ]
        )
    try:
        summary = json.loads(proc.stdout)["summary"]
        ok = proc.returncode == 0 and summary["failed"] == 0 and summary["passed"] == 4
        detail = f"passed={summary['passed']}, failed={summary['failed']}, judge={summary['judge']}"
    except (json.JSONDecodeError, KeyError):
        ok, detail = False, describe(proc)
    return CheckResult("evals:runner", PASS if ok else FAIL, detail)


def check_lyric_lint_fixture() -> CheckResult:
    """Check 6: lyric_lint.py flags its built-in cliche fixture (exit 1)."""
    script = SCRIPTS_DIR / LYRIC_LINT
    if not script.is_file():
        return CheckResult("fixture:lyric_lint", SKIP, "script not present")
    proc = run_tool(
        [str(script), "--text", "[Chorus]\nwe reach for the stars\ndance in the rain"]
    )
    verdict = PASS if proc.returncode == 1 else FAIL
    return CheckResult("fixture:lyric_lint", verdict, describe(proc))


def check_json_file(rel_path: str) -> CheckResult:
    """Check 7: one JSON asset parses (or FAIL if missing/invalid)."""
    path = SKILL_ROOT / rel_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return CheckResult(f"json:{rel_path}", FAIL, str(exc))
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return CheckResult(f"json:{rel_path}", FAIL, str(exc))
    return CheckResult(f"json:{rel_path}", PASS, "parsed")


def check_install_smoke() -> CheckResult:
    """Check 9: install.sh lands the payload without repo-dev artifacts."""
    installer = SKILL_ROOT / "install.sh"
    bash = shutil.which("bash")
    if bash is None or not installer.is_file():
        return CheckResult("install:smoke", SKIP, "bash or install.sh not present")
    with tempfile.TemporaryDirectory(prefix="swsuno-install-smoke-") as tmp:
        dest = Path(tmp) / "skills" / "songwriting-suno"
        try:
            proc = subprocess.run(
                [bash, str(installer), str(Path(tmp) / "skills")],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            return CheckResult("install:smoke", FAIL, f"installer timed out: {exc}")
        problems: list[str] = []
        if proc.returncode != 0:
            problems.append(f"installer exit={proc.returncode}")
        problems.extend(f"missing {r}" for r in INSTALL_PAYLOAD if not (dest / r).is_file())
        problems.extend(f"leaked {r}" for r in INSTALL_ARTIFACTS if (dest / r).exists())
        verdict = FAIL if problems else PASS
        detail = "; ".join(problems) if problems else "payload present, artifacts excluded"
        return CheckResult("install:smoke", verdict, detail)


def run_checks() -> list[CheckResult]:
    checks: list[CheckResult] = []
    checks.extend(script_help_checks())
    checks.extend(check_unittest(d) for d in tests_dirs())
    checks.append(check_freshness_coverage())
    checks.append(check_evals_structure())
    checks.append(check_evals_runner())

    structure = run_tool(
        [str(SCRIPTS_DIR / "validate_structure.py")], STRUCTURE_FIXTURE
    )
    checks.append(
        CheckResult(
            "fixture:validate_structure",
            PASS if structure.returncode == 0 else FAIL,
            describe(structure),
        )
    )

    meter = run_tool(
        [str(SCRIPTS_DIR / "syllable_meter.py"), "--expect", "5,6"],
        METER_FIXTURE,
    )
    checks.append(
        CheckResult(
            "fixture:syllable_meter",
            PASS if meter.returncode == 0 else FAIL,
            describe(meter),
        )
    )

    checks.append(check_lyric_lint_fixture())
    checks.extend(check_json_file(rel) for rel in JSON_PATHS)
    checks.append(check_install_smoke())
    return checks


def render(checks: Iterable[CheckResult], verbose: bool) -> list[str]:
    lines: list[str] = []
    for check in checks:
        lines.append(f"{check.verdict} {check.name}")
        if check.verdict == FAIL or verbose:
            lines.append(f"    {check.detail}")
    return lines


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="selftest.py",
        description="Run the full self-check suite for the songwriting-suno skill bundle.",
        epilog=(
            "Exit code: 0 = no failures, 1 = at least one check failed.\n"
            "Example:\n"
            "  python3 %(prog)s --verbose\n"
            "  python3 %(prog)s --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--verbose", action="store_true", help="show captured output for all checks"
    )
    parser.add_argument("--json", action="store_true", help="emit results as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checks = run_checks()
    passed = sum(c.verdict == PASS for c in checks)
    failed = sum(c.verdict == FAIL for c in checks)
    skipped = sum(c.verdict == SKIP for c in checks)
    summary = f"{passed} passed, {failed} failed, {skipped} skipped"
    exit_code = 1 if failed else 0

    if args.json:
        print(
            json.dumps(
                {
                    "results": [
                        vars_check(c) for c in checks
                    ],
                    "summary": {
                        "passed": passed,
                        "failed": failed,
                        "skipped": skipped,
                    },
                    "exit_code": exit_code,
                },
                indent=2,
            )
        )
        return exit_code

    for line in render(checks, args.verbose):
        print(line)
    print(summary)
    return exit_code


def vars_check(check: CheckResult) -> dict[str, str]:
    return {
        "name": check.name,
        "verdict": check.verdict,
        "detail": check.detail,
    }


if __name__ == "__main__":
    sys.exit(main())
