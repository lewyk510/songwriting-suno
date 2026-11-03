---
name: songwriting-suno
description: >
  Write original songs end-to-end and craft Suno (and other AI-music) prompts.
  Use whenever the user wants to write a song or lyrics, design song structure
  (verse / chorus / bridge / pre-chorus), set rhythm, melody, harmony, mood or
  vibe, layer meaning / subtext / symbolism, write in a specific language
  (English, Chinese, Japanese, Korean, Malay / Indonesian, Spanish, etc.),
  build a Suno style prompt or meta-tags, control the AI vocal, use Suno
  features (Custom Mode, extend, cover, persona, stems), pick a genre or
  artist vibe, or iterate on a generated track — even if they only say
  "make me a chorus", "write a sad city-pop song", or name a genre. Also use
  when auditing or improving existing lyrics for prosody, meter and rhyme.
  Also use in LEARN mode ("teach me", "let's co-write", "critique my lyrics",
  "give me an exercise", "assess my level") and in UPDATE mode ("update the
  skill", "refresh the Suno docs", "check freshness").
license: MIT
compatibility: Bundled scripts need Python 3.10+ and no network. UPDATE mode may use network to re-verify sources. Suno feature details change fast — treat references/10-13 as dated and verify on help.suno.com before relying on limits or pricing.
metadata:
  domain: music
  updated: 2026-11-03
---

# Songwriting + Suno

A knowledge pack and workflow for writing songs and steering AI music generation
(mainly Suno). The core consists of the workflow below plus on-demand reference
files. Load a reference file ONLY when its task comes up.

## When to use

Trigger on any of these (the description above is deliberately pushy):

- "write me a song / lyrics / a chorus / a bridge"
- "make a Suno prompt / style prompt / meta-tags"
- "what structure should this song have", "why does my chorus feel flat"
- "write something in Chinese / Japanese / Malay / Korean"
- "control the AI voice / make it female / breathy / sing softly"
- "this genre-vibe" (city-pop, lo-fi, trap, dangdut, K-pop, mandopop, ballad…)
- auditing existing lyrics for meter, rhyme, prosody, cliché

## Modes

| Mode | Use when | Outcome |
|---|---|---|
| **BUILD** (default) | The user wants a deliverable: a song, lyrics, or a Suno prompt. | A finished song artifact (see workflow below). |
| **LEARN** | The user wants to *learn*: "teach me", "explain", "let's discuss", "co-write with me line by line", "critique my lyrics", "give me an exercise", "quiz me", "assess my level". | The user writes/improves; you coach. Read `references/40-learn-with-me.md`. |
| **UPDATE** | The user wants the *bundle* maintained: "update the skill", "refresh the Suno docs", "check freshness", or you detect a stale/contradicted Suno fact. | Refreshed, re-verified reference files + changelog. Read `references/50-self-update.md`. |

Disambiguation: deliverable → BUILD; user capability → LEARN; bundle upkeep → UPDATE. Ambiguous "improve my lyrics" defaults to BUILD with a one-line offer to switch to LEARN.

Freshness: before quoting any Suno limit/pricing/feature as fact, if you have not already checked this session, run `python3 scripts/check_freshness.py`; if it reports STALE, flag it once and offer to refresh — do not block.

## Core workflow (BUILD mode)

1. **Clarify the brief** (ask only what is missing): concept/story, language(s),
   genre, mood, target length, reference vibe, vocal type, must-have lines.
2. **Choose a structure** → `references/01-song-structure.md`.
3. **Set groove + tempo + feel** → `references/02-rhythm-groove.md`.
4. **Write melody/harmony ideas** (contour, hook, chords) →
   `references/03-melody-harmony.md`.
5. **Write or fix lyrics** (prosody, rhyme, imagery) →
   `references/04-lyric-craft.md`; check meter with
   `scripts/syllable_meter.py` and lint rhyme/cliché/repetition with
   `scripts/lyric_lint.py`.
6. **Choose sonic identity** (instrumentation, timbre, production) →
   `references/05-mood-production.md`.
7. **Layer meaning / subtext** → `references/06-meaning-subtext.md`.
8. **Non-English?** Read `references/30-multilingual.md` BEFORE writing lyrics —
   tone/prosody/rhyme rules differ per language.
9. **Assemble the Suno style prompt** →
   `references/11-suno-prompting.md`; build it with
   `scripts/format_style_prompt.py`.
10. **Check Suno mechanics & limits** → `references/10-suno-mechanics.md`.
11. **Emit the song** using `assets/song-template.md`; validate structure with
    `scripts/validate_structure.py`.
12. **Iterate** (extend / cover / persona / stems) →
    `references/12-suno-workflows.md`, `references/13-vocal-control.md`.

## Reference map — read on demand

| File | Read when… |
|---|---|
| `references/01-song-structure.md` | Designing form: sections, orders, templates |
| `references/02-rhythm-groove.md` | Tempo, meter, groove, swing, genre BPM |
| `references/03-melody-harmony.md` | Melody, hooks, chord progressions, cadences |
| `references/04-lyric-craft.md` | Writing/repairing lyrics, prosody, rhyme, imagery |
| `references/05-mood-production.md` | Mood, instrumentation, timbre, arrangement |
| `references/06-meaning-subtext.md` | Theme, subtext, symbolism, double meaning |
| `references/07-worked-examples.md` | Seeing a finished BUILD deliverable (two worked songs: English + bilingual) |
| `references/10-suno-mechanics.md` | How Suno works, modes, limits, pricing, rights |
| `references/11-suno-prompting.md` | Style prompts, meta-tags, prompt recipes |
| `references/12-suno-workflows.md` | Extend, cover, remix, stems, alternatives |
| `references/13-vocal-control.md` | Steering the AI vocal delivery |
| `references/20-tools-and-projects.md` | Libraries, APIs, GitHub projects, datasets |
| `references/30-multilingual.md` | Writing in a non-English language |
| `references/40-learn-with-me.md` | LEARN mode: teaching, co-writing, critique, exercises, level assessment |
| `references/50-self-update.md` | UPDATE mode: freshness protocol, staleness thresholds, changelog |
| `references/60-knowledge-and-retrieval.md` | Offline KB vs online retrieval, plausibility gate, anti-sameness/variation, token discipline |
| `references/70-craft-gate-and-spec.md` | Pre-writing gate, LYR-/ARR-SPEC sheet, AI-tell audit, routing to the `lw-*`/`mc-*` companion libraries |
| `references/00-index.md` | Full annotated index of everything |
| `CHANGELOG.md` | Log of factual updates to this skill (skill root) |

## Quick rules (essentials)

- **Hook is king**: the chorus must be repeatable, singable, and arrive early
  (often < 60s). One strong melodic idea beats five clever ones.
- **Prosody first**: the stressed syllable must land on the strong beat; if a
  line is awkward to say, it is wrong to sing.
- **Say it plainly, imply the rest**: concrete images > abstract statements;
  subtext lives in what you don't spell out.
- **Structure before ornament**: get verse/chorus contrast right before adding
  production tricks.
- **Match language to craft**: tonal languages (Mandarin/Cantonese/Thai/Viet)
  constrain melody by tone; Japanese counts morae; English/Spanish are
  stress- vs syllable-timed. See `references/30-multilingual.md`.
- **Prompt with genre + mood + instrumentation + vocal + era + BPM**, then a
  separate negative/exclude list. Keep the style field tight (it has a hard
  character cap — see `references/10-suno-mechanics.md`).
- **Verify Suno facts**: limits, features and pricing change; run
  `scripts/check_freshness.py`, confirm on `help.suno.com`, and see
  `references/50-self-update.md` before depending on them.
- **Keep it sane and fresh**: before shipping, run the reality audit in
  `assets/plausibility-checks.md`, pull concrete detail from ONE
  `assets/imagery/<theme>.json` theme, and vary at least three axes from your
  last song (see `references/60-knowledge-and-retrieval.md`). Go online only for
  real facts you cannot know offline.
- **Gate before you write**: for any non-trivial lyric, run the five-question
  pre-writing gate and the stranger test, and offer the spec sheet — see
  `references/70-craft-gate-and-spec.md`. For professional depth, hand off to the
  companion `lw-*`/`mc-*` libraries rather than reinventing their craft here.

## Output template

ALWAYS emit finished songs with `assets/song-template.md` (title, concept,
style prompt, exclude, BPM/key, tagged structure, lyrics, vocal direction,
production notes, meaning/subtext, iteration log).

## Gotchas

- Do not stuff a whole paragraph into the Suno *style* field — it has a hard
  character limit; move narrative into the *lyrics* field.
- Bracketed meta-tags are instructions to the model, not lyric content; do not
  rhyme them or count them in meter.
- AI vocals often mispronounce non-English words and tonal languages; expect to
  re-roll and keep the best take. See `references/30-multilingual.md`.
- Never present AI-generated "facts" about Suno as authoritative — cite the
  reference file's dated notes and re-check the live docs.

## Reuse across sessions

This skill lives at `~/.agents/skills/songwriting-suno/` and is discovered
globally by opencode (and Claude Code). It is available in every new chat. To
extend it, add a file under `references/`, a row to `references/00-index.md`,
and an entry to `assets/freshness.json`. To refresh its facts, see
`references/50-self-update.md` and log the change in `CHANGELOG.md`.

Learner data (LEARN mode) lives OUTSIDE the bundle at
`~/.agents/learner-profiles/songwriting-suno.md`, created from
`assets/learner-profile.md`. NEVER delete or overwrite it during an update — it
must survive every self-update.

Helper scripts (run with `python3`):
- `scripts/format_style_prompt.py` — assemble a Suno style + exclude prompt.
- `scripts/syllable_meter.py` — count syllables per line; check a target meter.
- `scripts/lyric_lint.py` — approximate rhyme scheme / near-rhyme / repetition / line-spread / cliché lint (exit 0 clean / 1 findings / 2 usage).
- `scripts/validate_structure.py` — check section tags and basic song shape.
- `scripts/check_freshness.py` — report per-file staleness from `assets/freshness.json` (exit 0 fresh / 1 stale / 2 registry problem); `--check-sources` (implied by `--check-coverage`) also flags broken source URLs.
- `scripts/check_evals.py` — structural check of `evals/evals.json`: unique non-empty ids, required fields, referenced script/asset paths exist (exit 0 valid / 1 findings / 2 usage).
- `scripts/run_evals.py` — grade one eval case's recorded artifacts (`style_prompt.txt` / `lyrics.txt`) against its machine-checkable success criteria; the rest need a judge (exit 0 no FAIL / 1 FAIL / 2 usage or spec drift).
- `scripts/selftest.py` — one cwd-independent command that runs the whole bundle's checks (script help, unit tests, freshness coverage, tool fixtures); it must exit 0.
- `scripts/source_check.py` — helper module for source-URL validation, imported by `check_freshness.py` (not run directly).

Offline assets (read cheaply): `assets/imagery-lexicon.json` is the *index* to the imagery bank — read only the ONE theme you need from `assets/imagery/<theme>.json`, never all of them; `assets/plausibility-checks.md` is the pre-ship reality audit; `assets/power-words.json` holds concrete swaps for generic/clichéd language; `references/60-knowledge-and-retrieval.md` covers offline-vs-online and anti-sameness.

Companion craft libraries (MIT, by jtydhr88; `lw-*` lyric, `mc-*` composition): **when installed on this host** (check for `lw-*`/`mc-*` in `~/.agents/skills/` and `~/.agents/skills-library/`), hand professional-depth craft to them — routing table in `references/70-craft-gate-and-spec.md` §5 (the author's setup runs 12 active plus 35 parked). When they are absent, run the whole pipeline from this bundle alone — §5's fallback keeps every step covered. Either way, this bundle owns the Suno pipeline and tooling.

After any change to the bundle, run `python3 scripts/selftest.py` — it must exit 0.
