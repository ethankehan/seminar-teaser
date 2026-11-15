#!/usr/bin/env python3
"""One-time (and every-run) environment check for /seminar-teaser. Safe to run again: it only repairs.

Run with whatever Python the machine has:  python3 setup.py   |   python setup.py   |   py -3 setup.py
It prints STATUS lines and ends with READY, or tells you the one command that fixes what is missing.
Writes <skill>/.platform.json: {"python": "<the skill's own venv python>", "os": ..., "ready": true}.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.path.join(SK, '.venv')
OSN = {'Darwin': 'macos', 'Windows': 'windows'}.get(platform.system(), 'linux')
PY = os.path.join(VENV, 'Scripts', 'python.exe') if OSN == 'windows' else os.path.join(VENV, 'bin', 'python')
# Pinned: PyAV 19 broke faster-whisper 1.2.1 ("unexpected keyword argument 'metadata_errors'").
PACKAGES = ['faster-whisper==1.2.1', 'av<19', 'pillow>=10']
FILTERS = ['arnndn', 'afftdn', 'zoompan', 'xfade', 'loudnorm', 'vignette', 'colorbalance']
SFX = ['whoosh-short', 'impact-bass-1']
# Pixabay-licensed pack: fine to use inside videos, not to redistribute as files, so it is fetched, not stored here.
SFX_URL = 'https://raw.githubusercontent.com/heygen-com/hyperframes/main/skills/media-use/audio/assets/sfx'
RESTART = 'then quit Claude Code completely and reopen it'
FIX = {'ffmpeg': {'macos': 'brew install ffmpeg', 'linux': 'sudo apt install ffmpeg',
                  'windows': f'winget install --id Gyan.FFmpeg -e   ({RESTART})'},
       'python': {'macos': 'brew install python', 'linux': 'sudo apt install python3 python3-venv',
                  'windows': f'winget install --id Python.Python.3.12 -e   ({RESTART})'}}
TXT = dict(capture_output=True, encoding='utf-8', errors='replace')


def say(*a):
    print(*a, flush=True)


def check_ffmpeg():
    ff = shutil.which('ffmpeg')
    if not ff or not shutil.which('ffprobe'):
        say(f"STATUS ffmpeg MISSING -> {FIX['ffmpeg'][OSN]}")
        return False
    have = subprocess.run([ff, '-hide_banner', '-filters'], **TXT).stdout
    lacking = [f for f in FILTERS if f' {f} ' not in have]
    if lacking:
        say(f"STATUS ffmpeg INCOMPLETE (no {' / '.join(lacking)}) -> install a full build: {FIX['ffmpeg'][OSN]}")
        return False
    say('STATUS ffmpeg OK')
    return True


def venv_works():
    if not os.path.exists(PY):
        return False
    test = ("import faster_whisper, PIL, av; from PIL import ImageFont; import sys; "
            "ImageFont.truetype(sys.argv[1], 40); print('ok')")
    r = subprocess.run([PY, '-c', test, os.path.join(SK, 'assets', 'fonts', 'Inter-600-normal.ttf')], **TXT)
    return r.stdout.strip() == 'ok'


def check_venv():
    if venv_works():
        say('STATUS python environment OK')
        return True
    if sys.version_info < (3, 9):
        say(f"STATUS python TOO OLD ({platform.python_version()}) -> {FIX['python'][OSN]}")
        return False
    say('STATUS python environment: installing (about 2 minutes, one time) ...')
    if not os.path.exists(PY):
        r = subprocess.run([sys.executable, '-m', 'venv', VENV], **TXT)
        if r.returncode:
            say(f"STATUS python environment FAILED (venv): {r.stderr.strip()[-300:]} -> {FIX['python'][OSN]}")
            return False
    subprocess.run([PY, '-m', 'pip', 'install', '--quiet', '--upgrade', 'pip'], **TXT)
    r = subprocess.run([PY, '-m', 'pip', 'install', '--quiet', *PACKAGES], **TXT)
    if r.returncode or not venv_works():
        say(f'STATUS python environment FAILED (pip): {(r.stderr or r.stdout).strip()[-400:]}')
        say('        Check the internet connection and run this script again.')
        return False
    say('STATUS python environment OK')
    return True


def check_sfx():
    d = os.path.join(SK, 'assets', 'sfx')
    os.makedirs(d, exist_ok=True)
    for n in SFX:
        p = os.path.join(d, n + '.mp3')
        if os.path.exists(p) and os.path.getsize(p) > 2000:
            continue
        try:
            req = urllib.request.Request(f'{SFX_URL}/{n}.mp3', headers={'User-Agent': 'seminar-teaser-setup'})
            with urllib.request.urlopen(req, timeout=30) as r, open(p, 'wb') as f:
                f.write(r.read())
        except Exception as e:  # offline: the video still renders, just without hits
            say(f'        could not download {n}.mp3 ({e})')
    missing = [n for n in SFX if not os.path.exists(os.path.join(d, n + '.mp3'))]
    say('STATUS sound effects OK' if not missing else
        f"STATUS sound effects MISSING ({' '.join(missing)}) -> optional; videos render without the card hits")
    return not missing


def main():
    say(f'STATUS system {OSN} {platform.machine()}')
    ok_ff, ok_py = check_ffmpeg(), check_venv()
    sfx = check_sfx()
    ready = ok_ff and ok_py
    with open(os.path.join(SK, '.platform.json'), 'w', encoding='utf-8') as f:
        json.dump({'schema': 1, 'ready': ready, 'os': OSN, 'python': PY.replace('\\', '/'),
                   'skill_dir': SK.replace('\\', '/'), 'sfx': sfx}, f, indent=1)
    say('READY' if ready else 'NOT READY: fix the lines above, then run this script again')
    sys.exit(0 if ready else 1)


if __name__ == '__main__':
    main()
