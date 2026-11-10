#!/usr/bin/env python3
"""Objective-ish lint for lyric sheets: end-rhyme scheme, near rhymes,
repeated lines, line-length spread, and cliche hits.

THIS IS AN AID, NOT GROUND TRUTH. Every check is an orthographic
approximation with no pronouncing dictionary:

- Rhyme keys come from spelling only: the trailing alphabetic word of a
  line (lowercased, punctuation stripped) cut from its last vowel group
  (aeiouy) through the end. Equal keys => PERFECT rhyme (shared uppercase
  letter). Same final vowel group but a different coda => NEAR rhyme /
  assonance: the line displays the earlier group's letter lowercased plus
  ' (e.g. a'). Eye-rhymes count as perfect (love/name both key 'e') and
  true rhymes with different spellings can be missed.
- Syllable counts reuse scripts/syllable_meter.py when importable, else a
  cruder vowel-group fallback (keeps silent trailing e).
- CLICHE_LIST below is a fixed, conservative sample of common pop
  phrases; zero hits is not a quality badge.

Input follows the sibling-script convention: positional file, else --text
('\\n' splits lines), else stdin. Blank lines are skipped; all non-blank
lines (section tags included) are numbered sequentially from 1 and every
report references that number. Lines before the first [Tag] form a
"(preamble)" group; the TAG_RE convention is shared with
validate_structure.py. Repetition is informational by design (chorus
repeats are normal): a normalized line appearing >= --min-repeat times
(default 2) is reported, and only counts strictly above --min-repeat are
treated as actionable.

- Machine-lyric tells are density rules over one section or the whole
  sheet (see NEGATION_FRAME_RE / ANAPHORA_MIN / IMAGERY_WORDS). Only
  negation_frame is actionable; anaphora_run and imagery_cluster are
  advisory because human writers use both on purpose.

Exit code: 0 = no actionable findings, 1 = cliche hit, a repetition
count above --min-repeat, or an actionable tell, 2 = usage problem. --warn-only forces exit 0
for findings (usage errors still exit 2). --json prints a structured
report and keeps the same exit codes.

Usage:
  python3 lyric_lint.py song.txt
  python3 lyric_lint.py --text "[Verse]\\nI drive until the streetlights end\\nThe engine hums your name"
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import statistics
import sys

TAG_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*$")  # shared with validate_structure.py
VOWELS = re.compile(r"[aeiouy]+")
# Inner apostrophes stay in the word so "won't"/"don't" rhyme on "ont".
TRAILING_WORD = re.compile(r"([A-Za-z]+(?:['\u2019][A-Za-z]+)*)[^A-Za-z]*$")
WORD_RE = re.compile(r"[A-Za-z]+")
CJK = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")

# Fixed, documented sample of common pop-songwriting cliches.
# Case-insensitive; matched on normalized word boundaries (punctuation and
# repeated whitespace are collapsed identically on both sides first). This is
# a deliberately conservative aid, not a blacklist; extend here in one place.
CLICHE_LIST: tuple[str, ...] = (
    "heart of gold",
    "set me free",
    "tears fall like rain",
    "burning desire",
    "broken heart",
    "fire in my soul",
    "can't stop loving you",
    "dance in the rain",
    "reach for the stars",
    "endless night",
    "baby baby",
    "on my knees",
    "wings to fly",
    "fade to black",
    "light of my life",
    "against the world",
    "the way you make me feel",
    "hold me tight",
    "lost without you",
    "love is a battlefield",
    "till the end of time",
    "cry me a river",
    "angel in disguise",
    "walking on sunshine",
    "shine bright like a diamond",
    "dancing in the moonlight",
    "you are my everything",
    "all night long",
    # Added 2026-11-10 from machine-written samples the list missed.
    "stole my heart",
    "heart skip a beat",
    "heart skips a beat",
    "heart skipped a beat",
    "burning bright",
    "nothing left to lose",
    "won't back down",
    "pieces of my heart",
    "fire in my veins",
    "break the silence",
    "forever young",
    "born to fly",
    "the tide is gonna turn",
    "beneath the stars",
    # Mandarin stock phrases (matched as substrings; Chinese has no word spaces).
    "\u601d\u5ff5\u50cf\u6f6e\u6c34",  # 思念像潮水
    "\u6cea\u6c34\u8fd8\u662f\u96e8\u6c34",  # 泪水还是雨水
    "\u753b\u4e0b\u53e5\u53f7",  # 画下句号
    "\u56de\u5230\u4f60\u8eab\u65c1",  # 回到你身旁
    "\u5343\u91cc\u4e4b\u5916",  # 千里之外
    "\u56de\u4e0d\u53bb\u4e86",  # 回不去了
    "\u6d77\u67af\u77f3\u70c2",  # 海枯石烂
    "\u5929\u957f\u5730\u4e45",  # 天长地久
    "\u523b\u9aa8\u94ed\u5fc3",  # 刻骨铭心
    "\u6495\u5fc3\u88c2\u80ba",  # 撕心裂肺
)

# Machine-lyric tells beyond fixed phrases. Density rules, never single-word
# bans: one use of any of these is ordinary writing.
#   negation_frame  "I'm not X, I'm just Y" / "not X, but Y" lines (needs a
#                   pronoun subject and a punctuation turn — comma/semicolon,
#                   dash, or ellipsis — so imperatives like "Don't look back,
#                   just drive" and scene-setting "Not a sound, only rain"
#                   are spared); two or more distinct per section is ACTIONABLE.
#   anaphora_run    three or more distinct lines in a section opening on the
#                   same word (Maybe.../Every...). Advisory: also a real device.
#   imagery_cluster four or more distinct stock-atmosphere words in the whole
#                   sheet. Advisory: some genres live on this vocabulary.
NEGATION_FRAME_RE = re.compile(
    r"\b(?:i|you|we|it|he|she|they|this|that)\b[^,;.\u2014\u2013-]{0,20}?"
    r"(?:\bnot\b|n['\u2019]t\b)[^,;.\u2014\u2013-]{0,30}"
    r"(?:[,;\u2014\u2013-]|\.\.\.|\u2026)\s*(?:[\w'\u2019]+\s+){0,2}(?:but|just|only)\b",
    re.IGNORECASE,
)
NEGATION_FRAME_MIN = 2
ANAPHORA_MIN = 3
ANAPHORA_SKIP = frozenset(
    "i i'm im and the a an you we he she they but oh yeah in on so my your it to of with".split()
)
IMAGERY_WORDS = frozenset(
    "neon chrome static midnight skyline shadow shadows echo echoes whisper whispers "
    "ember embers ash ashes thunder storm storms silhouette silhouettes "
    "kaleidoscope kaleidoscopes tapestry tapestries symphony symphonies velvet ethereal".split()
)
IMAGERY_MIN = 4


def norm_phrase(text: str) -> str:
    """Lowercase, replace punctuation with spaces, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


CLICHE_PATTERNS: tuple[tuple[str, str], ...] = tuple(
    (entry, norm_phrase(entry)) for entry in CLICHE_LIST
)


def cliche_hit(needle: str, normalized_line: str) -> bool:
    """Whole-word match; CJK needles match as substrings with spaces dropped."""
    if CJK.search(needle):
        return needle.replace(" ", "") in normalized_line.replace(" ", "")
    return f" {needle} " in f" {normalized_line} "


def find_tells(sections: list[dict], lyric_lines: list[dict]) -> list[dict]:
    """Density-gated machine-lyric tells (see the constants above)."""
    tells: list[dict] = []
    for position, section in enumerate(sections):
        index = section.get("index", position + 1)
        distinct: dict[str, dict] = {}
        for entry in section["lines"]:
            distinct.setdefault(norm_phrase(entry["text"]), entry)
        frames = [e["n"] for e in distinct.values() if NEGATION_FRAME_RE.search(e["text"])]
        if len(frames) >= NEGATION_FRAME_MIN:
            tells.append({
                "rule": "negation_frame", "actionable": True, "section": index,
                "tag": section["tag"], "lines": frames,
                "detail": f"{len(frames)} 'not X, just/but Y' lines in one section",
            })
        openers: dict[str, list[int]] = {}
        for normalized, entry in distinct.items():
            first = normalized.split(" ", 1)[0]
            if CJK.search(first):
                first = first[:1]  # CJK has no spaces: the opener is the first character
            if first and first not in ANAPHORA_SKIP:
                openers.setdefault(first, []).append(entry["n"])
        for first, numbers in openers.items():
            if len(numbers) >= ANAPHORA_MIN:
                tells.append({
                    "rule": "anaphora_run", "actionable": False, "section": index,
                    "tag": section["tag"], "lines": numbers,
                    "detail": f"{len(numbers)} lines open on '{first}'",
                })
    found: dict[str, int] = {}
    for entry in lyric_lines:
        for word in norm_phrase(entry["text"]).split():
            if word in IMAGERY_WORDS:
                found.setdefault(word, entry["n"])
    if len(found) >= IMAGERY_MIN:
        tells.append({
            "rule": "imagery_cluster", "actionable": False, "section": None,
            "tag": None, "lines": sorted(found.values()),
            "detail": f"{len(found)} stock-atmosphere words: {', '.join(sorted(found))}",
        })
    return tells


def rhyme_key(line: str) -> tuple[str | None, str | None]:
    """Return (key, nucleus) from the line's trailing alphabetic word.

    key = the last vowel group (aeiouy) of the word through the end;
    nucleus = that vowel group. (None, None) when the line has no
    rhymable word. Orthographic approximation - no pronouncing dictionary.
    """
    match = TRAILING_WORD.search(line)
    if not match:
        return None, None
    word = match.group(1).lower().replace("'", "").replace("\u2019", "")
    last = None
    for group in VOWELS.finditer(word):
        last = group
    if last is None:
        return None, None
    key = word[last.start():]
    return key, VOWELS.match(key).group(0)


def group_letter(index: int) -> str:
    """A, B, ..., Z, then A2, B2, ... (deterministic; >26 groups are rare)."""
    return chr(ord("A") + index % 26) + (str(index // 26) if index >= 26 else "")


def scheme_for(lines: list[dict]) -> dict:
    """Assign rhyme symbols to one group's lyric lines.

    lines: [{'n': <global non-blank line number>, 'text': <line>}, ...]
    Lines are grouped by exact rhyme key; first appearance gives the
    letters. A group whose key differs from every earlier key but whose
    final vowel group matches an earlier group's nucleus is NEAR
    (assonance) to that earliest group: it keeps its own letter internally
    but displays the target's letter lowercased plus ' (e.g. a'). Lines
    with no rhymable word get '-'.
    """
    groups: list[dict] = []
    per_line: list[dict] = []
    for ln in lines:
        key, nucleus = rhyme_key(ln["text"])
        entry = dict(ln, symbol="-", rhyme_key=None)
        if key is not None:
            grp = next((g for g in groups if g["key"] == key), None)
            if grp is None:
                grp = {
                    "letter": group_letter(len(groups)),
                    "key": key,
                    "nucleus": nucleus,
                    "members": [],
                    "near_to": next(
                        (g for g in groups if g["nucleus"] == nucleus), None
                    ),
                }
                groups.append(grp)
            grp["members"].append(entry["n"])
            entry["rhyme_key"] = key
        per_line.append(entry)
    for grp in groups:
        if grp["near_to"]:
            grp["symbol"] = grp["near_to"]["letter"].lower() + "'"
        else:
            grp["symbol"] = grp["letter"]
    for entry in per_line:
        if entry["rhyme_key"] is not None:
            grp = next(g for g in groups if g["key"] == entry["rhyme_key"])
            entry["symbol"] = grp["symbol"]
    perfect_pairs: list[list[int]] = []
    near_pairs: list[list[int]] = []
    near_desc: list[str] = []
    for grp in groups:
        perfect_pairs.extend(
            list(pair) for pair in itertools.combinations(sorted(grp["members"]), 2)
        )
        if grp["near_to"]:
            pairs = [
                (a, b)
                for a in sorted(grp["members"])
                for b in sorted(grp["near_to"]["members"])
            ]
            near_pairs.extend(sorted(pair) for pair in pairs)
            shown = ", ".join(f"({min(a, b)},{max(a, b)})" for a, b in pairs)
            near_desc.append(f"{shown} vowel '{grp['near_to']['nucleus']}'")
    return {
        "lines": per_line,
        "scheme": "".join(e["symbol"] for e in per_line),
        "perfect_pairs": sorted(perfect_pairs),
        "near_pairs": sorted(near_pairs),
        "near_desc": near_desc,
    }


_SYLLABLE_COUNTER = None


def _rough_syllables(line: str) -> int:
    """Fallback counter (cruder than syllable_meter.py: keeps silent e)."""
    total = len(CJK.findall(line))
    for word in WORD_RE.findall(CJK.sub(" ", line)):
        total += max(len(VOWELS.findall(word.lower())), 1)
    return total


def _make_syllable_counter():
    """Prefer the sibling syllable_meter; degrade to the fallback."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import syllable_meter  # type: ignore[import-not-found]

        return lambda line: syllable_meter.count_line(line, "auto")[0]
    except Exception:
        return _rough_syllables


def syllable_count(line: str) -> int:
    global _SYLLABLE_COUNTER
    if _SYLLABLE_COUNTER is None:
        _SYLLABLE_COUNTER = _make_syllable_counter()
    return _SYLLABLE_COUNTER(line)


def parse_groups(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split numbered entries into (sections, preamble lines).

    Same bracket-tag convention as validate_structure.py, but entries keep
    their global non-blank line number.
    """
    sections: list[dict] = []
    preamble: list[dict] = []
    current: dict | None = None
    for entry in entries:
        match = TAG_RE.match(entry["text"])
        if match:
            current = {"tag": match.group(1).strip(), "lines": []}
            sections.append(current)
        elif current is None:
            preamble.append(entry)
        else:
            current["lines"].append(entry)
    return sections, preamble


def _median_value(values: list[int]):
    if not values:
        return 0
    med = statistics.median(values)
    return int(med) if med == int(med) else med


def analyze(text: str, min_repeat: int = 2, no_cliche: bool = False) -> dict:
    """Run all checks; returns a JSON-ready dict (stable, deterministic order)."""
    entries = [
        {"n": n, "text": raw, "is_tag": bool(TAG_RE.match(raw))}
        for n, raw in enumerate(
            (ln.rstrip() for ln in text.splitlines() if ln.strip()), 1
        )
    ]
    sections, preamble = parse_groups(entries)

    def build_group(index: int, tag: str, lines: list[dict]) -> dict:
        scheme = scheme_for(lines)
        counts = [syllable_count(e["text"]) for e in lines]
        return {
            "index": index,
            "tag": tag,
            "line_count": len(lines),
            "lines": [
                {"n": e["n"], "text": e["text"], "symbol": e["symbol"],
                 "rhyme_key": e["rhyme_key"], "syllables": c}
                for e, c in zip(scheme["lines"], counts)
            ],
            "scheme": scheme["scheme"],
            "perfect_pairs": scheme["perfect_pairs"],
            "near_pairs": scheme["near_pairs"],
            "near_desc": scheme["near_desc"],
            "syllables": {
                "min": min(counts) if counts else 0,
                "max": max(counts) if counts else 0,
                "median": _median_value(counts),
                "spread": (max(counts) - min(counts)) if counts else 0,
            },
        }

    groups = [build_group(0, "(preamble)", preamble)]
    groups += [build_group(i, s["tag"], s["lines"]) for i, s in enumerate(sections, 1)]

    lyric_lines = [e for e in entries if not e["is_tag"]]
    seen: dict[str, dict] = {}
    for e in lyric_lines:
        normalized = norm_phrase(e["text"])
        if not normalized:
            continue
        if normalized not in seen:
            seen[normalized] = {
                "count": 0,
                "first_line": e["n"],
                "text": e["text"],
                "normalized": normalized,
            }
        seen[normalized]["count"] += 1
    repeats = [
        dict(info, excessive=info["count"] > min_repeat)
        for info in seen.values()  # dict preserves first-appearance order
        if info["count"] >= max(2, min_repeat)
    ]

    cliche_matches: list[dict] = []
    if not no_cliche:
        for e in lyric_lines:
            haystack = norm_phrase(e["text"])
            for cliche, needle in CLICHE_PATTERNS:
                if cliche_hit(needle, haystack):
                    cliche_matches.append(
                        {"line": e["n"], "text": e["text"], "cliche": cliche}
                    )

    tell_sections: list[dict] = [
        dict(section, index=i) for i, section in enumerate(sections, 1)
    ]
    if preamble:
        # Untagged sheets and preamble lines are lyrics too: scan them as a
        # pseudo-section so the tell rules cannot be dodged by dropping tags.
        tell_sections.insert(0, {"tag": "(preamble)", "lines": preamble, "index": 0})
    tells = find_tells(tell_sections, lyric_lines)

    return {
        "tool": "lyric_lint",
        "approximate": True,
        "min_repeat": min_repeat,
        "total_lines": len(entries),
        "section_count": len(sections),
        "preamble_count": len(preamble),
        "groups": groups,
        "repeats": repeats,
        "cliche_matches": cliche_matches,
        "cliche_scan_disabled": bool(no_cliche),
        "tells": tells,
        "actionable": bool(cliche_matches)
        or any(r["excessive"] for r in repeats)
        or any(t["actionable"] for t in tells),
    }


def print_report(res: dict) -> None:
    print(
        "lyric_lint: approximate rhyme/repetition/cliche report "
        "(no pronouncing dictionary; an aid, not ground truth)"
    )
    print(
        f"Non-blank lines: {res['total_lines']} | sections: {res['section_count']}"
        f" | preamble line(s): {res['preamble_count']}"
    )
    print(
        "legend: A/B = perfect rhyme group | a' = near rhyme (assonance) to group A"
        " | '-' = no rhymable word"
    )
    for group in res["groups"]:
        label = group["tag"] if group["tag"] == "(preamble)" else f"[{group['tag']}]"
        head = f"  {group['index']}. {label} - {group['line_count']} line(s)"
        if group["line_count"]:
            head += f" | scheme: {group['scheme']}"
        print(head)
        for line in group["lines"]:
            print(
                f"     {line['n']:>3} | {line['symbol']:<4} |"
                f" {line['text']}  ({line['syllables']} syl)"
            )
        if group["line_count"]:
            pairs = (
                ", ".join(f"({a},{b})" for a, b in group["perfect_pairs"]) or "(none)"
            )
            print(f"     perfect rhymes: {pairs}")
            print("     near rhymes: " + ("; ".join(group["near_desc"]) or "(none)"))
            syl = group["syllables"]
            print(
                f"     syllables: min {syl['min']} | max {syl['max']}"
                f" | median {syl['median']:g} | spread {syl['spread']}"
            )
    print("Repeats (informational; chorus repeats are expected):")
    if not res["repeats"]:
        print("  (none)")
    for rep in res["repeats"]:
        flag = (
            f"above --min-repeat {res['min_repeat']}"
            if rep["excessive"]
            else "informational"
        )
        print(
            f"  {rep['count']}x | {flag} | first seen line {rep['first_line']}:"
            f" {rep['text']}"
        )
    if res["cliche_scan_disabled"]:
        print("Cliche hits: (scan disabled by --no-cliche)")
    else:
        print("Cliche hits (built-in sample list; --no-cliche disables):")
        if not res["cliche_matches"]:
            print("  (none)")
        for hit in res["cliche_matches"]:
            print(f"  line {hit['line']}: matched '{hit['cliche']}'")
    print("Machine-lyric tells (density rules; advisory unless marked actionable):")
    if not res["tells"]:
        print("  (none)")
    for tell in res["tells"]:
        where = f"[{tell['tag']}]" if tell["tag"] else "whole sheet"
        kind = "actionable" if tell["actionable"] else "advisory"
        shown = ", ".join(str(n) for n in tell["lines"])
        print(f"  {tell['rule']} | {kind} | {where} | {tell['detail']} | lines {shown}")
    if res["actionable"] and res.get("warn_only"):
        print("Result: PASS (--warn-only: findings present, exit forced to 0)")
    else:
        print(f"Result: {'FAIL' if res['actionable'] else 'PASS'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="lyric_lint.py",
        description=(
            "Approximate lyric lint: end-rhyme scheme (perfect vs near), repeated "
            "lines, per-section syllable spread, and cliche hits. Heuristic aid, "
            "not ground truth."
        ),
        epilog=(
            "Example:\n"
            "  python3 %(prog)s --text \"[Verse]\\nI drive until the streetlights end"
            "\\nThe engine hums your name\"\n"
            "Exit code: 0 = no actionable findings, 1 = cliche hit, repetition above\n"
            "--min-repeat, or an actionable tell; 2 = usage problem. --warn-only forces 0."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("file", nargs="?", help="lyric sheet file (else --text, else stdin)")
    ap.add_argument("--text", help="inline lyrics instead of file/stdin ('\\n' splits lines)")
    ap.add_argument(
        "--json", action="store_true", help="print a structured JSON report (same exit codes)"
    )
    ap.add_argument("--no-cliche", action="store_true", help="skip the built-in cliche list")
    ap.add_argument(
        "--min-repeat",
        type=int,
        default=2,
        metavar="N",
        help="report lines appearing >= max(N, 2) times (default 2); counts strictly above N are actionable",
    )
    ap.add_argument(
        "--warn-only",
        action="store_true",
        help="always exit 0 for findings (usage errors still exit 2)",
    )
    args = ap.parse_args(argv)

    if args.min_repeat < 1:
        ap.error("--min-repeat must be >= 1")

    if args.file:
        try:
            with open(args.file, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            ap.error(f"cannot read {args.file}: {exc}")
    elif args.text is not None:
        text = args.text.replace("\\n", "\n")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.error("no input: pass a file, --text, or pipe lyrics via stdin")

    res = analyze(text, min_repeat=args.min_repeat, no_cliche=args.no_cliche)
    res["warn_only"] = args.warn_only
    if not res["total_lines"]:
        print("No non-blank lyric lines found.", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print_report(res)
    if args.warn_only:
        return 0
    return 1 if res["actionable"] else 0


if __name__ == "__main__":
    sys.exit(main())
