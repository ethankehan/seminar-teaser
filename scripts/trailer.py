#!/usr/bin/env python3
"""Seminar trailer builder (movie-trailer grammar): black number cards with bass hits, letterboxed graded shots
with a slow push-in, hard cuts into black, title card, then one stinger line.

  PY trailer.py <project_dir> --check     lint captions + print the timeline
  PY trailer.py <project_dir>             render renders/<name>-vN.mp4 (+ -phone.mp4) and work/qa.jpg

<project_dir>/trailer.json: {"name", "budget", "window": {"y","h"}, "bed": true, "items": [...]}
  shot: {"type":"shot","id","clip","in","out","cx","cy","zoom","push":0.05,"captions":[[src_time,"text"],...]}
  card: {"type":"card","id","seconds","kicker","big","sub","hit":0.35,"fade_out":0}
One ffmpeg at a time; every item is cached by content hash.
"""
import hashlib
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teaser as T  # noqa: E402

CW, CH = T.CW, T.CH
IMPACT = os.path.join(T.SK, 'assets', 'sfx', 'impact-bass-1.mp3')
GRADE = ('eq=contrast=1.14:saturation=0.78:brightness=-0.04,'
         'colorbalance=bs=0.07:gs=0.01:rs=-0.05:bh=-0.04:rh=0.04,vignette=PI/4.6')
AFMT = 'aformat=sample_rates=48000:channel_layouts=stereo'


def h8(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:8]


def caption_png(path, win, text):
    im = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    if text:
        d = ImageDraw.Draw(im)
        f = T.font('Inter-600-normal', 44)
        y = win['y'] + win['h'] + 64
        for ln in T.balanced(d, text, f, T.CAP_W) or T.wrap(d, text, f, T.CAP_W):
            d.text((540, y), ln, font=f, fill=(255, 255, 255, 240), anchor='ma')
            y += 56
    im.save(path)


def fit(d, text, name, size, maxw):
    while size > 20:
        f = T.font(name, size)
        if d.textlength(text, font=f) <= maxw:
            return f
        size -= 4
    return f


def card_png(path, it):
    S = 2                                           # drawn at 2x so the slow zoom stays smooth
    im = Image.new('RGB', (CW * S, CH * S), (0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = CW * S // 2, CH * S // 2 - 40 * S
    big = it.get('big', '')
    fb = fit(d, big, 'DMSerifDisplay-400-normal', 250 * S, 940 * S)
    if it.get('kicker'):
        fk = T.font('Montserrat-600-normal', 34 * S)
        d.text((cx, cy - fb.size * 0.62 - 40 * S), ' '.join(it['kicker'].upper()), font=fk, fill=T.GOLD[:3], anchor='mm')
    d.text((cx, cy), big, font=fb, fill=T.CREAM[:3], anchor='mm')
    if it.get('sub'):
        fs = T.font('Montserrat-600-normal', 30 * S)
        d.line([(cx - 40 * S, cy + fb.size * 0.62 + 30 * S), (cx + 40 * S, cy + fb.size * 0.62 + 30 * S)],
               fill=(214, 196, 150), width=2 * S)
        d.text((cx, cy + fb.size * 0.62 + 84 * S), ' '.join(it['sub'].upper()), font=fs, fill=(235, 232, 226), anchor='mm')
    im.save(path)


def render_shot(P, it, src, win, o):
    a, d = it['in'], it['out'] - it['in']
    N = max(1, round(d * 30))
    wav = o[:-4] + '.wav'
    af = (f"{T.DENOISE},"
          f"afade=t=in:d=0.04,afade=t=out:st={d - 0.06:.3f}:d=0.06,apad=whole_dur={N / 30:.4f}")
    T.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{a:.3f}', '-t', f'{d:.3f}', '-i', src, '-vn', '-af', af,
           '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', wav], cwd=T.ASSETS)
    # caption track for this shot
    sd = os.path.join(P, 'work', 'states'); os.makedirs(sd, exist_ok=True)
    pts = [(0.0, '')] + [(max(0, c[0] - a - 0.05), c[1]) for c in it.get('captions', [])]
    tf = o[:-4] + '.txt'
    with open(tf, 'w', encoding='utf-8') as f:
        last = None
        for (t0, text), (t1, _) in zip(pts, pts[1:] + [(N / 30, '')]):
            if t1 - t0 < 0.005:
                continue
            last = os.path.join(sd, 'cap-' + h8([text, win]) + '.png')
            if not os.path.exists(last):
                caption_png(last, win, text)
            f.write(f"file '{T.fp(last)}'\nduration {t1 - t0:.4f}\n")
        f.write(f"file '{T.fp(last)}'\n")
    z = it.get('zoom', 1.0)
    w, hh = T.probe_size(src)
    cw, ch = round(CW / z / 2) * 2, round(win['h'] / z / 2) * 2
    x = max(0, min(w - cw, round(it['cx'] - cw / 2)))
    y = max(0, min(hh - ch, round(it['cy'] - ch / 2)))
    push = it.get('push', 0.05)
    fc = (f"[0:v]fps=30,setsar=1,crop={cw}:{ch}:{x}:{y},scale={2 * CW}:{2 * win['h']}:flags=lanczos,"
          f"zoompan=z='1+{push}*on/{N}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={CW}x{win['h']}:fps=30,"
          f"{GRADE},pad={CW}:{CH}:0:{win['y']}:black[p];[2:v]fps=30,format=rgba[t];"
          f"[p][t]overlay=0:0:eof_action=pass,fade=t=in:d=0.12,fade=t=out:st={N / 30 - 0.1:.3f}:d=0.1,setsar=1,format=yuv420p[v]")
    T.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{a:.3f}', '-t', f'{d:.3f}', '-i', src, '-i', wav,
           '-f', 'concat', '-safe', '0', '-i', tf, '-filter_complex', fc, '-map', '[v]', '-map', '1:a',
           '-frames:v', str(N), '-t', f'{N / 30:.4f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-r', '30',
           '-c:a', 'aac', '-b:a', '192k', '-threads', T.THREADS, o])
    os.remove(wav)


def render_card(P, it, o):
    d = it['seconds']
    N = round(d * 30)
    png = o[:-4] + '.png'
    card_png(png, it)
    fo = it.get('fade_out', 0)
    fade = f",fade=t=out:st={d - fo:.3f}:d={fo}" if fo else ''
    fc = (f"[0:v]zoompan=z='1+{it.get('push', 0.06)}*on/{N}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
          f"s={CW}x{CH}:fps=30,fade=t=in:d=0.08{fade},setsar=1,format=yuv420p[v]")
    T.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-framerate', '30', '-t', f'{d:.3f}', '-i', png,
           '-f', 'lavfi', '-t', f'{d:.3f}', '-i', 'anullsrc=r=48000:cl=stereo', '-filter_complex', fc, '-map', '[v]',
           '-map', '1:a', '-frames:v', str(N), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-r', '30',
           '-c:a', 'aac', '-b:a', '192k', '-threads', T.THREADS, o])


def main():
    P = os.path.abspath(sys.argv[1])
    cfg = json.load(open(os.path.join(P, 'trailer.json'), encoding='utf-8'))
    src = json.load(open(os.path.join(P, 'sources.json'), encoding='utf-8'))
    win = cfg.get('window', {'y': 600, 'h': 640})
    items, budget = cfg['items'], cfg.get('budget', 60)
    shots = [i for i in items if i['type'] == 'shot']

    problems = T.lint({'segments': shots})
    for it in shots:
        if it.get('framed') is False:
            problems.append(f"{it['id']}: not framed yet. Look at work/framing.jpg, set cx/cy/zoom, then delete \"framed\": false")
    t = 0.0
    for it in items:
        d = it['seconds'] if it['type'] == 'card' else it['out'] - it['in']
        if it['type'] == 'card':
            print(f"{t:6.1f}s  CARD  {it.get('kicker', '')} / {it.get('big', '')}  ({d:.1f}s)")
        else:
            print(f"{t:6.1f}s  shot  {it['id']} {it['clip']} {it['in']:.2f}-{it['out']:.2f} ({d:.1f}s)")
            for ct, text in it.get('captions', []):
                print(f"         {t + ct - it['in']:6.1f}  {text}")
        t += d
    print(f'TOTAL {t:.1f}s (budget {budget}s)')
    if t > budget:
        problems.append(f'total {t:.1f}s is over the {budget}s budget: drop a line')
    for p in problems:
        print('PROBLEM:', p)
    if problems and '--force' not in sys.argv:
        sys.exit('Fix the problems above (or pass --force).')
    if '--check' in sys.argv:
        return

    os.makedirs(os.path.join(P, 'work', 'tr'), exist_ok=True)
    os.makedirs(os.path.join(P, 'renders'), exist_ok=True)
    files = []
    for it in items:
        o = os.path.join(P, 'work', 'tr', f"{it.get('id', it['type'])}-{h8([it, win])}.mp4")
        if not os.path.exists(o):
            render_shot(P, it, src[it['clip']], win, o) if it['type'] == 'shot' else render_card(P, it, o)
        files.append(o)
    lens = [T.vlen(f) for f in files]
    starts = [sum(lens[:i]) for i in range(len(lens))]
    total = sum(lens)

    n = 1
    while os.path.exists(os.path.join(P, 'renders', f"{cfg['name']}-v{n}.mp4")):
        n += 1
    if '--overwrite' in sys.argv and n > 1:
        n -= 1
    out = os.path.join(P, 'renders', f"{cfg['name']}-v{n}.mp4")
    N = len(files)
    inputs = [x for f in files for x in ('-i', f)]
    fc = [f'[{i}:v]setsar=1,fps=30,format=yuv420p[n{i}]' for i in range(N)]      # zoomed crops leave odd SARs
    fc += [''.join(f'[n{i}][{i}:a]' for i in range(N)) + f'concat=n={N}:v=1:a=1[vc][ac]',
          f'[vc]fade=t=out:st={total - 0.5:.3f}:d=0.5[v]', f'[ac]loudnorm=I=-15:TP=-1.5:LRA=9,{AFMT}[voice]']
    mix = ['[voice]']
    hits = [(starts[i], it.get('hit', 0.35)) for i, it in enumerate(items) if it['type'] == 'card' and it.get('hit', 0.35) > 0]
    k = N
    if hits and os.path.exists(IMPACT) and os.path.exists(T.WHOOSH):   # bass hit as each card lands, short whoosh pulling into it
        inputs += ['-i', IMPACT, '-i', T.WHOOSH]
        fc.append(f'[{k}:a]asplit={len(hits)}' + ''.join(f'[i{j}]' for j in range(len(hits))))
        fc.append(f'[{k + 1}:a]asplit={len(hits)}' + ''.join(f'[w{j}]' for j in range(len(hits))))
        for j, (st, vol) in enumerate(hits):
            fc.append(f'[i{j}]adelay={int(st * 1000)}:all=1,volume={vol},{AFMT}[hi{j}]')
            fc.append(f'[w{j}]adelay={max(0, int((st - 0.22) * 1000))}:all=1,volume={cfg.get("whoosh", 0.08)},{AFMT}[wo{j}]')
            mix += [f'[hi{j}]', f'[wo{j}]']
        k += 2
    if cfg.get('bed', True):                  # quiet low drone under everything
        inputs += ['-f', 'lavfi', '-t', f'{total:.3f}', '-i',
                   'sine=f=55:r=48000[a];sine=f=110:r=48000[b];sine=f=164.81:r=48000[c];sine=f=82.4:r=48000[e];'
                   '[a][b][c][e]amix=inputs=4:normalize=0,tremolo=f=0.13:d=0.55,lowpass=f=420[out0]']
        fc.append(f'[{k}:a]volume={cfg.get("bed_volume", 0.022)},afade=t=in:d=2,afade=t=out:st={total - 2:.3f}:d=2,{AFMT}[bed]')
        mix.append('[bed]')
    fc.append(''.join(mix) + f'amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.8:level=false[a]')
    T.run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ';'.join(fc), '-map', '[v]', '-map', '[a]',
           '-t', f'{total:.3f}', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-c:a', 'aac', '-b:a', '192k',
           '-ar', '48000', '-movflags', '+faststart', '-threads', T.THREADS, out])
    phone = out[:-4] + '-phone.mp4'
    T.run(['ffmpeg', '-v', 'error', '-y', '-i', out, '-vf', 'scale=720:-2', '-c:v', 'libx264', '-preset', 'veryfast',
           '-crf', '26', '-c:a', 'aac', '-b:a', '128k', '-threads', T.THREADS, phone])

    shots_png = []
    for i, (st, ln) in enumerate(zip(starts, lens)):
        f = os.path.join(P, 'work', f'qa_{i:02d}.png')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{st + ln * 0.6:.2f}', '-i', out, '-frames:v', '1',
                        '-update', '1', '-vf', 'scale=270:480', f], check=True)
        shots_png.append(f)
    cols = 8
    lay = '|'.join(f'{(i % cols) * 270}_{(i // cols) * 480}' for i in range(len(shots_png)))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *[x for f in shots_png for x in ('-i', f)], '-filter_complex',
                    f'xstack=inputs={len(shots_png)}:layout={lay}:fill=black', os.path.join(P, 'work', 'qa.jpg')], check=True)
    for f in shots_png:
        os.remove(f)
    print(f'DONE {out} ({total:.1f}s)\nPHONE {phone}\nQA {os.path.join(P, "work", "qa.jpg")}')


if __name__ == '__main__':
    main()
