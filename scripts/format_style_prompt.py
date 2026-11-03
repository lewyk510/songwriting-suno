#!/usr/bin/env python3
"""Assemble a compact style prompt for Suno-style text-to-song tools.

Assumptions (no official API contract is claimed or invented):
- Text-to-song tools take a free-text "style" description; this tool assumes a
  conservative 200-character budget (override it with --limit N, a positive
  integer). If the assembled prompt exceeds the budget, lower priority
  (trailing) parts are dropped, and if a single part alone is too long it is
  hard-cut at a word boundary. A warning goes to stderr.
- Negative tags are emitted on a separate "EXCLUDE:" line so the caller can
  keep them out of the main prompt.

Usage:
  python3 format_style_prompt.py --genre synth-pop --mood melancholic --tempo 110 \
      --instruments "analog synth, drum machine" --vocal "female, airy" \
      --era "80s" --exclude "harsh vocals, metal"
"""
import argparse
import json
import sys

DEFAULT_CHAR_LIMIT = 200


def positive_int(value: str) -> int:
    """--limit must be a positive integer (argparse errors exit with code 2)."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer: {value!r}")
    return parsed


def build_parser():
    p = argparse.ArgumentParser(
        prog="format_style_prompt.py",
        description="Assemble a single compact comma-separated style prompt from structured flags.",
        epilog=(
            "Example:\n"
            "  python3 %(prog)s --genre synth-pop --mood melancholic --tempo 110 \\\n"
            "      --instruments \"analog synth, drum machine\" --vocal \"female, airy\" \\\n"
            "      --exclude \"harsh vocals\"\n"
            "Output:\n"
            "  synth-pop, melancholic, 110 BPM, female, airy, analog synth, drum machine\n"
            "  EXCLUDE: harsh vocals"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--genre", help="primary genre, e.g. synth-pop")
    p.add_argument("--mood", help="mood / emotion, e.g. melancholic")
    p.add_argument("--tempo", type=int, help="tempo in BPM, e.g. 110")
    p.add_argument("--instruments", help='comma-separated instrument list, e.g. "analog synth, drum machine"')
    p.add_argument("--vocal", help='vocal description, e.g. "female, breathy"')
    p.add_argument("--era", help="era flavor, e.g. 80s")
    p.add_argument("--extra", help="extra free-text tags appended at the end")
    p.add_argument("--exclude", help='comma-separated negative tags, e.g. "metal, screaming"')
    p.add_argument(
        "--limit",
        type=positive_int,
        default=DEFAULT_CHAR_LIMIT,
        metavar="N",
        help=f"character budget for the style prompt (default {DEFAULT_CHAR_LIMIT})",
    )
    p.add_argument("--json", action="store_true", help="emit structured JSON instead of two text lines")
    return p


def split_list(value):
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def truncate(parts, limit):
    """Join parts with ', ' under `limit` chars, dropping trailing parts first.

    Returns (text, truncated_flag).
    """
    if not parts:
        return "", False
    kept = []
    for part in parts:
        if len(", ".join(kept + [part])) <= limit:
            kept.append(part)
        else:
            break
    if kept:
        return ", ".join(kept), len(kept) < len(parts)
    head = parts[0][:limit]  # single part alone exceeds limit: cut at word boundary
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    return head, True


def main():
    args = build_parser().parse_args()
    raw_parts = [
        args.genre, args.era, args.mood,
        f"{args.tempo} BPM" if args.tempo else None,
        args.vocal, args.instruments, args.extra,
    ]
    parts = [p.strip() for p in raw_parts if p and p.strip()]
    exclude = split_list(args.exclude)
    if not parts:
        if exclude:
            print(
                "No style flags given (only --exclude). Provide at least one of "
                "--genre/--mood/--tempo/--instruments/--vocal/--era/--extra. Try --help.",
                file=sys.stderr,
            )
        else:
            print("No input flags given. Try --help.", file=sys.stderr)
        return 2

    style, truncated = truncate(parts, args.limit)
    if truncated:
        print(
            f"WARNING: style prompt exceeded {args.limit} chars; truncated to "
            f"{len(style)} chars. Drop lower-priority flags or shorten tags.",
            file=sys.stderr,
        )

    if args.json:
        print(json.dumps(
            {
                "style_prompt": style,
                "exclude": exclude,
                "char_count": len(style),
                "truncated": truncated,
            },
            ensure_ascii=False, indent=2,
        ))
        return 0

    print(style)
    print(f"EXCLUDE: {', '.join(exclude) if exclude else '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
