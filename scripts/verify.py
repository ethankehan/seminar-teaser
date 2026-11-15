#!/usr/bin/env python3
"""After a render: transcribe the newest video in <project>/renders and print it next to the captions, plus levels.

  PY verify.py <project_dir> [video.mp4]

Compare the two lists by eye: a word missing or added at the start or end of a line means a cut clipped speech.
"""
import glob
import json
import os
import re
import subprocess
import sys

from faster_whisper import WhisperModel

TXT = dict(capture_output=True, encoding='utf-8', errors='replace')


def main():
    project = os.path.abspath(os.path.expanduser(sys.argv[1]))
    if len(sys.argv) > 2:
        video = sys.argv[2]
    else:
        vids = [v for v in glob.glob(os.path.join(project, 'renders', '*.mp4')) if not v.endswith('-phone.mp4')]
        if not vids:
            sys.exit('No render found.')
        video = max(vids, key=os.path.getmtime)
    wav = os.path.join(project, 'work', 'verify.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-vn', '-ar', '16000', '-ac', '1', wav], check=True)
    vol = subprocess.run(['ffmpeg', '-hide_banner', '-i', video, '-af', 'volumedetect', '-f', 'null', '-'], **TXT).stderr
    levels = ' '.join(re.findall(r'(mean_volume: [-\d.]+ dB|max_volume: [-\d.]+ dB)', vol))
    model = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=4)
    segs, _ = model.transcribe(wav, beam_size=5)
    print(f'VIDEO {video}\nLEVELS {levels}\n\nHEARD IN THE RENDER:')
    for s in segs:
        print(f'  {s.start:5.1f}  {s.text.strip()}')
    for name, key in (('trailer.json', 'items'), ('teaser.json', 'segments')):
        p = os.path.join(project, name)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                items = json.load(f)[key]
            print(f'\nCAPTIONS IN {name}:')
            for it in items:
                for _, text in it.get('captions', []):
                    print(f'         {text}')
            break
    os.remove(wav)


if __name__ == '__main__':
    main()
