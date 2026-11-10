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
  song.md           optional: the finished song as emitted through
                    assets/song-template.md. The template-order,
                    filled-section and iteration-log checks read it; when it
                    is not recorded those criteria are graded JUDGE, not FAIL.

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
  python3 run_evals.py --coverage      # machine-checkable share per case
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import syllable_meter
import validate_structure

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
DEFAULT_EVALS = SKILL_ROOT / "evals" / "evals.json"
VALIDATE_SCRIPT = SCRIPTS_DIR / "validate_structure.py"

PASS = "PASS"
FAIL = "FAIL"
JUDGE = "JUDGE"

STYLE_ARTIFACT = "style_prompt.txt"
LYRICS_ARTIFACT = "lyrics.txt"
SONG_ARTIFACT = "song.md"
TEMPLATE_PATH = SKILL_ROOT / "assets" / "song-template.md"
SONG_NOT_RECORDED = f"{SONG_ARTIFACT} not recorded, so not machine-checked"
STYLE_CHAR_LIMIT = 200
VALIDATE_TIMEOUT_S = 30
# Same character class as syllable_meter.py / lyric_lint.py — change together.
CJK_RE = re.compile(
    r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)


class ArtifactError(Exception):
    """An artifact exists but cannot be read (bad encoding / IO error)."""


# A check answers True (PASS), False (FAIL), or None (JUDGE: the optional
# artifact it needs was not recorded, so the criterion goes to the judge).
Verdict = tuple[bool | None, str]
Check = Callable[[Path], Verdict]


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

    def check(dir_path: Path) -> Verdict:
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


def check_validate_exit0(dir_path: Path) -> Verdict:
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

    def check(dir_path: Path) -> Verdict:
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

    def check(dir_path: Path) -> Verdict:
        lines = artifact_lines(dir_path, LYRICS_ARTIFACT)
        if lines is None:
            return False, f"artifact missing: {LYRICS_ARTIFACT}"
        lowered = [tag.lower() for tag in section_tags(lines)]
        if prefix and any(tag.startswith(f"[{prefix}".lower()) for tag in lowered):
            return True, f"tag [{prefix}...] present"
        if contains and any(contains.lower() in tag for tag in lowered):
            return True, f"tag containing {contains!r} present"
        return False, f"no matching section tag ({prefix or contains})"

    return check


LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def has_latin_line(lines: list[str]) -> bool:
    """A line with at least two Latin words, so a lone "(hey)" is not a language."""
    return any(len(LATIN_WORD_RE.findall(line)) >= 2 for line in lines)


def check_bilingual(dir_path: Path) -> Verdict:
    """CJK and Latin must both appear in LYRIC lines (tags excluded)."""
    lines = artifact_lines(dir_path, LYRICS_ARTIFACT)
    if lines is None:
        return False, f"artifact missing: {LYRICS_ARTIFACT}"
    body = lyric_body(lines)
    cjk = CJK_RE.search(body)
    latin = has_latin_line(body.splitlines())
    if cjk and latin:
        return (
            True,
            "CJK and Latin lyric lines present (tags excluded; "
            "per-character metering stays with the judge)",
        )
    return False, (
        f"CJK lyric text={bool(cjk)}, Latin lyric line (>=2 words)={latin} (tags excluded)"
    )


def lyric_sections(dir_path: Path) -> list[tuple[str, list[str]]] | None:
    """(lowercased tag name, non-blank lyric lines) per section; None = no artifact.

    Uses validate_structure.parse_sections so tags are classified the same
    way the validator classifies them.
    """
    lines = artifact_lines(dir_path, LYRICS_ARTIFACT)
    if lines is None:
        return None
    sections, _preamble = validate_structure.parse_sections(lines)
    return [
        (s["tag"].lower(), [ln.strip() for ln in s["lines"] if ln.strip()])
        for s in sections
    ]


def units(line: str) -> int:
    """Meter units exactly as syllable_meter.py prints them (CJK char = 1)."""
    return syllable_meter.count_line(line, "auto")[0]


def check_section_meter(
    prefixes: tuple[str, ...], low: int, high: int, first_only: bool = False
) -> Check:
    """Every lyric line in the matching sections meters to low..high units."""

    def check(dir_path: Path) -> Verdict:
        sections = lyric_sections(dir_path)
        if sections is None:
            return False, f"artifact missing: {LYRICS_ARTIFACT}"
        matched = [
            (tag, body) for tag, body in sections if tag.startswith(prefixes) and body
        ]
        if first_only:
            matched = matched[:1]
        if not matched:
            return False, f"no sung section tagged [{'/'.join(prefixes)}...]"
        span = str(low) if low == high else f"{low}-{high}"
        bad = [
            f"[{tag}] {line!r} = {units(line)}"
            for tag, body in matched
            for line in body
            if not low <= units(line) <= high
        ]
        if bad:
            return False, f"{len(bad)} line(s) outside {span} units: {bad[0]}"
        count = sum(len(body) for _tag, body in matched)
        return True, (
            f"{count} line(s) in [{'/'.join(prefixes)}...] meter to {span} units "
            "(syllable_meter heuristic; showing its output stays with the judge)"
        )

    return check


def check_hook(max_distinct: int = 2, min_repeats: int = 2) -> Check:
    """The hook holds <= max_distinct distinct lines, each sung >= min_repeats times."""

    def norm(line: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", line.lower())).strip()

    def check(dir_path: Path) -> Verdict:
        sections = lyric_sections(dir_path)
        if sections is None:
            return False, f"artifact missing: {LYRICS_ARTIFACT}"
        # [Hook] sections are the hook; only a sheet without one falls back to
        # [Chorus], so a full chorus beside a short hook is not miscounted.
        hooks = [body for tag, body in sections if tag.startswith("hook")] or [
            body for tag, body in sections if tag.startswith("chorus")
        ]
        distinct = {norm(line) for body in hooks for line in body} - {""}
        if not distinct:
            return False, "no lyric lines under a [Hook]/[Chorus] tag"
        if len(distinct) > max_distinct:
            return False, f"hook has {len(distinct)} distinct lines > {max_distinct}"
        sheet = [norm(line) for _tag, body in sections for line in body]
        rare = sorted(line for line in distinct if sheet.count(line) < min_repeats)
        if rare:
            return False, f"hook line sung fewer than {min_repeats} times: {rare[0]!r}"
        return True, (
            f"{len(distinct)} distinct hook line(s), each sung >= {min_repeats} times"
        )

    return check


def check_bilingual_sections(prefixes: tuple[str, ...]) -> Check:
    """CJK and Latin both appear in the lyric lines of the matching sections."""

    def check(dir_path: Path) -> Verdict:
        sections = lyric_sections(dir_path)
        if sections is None:
            return False, f"artifact missing: {LYRICS_ARTIFACT}"
        body = [
            line for tag, lines in sections if tag.startswith(prefixes) for line in lines
        ]
        cjk = bool(CJK_RE.search("\n".join(body)))
        latin = has_latin_line(body)
        where = f"[{'/'.join(prefixes)}...] lines"
        if cjk and latin:
            return True, (
                f"CJK and Latin both in {where} "
                "(per-character metering stays with the judge)"
            )
        return False, f"{where}: CJK={cjk}, Latin line (>=2 words)={latin}"

    return check


def check_exclude(*groups: tuple[str, ...]) -> Check:
    """The EXCLUDE line names at least one term from every group."""

    def check(dir_path: Path) -> Verdict:
        lines = artifact_lines(dir_path, STYLE_ARTIFACT)
        if lines is None:
            return False, f"artifact missing: {STYLE_ARTIFACT}"
        if len(lines) < 2 or not lines[1].startswith("EXCLUDE:"):
            return False, "no EXCLUDE: line"
        value = lines[1][len("EXCLUDE:") :].lower()
        missing = [group for group in groups if not any(t in value for t in group)]
        if missing:
            return False, f"EXCLUDE lacks any of {missing[0]!r}"
        return True, f"EXCLUDE names {len(groups)} required exclusion(s)"

    return check


PLACEHOLDER_RE = re.compile(r"<[^<>\n]*>")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
TABLE_RULE_RE = re.compile(r"^\|[\s:|-]+\|$")
TABLE_HEADER_RE = re.compile(r"^\|\s*#\s*\|")  # the "| # | Change | ..." label row


def h2_sections(text: str) -> list[tuple[str, str]]:
    """(heading, body) for every '## ' heading, in document order."""
    out: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            out.append((line[3:].strip(), []))
        elif out:
            out[-1][1].append(line)
    return [(head, "\n".join(body)) for head, body in out]


def song_sections(dir_path: Path) -> list[tuple[str, str]] | None:
    lines = artifact_lines(dir_path, SONG_ARTIFACT)
    return None if lines is None else h2_sections("\n".join(lines))


def filled(body: str) -> bool:
    """True when something remains after dropping comments and <placeholders>."""
    return bool(PLACEHOLDER_RE.sub("", COMMENT_RE.sub("", body)).strip())


def check_template_order(dir_path: Path) -> Verdict:
    """song.md has the H2 headings of assets/song-template.md, in its order."""
    sections = song_sections(dir_path)
    if sections is None:
        return None, SONG_NOT_RECORDED
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactError(f"unreadable template {TEMPLATE_PATH}: {exc}") from exc
    want = [head for head, _body in h2_sections(template)]
    got = [head for head, _body in sections]
    if got != want:
        missing = [head for head in want if head not in got]
        extra = [head for head in got if head not in want]
        if missing or extra:
            return False, f"template requires all H2 headings: missing {missing}, unexpected {extra}"
        return False, f"H2 headings out of template order: {got}"
    return True, f"{len(want)} H2 headings match assets/song-template.md order"


def check_song_filled(*names: str, mention: tuple[str, ...] = ()) -> Check:
    """The named song.md sections exist and hold more than placeholders.

    With `mention`, the named sections together must use one of those words.
    """

    def check(dir_path: Path) -> Verdict:
        sections = song_sections(dir_path)
        if sections is None:
            return None, SONG_NOT_RECORDED
        bodies = {head.lower(): body for head, body in sections}
        empty = [name for name in names if not filled(bodies.get(name.lower(), ""))]
        if empty:
            return False, f"section(s) missing or unfilled in {SONG_ARTIFACT}: {empty}"
        text = " ".join(bodies[name.lower()] for name in names).lower()
        if mention and not any(word in text for word in mention):
            return False, f"{', '.join(names)} mentions none of {mention!r}"
        suffix = f" (mentions one of {mention!r}; quality stays with the judge)" if mention else ""
        return True, f"filled: {', '.join(names)}{suffix}"

    return check


def check_iteration_log(keywords: tuple[str, ...] = ()) -> Check:
    """Iteration log has a filled data row (mentioning a keyword when given)."""

    def check(dir_path: Path) -> Verdict:
        sections = song_sections(dir_path)
        if sections is None:
            return None, SONG_NOT_RECORDED
        body = next((b for head, b in sections if head.lower() == "iteration log"), None)
        if body is None:
            return False, "no '## Iteration log' section"
        table = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("|")]
        rows = [
            row
            for row in table
            if not TABLE_RULE_RE.match(row)
            and not TABLE_HEADER_RE.match(row)  # column-label row, header or not first
            and row.replace("|", "").strip()
            and not PLACEHOLDER_RE.search(row)
        ]
        if not rows:
            return False, "iteration log has no filled entry"
        if keywords and not any(k in row.lower() for row in rows for k in keywords):
            return False, f"no iteration-log entry mentions any of {keywords!r}"
        suffix = f" (mentions one of {keywords!r})" if keywords else ""
        return True, f"{len(rows)} iteration-log entr(y/ies){suffix}"

    return check


def check_all(*checks: Check) -> Check:
    """Every check must pass; details are joined so each conjunct is visible.

    Any FAIL wins; otherwise one unrecorded optional artifact sends the whole
    criterion to the judge.
    """

    def check(dir_path: Path) -> Verdict:
        results = [one(dir_path) for one in checks]
        oks = [ok for ok, _detail in results]
        ok = False if False in oks else None if None in oks else True
        return ok, "; ".join(detail for _ok, detail in results)

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
        # 3 ("Both Chinese and English ... metered as 1 unit") stays JUDGE:
        # the metering half is a claim about how the run worked, not
        # checkable from the artifacts; a PASS would certify the whole sentence.
        4: (
            "sections are filled in the template",
            check_song_filled("Title", "Concept", "Vocal direction", "Meaning & subtext"),
        ),
    },
    "wedding-acoustic-ballad": {
        0: (
            "72 BPM",
            check_style(
                must_contain=("72 BPM",), must_contain_any=("acoustic", "ballad")
            ),
        ),
        1: (
            "rules out electronic drums / autotune",
            check_exclude(
                ("electronic", "drum machine", "synth drum"),
                ("autotune", "auto-tune", "auto tune"),
            ),
        ),
        # 2 ("... (syllable_meter.py output shown)") stays JUDGE: the
        # parenthetical needs a process transcript; a PASS would certify the
        # whole sentence (same call as worked-example #2 below).
        3: (
            "counts differ by at most 1",
            check_all(check_validate_exit0, check_section_balance(1)),
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
        # 1 ("Verse 1 lines match the declared expected meter (PASS on all
        # lines)") stays JUDGE: the parenthetical needs the syllable_meter
        # transcript — expected_behavior fixes --expect 8,8,8,8, but the
        # criterion also asserts the shown output, and a PASS would certify
        # the whole sentence.
        2: ("<=2 distinct lines and repeats at least twice", check_hook(2, 2)),
        3: ("validate_structure.py exits 0", check_validate_exit0),
        4: (
            "at least one meter-driven revision",
            check_iteration_log(keywords=("meter", "syllable")),
        ),
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
        4: (
            "Vocal direction section explains the murmured-phrase treatment",
            check_song_filled(
                "Vocal direction", mention=("murmur", "mumbl", "whisper", "hummed", "humming", "spoken")
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
        2: ("<=6 syllables per chant line", check_section_meter(("chorus",), 1, 6)),
        # 3 ("... CJK lines metered per character if used") stays JUDGE: the
        # metering conjunct is a process claim, not checkable from artifacts.
        4: ("EXCLUDE line present", check_style()),
    },
    "build-default-unaffected": {
        2: ("assets/song-template.md is used for output", check_template_order),
    },
    "worked-example-as-model": {
        0: (
            "one comma-separated string <=200 chars",
            check_style(require_commas=True),
        ),
        # #2 stays JUDGE: half of it ("syllable_meter.py output is shown")
        # needs a transcript, and a PASS would certify the whole sentence.
        2: ("song-template.md section order", check_template_order),
        3: ("at least one entry", check_iteration_log()),
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
                "verdict": JUDGE if ok is None else PASS if ok else FAIL,
                "criterion": criterion,
                "detail": detail,
            }
        )
    return results


def coverage(evals_path: Path) -> tuple[list[tuple[str, int, int]], list[str]]:
    """([(case id, machine-checked criteria, all criteria)], errors) for every case."""
    try:
        data = json.loads(evals_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"cannot read evals file {evals_path}: {exc}"]
    if not isinstance(data, dict) or not isinstance(data.get("evals"), list):
        return [], [f"invalid evals file {evals_path}: expected an object with an 'evals' list"]
    rows: list[tuple[str, int, int]] = []
    errors: list[str] = []
    for item in data["evals"]:
        case_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(case_id, str):
            errors.append("evals entry without a string id")
            continue
        case, case_errors = load_case(evals_path, case_id)
        errors.extend(case_errors)
        if case is not None:
            rows.append((case_id, len(CHECKS.get(case_id, {})), len(case[1])))
    known = {item.get("id") for item in data["evals"] if isinstance(item, dict)}
    errors.extend(
        f"CHECKS names unknown case {case_id!r}" for case_id in sorted(set(CHECKS) - known)
    )
    return rows, errors


def print_coverage(rows: list[tuple[str, int, int]], as_json: bool) -> None:
    machine = sum(row[1] for row in rows)
    total = sum(row[2] for row in rows)
    cases = sum(1 for row in rows if row[1])
    if as_json:
        print(json.dumps(
            {"cases": [{"case": c, "machine": m, "criteria": t} for c, m, t in rows],
             "summary": {"machine": machine, "criteria": total,
                         "cases_with_checks": cases, "cases": len(rows)}},
            ensure_ascii=False, indent=2,
        ))
        return
    for case_id, done, count in rows:
        print(f"{done:>2}/{count:<2} {case_id}")
    share = 100 * machine / total if total else 0
    print(
        f"machine-checkable: {machine}/{total} criteria ({share:.0f}%) "
        f"in {cases}/{len(rows)} cases; the rest need a judge"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_evals.py",
        description="Grade the machine-checkable criteria of one eval case from recorded artifacts.",
        epilog=(
            "Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = usage or criterion drift.\n"
            "Example:\n"
            "  python3 %(prog)s --case citypop-bilingual-leaving-home --dir artifacts/\n"
            "  python3 %(prog)s --coverage"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--case", help="eval case id from evals/evals.json")
    parser.add_argument("--dir", help="directory holding style_prompt.txt / lyrics.txt (and song.md)")
    parser.add_argument("--coverage", action="store_true", help="report how many criteria per case are machine-checked; needs no --case/--dir")
    parser.add_argument("--evals", default=str(DEFAULT_EVALS), help="evals.json to grade against (default: the bundle's)")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    args = parser.parse_args(argv)
    if not args.coverage and not (args.case and args.dir):
        parser.error("--case and --dir are required (or pass --coverage)")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.coverage:
        rows, errors = coverage(Path(args.evals))
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 2
        print_coverage(rows, args.json)
        return 0
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
        if r["detail"]:
            print(f"         -> {r['detail']}")
    print(f"{passed} PASS, {failed} FAIL, {judged} JUDGE")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
