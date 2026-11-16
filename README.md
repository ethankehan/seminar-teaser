# seminar-teaser

A Claude Code skill that turns seminar or talk footage into a short, trailer-style social video.

One page opens in your browser and walks you through it: add the videos, choose who it is for, what it should
achieve and how long, adjust the lines Claude recommends, pick the music, then watch the result and type what to
change. Claude cuts, crops out the audience, cleans the audio and adds subtitles and number cards in between.

Everything runs on your own computer. No footage is uploaded and nothing is paid for per use.

## What you need
- [Claude Code](https://claude.com/claude-code)
- Python 3.9 or newer
- ffmpeg

| | macOS | Windows (PowerShell) |
|---|---|---|
| ffmpeg | `brew install ffmpeg` | `winget install --id Gyan.FFmpeg -e` |
| Python | `brew install python` | `winget install --id Python.Python.3.12 -e` |

On Windows, quit Claude Code completely and reopen it after installing either of these.

## Install
macOS:
```bash
git clone https://github.com/ethankehan/seminar-teaser.git ~/.claude/skills/seminar-teaser
```
Windows (PowerShell):
```powershell
git clone https://github.com/ethankehan/seminar-teaser.git "$env:USERPROFILE\.claude\skills\seminar-teaser"
```
Restart Claude Code. The first run sets itself up (about 2 minutes) and downloads a speech-recognition model
(about 0.5 GB) the first time it transcribes.

Update later with `git pull` inside that folder.

## Use
In Claude Code, type:
```
/seminar-teaser
```
A page opens in your browser:
1. Drop in your videos and choose the language of the talk (English, 中文, or both).
2. Choose the audience (Claude suggests a few), the goal and the length.
3. If there is more good material than one video holds, Claude offers ways to cut it (one video, or a series).
4. Claude highlights the lines it would use, for each video. Add or remove lines; the counter shows the seconds.
5. Pick a track, use your own, or go without music.
6. Watch the result. Type what should change, or press **Save**.
7. Choose the folder, which videos to keep, and full quality or a small copy for messaging.

Waiting pages show roughly how long is left.

Footage that works best: vertical phone video of one speaker in front of slides, filmed from as close as possible.

## Your brand
On the second page you can switch on a brand: logo and account name on the last card, your colour as the accent.
Set it up once (name, account, colour, a logo PNG for dark backgrounds); it is kept in a `seminar-videos/brand`
folder in your home folder on that computer and is never uploaded anywhere. One optional line in its
`brand.json` helps: `terms` (names and words of your field, so they are transcribed correctly).

## Updating
Tell Claude "update the seminar-teaser skill". It pulls the latest version from this page.

## Good to know
- 60 seconds is the upper limit.
- Any resolution works, portrait or landscape. Clips under 1080p bring up a warning first.
- A speaker who walks is followed automatically.
- Chinese and mixed talks use a larger speech model: slower, and a 1.6 GB download the first time.
- Claude cannot hear. Listen once and say if the music or the hits should be louder, softer or gone.
- Transcripts of live rooms contain mistakes. Claude fixes obvious ones and cuts around words it cannot make out.

## Not working?
Ask Claude to "run the seminar-teaser setup and tell me what is missing". It prints the exact command to fix it.

## License
The code is released under the MIT License (see `LICENSE`). The bundled fonts and the noise reduction model keep
their own terms, listed below.

## Credits
- Fonts: DM Serif Display, Inter, Montserrat, Noto Sans SC (SIL Open Font License, see `assets/fonts/OFL.txt`).
- Noise reduction model `assets/sh.rnnn`: from [GregorR/rnnoise-models](https://github.com/GregorR/rnnoise-models).
- Music in `assets/music/`: six CC0 (public domain) tracks from OpenGameArt; sources in `assets/music.json`.
- Sound effects are not stored in this repository. Setup downloads two files from a Pixabay-licensed pack, which
  may be used inside videos but not redistributed as files.
