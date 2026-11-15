---
name: seminar-teaser
description: "Turns seminar or talk footage (phone, vertical, filmed from the audience) into a short trailer-style social video through one local web page: the person drops in the videos, picks the audience, goal and length, adjusts the AI-recommended lines, chooses music, then reviews the result and sends notes. Claude does the reading, recommending, cutting, grading, denoising and subtitling in between. Everything runs locally. Trigger with /seminar-teaser or 'cut the seminar video', 'make a teaser from the talk', 'edit the talk footage', '剪 seminar 视频', '做个预告'."
---

# /seminar-teaser

Talk footage in, a short social video out. The person works in one web page; you work between its steps.

Speak to the person in their language. Everything in the video is in the language of the talk.
Nothing leaves this computer: no uploads to the internet, no paid services.

## Step 0: setup (every run, a few seconds after the first time)
`SK` = the folder holding this file (usually `~/.claude/skills/seminar-teaser`).
Run `SK/scripts/setup.py` with whichever Python exists; try in order `python3`, `python`, `py -3`. (On Windows
`python3` is often a Store stub that prints "Python was not found": try the next one.) Read its STATUS lines:
- `READY`: continue. Read `SK/.platform.json`; `PY` = its `python` value. Run every other script with `PY`.
- `MISSING` / `INCOMPLETE`: the line ends with the exact fix for this machine. Give it to the person, stop, and
  re-run setup after they did it. On Windows a newly installed program is only found after Claude Code is fully
  quit and reopened.
- The first run installs Python packages (~2 min); the first transcription downloads a speech model (~0.5 GB).

Command style that works in zsh, bash, Git Bash and PowerShell: full paths in double quotes with forward slashes,
one command per call, no `&&`, no `~` inside arguments. In PowerShell put `&` in front of a quoted program.

**One heavy process at a time.** Never run two renders, two transcriptions, or sub-agents in parallel.

## Step 1: open the page
Project folder: `<home>/seminar-videos/<YYYYMMDD-short-slug>`. Start the app in the background (it lives for the
whole session and exits by itself after the person presses Done):
`PY SK/scripts/app.py <project>`
- The person already told you where the clips are: add `--clips <folder or files>`; the page then skips the upload
  step and nothing is copied.
- Otherwise the page opens on "Add your videos" and they drop the files in (copied into `<project>/clips`).
Tell them one line: a page opened in the browser, follow it. If it did not open, the app printed `APP http://...`.

The page moves through stages; `state.json` holds the current one. You never poll. After each of your turns run
`PY SK/scripts/flow.py wait <project> <stages you act on>` in the background and act when it exits:

| Stage | Who | What happens |
|---|---|---|
| upload | person | drops videos |
| transcribing | app | transcribes (about 1 min per minute of footage) |
| **suggesting** | **you** | read the talk, write audience suggestions |
| brief | person | audience, goal, length |
| **recommending** | **you** | choose the lines for that brief |
| highlight | person | adjusts your selection |
| music | person | picks a track, their own file, or none |
| **editing** | **you** | build and render, or apply their notes |
| review | person | watches; sends notes (back to editing) or presses Done |
| done | | app closes |

First wait: `PY SK/scripts/flow.py wait <project> suggesting`. A stage of `error` ends any wait: read the message.

## Step 2: `suggesting` → audience suggestions
`PY SK/scripts/flow.py transcript <project>` prints every phrase with its key (`c1:14`), start time and length.
Read all of it. Write `<project>/suggest.json`: `{"audiences": ["...", "...", "..."]}`: three, at most four,
concrete groups this talk would actually matter to, each under ~45 characters, most likely first, in the language
of the talk. Then `PY SK/scripts/flow.py set <project> brief` and wait for `recommending`.

## Step 3: `recommending` → your version of the highlights
Read `<project>/brief.json` (`audience`, `goal`, `length_seconds`). Choose phrases whose lengths add up to at most
`length_seconds - 8` (cards and the title need the rest; for 15-20s videos leave 5). Apply the editing rules in
Step 5 already here: the right opening for this audience, the shape for this goal, complete phrases only.
Write `<project>/recommend.json`: `{"keys": ["c1:1", "c1:13", ...]}`, then
`PY SK/scripts/flow.py set <project> highlight` and wait for `editing`.

## Step 4: `editing`, first time → draft
The person's final selection is in `marks.json`, the music choice in `music.json` (trailer.py reads it by itself).
`PY SK/scripts/draft.py <project>` → `trailer.json` (one shot per run of highlighted phrases, one caption per
phrase, every shot `"framed": false`) and `work/framing.jpg`. Its report:
- **OVER BUDGET**: do not silently drop their lines. In chat, say how many seconds over, list the lines with their
  lengths, recommend what to drop, and ask (or offer a series of 2-3 videos). Then continue.
- **NOTHING HIGHLIGHTED**: they left it to you: use your recommendation.

## Step 5: edit `trailer.json` (the actual editing; take care)
The highlighted lines are the content. You decide order, trims, framing, cards and wording.

**The goal decides the shape:**
| Goal | Shape |
|---|---|
| Follows | Strongest line first. Leave one thing unfinished. Last card: follow line (+ handle if they gave one). |
| Likes and shares | One surprising fact, told completely, 20-35s. The fact is the first card. No cliffhanger. |
| Comments | End on the most debatable or counter-intuitive line; the last card asks one concrete question. |
| Sign-ups | Trailer for the next event: number cards, title card with the event name, date and link if given, then a stinger line. |

**The audience decides the opening and the vocabulary:** lead with the line about *their* situation, money or
odds, and put *their* word on the card kicker. Drop highlighted lines that only matter to a different audience and
say that you did.

**Order for impact, not chronology.** Opening: personal or startling. Middle: one idea per card. Close: the
"you must know this" line. A phrase can be trimmed to its strongest clause; never join words from different
sentences into a sentence the speaker did not say.

**Never invent** a date, venue, link, handle, name or title. Unknown means the card stays generic
("COMING SOON", "Follow for the date"). Ask in chat if the goal is sign-ups and nothing was given.

**Cards** (`"type": "card"`): a tracked gold `kicker` + one huge `big` fact, ~1.1s, placed BEFORE the line it sets
up. `big` must be something the speaker says in the following shot (a number, a term, 1-3 words). Title card ~2.8s
with `"hit": 0.55`; then one short stinger shot; then the end card with `sub` = the call to action and
`"fade_out": 0.6`. Short videos (under 25s): one or two cards plus the end card is enough.

**Framing** each shot from `work/framing.jpg` (grid labels are source pixels): `cx`, `cy` = centre of the stage
(speaker + slide), `zoom` so no audience heads are inside the window (1080x640 at zoom 1; zoom 2 is the limit for
1080p). Two shots in a row from the same clip: give the second a different zoom (1.15-1.3). Then delete
`"framed": false`.

**Captions** are `[source_time, "text"]`, one per phrase, time = start of its first word:
- A caption ends where the speaker's phrase ends. Never let the last word of a phrase fall into the next caption
  ("I have three" / "wallets ..."). Too long for two lines: split at a natural point. `--check` rejects the known
  bad shapes.
- Captions say what was said. Fix mis-heard names and terms, write numbers and money as digits. A word you cannot
  make out even after re-transcribing that snippet: cut around it.
- `in` = first word - 0.07s, `out` = last word + 0.10s and before the next word starts.

## Step 6: render, check, show
1. `PY SK/scripts/trailer.py <project> --check` until no PROBLEM line and TOTAL fits the length they chose.
   Over: drop a line. Never speed up speech.
2. `PY SK/scripts/trailer.py <project>` (2-3 min; later rounds ~1 min, unchanged shots are cached).
3. Look at `work/qa.jpg`: no heads in the window, cards readable, captions inside the black band.
4. `PY SK/scripts/verify.py <project>`: compares what is heard in the render with the captions. A missing or extra
   word at a cut means speech was clipped: move that `in`/`out` by 0.05-0.1s and render again.
5. `PY SK/scripts/flow.py set <project> review --video <the -phone.mp4>`; the page now plays it.
   Wait: `PY SK/scripts/flow.py wait <project> editing done`.

## Step 7: notes loop
`editing` again means they sent notes: read the entries with `"handled": false` in `notes.json`, apply them to
`trailer.json`, set them handled, render, verify, `set review --video ...` again, wait again.
Music notes: `"music": {"file": "...", "volume": 0.7}` in trailer.json overrides the page's choice (1.0 is the
default level; the track ducks under the voice by itself). `"bed": false` removes the drone used when there is no
track; `"hit"` per card sets the bass hit.
`done`: tell them where the files are (full quality and `-phone.mp4` in `<project>/renders`), the lines in order,
what you dropped and why. You cannot hear the mix: say so once and ask them to listen for the music level.

## Rules that came from real feedback (not up for debate)
1. 60 seconds is the ceiling.
2. It is a teaser, not a summary: a few impressive lines, not every topic.
3. Captions break at phrase boundaries.
4. Trailer grammar, not plain hard cuts and not dissolves: black number cards on a bass hit, letterboxed graded
   shots with a slow push-in, hard cuts into black, title card, stinger.
5. Audience heads are cropped out; the frame is the speaker and the slide.
6. Side noise is removed.
7. The web page stays minimal: one title per step, no sub-headings, no explanatory sentences, no examples unless
   something cannot be understood without one. Keep it that way when changing `app.py`.

## Files
`scripts/setup.py` environment · `app.py` the web page and its server · `flow.py` wait / set / transcript ·
`ingest.py` transcription · `draft.py` marks → first edit · `trailer.py` render · `verify.py` post-render check ·
`teaser.py` shared helpers and an older plain style · `words.py` phrase chunking.
`assets/music/` five CC0 tracks listed in `assets/music.json`. `assets/trailer.example.json` shows the edit format.

## Gotchas
- This ffmpeg may lack drawtext/subtitles: all text is drawn with Pillow.
- The denoiser runs in a separate audio pass from inside `assets/` (in one graph with the video it produced NaN
  samples; a Windows path inside a filter string needs escaping).
- Whisper's word times on room audio drift 0.1-0.3s: trust `verify.py` on the render.
- A far-back wide angle needs zoom 2 and is visibly softer: prefer lines filmed from closer.
- The app was restarted or crashed: start it again on the same project; it resumes at the saved stage.
- Never delete, move or re-encode the person's original clips.
