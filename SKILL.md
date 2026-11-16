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
**Continuing an earlier session?** If the person says so, or `<home>/seminar-videos/` holds a folder they mean,
run `PY SK/scripts/flow.py status <that folder>`: it prints the stage and whose move it is. Start `app.py` on that
folder again (it resumes where it stopped) and pick up from that stage. A page stuck on "Editing" means the
previous session ended before finishing: the move is yours.

Project folder: `<home>/seminar-videos/<YYYYMMDD-short-slug>`. Start the app in the background (it lives for the
whole session and exits by itself after the person presses Done):
`PY SK/scripts/app.py <project>`
- The person already told you where the clips are: add `--clips <folder or files>`; the first page lists them
  and nothing is copied. Add `--language en|zh|mixed` if they told you the language.
- Otherwise the page opens on "Add your videos" and they drop the files in (copied into `<project>/clips`).
- Either way the first page asks the language of the talk: English, 中文, or both mixed. English uses a small
  fast model; Chinese and mixed use a stronger one (about 3x slower, 1.6 GB download the first time).
- Clips under 1080p on the short side bring up a "Low resolution" page; the person decides to continue or go
  back. Any resolution and orientation is accepted and framed the same way.
Tell them one line: a page opened in the browser, follow it. If it did not open, the app printed `APP http://...`.

The page moves through stages; `state.json` holds the current one. You never poll. After each of your turns run
`PY SK/scripts/flow.py wait <project> <stages you act on>` in the background and act when it exits:

| Stage | Who | What happens |
|---|---|---|
| upload | person | drops videos, picks the language |
| lowres | person | only when a clip is under 1080p: continue or go back |
| transcribing | app | transcribes (about 1 min per minute of footage) |
| **suggesting** | **you** | read the talk, write audience suggestions |
| brief | person | audience, goal, length, optional speaker name and title |
| **planning** | **you** | decide how the material should be cut (one video or a series) and choose the lines |
| plan | person | picks one of your options (skipped when you offer only one) |
| highlight | person | adjusts your selection, once per video |
| music | person | picks a track, their own file, or none |
| **editing** | **you** | build and render, or apply their notes |
| review | person | watches; sends notes (back to editing) or presses Save |
| save | person | chooses the folder, which videos, and the quality; the app copies the files there |
| done | | app closes |

The page has a Back link (plan → brief, highlight → previous video / plan / brief, music → highlight, review →
music), so a stage can come round again.
`wait` prints `STAGE editing reason=...` so you know why you are editing:
- `lines`: first build, or they changed lines. `flow.py videos` marks each video CHANGED or not: rebuild only the
  changed ones (Step 4 with `draft.py --force`; first copy the `cx`/`cy`/`zoom` you already worked out for the
  same clips from the old `trailer.json`).
- `music`: only the music changed. Render again (about 1 minute), nothing else.
- `notes`: Step 7.

While you work the page shows "About N min left". The app estimates it (transcription from the footage length
and the measured speed; your stages from typical times). When you know better, say so:
`PY SK/scripts/flow.py set <project> editing "Editing video 2 of 4" --eta 300` (seconds from now). Update the
message as you move from one video to the next so the person sees progress.

First wait: `PY SK/scripts/flow.py wait <project> suggesting`. A stage of `error` ends any wait: read the message.

## Step 2: `suggesting` → audience suggestions
`PY SK/scripts/flow.py transcript <project>` prints every phrase with its key (`c1:14`), start time and length.
Read all of it. First write `<project>/fixes.json` for words the transcription clearly got wrong, so the person
never sees them: `[["BTOQ", "BTO queue"], ["introsa", "interest rate"]]` (whole words, case-sensitive; names,
terms and acronyms of the field; only where the context leaves no doubt). Run `transcript` again to check.
The person can also correct any phrase themselves on the "Pick the lines" page ("Edit text"); their wording is
kept in `edits.json`, wins over yours, and is what the captions use.
Then write `<project>/suggest.json`: `{"audiences": ["...", "...", "..."]}`: three, at most four,
concrete groups this talk would actually matter to, each under ~45 characters, most likely first, in the language
of the talk. Then `PY SK/scripts/flow.py set <project> brief` and wait for `planning`.

## Step 3: `planning` → how to cut it, and your lines for each video
Read `<project>/brief.json` (`audience`, `goal`, `length_seconds`; `speaker_name` / `speaker_title` are optional:
empty means no name tag, and `draft.py` adds the tag by itself when they are filled). `flow.py transcript` ends
with TOTAL SPEECH: compare what is worth showing with the length they chose.

Write `<project>/plan.json`:
```json
{"options": [
  {"id": "series", "title": "A series of three", "videos": [
     {"title": "Applying: timing and odds", "keys": ["c8:60", "c8:61", "c6:44"]},
     {"title": "Plus and Prime: the catch", "keys": ["c8:104", "c8:105"]},
     {"title": "Your CPF at key collection", "keys": ["c4:1", "c4:12", "c4:13"]}]},
  {"id": "one", "title": "One video", "videos": [{"title": "The BTO Seminar", "keys": ["c8:20", "c4:1", "c4:12"]}]}
]}
```
- **The material fits one video** (the good lines for this audience add up to about the chosen length or less):
  write ONE option with one video. The page skips the plan step.
- **More good material than one video holds** (many clips, several distinct topics): offer two or three options,
  the one you recommend first. The usual ones:
  - *One video*: the strongest lines across everything. Right when the goal is a single trailer or sign-up push.
  - *A series of N* (2-5): one topic per video, each able to stand alone, each with its own opening and close.
    Right for follows and when topics serve different viewers. Do not pad: a topic with under ~10s of good lines is
    not a video.
  - *A trailer plus a series*: only when both are genuinely wanted (sign-ups now, follow-up content later).
  Titles are 2-5 words in the talk's language; they show on the page and become each video's working title.
- For every video choose phrases adding up to at most `length_seconds - 8` (cards and the title need the rest;
  leave 5 for 15-20s videos), applying Step 5 already: the opening for this audience, the shape for this goal,
  complete phrases only. In a series no line appears in two videos.
Then `PY SK/scripts/flow.py set <project> plan` and wait for `editing`.

## Step 4: `editing`, first time → one folder per video
`PY SK/scripts/flow.py videos <project>` lists the videos: `<project>/v1`, `v2`, ... Each folder is a complete
project (their final lines in `marks.json`, `music.json`, `brief.json` with `video_title`). Work through them
**one at a time, in order**; everything below takes the video's folder as `<video>`.
`PY SK/scripts/draft.py <video>` → `trailer.json` (one shot per run of highlighted phrases, one caption per
phrase, every shot `"framed": false`) and `work/framing.jpg`. Its report:
- **OVER BUDGET**: do not silently drop their lines. In chat, say how many seconds over, list the lines with their
  lengths, recommend what to drop, and ask. Then continue.
- **NOTHING HIGHLIGHTED**: they left it to you: use your recommendation for that video.
A series should look like one family: same card style, same end card wording apart from the topic, the same
handful of techniques; number the end cards only if the person asked for numbering.

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
(speaker + slide), `zoom` so no audience heads are inside the window. Zoom 1 shows the full width of the footage;
keep zoom at 2 or below for 1080p footage and 4 or below for 4K. Two shots in a row from the same clip: give the
second a different zoom (1.15-1.3). Then delete `"framed": false`.
The speaker is followed automatically: when they would walk out of your framing the crop pans with them, like a
camera operator (face tracking; it leaves the shot alone when they stay inside). Frame for where they are at the
start of the shot. `"track": false` on a shot pins the frame, e.g. for a slide close-up.

**Techniques: choose, do not stack.** `SK/references/techniques.md` is the library: structure, openings, cuts,
captions, cards, sound, endings, each with when to use it, when to skip it and how to do it here, plus tables by
goal and by footage. Read it before the first edit of a session. Then pick the few that fit *this* video: its
goal, its length, what is really in the frame. Most videos need three to five; using everything makes every video
look the same and none of them good. If a technique does not clearly help, leave it out. When you find a
technique worth keeping (from the person's notes or elsewhere), add it to that file in the same format.
Quick map of what `trailer.json` supports: top level `hook`, `speaker`, `karaoke`, `progress`, `music`, `bed`;
per shot `zoom`, `push`, `cont`, `picture`, `jcut`, `mute`; per card `kicker`, `big`, `sub`, `hit`, `count`,
`flash`, `drop`, `fade_out`.

**Captions** are `[source_time, "text"]`, one per phrase, time = start of its first word:
- A caption ends where the speaker's phrase ends. Never let the last word of a phrase fall into the next caption
  ("I have three" / "wallets ..."). Too long for two lines: split at a natural point. `--check` rejects the known
  bad shapes.
- Captions say what was said. Fix mis-heard names and terms, write numbers and money as digits. A word you cannot
  make out even after re-transcribing that snippet: cut around it.
- `in` = first word - 0.07s, `out` = last word + 0.10s and before the next word starts.

**Brand.** `brief.json` has `brand` (what to apply: `logo`, `handle`, `color`; empty = none) and `brand_kit`
(name, handle, colour, logo path). `draft.py` puts it into `trailer.json` and the renderer does the rest: the
accent colour replaces gold, the logo and the account name go on the last card. The brand is visual only: it does
not change which lines you choose or how you word them. Tone requirements come from the person, in their words.
The kit lives in `<home>/seminar-videos/brand/` on each computer and is edited on the page. Never copy brand
files, names or colours into the skill folder: the skill is public, the brand is not.

**Chinese and mixed talks.** Everything above holds. Captions break at Chinese punctuation; a caption fits about
20 characters per line. Card text, hook and name tag can be Chinese (a Chinese font is bundled). Keep each on-screen
text in the language the speaker used for that line; do not translate.

## Step 6: render, check, show
1. `PY SK/scripts/trailer.py <video> --check` until no PROBLEM line and TOTAL fits the length they chose.
   Over: drop a line. Never speed up speech.
2. `PY SK/scripts/trailer.py <video>` (2-3 min; later rounds ~1 min, unchanged shots are cached).
3. Look at `work/qa.jpg`: no heads in the window, cards readable, captions inside the black band.
4. `PY SK/scripts/verify.py <video>`: compares what is heard in the render with the captions. A missing or extra
   word at a cut means speech was clipped: move that `in`/`out` by 0.05-0.1s and render again.
5. When every video is rendered and checked:
   `PY SK/scripts/flow.py set <project> review --video <v1 -phone.mp4> --video <v2 -phone.mp4> ...` (one `--video`
   per video, in order); the page now plays them.
   Wait: `PY SK/scripts/flow.py wait <project> editing done`.

## Step 7: notes loop
`editing reason=notes` means they sent notes: read the entries with `"handled": false` in `<project>/notes.json`
(`video` says which one), apply them to
`trailer.json`, set them handled, render, verify, `set review --video ...` again, wait again.
Music notes: `"music": {"file": "...", "volume": 0.7}` in trailer.json overrides the page's choice (1.0 is the
default level; the track ducks under the voice by itself). `"bed": false` removes the drone used when there is no
track; `"hit"` per card sets the bass hit.
`done`: they saved the videos from the page (`saved` in `state.json` lists the files and the folder they chose;
the originals stay in each `<project>/vN/renders`). Tell them where the files are, the lines in order,
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
`teaser.py` shared helpers and an older plain style · `words.py` phrase chunking · `track.py` speaker tracking.
`references/techniques.md` the technique library. `assets/music/` six CC0 tracks (five calm, one intense "Trailer") listed in `assets/music.json`. `assets/trailer.example.json` shows the edit format.

## Gotchas
- This ffmpeg may lack drawtext/subtitles: all text is drawn with Pillow.
- The denoiser runs in a separate audio pass from inside `assets/` (in one graph with the video it produced NaN
  samples; a Windows path inside a filter string needs escaping).
- Whisper's word times on room audio drift 0.1-0.3s: trust `verify.py` on the render.
- A far-back wide angle needs zoom 2 and is visibly softer: prefer lines filmed from closer.
- The app was restarted or crashed: start it again on the same project; it resumes at the saved stage.
- Never delete, move or re-encode the person's original clips.

## Updating the skill
When the person asks to update: `git -C "SK" pull --ff-only`, then run `SK/scripts/setup.py` again and tell them
what changed (`git -C "SK" log --oneline -5`). Never update on your own in the middle of a session.
