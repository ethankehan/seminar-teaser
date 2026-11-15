#!/usr/bin/env python3
"""Register the raw clips of a project and transcribe them with word timestamps.

  PY ingest.py <project_dir> <clip files or one folder> [--model small.en] [--language en]

Writes <project_dir>/sources.json ({"c1": "/abs/clip.mp4", ...}, ordered by file name) and words_cN.json
([{"text", "start", "end"}, ...]). Clips already transcribed are skipped, so it can be re-run after an interruption.
About 1 minute per minute of footage on a laptop CPU; the first run downloads the Whisper model (~0.5 GB).
Originals are only read.
"""
import json
import os
import sys

from faster_whisper import WhisperModel

VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.mkv', '.avi')


def main():
    args = [a for a in sys.argv[1:]]
    opt = {'--model': 'small.en', '--language': 'en'}
    for k in list(opt):
        if k in args:
            i = args.index(k); opt[k] = args[i + 1]; del args[i:i + 2]
    project, inputs = os.path.abspath(os.path.expanduser(args[0])), [os.path.expanduser(a) for a in args[1:]]
    files = []
    for p in inputs:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(VIDEO_EXT) and not f.startswith('.')]
        else:
            files.append(p)
    files = sorted(set(os.path.abspath(f) for f in files), key=lambda f: os.path.basename(f).lower())
    if not files:
        sys.exit('No video files found.')
    os.makedirs(os.path.join(project, 'work'), exist_ok=True)
    src_path = os.path.join(project, 'sources.json')
    src = json.load(open(src_path, encoding='utf-8')) if os.path.exists(src_path) else {}
    for f in files:                       # keep existing ids stable, append new clips
        f = f.replace('\\', '/')
        if f not in src.values():
            src[f'c{len(src) + 1}'] = f
    with open(src_path, 'w', encoding='utf-8') as fh:
        json.dump(src, fh, indent=1, ensure_ascii=False)

    model = None
    for cid, f in src.items():
        out = os.path.join(project, f'words_{cid}.json')
        if os.path.exists(out):
            print(f'{cid} already transcribed', flush=True)
            continue
        if model is None:
            model = WhisperModel(opt['--model'], device='cpu', compute_type='int8', cpu_threads=4)
        print(f'{cid} transcribing {os.path.basename(f)} ...', flush=True)
        lang = None if opt['--language'] in ('auto', '') or opt['--model'].endswith('.en') else opt['--language']
        segs, _ = model.transcribe(f, word_timestamps=True, beam_size=5, language=lang or ('en' if opt['--model'].endswith('.en') else None))
        words = [{'text': w.word.strip(), 'start': round(float(w.start), 2), 'end': round(float(w.end), 2)}
                 for s in segs for w in s.words if w.word.strip()]
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(words, fh, ensure_ascii=False)
        print(f'{cid} done: {len(words)} words', flush=True)
    print(f'INGESTED {len(src)} clips -> {project}', flush=True)


if __name__ == '__main__':
    main()
