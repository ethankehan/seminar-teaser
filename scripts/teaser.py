#!/usr/bin/env python3
"""Seminar teaser builder: a few punchy lines from talk footage -> one <=60s vertical teaser.

  PY teaser.py <project_dir> --check     lint captions + print the timeline, render nothing
  PY teaser.py <project_dir>             render renders/<name>-vN.mp4 (+ -phone.mp4) and work/qa.jpg

<project_dir> holds sources.json ({"c1": "/abs/clip.mp4"}, written by video-edit's ingest.py) and teaser.json
(same idea as assets/trailer.example.json, with "segments" and a "headline" per segment). PY is this skill's own venv python (scripts/setup.py makes it).

Light on purpose: plain ffmpeg + Pillow, ONE process at a time, segments cached by content hash so a caption or
headline change only re-runs the final pass (~1 min).
"""
import hashlib
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(SK, 'assets')
FONTS = os.path.join(ASSETS, 'fonts')
WHOOSH = os.path.join(ASSETS, 'sfx', 'whoosh-short.mp3')
# The RNNoise model is named by a bare file name and ffmpeg is started inside assets/ for the audio pass: a full
# Windows path ("C:\...") inside a filter string would need its colon and backslashes escaped.
DENOISE = ('highpass=f=90,' + ('arnndn=m=sh.rnnn:mix=0.85,' if os.path.exists(os.path.join(ASSETS, 'sh.rnnn')) else '')
           + 'afftdn=nf=-25,equalizer=f=3000:t=q:w=1:g=2')
TXT = dict(capture_output=True, encoding='utf-8', errors='replace')
THREADS = '4'
CW, CH = 1080, 1920
CAP_Y, CAP_SIZE, CAP_W, CAP_LH = 1336, 46, 900, 58     # captions sit under the window, above the y=1470 safe line
GOLD, CREAM = (232, 214, 166, 255), (247, 244, 238, 255)
WEAK_END = {'the', 'a', 'an', 'to', 'of', 'and', 'or', 'but', 'your', 'my', 'our', 'his', 'her', 'their', 'in', 'on',
            'for', 'is', 'are', 'was', 'with', 'at', 'this', 'that', 'so', 'because', 'if', 'you', 'i', 'we', 'will'}


def run(cmd, cwd=None):
    print('>>', os.path.basename(cmd[-1]), flush=True)
    subprocess.run(cmd, check=True, cwd=cwd)


def fp(path):
    """A path as ffmpeg's concat list wants it: forward slashes, apostrophes escaped."""
    return path.replace('\\', '/').replace("'", "'\\''")


def dur(f):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f],
                                **TXT).stdout)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name + '.ttf'), size)


def balanced(draw, text, f, maxw):
    """1 line if it fits, else the 2-line split with the most even widths. None if it needs 3+ lines."""
    if draw.textlength(text, font=f) <= maxw:
        return [text]
    words, best = text.split(), None
    for i in range(1, len(words)):
        a, b = ' '.join(words[:i]), ' '.join(words[i:])
        wa, wb = draw.textlength(a, font=f), draw.textlength(b, font=f)
        if wa <= maxw and wb <= maxw and (best is None or abs(wa - wb) < best[0]):
            best = (abs(wa - wb), [a, b])
    return best[1] if best else None


def lint(cfg):
    """The caption rules that came from real feedback. Returns a list of problems."""
    d = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    f, bad = font('Inter-600-normal', CAP_SIZE), []
    for s in cfg['segments']:
        caps = s.get('captions', [])
        for i, (t, text) in enumerate(caps):
            words = text.split()
            where = f"{s['id']} caption {i + 1} \"{text}\""
            if not (s['in'] - 0.01 <= t < s['out']):
                bad.append(f'{where}: time {t} is outside the segment {s["in"]}-{s["out"]}')
            if i and t <= caps[i - 1][0]:
                bad.append(f'{where}: starts before the previous caption')
            if balanced(d, text, f, CAP_W) is None:
                bad.append(f'{where}: too long for two lines, split it at a phrase boundary')
            if i and len(words) > 1 and re.search(r'[.?!,;:]$', words[0]) and not re.search(r'[.?!,;:]$', caps[i - 1][1]):
                bad.append(f'{where}: starts with the tail of the previous phrase ("{words[0]}"), move it back')
            if len(words) == 1 and i and not re.search(r'[.?!]$', caps[i - 1][1]):
                bad.append(f'{where}: a single word left over from the previous caption, merge it')
            if words and re.sub(r'\W', '', words[-1]).lower() in WEAK_END and not re.search(r'[.?!,]$', words[-1]):
                bad.append(f'{where}: ends on "{words[-1]}", the phrase is cut in the middle')
            nxt = caps[i + 1][0] if i + 1 < len(caps) else s['out']
            if nxt - t < 0.5:
                bad.append(f'{where}: on screen for only {nxt - t:.2f}s')
    return bad


def seg_file(P, s, win, h):
    key = json.dumps([s[k] for k in ('clip', 'in', 'out')] + [s.get(k) for k in ('cx', 'cy', 'zoom', 'full')] + [win, h],
                     sort_keys=True)
    return os.path.join(P, 'work', 'seg', f"{s['id']}-{hashlib.md5(key.encode()).hexdigest()[:8]}.mp4")


def render_segment(P, s, src, win, o, h):
    """Video runs from in-h to out+h (handles for the dissolve); the voice only from in to out, silence in the handles."""
    a, d = s['in'], s['out'] - s['in']
    head = min(h, a)                      # clip starts too early for a full handle: hold the first frame instead
    total = d + 2 * h
    wav = o[:-4] + '.wav'
    # audio on its own (in one filter graph with the video the denoiser emitted NaN samples and aac refused them)
    af = (f"{DENOISE},"
          f"afade=t=in:d=0.04,afade=t=out:st={d - 0.06:.3f}:d=0.06,adelay={int(h * 1000)}:all=1,apad=whole_dur={total:.3f}")
    run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{a:.3f}', '-t', f'{d:.3f}', '-i', src, '-vn', '-af', af,
         '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', wav], cwd=ASSETS)
    pad = f'tpad=start_mode=clone:start_duration={h - head:.3f},' if h - head > 0.001 else ''
    if s.get('full'):                     # a real wide/intro shot: whole frame, no window
        fc = (f'[0:v]fps=30,{pad}setsar=1,scale={CW}:{CH}:force_original_aspect_ratio=increase,crop={CW}:{CH},'
              f'format=yuv420p[v]')
    else:                                 # crop the stage (speaker + slides) into the window, blurred dark room behind
        z = s.get('zoom', 1.0)
        w, hh = probe_size(src)
        cw, ch = round(CW / z / 2) * 2, round(win['h'] / z / 2) * 2
        x = max(0, min(w - cw, round(s['cx'] - cw / 2)))
        y = max(0, min(hh - ch, round(s['cy'] - ch / 2)))
        fc = (f'[0:v]fps=30,{pad}setsar=1,split[s1][s2];'
              f'[s1]scale=135:240,boxblur=6:2,scale={CW}:{CH},eq=brightness=-0.36:saturation=0.45[bg];'
              f"[s2]crop={cw}:{ch}:{x}:{y},scale={CW}:{win['h']}:flags=lanczos,eq=contrast=1.05:saturation=0.92[win];"
              f"[bg][win]overlay=0:{win['y']},format=yuv420p[v]")
    run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{a - head:.3f}', '-t', f'{d + head + h:.3f}', '-i', src, '-i', wav,
         '-filter_complex', fc, '-map', '[v]', '-map', '1:a', '-t', f'{total:.3f}', '-c:v', 'libx264', '-preset', 'veryfast',
         '-crf', '18', '-r', '30', '-c:a', 'aac', '-b:a', '192k', '-threads', THREADS, o])
    os.remove(wav)


def vlen(f):
    n = subprocess.run(['ffprobe', '-v', 'error', '-count_packets', '-select_streams', 'v:0', '-show_entries',
                        'stream=nb_read_packets', '-of', 'csv=p=0', f], **TXT).stdout.strip()
    return int(n.split(',')[0]) / 30


def probe_size(f):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height:stream_side_data=rotation', '-of', 'json', f],
                         **TXT).stdout
    st = json.loads(out)['streams'][0]
    w, h = st['width'], st['height']
    rot = abs(int((st.get('side_data_list') or [{}])[0].get('rotation', 0)))
    return (h, w) if rot in (90, 270) else (w, h)


def end_card(P, seconds):
    o = os.path.join(P, 'work', 'seg', f'endcard-{seconds}.mp4')
    if not os.path.exists(o):
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=0x0d0f12:s={CW}x{CH}:r=30:d={seconds}',
             '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(seconds), '-c:v', 'libx264', '-preset',
             'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', o])
    return o


def draw_state(path, win, kicker, headline, cap, card=None):
    im = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if card:                              # end card: centred block
        fk, ft, fs = font('Montserrat-600-normal', 32), font('DMSerifDisplay-400-normal', 104), font('Inter-600-normal', 44)
        lines = wrap(d, card['headline'], ft, 940)
        y = 900 - 56 * len(lines)
        d.line([(500, y - 120), (580, y - 120)], fill=(214, 196, 150, 220), width=2)
        d.text((540, y - 66), ' '.join(card.get('kicker', '').upper()), font=fk, fill=GOLD, anchor='mm')
        for ln in lines:
            d.text((540, y), ln, font=ft, fill=CREAM, anchor='ma'); y += 112
        for ln in wrap(d, card.get('sub', ''), fs, 900):
            d.text((540, y + 44), ln, font=fs, fill=(255, 255, 255, 215), anchor='ma'); y += 58
    else:
        if headline:
            fk, ft = font('Montserrat-600-normal', 30), font('DMSerifDisplay-400-normal', 92)
            lines = wrap(d, headline, ft, 960)
            y = win['y'] - 42 - 98 * len(lines)          # bottom-anchored: the last line ends above the window
            if kicker:
                d.line([(500, y - 110), (580, y - 110)], fill=(214, 196, 150, 200), width=2)
                d.text((540, y - 60), ' '.join(kicker.upper()), font=fk, fill=GOLD, anchor='mm')
            for ln in lines:
                d.text((540, y), ln, font=ft, fill=CREAM, anchor='ma', stroke_width=2, stroke_fill=(0, 0, 0, 120)); y += 98
        if cap:
            fc = font('Inter-600-normal', CAP_SIZE)
            y = CAP_Y
            for ln in balanced(d, cap, fc, CAP_W) or wrap(d, cap, fc, CAP_W):
                d.text((540, y), ln, font=fc, fill=(255, 255, 255, 255), anchor='ma', stroke_width=3,
                       stroke_fill=(0, 0, 0, 170))
                y += CAP_LH
    im.save(path)


def wrap(draw, text, f, maxw):
    lines, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=f) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    return [l for l in lines + [cur] if l]


def main():
    P = os.path.abspath(sys.argv[1])
    check = '--check' in sys.argv
    cfg = json.load(open(os.path.join(P, 'teaser.json'), encoding='utf-8'))
    src = json.load(open(os.path.join(P, 'sources.json'), encoding='utf-8'))
    win = cfg.get('window', {'y': 620, 'h': 680})
    segs, card = cfg['segments'], cfg.get('end_card')
    budget = cfg.get('budget', 60)

    problems = lint(cfg)
    gap = 2 * cfg.get('transition', {}).get('handle', 0.2) - cfg.get('transition', {}).get('duration', 0.3)
    total = sum(s['out'] - s['in'] + gap for s in segs) + (card or {}).get('seconds', 0) + 0.3
    t = 0.0
    for s in segs:
        print(f"{t:6.1f}s  {s['id']:10s} {s['clip']} {s['in']:.2f}-{s['out']:.2f} ({s['out'] - s['in']:.1f}s)  "
              f"[{s.get('headline', '')}]")
        for ct, text in s.get('captions', []):
            print(f"         {t + ct - s['in']:6.1f}  {text}")
        t += s['out'] - s['in']
    print(f'TOTAL {total:.1f}s (budget {budget}s)')
    if total > budget:
        problems.append(f'total {total:.1f}s is over the {budget}s budget: drop a line, do not speed it up')
    for p in problems:
        print('PROBLEM:', p)
    if problems and '--force' not in sys.argv:
        sys.exit('Fix the problems above (or pass --force).')
    if check:
        return

    tr = cfg.get('transition', {})
    D, H = tr.get('duration', 0.3), tr.get('handle', 0.2)      # dissolve length; 2*H - D = breath between lines
    os.makedirs(os.path.join(P, 'work', 'seg'), exist_ok=True)
    os.makedirs(os.path.join(P, 'renders'), exist_ok=True)
    files = []
    for s in segs:
        o = seg_file(P, s, win, H)
        if not os.path.exists(o):
            render_segment(P, s, src[s['clip']], win, o, H)
        files.append(o)
    if card:
        files.append(end_card(P, card['seconds'] + D))
    lens = [vlen(f) for f in files]
    starts = [sum(lens[:i]) - i * D for i in range(len(lens))]
    total = starts[-1] + lens[-1]

    # per-segment overlay track (headline + captions), composited BEFORE the dissolve so text fades with the picture
    sd = os.path.join(P, 'work', 'states'); os.makedirs(sd, exist_ok=True)
    cache, tracks = {}, []

    def state(kick, head, text, c):
        key = json.dumps([kick, head, text, c], sort_keys=True)
        if key not in cache:
            cache[key] = os.path.join(sd, hashlib.md5(key.encode()).hexdigest()[:10] + '.png')
            draw_state(cache[key], win, kick, head, text, c)
        return cache[key]

    for i, ln in enumerate(lens):
        if i < len(segs):
            s = segs[i]
            kick, head = s.get('kicker', cfg.get('kicker', '')), s.get('headline', '')
            pts = [(0.0, '')] + [(max(0, H + c[0] - s['in'] - 0.05), c[1]) for c in s.get('captions', [])]
            pts.append((min(ln, H + s['out'] - s['in'] + 0.05), ''))
            ev = [(a, b, state(kick, head, text, None)) for (a, text), (b, _) in zip(pts, pts[1:] + [(ln, '')]) if b - a > 0.005]
        else:
            ev = [(0.0, ln, state('', '', '', card))]
        tf = os.path.join(P, 'work', f'states_{i:02d}.txt')
        with open(tf, 'w', encoding='utf-8') as f:
            f.writelines(f"file '{fp(png)}'\nduration {b - a:.4f}\n" for a, b, png in ev)
            f.write(f"file '{fp(ev[-1][2])}'\n")
        tracks.append(tf)

    n = 1
    while os.path.exists(os.path.join(P, 'renders', f"{cfg['name']}-v{n}.mp4")):
        n += 1
    if '--overwrite' in sys.argv and n > 1:
        n -= 1
    out = os.path.join(P, 'renders', f"{cfg['name']}-v{n}.mp4")
    N = len(files)
    inputs = []
    for f in files:
        inputs += ['-i', f]
    for tf in tracks:
        inputs += ['-f', 'concat', '-safe', '0', '-i', tf]
    fc = []
    for i in range(N):
        fc.append(f'[{N + i}:v]fps=30,format=rgba[t{i}];[{i}:v][t{i}]overlay=0:0:eof_action=pass,'
                  f'trim=duration={lens[i]:.4f},settb=AVTB,fps=30,format=yuv420p[v{i}]')
        fc.append(f'[{i}:a]adelay={int(starts[i] * 1000)}:all=1[a{i}]')
    prev = 'v0'
    for i in range(1, N):
        fc.append(f'[{prev}][v{i}]xfade=transition={tr.get("type", "fade")}:duration={D}:offset={starts[i]:.4f}[x{i}]')
        prev = f'x{i}'
    fc.append(f'[{prev}]fade=t=in:d=0.25,fade=t=out:st={total - 0.4:.3f}:d=0.4[v]')
    fc.append(''.join(f'[a{i}]' for i in range(N)) + f'amix=inputs={N}:normalize=0:duration=longest,'
              f'loudnorm=I=-15:TP=-1.5:LRA=9[voice]')
    cuts = [st + D / 2 for st in starts[1:]] if cfg.get('sfx', True) and os.path.exists(WHOOSH) else []
    if cuts:                              # one quiet whoosh under every dissolve, well below the voice
        inputs += ['-i', WHOOSH]
        fc.append(f'[{2 * N}:a]asplit={len(cuts)}' + ''.join(f'[w{i}]' for i in range(len(cuts))))
        for i, c in enumerate(cuts):
            fc.append(f'[w{i}]adelay={max(0, int((c - 0.2) * 1000))}:all=1,volume={cfg.get("sfx_volume", 0.07)}[s{i}]')
        fc.append('[voice]' + ''.join(f'[s{i}]' for i in range(len(cuts))) +
                  f'amix=inputs={len(cuts) + 1}:normalize=0:duration=first[a]')
    else:
        fc.append('[voice]anull[a]')
    run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ';'.join(fc), '-map', '[v]', '-map', '[a]',
         '-t', f'{total:.3f}', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-c:a', 'aac', '-b:a', '192k',
         '-ar', '48000', '-movflags', '+faststart', '-threads', THREADS, out])
    phone = out[:-4] + '-phone.mp4'
    run(['ffmpeg', '-v', 'error', '-y', '-i', out, '-vf', 'scale=720:-2', '-c:v', 'libx264', '-preset', 'veryfast',
         '-crf', '26', '-c:a', 'aac', '-b:a', '128k', '-threads', THREADS, phone])

    # QA sheet: one frame from the middle of every segment (+ end card)
    shots = []
    for i, (st, ln) in enumerate(zip(starts, lens)):
        f = os.path.join(P, 'work', f'qa_{i:02d}.png')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{st + ln * 0.5:.2f}', '-i', out, '-frames:v', '1',
                        '-update', '1', '-vf', 'scale=270:480', f], check=True)
        shots.append(f)
    args = [x for f in shots for x in ('-i', f)]
    cols = 6
    lay = '|'.join(f'{(i % cols) * 270}_{(i // cols) * 480}' for i in range(len(shots)))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args, '-filter_complex',
                    f'xstack=inputs={len(shots)}:layout={lay}:fill=black' if len(shots) > 1 else 'null',
                    os.path.join(P, 'work', 'qa.jpg')], check=True)
    for f in shots:
        os.remove(f)
    print(f'DONE {out} ({total:.1f}s)\nPHONE {phone}\nQA {os.path.join(P, "work", "qa.jpg")}')


if __name__ == '__main__':
    main()
