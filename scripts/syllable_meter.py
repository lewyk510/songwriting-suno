#!/usr/bin/env python3
"""Count syllables per lyric line with a simple English heuristic.

Heuristic (approximate, no pronunciation dictionary):
- per word: count vowel groups (runs of aeiouy), subtract one silent
  trailing 'e' (kept for -le/-ee/-ye/-oe/-ie endings), floor at 1.
  Contractions are one word ("won't" = 1); consonant + n't adds one
  ("didn't" = 2).
- CJK characters (Hanzi, kana, Hangul) count as exactly 1 unit each —
  --lang cjk makes that explicit; --lang auto (default) detects CJK runs.
  These are meter aids, not phonetic ground truth.

Reads lyrics from a positional file, --text, or stdin. Blank lines are
skipped; counted lines are numbered sequentially from 1.

Usage:
  python3 syllable_meter.py lyrics.txt --expect 8,8,6,6
  printf 'Hello world tonight\nI feel the city light\n' | python3 syllable_meter.py --expect 5,5
"""
import argparse
import re
import sys

VOWELS = re.compile(r"[aeiouy]+")
# A word keeps its inner apostrophes ("won't", "coffee's") so a contraction
# is metered as one word instead of two.
WORD = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*")
CONSONANT_NT = re.compile(r"[^aeiouy]n['\u2019]t$")
# Basic CJK detector: kana, CJK ideographs (+ ext A / compat), Hangul syllables.
CJK = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")
KEEP_E = ("le", "ee", "ye", "oe", "ie")


def syllables_en(word):
    """Heuristic syllable count for one ASCII word (min 1)."""
    w = word.lower()
    extra = 1 if CONSONANT_NT.search(w) else 0  # did-n't, could-n't (not won't)
    w = w.replace("'", "").replace("\u2019", "")
    n = len(VOWELS.findall(w)) + extra
    if w.endswith("e") and n > 1 and not w.endswith(KEEP_E):
        n -= 1  # silent trailing 'e'
    return max(n, 1)


def count_line(line, lang):
    """Return (total units, cjk char count) for one line."""
    cjk = CJK.findall(line)
    words = WORD.findall(CJK.sub(" ", line))
    total = sum(syllables_en(w) for w in words)
    if lang != "en":  # en mode ignores CJK; auto/cjk count each char as 1 unit
        total += len(cjk)
    return total, len(cjk)


def main():
    ap = argparse.ArgumentParser(
        prog="syllable_meter.py",
        description="Print per-line syllable counts for lyrics; optionally PASS/FAIL against expected counts.",
        epilog=(
            "Example:\n"
            "  printf 'Hello world tonight\\nI feel the city light\\n' | \\\n"
            "      python3 %(prog)s --expect 5,5\n"
            "Output:\n"
            "    1 |  5/5  | PASS | Hello world tonight\n"
            "    2 |  6/5  | FAIL | I feel the city light\n"
            "  Summary: 1/2 lines match expected meter."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("file", nargs="?", help="lyrics file (reads stdin if omitted)")
    ap.add_argument("--text", help="inline lyrics instead of file/stdin ('\\n' splits lines)")
    ap.add_argument("--expect", help="comma-separated expected counts, e.g. 8,8,6,6")
    ap.add_argument("--lang", choices=["en", "auto", "cjk"], default="auto",
                    help="en=English heuristic only; cjk=each CJK char is 1 unit; auto=detect (default)")
    args = ap.parse_args()

    if args.text is not None:
        text = args.text.replace("\\n", "\n")
    elif args.file:
        try:
            with open(args.file, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            ap.error(f"cannot read {args.file}: {exc}")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.error("no input: pass a file, --text, or pipe lyrics via stdin")

    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        print("No non-blank lyric lines found.", file=sys.stderr)
        return 2

    expect = None
    if args.expect:
        try:
            expect = [int(x) for x in args.expect.split(",")]
        except ValueError:
            ap.error("--expect must be comma-separated integers, e.g. 8,8,6,6")

    if args.lang == "cjk" or (args.lang == "auto" and any(CJK.search(ln) for ln in lines)):
        print("CJK mode: each CJK character counts as 1 syllable unit.")

    mismatches = 0
    for i, ln in enumerate(lines, 1):
        total, n_cjk = count_line(ln, args.lang)
        if expect is not None:
            want = expect[i - 1] if i - 1 < len(expect) else None
            status = "PASS" if want == total else "FAIL"
            mismatches += status == "FAIL"
            shown_want = want if want is not None else "-"
            print(f"{i:>3} | {total:>2}/{shown_want:<3} | {status} | {ln}")
        else:
            suffix = f" (+{n_cjk} CJK chars)" if n_cjk else ""
            print(f"{i:>3} | {total:>2} | {ln}{suffix}")

    if expect is not None:
        for j in range(len(lines), len(expect)):  # expected counts with no matching line
            print(f"{j + 1:>3} |  0/{expect[j]:<3} | FAIL | (input has no line {j + 1})")
            mismatches += 1
        total_cmp = max(len(lines), len(expect))
        print(f"Summary: {total_cmp - mismatches}/{total_cmp} lines match expected meter.")
        return 1 if mismatches else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
