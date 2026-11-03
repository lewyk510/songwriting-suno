#!/usr/bin/env python3
"""Grade one behavioral eval case from recorded artifacts (machine part).

evals/evals.json holds behavioral cases: a prompt, expected_behavior, and
success_criteria. Most criteria need a model-in-the-loop judge, but a subset
is deterministic given the artifacts a BUILD run leaves behind. This tool
grades exactly that subset and marks everything else JUDGE, so an evaluating
agent can: run the case, save the artifacts, machine-check what can be
machine-checked, and answer only the judgment items.

Artifact contract (files inside --dir):
  style_prompt.txt  exactly what format_style_prompt.py printed:
                    line 1 = the comma-separated style (<=200 chars),
                    line 2 = "EXCLUDE: ..." (may be "(none)")
  lyrics.txt        the final tagged lyric sheet ([Verse]/[Chorus]/...)

A PASS certifies the conjuncts the check actually inspected (the PASS detail
names them); conjuncts that need a process transcript or taste stay with the
JUDGE grader. Unregistered criteria are JUDGE wholesale.

Exit codes:
    0  no FAIL verdicts (PASS and JUDGE allowed)
    1  at least one criterion FAILED
    2  usage error, unknown case, unreadable input, or criterion drift
       (a registry fragment no longer matches evals.json — the spec changed
       under us)

Usage:
  python3 run_evals.py --case citypop-bilingual-leaving-home --dir artifacts/
  python3 run_evals.py --case <id> --dir <dir> --json
  python3 run_evals.py --case <id> --dir <dir> --evals other_evals.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
DEFAULT_EVALS = SKILL_ROOT / "evals" / "evals.json"
VALIDATE_SCRIPT = SCRIPTS_DIR / "validate_structure.py"

PASS = "PASS"
FAIL = "FAIL"
JUDGE = "JUDGE"

STYLE_ARTIFACT = "style_prompt.txt"
LYRICS_ARTIFACT = "lyrics.txt"
STYLE_CHAR_LIMIT = 200
VALIDATE_TIMEOUT_S = 30
# Same character class as syllable_meter.py / lyric_lint.py — change together.
CJK_RE = re.compile(
    r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)


class ArtifactError(Exception):
    """An artifact exists but cannot be read (bad encoding / IO error)."""


Check = Callable[[Path], tuple[bool, str]]


def is_tag_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def artifact_lines(dir_path: Path, name: str) -> list[str] | None:
    """Lines of one artifact; None = missing; ArtifactError = unreadable."""
    path = dir_path / name
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactError(f"unreadable artifact {name}: {exc}") from exc


def lyric_body(lines: list[str]) -> str:
    """Non-tag lines only, so bracket tags never count as lyric content."""
    return "\n".join(line for line in lines if not is_tag_line(line))


def section_tags(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if is_tag_line(line)]


def check_style(
    must_contain: tuple[str, ...] = (),
    must_contain_any: tuple[str, ...] = (),
    must_not_contains: tuple[str, ...] = (),
    require_commas: bool = False,
) -> Check:
    """Line 1: budget, commas, descriptor conjuncts; line 2: EXCLUDE line."""

    def check(dir_path: Path) -> tuple[bool, str]:
        lines = artifact_lines(dir_path, STYLE_ARTIFACT)
        if lines is None:
            return False, f"artifact missing: {STYLE_ARTIFACT}"
        if not lines or not lines[0].strip():
            return False, f"{STYLE_ARTIFACT} has no style line"
        style = lines[0].strip()
        lowered = style.lower()
        problems: list[str] = []
        if len(style) > STYLE_CHAR_LIMIT:
            problems.append(f"style is {len(style)} chars > {STYLE_CHAR_LIMIT}")
        if require_commas and "," not in style:
            problems.append("style is not comma-separated")
        for needle in must_contain:
            if needle.lower() not in lowered:
                problems.append(f"style lacks {needle!r}")
        if must_contain_any and not any(
            needle.lower() in lowered for needle in must_contain_any
        ):
            problems.append(f"style lacks any of {must_contain_any!r}")
        for banned in must_not_contains:
            if banned.lower() in lowered:
                problems.append(f"style has banned tag {banned!r}")
        if len(lines) < 2 or not lines[1].startswith("EXCLUDE:"):
            problems.append("no EXCLUDE: line")
        elif not lines[1][len("EXCLUDE:") :].strip():
            problems.append("EXCLUDE line has no value")
        if problems:
            return False, "; ".join(problems)
        checked = ["<=200 chars", "EXCLUDE line"]
        if require_commas:
            checked.append("comma-separated")
        if must_contain or must_contain_any:
            checked.append("required descriptors")
        if must_not_contains:
            checked.append("no banned tags")
        return True, f"checked: {', '.join(checked)}"

    return check


def check_validate_exit0(dir_path: Path) -> tuple[bool, str]:
    lyrics = dir_path / LYRICS_ARTIFACT
    if not lyrics.is_file():
        return False, f"artifact missing: {LYRICS_ARTIFACT}"
    try:
        proc = subprocess.run(
            [sys.executable, str(VALIDATE_SCRIPT), str(lyrics)],
            capture_output=True,
            text=True,
            timeout=VALIDATE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, f"validate_structure timed out after {VALIDATE_TIMEOUT_S}s"
    if proc.returncode != 0:
        errors = [
            line.strip()
            for line in (proc.stdout or "").splitlines()
            if line.startswith("ERROR:")
        ]
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        detail = errors[0] if errors else (tail[-1] if tail else "")
        return False, f"validate_structure exit={proc.returncode}: {detail[:70]}"
    return True, "validate_structure exit 0"


def check_section_balance(max_gap: int = 1) -> Check:
    """Verse/chorus tag counts differ by at most `max_gap`.

    validate_structure only WARNS on this, so the exit code alone can never
    fail it; count the tags here instead (same prefix classification).
    """

    def check(dir_path: Path) -> tuple[bool, str]:
        lines = artifact_lines(dir_path, LYRICS_ARTIFACT)
        if lines is None:
            return False, f"artifact missing: {LYRICS_ARTIFACT}"
        names = [tag[1:-1].strip().lower() for tag in section_tags(lines)]
        verses = sum(name.startswith("verse") for name in names)
        choruses = sum(name.startswith("chorus") for name in names)
        gap = abs(verses - choruses)
        detail = f"{verses} [Verse] vs {choruses} [Chorus], gap {gap}"
        return gap <= max_gap, f"{detail} (max {max_gap})"

    return check


def check_tag(prefix: str = "", contains: str = "") -> Check:
    """A tag whose name starts with `prefix` or contains `contains` (case-insensitive)."""

    def check(dir_path: Path) -> tuple[bool, str]:
        lines = artifact_lines(dir_path, LYRICS_ARTIFACT)
        if lines is None:
            return False, f"artifact missing: {LYRICS_ARTIFACT}"
        lowered = [tag.lower() for tag in section_tags(lines)]
        if prefix and any(tag.startswith(f"[{prefix}".lower()) for tag in lowered):
            return True, f"tag [{prefix}...] present"
        if contains and any(contains in tag for tag in lowered):
            return True, f"tag containing {contains!r} present"
        return False, f"no matching section tag ({prefix or contains})"

    return check


def check_bilingual(dir_path: Path) -> tuple[bool, str]:
    """CJK and Latin must both appear in LYRIC lines (tags excluded)."""
    lines = artifact_lines(dir_path, LYRICS_ARTIFACT)
    if lines is None:
        return False, f"artifact missing: {LYRICS_ARTIFACT}"
    body = lyric_body(lines)
    cjk = CJK_RE.search(body)
    latin = any(ch.isascii() and ch.isalpha() for ch in body)
    if cjk and latin:
        return (
            True,
            "CJK and Latin lyric lines present (tags excluded; "
            "per-character metering stays with the judge)",
        )
    return False, f"CJK lyric text={bool(cjk)}, Latin lyric text={latin} (tags excluded)"


def check_all(*checks: Check) -> Check:
    """Every check must pass; details are joined so each conjunct is visible."""

    def check(dir_path: Path) -> tuple[bool, str]:
        results = [one(dir_path) for one in checks]
        return all(ok for ok, _detail in results), "; ".join(
            detail for _ok, detail in results
        )

    return check


# Registry: case id -> {criterion index (0-based) -> (drift fragment, check)}.
# A fragment MUST appear verbatim in that criterion's text in evals.json;
# if the spec is reworded, run_evals exits 2 instead of checking the wrong
# thing. Criteria absent from the registry are graded JUDGE.
CHECKS: dict[str, dict[int, tuple[str, Check]]] = {
    "citypop-bilingual-leaving-home": {
        0: ("single comma-separated string", check_style(require_commas=True)),
        1: (
            "at least one [Chorus]",
            check_all(check_tag(prefix="Chorus"), check_validate_exit0),
        ),
        2: ("exits 0 on the final lyrics", check_validate_exit0),
        3: ("Both Chinese and English", check_bilingual),
    },
    "wedding-acoustic-ballad": {
        0: (
            "72 BPM",
            check_style(
                must_contain=("72 BPM",), must_contain_any=("acoustic", "ballad")
            ),
        ),
    },
    "trap-motivation-tight-meter": {
        0: (
            "140 BPM",
            check_style(
                must_contain=("140 BPM",),
                must_contain_any=("trap", "808", "hip-hop", "hip hop"),
            ),
        ),
        3: ("validate_structure.py exits 0", check_validate_exit0),
    },
    "lofi-study-instrumental": {
        0: (
            "[Instrumental ...] exists",
            check_all(check_tag(prefix="Instrumental"), check_validate_exit0),
        ),
        1: ("Any sung section has lyric lines", check_validate_exit0),
        2: (
            "<=200 chars with lo-fi descriptors",
            check_style(
                must_contain_any=("lo-fi", "lofi", "chill", "mellow", "study", "soft"),
                must_not_contains=("screaming", "shouting", "belt", "belting", "loud vocal"),
            ),
        ),
    },
    "kpop-girlgroup-debut": {
        0: (
            "tagged dance break section",
            check_all(check_tag(contains="dance"), check_tag(prefix="Chorus")),
        ),
        1: (
            "exits 0 with no more than",
            check_all(check_validate_exit0, check_section_balance(1)),
        ),
        4: ("EXCLUDE line present", check_style()),
    },
    "worked-example-as-model": {
        0: (
            "one comma-separated string <=200 chars",
            check_style(require_commas=True),
        ),
    },
}


def load_case(
    evals_path: Path, case_id: str
) -> tuple[tuple[str, list[str]] | None, list[str]]:
    """((case id, criteria) or None, usage/drift errors). Errors mean exit 2."""
    try:
        data = json.loads(evals_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # ValueError: JSON + Unicode decode
        return None, [f"cannot read evals file {evals_path}: {exc}"]
    if not isinstance(data, dict) or not isinstance(data.get("evals"), list):
        return None, [f"invalid evals file {evals_path}: expected an object with an 'evals' list"]
    case = next(
        (c for c in data["evals"] if isinstance(c, dict) and c.get("id") == case_id),
        None,
    )
    if case is None:
        ids = ", ".join(
            str(c.get("id", "?")) for c in data["evals"] if isinstance(c, dict)
        )
        return None, [f"unknown case {case_id!r}; known: {ids}"]
    criteria = case.get("success_criteria", [])
    if not isinstance(criteria, list) or not all(isinstance(c, str) for c in criteria):
        return None, [f"case {case_id}: success_criteria is not a list of strings"]
    if not criteria:
        return None, [f"case {case_id}: no success_criteria to grade"]
    errors: list[str] = []
    for index, (fragment, _check) in CHECKS.get(case_id, {}).items():
        if index >= len(criteria) or fragment not in criteria[index]:
            errors.append(
                f"criterion drift for {case_id} #{index + 1}: "
                f"fragment {fragment!r} not found — update CHECKS"
            )
    if errors:
        return None, errors
    return (case_id, criteria), []


def grade(
    case_id: str, criteria: list[str], artifacts: Path
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    registry = CHECKS.get(case_id, {})
    for index, criterion in enumerate(criteria):
        entry = registry.get(index)
        if entry is None:
            results.append(
                {
                    "index": index + 1,
                    "verdict": JUDGE,
                    "criterion": criterion,
                    "detail": "needs model-in-the-loop judgment",
                }
            )
            continue
        ok, detail = entry[1](artifacts)
        results.append(
            {
                "index": index + 1,
                "verdict": PASS if ok else FAIL,
                "criterion": criterion,
                "detail": detail,
            }
        )
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_evals.py",
        description="Grade the machine-checkable criteria of one eval case from recorded artifacts.",
        epilog=(
            "Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = usage or criterion drift.\n"
            "Example:\n"
            "  python3 %(prog)s --case citypop-bilingual-leaving-home --dir artifacts/"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--case", required=True, help="eval case id from evals/evals.json")
    parser.add_argument("--dir", required=True, help="directory holding style_prompt.txt / lyrics.txt")
    parser.add_argument("--evals", default=str(DEFAULT_EVALS), help="evals.json to grade against (default: the bundle's)")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifacts = Path(args.dir)
    if not artifacts.is_dir():
        print(f"artifacts dir not found: {artifacts}", file=sys.stderr)
        return 2
    case, errors = load_case(Path(args.evals), args.case)
    if case is None:
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    try:
        results = grade(case[0], case[1], artifacts)
    except ArtifactError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    passed = sum(r["verdict"] == PASS for r in results)
    failed = sum(r["verdict"] == FAIL for r in results)
    judged = sum(r["verdict"] == JUDGE for r in results)
    exit_code = 1 if failed else 0

    if args.json:
        print(json.dumps(
            {"case": case[0], "results": results,
             "summary": {"passed": passed, "failed": failed, "judge": judged},
             "exit_code": exit_code},
            ensure_ascii=False, indent=2,
        ))
        return exit_code

    print(f"case: {case[0]}")
    for r in results:
        print(f"{r['verdict']:5}  #{r['index']} {r['criterion']}")
        if r["verdict"] == FAIL:
            print(f"         -> {r['detail']}")
    print(f"{passed} PASS, {failed} FAIL, {judged} JUDGE")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
