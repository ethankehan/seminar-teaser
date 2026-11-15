---
name: seminar-teaser
description: "Turns seminar or talk footage (phone, vertical, filmed from the audience) into a short social video, driven by the owner's brief: asks who the video is for and what it should achieve, opens the transcript in the browser so they highlight the points to showcase, then cuts, grades, denoises and subtitles a ~60s trailer-style video from those points. Everything runs locally. Trigger with /seminar-teaser or 'cut the seminar video', 'make a teaser from the talk', 'edit the talk footage', '剪 seminar 视频', '做个预告'."
---

# /seminar-teaser

Talk footage in, a short social video out. The person never opens an editor: they answer three questions, highlight
lines on one web page, then give notes on the result.

Speak to the person in their language. Everything that appears in the video is in the language of the talk.
Nothing leaves this computer: no uploads, no paid services.

## Step 0: setup (every run, a few seconds after the first time)
`SK` = the folder holding this file (usually `~/.claude/skills/seminar-teaser`).
Run `SK/scripts/setup.py` with whichever Python exists; try in order `python3`, `python`, `py -3`. (On Windows
`python3` is often a Store stub that prints "Python was not found": try the next one.) Read its STATUS lines:
- `READY`: continue. Read `SK/.platform.json`; `PY` = its `python` value. Run every other script with `PY`.
- `MISSING` / `INCOMPLETE`: the line ends with the exact fix for this machine. Give it to the person, stop, and
  re-run setup after they did it. On Windows a newly installed program is only found after Claude Code is fully
  quit and reopened.
- First run installs the Python packages (~2 min) and later downloads a speech model (~0.5 GB) at the first
  transcription. Say so before it starts.

Command style that works in zsh, bash, Git Bash and PowerShell: full paths in double quotes with forward slashes,
one command per call, no `&&`, no `~` inside arguments, no `VAR=1 cmd`. In PowerShell put `&` in front of a quoted
program: `& "PY" "SK/scripts/ingest.py" ...`.

**One heavy process at a time.** Never run two renders, two transcriptions, or sub-agents in parallel: these
laptops cannot take it.

## Step 1: footage
Ask where the clips are if not given (a folder is best). Project folder: `<home>/seminar-videos/<short-slug>`.
Start the transcription in the background and go straight to Step 2 while it runs (about 1 minute per minute of
footage):
`PY SK/scripts/ingest.py <project> <folder or files>`  → `sources.json`, `words_cN.json`. Originals are only read.

## Step 2: the brief (ask, do not assume)
Ask these with the question tool, in one go, while the transcription runs. Offer the options, always allow a
free answer:
1. **Who is this video for?** e.g. first-time buyers / people who already attended / existing clients / general
   public. (Use options that fit the topic if it is already known.)
2. **What should it achieve?** Follows · Likes and shares · Comments and discussion · Sign-ups for the next event.
3. **How long?** 30s · 45s · 60s (60 is the ceiling; nobody watches longer on social media).
Then, only if needed: for sign-ups, the next event's name, date and link; for follows, the account handle.
**Never invent a date, venue, link, handle, name or title.** No answer means the card stays generic.
Save `<project>/brief.json`:
`{"audience": "...", "goal": "Follows|Likes and shares|Comments|Sign-ups", "length_seconds": 60, "cta": "...", "event": "...", "date": "...", "link": "..."}`

## Step 3: they highlight the transcript
When the transcription has finished, run in the background and wait for it to exit (do not poll):
`PY SK/scripts/mark.py <project>`
It opens a page in their browser with the whole transcript as clickable phrases, their brief on top, and a counter
of highlighted seconds against the length they chose. Tell them: "A page just opened in your browser. Click the
lines you want in the video, then press Done." If the browser did not open, give them the `MARK PAGE http://...`
address the script printed. The script exits with `SAVED ...` and writes `marks.json` (phrases + an optional note).
`TIMEOUT` means nobody pressed Done: ask, then run it again (earlier highlights are kept).

## Step 4: draft
`PY SK/scripts/draft.py <project>` → `trailer.json` (one shot per run of highlighted phrases, one caption per
phrase, every shot marked `"framed": false`) and `work/framing.jpg`. Read its report:
- **OVER BUDGET**: do not silently drop their lines. Tell them how many seconds over, list the highlighted lines
  with their lengths, and ask: drop which ones, or make it a series of 2-3 videos? Recommend what to drop.
- **NOTHING HIGHLIGHTED**: they left it to you. Pick lines yourself (rules below) and tell them which.
- Read the `note` in marks.json; it may hold a must-be-first line or event details.

## Step 5: edit `trailer.json` (this is the actual editing; take care)
The highlighted lines are the content. You decide order, trims, framing, cards and wording.

**What they asked for decides the shape:**
| Goal | Shape |
|---|---|
| Follows | Strongest line first. Leave one thing unfinished ("...and the third rule is the one people miss"). Last card: follow line + handle. |
| Likes and shares | One surprising fact, told completely, 20-35s. The fact is the first card. No cliffhanger. |
| Comments | End on the most debatable or counter-intuitive line, last card asks one concrete question. |
| Sign-ups | Trailer for the next event: number cards, title card with the event name, date and link if given, then a stinger line. |

**The audience decides the opening and the vocabulary:** lead with the line that concerns *them* (their situation,
their money, their odds), and put *their* word on the kicker of the card ("SECOND-TIMERS", "FIRST HOME"). Drop
highlighted lines that only matter to a different audience and say that you did.

**Order for impact, not chronology.** Opening: personal or startling. Middle: one idea per card. Close: the
"you must know this" line. A highlighted phrase can be trimmed to its strongest clause if it is too long; never
join words from different sentences into a sentence the speaker did not say.

**Cards** (`"type": "card"`): a tracked gold `kicker` + one huge `big` fact, ~1.1s, placed BEFORE the line it sets
up. The `big` text must be something the speaker actually says in the following shot (a number, a term, 1-3 words).
Title card ~2.8s with `"hit": 0.55`; then one short stinger shot; then the end card with `sub` = the call to action
and `"fade_out": 0.6`.

**Framing** each shot from `work/framing.jpg` (grid labels are source pixels): set `cx`, `cy` to the centre of the
stage (speaker + slide) and `zoom` so no audience heads are inside the window. The window is 1080x640 at zoom 1;
zoom 2 is the limit for 1080p footage. Two shots in a row from the same clip: give the second a different zoom
(1.15-1.3) so the cut reads as a punch-in. Then delete `"framed": false`.

**Captions** are `[source_time, "text"]`, one per phrase, time = start of its first word:
- A caption ends where the speaker's phrase ends. Never let the last word of a phrase fall into the next caption
  ("I have three" / "wallets ..."). Too long for two lines: split at a natural point (before "but", "because",
  a comma). This was called out as amateur; `--check` rejects the known bad shapes.
- Captions say what was said. Fix mis-heard names and terms, write numbers and money as digits. A word you cannot
  make out even after re-transcribing that snippet: cut around it, do not guess.
- `in` = first word - 0.07s, `out` = last word + 0.10s and before the next word starts.

## Step 6: render and check
1. `PY SK/scripts/trailer.py <project> --check` until there is no PROBLEM line and TOTAL is inside the budget.
   Over budget: drop a line. Never speed up speech.
2. `PY SK/scripts/trailer.py <project>` (2-3 min; later rounds ~1 min, unchanged shots are cached).
   `--overwrite` replaces the latest version instead of making vN+1.
3. Look at `work/qa.jpg`: no heads in the window, cards readable, captions inside the black band.
4. `PY SK/scripts/verify.py <project>`: it transcribes the render and prints it next to the captions. A missing or
   extra word at a cut means speech was clipped: move that `in`/`out` by 0.05-0.1s and render again. Levels should be
   about mean -16 dB, max -1.5 dB.

## Step 7: hand over
Give the path of the `-phone.mp4` (small, for messaging) and the full file, the line list in order, what you
dropped and why, and what you were unsure of. Say plainly that you cannot hear the mix: they should listen once
for the card hits and the low drone, and tell you "hits louder", "no drone" (`"bed": false`), etc.
The built-in drone is a placeholder; a real track added in Instagram or CapCut, or an mp3 they give you, does more
for the trailer feel than anything else. Notes come back → edit `trailer.json` → render again.

## Rules that came from real feedback (not up for debate)
1. 60 seconds is the ceiling. Aim under it.
2. It is a teaser, not a summary: a few impressive lines, not every topic.
3. Captions break at phrase boundaries (above).
4. Trailer grammar, not plain hard cuts and not dissolves: black number cards landing on a bass hit, letterboxed
   graded shots with a slow push-in, hard cuts into black, title card, stinger.
5. Audience heads are cropped out; the frame is the speaker and the slide.
6. Side noise is removed; the speaker's voice is the only thing the viewer should hear clearly.
7. Messages meant for a boss or a client: 3-4 casual lines.

## Files
`scripts/setup.py` environment · `ingest.py` transcription · `mark.py` highlight page · `draft.py` marks → first
edit · `trailer.py` render (trailer style) · `teaser.py` plainer style with headlines and dissolves (older, kept
for "simple" requests) · `verify.py` post-render check · `words.py` phrase chunking.
`trailer.json`: `{"name", "budget", "window": {"y", "h"}, "bed": true, "items": [shot | card, ...]}`; see
`assets/trailer.example.json`.

## Gotchas
- This ffmpeg may lack drawtext/subtitles: all text is drawn with Pillow. Do not try to burn subtitles with ffmpeg.
- The denoiser is run in a separate audio pass from inside `assets/` (in one graph with the video it produced NaN
  samples the AAC encoder refused; a Windows path inside a filter string needs escaping).
- Whisper's word times on room audio drift 0.1-0.3s and it can stretch the last word of a sentence: trust
  `verify.py` on the final render, not the first transcript.
- A far-back wide angle needs zoom 2 and is visibly softer: prefer lines filmed from closer.
- Never delete, move or re-encode the person's original clips.
