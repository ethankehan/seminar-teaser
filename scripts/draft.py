#!/usr/bin/env python3
"""Turn the highlighted phrases (marks.json) into a first trailer.json and a framing sheet.

  PY draft.py <project_dir> [--force]

- Neighbouring highlighted phrases of one clip become one shot; each phrase becomes one caption (already phrase
  shaped, so captions break where the speaker breaks).
- In/out come from the word times: first word - 0.07s, last word + 0.10s (never into the next word).
- Shots are written in the order they were spoken, each with "framed": false and a centred default crop.
  The editor (Claude) then reorders for impact, trims to the budget, sets cx/cy/zoom from work/framing.jpg,
  fixes mis-heard words, and adds the cards. trailer.py refuses to render while a shot is still unframed.
- An existing trailer.json is kept; the draft goes to trailer.draft.json unless --force.
"""
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teaser as T  # noqa: E402
import words as W  # noqa: E402


def main():
    project = os.path.abspath(os.path.expanduser(sys.argv[1]))
    src, words = W.load(project)
    with open(os.path.join(project, 'marks.json'), encoding='utf-8') as f:
        marks = json.load(f)
    brief = {}
    if os.path.exists(os.path.join(project, 'brief.json')):
        with open(os.path.join(project, 'brief.json'), encoding='utf-8') as f:
            brief = json.load(f)
    budget = int(brief.get('length_seconds', 60))
    order = list(src)
    ms = sorted(marks.get('marks', []), key=lambda m: (order.index(m['clip']), m['w0']))
    groups = []
    for m in ms:
        g = groups[-1] if groups else None
        if g and g[-1]['clip'] == m['clip'] and m['w0'] == g[-1]['w1'] + 1 and m['start'] - g[-1]['end'] < 0.9:
            g.append(m)
        else:
            groups.append([m])
    items, sizes = [], {}
    for n, g in enumerate(groups, 1):
        cid, ws = g[0]['clip'], words[g[0]['clip']]
        w0, w1 = g[0]['w0'], g[-1]['w1']
        t_in = max(0.0, ws[w0]['start'] - 0.07)
        if w0 and t_in < ws[w0 - 1]['end']:
            t_in = min(ws[w0]['start'], (ws[w0 - 1]['end'] + ws[w0]['start']) / 2)
        t_out = ws[w1]['end'] + 0.10
        if w1 + 1 < len(ws) and t_out > ws[w1 + 1]['start'] - 0.01:
            t_out = max(ws[w1]['end'], ws[w1 + 1]['start'] - 0.01)
        if cid not in sizes:
            sizes[cid] = T.probe_size(src[cid])
        w, h = sizes[cid]
        items.append({'type': 'shot', 'id': f's{n:02d}', 'clip': cid, 'in': round(t_in, 2), 'out': round(t_out, 2),
                      'cx': w // 2, 'cy': int(h * 0.4), 'zoom': 1.0, 'framed': False,
                      'captions': [[m['start'], m['text']] for m in g]})
    total = sum(i['out'] - i['in'] for i in items)
    base = os.path.basename(project)
    if re.fullmatch(r'v\d+', base):                 # a video of a series: <session>-v2
        base = os.path.basename(os.path.dirname(project)) + '-' + base
    cfg = {'name': base, 'budget': budget, 'title': brief.get('video_title', ''), 'window': {'y': 600, 'h': 640}, 'bed': True,
           'brief': brief, 'note': marks.get('note', ''), 'items': items + [
               {'type': 'card', 'id': 'title', 'seconds': 2.8, 'kicker': 'Coming soon', 'big': 'TITLE', 'hit': 0.55, 'push': 0.1},
               {'type': 'card', 'id': 'end', 'seconds': 2.2, 'kicker': 'Coming soon', 'big': 'TITLE', 'sub': 'Follow for more',
                'hit': 0.3, 'push': 0.04, 'fade_out': 0.6}]}
    kit = brief.get('brand_kit') or {}
    if brief.get('brand') and kit:                   # chosen on the page; the kit lives outside the skill folder
        cfg['brand'] = {'use': brief['brand'], 'name': kit.get('name', ''), 'handle': kit.get('handle', ''),
                        'color': kit.get('color', ''), 'logo': kit.get('logo', ''), 'voice': kit.get('voice', '')}
    if brief.get('speaker_name'):                    # typed on the page; empty means no name tag
        cfg['speaker'] = {'name': brief['speaker_name'], 'title': brief.get('speaker_title', '')}
    out = os.path.join(project, 'trailer.json')
    if os.path.exists(out) and '--force' not in sys.argv:
        out = os.path.join(project, 'trailer.draft.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)

    # framing sheet: start / middle / end of every shot with a labelled 10x grid in SOURCE pixels
    os.makedirs(os.path.join(project, 'work'), exist_ok=True)
    tw = 270
    tiles = []
    for it in items:
        w, h = sizes[it['clip']]
        th = round(tw * h / w)
        for frac in (0.1, 0.5, 0.9):
            t = it['in'] + (it['out'] - it['in']) * frac
            png = os.path.join(project, 'work', '_f.png')
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', src[it['clip']], '-frames:v', '1',
                            '-update', '1', '-vf', f'scale={tw}:{th}', png], check=True)
            im = Image.open(png).convert('RGB')
            d = ImageDraw.Draw(im)
            f = T.font('Inter-600-normal', 11)
            for k in range(1, 10):
                y = th * k // 10
                d.line([(0, y), (tw, y)], fill=(255, 60, 60), width=1)
                d.text((2, y + 1), str(h * k // 10), font=f, fill=(255, 235, 60))
                x = tw * k // 10
                d.line([(x, 0), (x, 6)], fill=(255, 60, 60), width=1)
            d.rectangle([0, 0, tw, 15], fill=(0, 0, 0))
            d.text((3, 2), f"{it['id']} {it['clip']} @{t:.1f}s  (src {w}x{h})", font=f, fill=(255, 255, 255))
            tiles.append(im)
            os.remove(png)
    if tiles:
        cols = 6
        rows = (len(tiles) + cols - 1) // cols
        th = max(t.height for t in tiles)
        sheet = Image.new('RGB', (cols * tw, rows * th), (0, 0, 0))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
        sheet.save(os.path.join(project, 'work', 'framing.jpg'), quality=85)

    print(f'DRAFT {out}')
    print(f'{len(items)} shots from {len(ms)} highlighted phrases: {total:.1f}s of speech (budget {budget}s, '
          f'leave ~8-10s for cards)')
    if total > budget - 8:
        print(f'OVER BUDGET by about {total - (budget - 8):.0f}s: ask which highlighted lines to drop, or offer a series')
    if not items:
        print('NOTHING HIGHLIGHTED: pick the lines yourself from the transcript, guided by the brief')
    print(f"FRAMING {os.path.join(project, 'work', 'framing.jpg')}")


if __name__ == '__main__':
    main()
