# Editing techniques: a library to choose from

This is a reference, not a checklist. No video uses all of it. Read the footage and the brief first, then pick
the few techniques that serve *this* video and leave the rest. A 20-second fact needs two or three; a 60-second
trailer maybe six. When a technique does not clearly help, skip it.

How to choose:
- **Start from the goal** (table at the end), then the footage: what is actually in the frame, how clean the
  takes are, whether the slides are readable.
- **One job per technique.** If two techniques do the same job (a punch-in and a card both stressing the same
  number), keep the stronger one.
- **Consistency beats variety.** A device used once looks like a glitch; used with a pattern (every number gets a
  card) it looks like style. Random changes of rhythm read as mistakes.
- **Nothing static for long.** A rule of thumb from retention editors: on short-form, look for any ~5-second
  stretch where nothing changes (no cut, zoom, text or sound) and give it one change. One, not three.
- **Honesty limits everything:** never rearrange words into a sentence the speaker did not say, never put a
  number or claim on screen that is not in the talk, never invent names, dates or links.

Each entry: what it is · use it when · skip it when · how to do it here. "Built in" means `trailer.py` does it
from `trailer.json`; "not built" entries are ideas with what they would need.

---

## Structure

**Cold open.** Start on the strongest line with no intro, logo or greeting. · Almost always. · Never skip; a title
or "hi everyone" first loses the first second, which is where most viewers leave. · Put that shot first.

**Three waves (trailer build).** Sparse opening, a middle that adds stakes, a fast finish with the biggest hits,
then the title. · Sign-up trailers of 40-60s with 5+ lines. · Short single-fact videos. · Order shots from
calm/personal to alarming; shorten shots as it goes; biggest number card last before the title.

**Nothing resolves.** Raise the question, withhold the full answer. · Follows and sign-ups. · Likes-and-shares
videos, which must feel complete. · End a section on the problem ("they take everything but $20,000") and cut
before the fix, or show only the first half of the fix.

**One idea only.** The whole video is a single fact and its consequence. · "Likes and shares", lengths under 30s.
· When the brief is a trailer. · One card, two or three shots, end card.

**Open loop early, close it late.** State in the first line that something is coming ("there are two reasons"),
deliver it at the end. · The speaker himself sets it up in the talk. · You would have to invent the setup.

**Button / stinger.** One last short line after the title card, the thing people remember. · Trailers; when
there is a punchy 1-2s line ("This one you must know."). · No short line exists; do not force a long one.
· Title card → 1s shot at higher zoom, `push` 0.03 → end card.

## Opening (the first 2 seconds)

**On-screen hook.** A short claim or question in large type while the first line plays, so the point lands on
mute. · The first line needs context, or the audience would not know it concerns them. · The first line is
already a complete, startling sentence (the caption does the job). · Built in: top-level `"hook": "..."`, shown
above the window during the first shot. Use the speaker's own claim, 3-7 words.

**Name tag (lower third).** Who is speaking, for credibility. · A name and title were given on the page. ·
Never invent one; skip when not given. · Built in: `"speaker": {"name", "title"}`, first shot, 3.5s.

**Start mid-gesture.** Begin the first shot when the speaker is already moving or pointing, not from rest. ·
Always worth a look. · Would clip the first word. · Choose `in` by the word time; check the framing sheet.

## Cuts and framing

**Punch-in on the key word.** Mid-sentence, the frame jumps closer exactly as the important number or claim
starts; the voice does not break. · One to three key claims per video. · Every sentence (it stops meaning
anything); wide shots that are already at zoom 2. · Built in: split the shot at the word, second part
`"cont": true` with `zoom` +0.25 to +0.35.

**Punch-out for the reveal.** The reverse: start tight, cut wider when the slide or the result matters. · The
slide shows the number being discussed. · The slide is unreadable. · Same as above with a lower `zoom`.

**Slide close-up (cutaway to evidence).** While he keeps talking, cut to the part of the slide that proves it.
· Readable chart, table or figure. · Text too small to read at 1080 wide: use a card instead. · Built in:
`"cont": true` shot with `cx`/`cy`/`zoom` on the slide.

**Cutaway / B-roll over the voice (L-cut).** The voice continues while the picture shows something else: the
room, an audience reaction, another moment. · A long line that needs a visual change; a reaction shot exists. ·
The cutaway shows nothing in particular. · Built in: `"cont": true` shot with
`"picture": {"clip": "c3", "in": 41.0}` (frames from there, voice from here; `cx`/`cy`/`zoom` refer to the picture).

**J-cut onto a card.** The next line starts under the card before the picture arrives; hides the seam and pulls
the viewer forward. · Number cards followed by the line that explains them. · The first words of the line are
essential to read on a caption (they play over the card without one). · Built in: `"jcut": 0.5` on the shot after
the card (0.3-0.6s; 6-18 frames is the usual range).

**Wordless scene.** A second or two of the room, the crowd, the speaker laughing, with only music. · Events with
real atmosphere: full room, reactions, applause. · Small rooms and backs of heads: it shows the opposite of what
you want. · Built in: a shot with `"mute": true` and no captions.

**Jump cut inside a sentence.** Remove a filler or a restart and hide it with a zoom change. · "Um", repeated
words, a restarted sentence. · The join would change the meaning. · Two shots, second one a different `zoom`.

**Follow the speaker.** The crop pans with a speaker who walks, as a camera operator would. · Default; it only
moves when they would leave the frame. · Slide close-ups and any shot that must stay locked (`"track": false`).
· Built in.

**Slow push-in.** A barely visible zoom through each shot so nothing is ever still. · Default. · Shots under 1s
(use `push` 0.03). · Built in: `push`, default 0.05.

**Shorter shots toward the end.** Acceleration reads as momentum. · Trailers. · Videos with only 2-3 shots.

**Letterbox + grade.** Black bars, darker, less saturated, vignette: reads as "film" and hides a plain room. ·
Default for this skill. · If the person asks for a bright, plain look (then use `teaser.py`).

**Crop the audience out.** Frame only the speaker and the slide. · Always, when filmed from the seats.

## Captions and on-screen text

**Phrase-accurate captions.** One caption per spoken phrase, breaking where he breaks. · Always; most social
video is watched without sound. · Built in; `--check` enforces it.

**Spoken-word highlight.** The word being said turns gold. · Default; keeps the eye moving. · Dense technical
lines where the flicker distracts (`"karaoke": false`). · Built in.

**Digits, not words.** "$110,000", "10-year", "1 in 11". · Always.

**Keyword card instead of a long caption.** If a line is too long to read, the card carries the fact and the
caption stays short. · Lines with one number that matters.

**Not built: keyword colour inside captions** (a fixed emphasised word per caption regardless of timing), **emoji
or arrows**, **word-by-word pop-in**. Arrows and emoji suit casual creator content more than a finance seminar.

## Cards and graphics

**Number card.** Black, one huge fact, ~1.1s, before the line that explains it. · Any line built on a number or
a hard term. · More than ~5 in a video; facts the speaker does not say. · Built in: `"type": "card"`.

**Slam + flash.** The card lands with a scale overshoot and a one-frame flash, on a bass hit. · Default for
cards. · Calm, reflective videos: `"flash": false`, lower `"hit"`. · Built in.

**Number roll-up.** The figure counts up from 0. · Money and counts of 10 or more. · Years, dates, ratios like
"1 IN 11" (handled: only a leading number ≥ 10 rolls); set `"count": false` when rolling makes no sense. · Built in.

**Title card.** Event or series name, "COMING SOON". · Sign-ups, series. · Single-fact videos. · Built in.

**Copy card.** A card that states the theme in words rather than a number ("THE CATCH"). · One per video at most,
to turn the story. · When a number card is available; too many copy cards break the rhythm.

**Progress line.** A thin line that fills as the video plays; viewers who see the end is near tend to stay. ·
Default, 30s+. · Very short videos or when the person finds it distracting (`"progress": false`). · Built in.

**Brand on the last card.** Logo above, account name below, the brand's accent colour throughout. · The person
switched a brand on. · Never on your own; never a watermark over the footage. · Built in from `brand`.

**Graphics stay quiet.** Text exists to be read once and get out of the way. If a card draws attention to its
own animation, tone it down.

**Not built: speaker + slide split screen** (slide large on top, speaker below; would use the empty bands and
make small slides readable; needs a second crop and a stacked layout), **animated chart rebuild** of a slide.

## Sound and music

**Voice first.** Denoise, level, and keep everything else under it. · Always. · Built in.

**Music that ducks.** The track drops under speech and swells on cards. · Whenever a track is chosen. · Built in.

**Match the music to the talk.** Calm piano or ambient for an advisory seminar; the intense "Trailer" track only
for a deliberate movie-trailer joke or a big launch. The person chooses on the page; if they ask, recommend calm.

**Hit on every card.** A low impact as the card lands; ties picture to sound. · Default. · Gentle videos:
`"hit": 0.15` or `0`. · Built in.

**Silence before the title.** Everything drops out for half a second, then the title lands; the contrast makes
the hit feel twice as big. · Once per video, before the title or the biggest card. · More than once. · Built in:
`"drop": 0.5` on that card (needs a music track).

**Whoosh into a card.** A short air sound pulling into the cut. · Default, very quiet. · Built in.

**Leave a breath.** A beat of nothing after a heavy line lets it land. · After the single most important line.
· Everywhere (kills pace). · Extend that shot's `out` by 0.2-0.3s if the room is quiet there.

**Not built: riser into the hit** (needs a riser sound), **cutting on the beat of the track** (needs beat
detection; would let cards land on downbeats).

## Endings

**End card with one action.** One line: follow, comment with X, sign up at Y. · Always. · Never two asks.

**Question ending.** The last card asks something concrete the viewer can answer in a comment. · Goal: comments.
· The question is generic ("What do you think?").

**Cliffhanger ending.** Stop before the answer; "Follow for part 2". · Goal: follows, and a part 2 will really
exist. · When there is no next part: it reads as bait.

**Not built: loop ending** (last frame flows back into the first so replays count; needs a line whose end leads
into the opening).

---

## By goal

| Goal | Usually | Sometimes | Rarely |
|---|---|---|---|
| Sign-ups | three waves, number cards, title card, stinger, silence before the title, J-cuts | hook text, name tag, punch-ins | question ending |
| Follows | cold open, nothing resolves, cliffhanger ending, one or two cards | punch-in, hook text | title card, stinger |
| Likes and shares | one idea only, one card with roll-up, complete ending | slide close-up, punch-in on the number | cliffhanger, three waves |
| Comments | cold open, debatable line last, question ending | copy card | title card, heavy hits |

## By footage

- Readable slides → slide close-ups. Unreadable slides → number cards carry the facts.
- Close, clean angle → punch-ins and tight framing. Far wide angle (already at zoom 2) → no punch-ins; cut more
  often between lines instead.
- Full, lively room → wordless scenes and reaction cutaways. Small room → keep the audience out entirely.
- One continuous take with fillers → jump cuts with zoom changes. Clean separate lines → cards between them.
- Under 25 seconds → cold open, one card, end card. Leave everything else out.

## Sources behind this list

Rules of thumb collected from trailer-editing and retention-editing guides; the numbers in such guides disagree
with each other and are starting points, not laws.
- Trailer structure, title cards, the button: jonnyelwyn.co.uk "How to Edit a Movie Trailer"; filmeditingpro.com
  "Hollywood trailer editing basics"; indiefilmhustle.com IFH 181.
- Trailer sound (riser → hit, silence before the hit, ducking under dialogue): violetrecording.com "Sound Design
  for Trailers".
- J-cuts and L-cuts: capcut.com "J-cuts and L-cuts"; finchley.co.uk podcast post-production notes (6-12 frames).
- Retention editing (pattern interrupts, punch-ins, no static stretches): opus.pro "50 video editing tips";
  joyspace.ai "Pattern interrupts"; air.io "Advanced retention editing".
- Talks into social clips (hook, captions for muted viewing, readable slides, reactions): klap.app "Conference
  video editing"; slideslive.com "Get more value from your event recordings".
