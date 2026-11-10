#!/usr/bin/env python3
"""Validate lyric-sheet structure for text-to-song tools (e.g. Suno).

Checks a lyric sheet containing bracketed section tags such as
[Intro], [Verse], [Pre-Chorus], [Chorus], [Bridge], [Outro], [Hook],
[Interlude], [Instrumental Break]:

  1. ERROR   if no [Chorus] section exists
  2. ERROR   if a section has no lyric lines under it (allowed only for
             [Instrumental ...] tags like [Instrumental Break])
  3. WARNING if [Verse] count differs from [Chorus] count by more than 1
  4. WARNING if lyric lines appear before the first section tag

Also reports total sections, total lyric lines, and estimated song length
at an assumed 3.5 seconds per lyric line (a rough local default, not an
official figure of any tool).

Reads a lyric file positionally or from stdin. Exit code: 0 = no errors
(warnings allowed), 1 = errors found, 2 = usage problem.

Usage:
  printf '[Verse]\nline one\n[Chorus]\nbig hook\n' | python3 validate_structure.py
"""
import argparse
import re
import sys

TAG_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*$")


def is_instrumental(tag):
    return "instrumental" in tag.lower()


def is_chorus(tag):
    return tag.strip().lower().startswith("chorus")  # [Chorus], [Chorus 2]... (not [Pre-Chorus])


def is_verse(tag):
    return tag.strip().lower().startswith("verse")


def parse_sections(lines):
    """Split raw lines into preamble lines and [{'tag', 'lines'}, ...]."""
    sections, preamble, current = [], [], None
    for raw in lines:
        m = TAG_RE.match(raw)
        if m:
            current = {"tag": m.group(1).strip(), "lines": []}
            sections.append(current)
        elif current is None:
            if raw.strip():
                preamble.append(raw)
        else:
            current["lines"].append(raw)
    return sections, preamble


def main():
    ap = argparse.ArgumentParser(
        prog="validate_structure.py",
        description="Validate bracketed section structure of a lyric sheet (chorus presence, non-empty sections, verse/chorus balance).",
        epilog=(
            "Example:\n"
            "  printf '[Verse]\\nline one\\n[Chorus]\\nbig hook\\n' | python3 %(prog)s\n"
            "Exit code: 0 = PASS (warnings allowed), 1 = FAIL (errors)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("file", nargs="?", help="lyric sheet file (reads stdin if omitted)")
    args = ap.parse_args()

    if args.file:
        try:
            with open(args.file, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            ap.error(f"cannot read {args.file}: {exc}")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.error("no input: pass a file or pipe lyrics via stdin")

    sections, preamble = parse_sections(text.splitlines())
    errors, warnings = [], []

    choruses = [s for s in sections if is_chorus(s["tag"])]
    verses = [s for s in sections if is_verse(s["tag"])]
    if not choruses:
        errors.append("no [Chorus] section found (at least one is required)")
    for s in sections:
        if not any(ln.strip() for ln in s["lines"]) and not is_instrumental(s["tag"]):
            errors.append(f"section [{s['tag']}] is empty (no lyric lines under it)")
    if verses and choruses and abs(len(verses) - len(choruses)) > 1:
        warnings.append(
            f"{len(verses)} [Verse] vs {len(choruses)} [Chorus]: counts differ by more than 1")
    if preamble:
        warnings.append(f"{len(preamble)} lyric line(s) appear before the first section tag")

    print(f"Sections found: {len(sections)}")
    for i, s in enumerate(sections, 1):
        n = sum(1 for ln in s["lines"] if ln.strip())
        kind = " (instrumental)" if is_instrumental(s["tag"]) else ""
        print(f"  {i:>2}. [{s['tag']}] - {n} line(s){kind}")
    lyric_lines = sum(sum(1 for ln in s["lines"] if ln.strip()) for s in sections) + len(preamble)
    seconds = lyric_lines * 3.5
    print(f"Lyric lines: {lyric_lines} | Estimated length @3.5s/line: {seconds:.0f}s "
          f"(~{int(seconds // 60)}:{int(seconds % 60):02d})")

    for e in errors:
        print(f"ERROR: {e}")
    for w in warnings:
        print(f"WARNING: {w}")
    if errors:
        print("Result: FAIL (structure errors)")
        return 1
    print("Result: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
