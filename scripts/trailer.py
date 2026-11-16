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
import re
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teaser as T  # noqa: E402
import words as W  # noqa: E402

CW, CH = T.CW, T.CH
IMPACT = os.path.join(T.SK, 'assets', 'sfx', 'impact-bass-1.mp3')
GRADE = ('eq=contrast=1.14:saturation=0.78:brightness=-0.04,'
         'colorbalance=bs=0.07:gs=0.01:rs=-0.05:bh=-0.04:rh=0.04,vignette=PI/4.6')
AFMT = 'aformat=sample_rates=48000:channel_layouts=stereo'


def h8(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:8]


HOT = (255, 212, 96, 255)          # the word being spoken
TAG_SECONDS = 3.5                  # how long the speaker's name stays on the first shot


def caption_png(path, win, text, active=None, tag=None, hook=None):
    im = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if text:
        f = T.font('Inter-600-normal', 44, text)
        y = win['y'] + win['h'] + 64
        idx = 0
        for ln in T.balanced(d, text, f, T.CAP_W) or T.wrap(d, text, f, T.CAP_W):
            x = 540 - d.textlength(ln, font=f) / 2
            toks = W.tokens(ln)
            for j, tok in enumerate(toks):
                d.text((x, y), tok, font=f, fill=HOT if idx == active else (255, 255, 255, 240), anchor='la')
                gap = ' ' if j + 1 < len(toks) and not (W.has_cjk(toks[j + 1][0]) or W.has_cjk(tok[-1])) else ''
                x += d.textlength(tok + gap, font=f)
                idx += 1
            y += 56
    if hook:                                        # the opening claim, big, in the band above the window
        fh = T.font('DMSerifDisplay-400-normal', 68, hook)
        lines = T.wrap(d, hook, fh, 960)[:3]
        y = win['y'] - 128 - 76 * len(lines)
        for ln in lines:
            d.text((540, y), ln, font=fh, fill=T.CREAM, anchor='ma')
            y += 76
    if tag and tag.get('name'):                     # lower third in the black band above the window
        fn = T.font('Montserrat-600-normal', 31, tag['name'])
        ft = T.font('Montserrat-600-normal', 24, tag.get('title', ''))
        sp = lambda t: t if W.has_cjk(t) else ' '.join(t.upper())      # noqa: E731  tracked caps for Latin only
        y = win['y'] - (80 if tag.get('title') else 50)
        d.line([(44, y + 4), (44, win['y'] - 22)], fill=T.GOLD, width=3)
        d.text((62, y), sp(tag['name']), font=fn, fill=T.CREAM, anchor='la')
        if tag.get('title'):
            d.text((62, y + 42), sp(tag['title']), font=ft, fill=T.GOLD, anchor='la')
    im.save(path)


def fit(d, text, name, size, maxw):
    while size > 20:
        f = T.font(name, size, text)
        if d.textlength(text, font=f) <= maxw:
            return f
        size -= 4
    return f


def card_layer(it, big, size=None):
    """The card's text on black at 2x, so scaling it per frame stays sharp."""
    S = 2
    im = Image.new('RGB', (CW * S, CH * S), (0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = CW * S // 2, CH * S // 2 - 40 * S
    sp = lambda t: t if W.has_cjk(t) else ' '.join(t.upper())          # noqa: E731  tracked caps for Latin only
    fb = (T.font('DMSerifDisplay-400-normal', size, big) if size
          else fit(d, big, 'DMSerifDisplay-400-normal', (190 if W.has_cjk(big) else 250) * S, 940 * S))
    bh = fb.size * (0.75 if W.has_cjk(big) else 0.62)
    if it.get('kicker'):
        fk = T.font('Montserrat-600-normal', 34 * S, it['kicker'])
        d.text((cx, cy - bh - 40 * S), sp(it['kicker']), font=fk, fill=T.GOLD[:3], anchor='mm')
    d.text((cx, cy), big, font=fb, fill=T.CREAM[:3], anchor='mm')
    y = cy + bh
    if it.get('sub'):
        fs = T.font('Montserrat-600-normal', 30 * S, it['sub'])
        d.line([(cx - 40 * S, y + 30 * S), (cx + 40 * S, y + 30 * S)], fill=T.GOLD[:3], width=2 * S)
        d.text((cx, y + 84 * S), sp(it['sub']), font=fs, fill=(235, 232, 226), anchor='mm')
        y += 110 * S
    if it.get('_handle'):                               # brand: account name under the call to action
        fh = T.font('Inter-600-normal', 34 * S, it['_handle'])
        d.text((cx, y + 70 * S), it['_handle'], font=fh, fill=T.GOLD[:3], anchor='mm')
    if it.get('_logo') and os.path.exists(it['_logo']):  # brand: logo above the text
        logo = Image.open(it['_logo']).convert('RGBA')
        lw = 330 * S
        logo = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
        im.paste(logo, (cx - lw // 2, round(cy - bh - 120 * S - logo.height)), logo)
    return im, fb.size


def count_texts(big, frames):
    """"$110,000" -> the texts to show while the number rolls up ("$0" ... "$110,000"); [] when there is no number
    worth rolling."""
    m = re.match(r'^(\D*?)(\d[\d,]*)(.*)$', big)
    if not m or int(m.group(2).replace(',', '')) < 10:
        return []
    target, comma = int(m.group(2).replace(',', '')), ',' in m.group(2)
    out = []
    for i in range(frames):
        v = round(target * (1 - (1 - (i + 1) / frames) ** 3))          # ease-out
        out.append(m.group(1) + (f'{v:,}' if comma else str(v)) + m.group(3))
    return out


def render_card(P, it, o, srcs=None):
    """Every frame is composed with Pillow: the text slams in (scale overshoot + a white flash), a number rolls up to
    its value, then a slow push. ffmpeg only encodes the frames."""
    d = it['seconds']
    N = round(d * 30)
    big = it.get('big', '')
    final, size = card_layer(it, big)
    roll = count_texts(big, 13) if it.get('count', True) else []
    layers = {big: final}
    slam, push, fo = 6, it.get('push', 0.06), it.get('fade_out', 0)
    fdir = o[:-4] + '_f'
    os.makedirs(fdir, exist_ok=True)
    white, black = Image.new('RGB', (CW, CH), (255, 255, 255)), Image.new('RGB', (CW, CH), (0, 0, 0))
    for i in range(N):
        text = roll[i] if i < len(roll) else big
        if text not in layers:
            layers[text] = card_layer(it, text, size)[0]
        sc = 1 + 0.2 * (1 - i / slam) ** 2 if i < slam else 1 + push * (i - slam) / max(1, N - slam)
        w, h = round(CW * sc), round(CH * sc)
        fr = layers[text].resize((w, h), Image.LANCZOS).crop(((w - CW) // 2, (h - CH) // 2, (w - CW) // 2 + CW, (h - CH) // 2 + CH))
        if i < 3 and it.get('flash', True):
            fr = Image.blend(fr, white, (0.5, 0.26, 0.1)[i])
        if fo and i > N - fo * 30:
            fr = Image.blend(fr, black, min(1, (i - (N - fo * 30)) / (fo * 30)))
        fr.save(os.path.join(fdir, f'{i:04d}.jpg'), quality=93)
    voice = it.get('_voice')                        # J-cut: the next line starts under this card
    if voice:
        wav = o[:-4] + '.wav'
        T.run(['ffmpeg', '-v', 'error', '-y', '-ss', f"{voice['in']:.4f}", '-t', f"{voice['dur']:.4f}", '-i', srcs[voice['clip']],
               '-vn', '-af', f"{T.DENOISE},afade=t=in:d=0.04,adelay={int((N / 30 - voice['dur']) * 1000)}:all=1,"
               f"apad=whole_dur={N / 30:.4f}", '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', wav], cwd=T.ASSETS)
        audio = ['-i', wav]
    else:
        audio = ['-f', 'lavfi', '-t', f'{N / 30:.4f}', '-i', 'anullsrc=r=48000:cl=stereo']
    T.run(['ffmpeg', '-v', 'error', '-y', '-framerate', '30', '-i', os.path.join(fdir, '%04d.jpg'),
           *audio, '-map', '0:v', '-map', '1:a', '-t', f'{N / 30:.4f}',
           '-frames:v', str(N), '-vf', 'setsar=1,format=yuv420p', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17',
           '-r', '30', '-c:a', 'aac', '-b:a', '192k', '-threads', T.THREADS, o])
    for f in os.listdir(fdir):
        os.remove(os.path.join(fdir, f))
    os.rmdir(fdir)
    if voice:
        os.remove(o[:-4] + '.wav')


def caption_states(it, N, words, opts):
    """[(t0, text, active word index or None, show name tag?)] on the shot's own clock."""
    a, caps = it['in'], it.get('captions', [])
    out = [(0.0, '', None)]
    for (t, text), te in zip(caps, [c[0] for c in caps[1:]] + [it['out']]):
        toks = W.tokens(text)
        if not opts.get('karaoke', True) or not toks:
            out.append((t - a - 0.05, text, None))
            continue
        ws = [w for w in words if t - 0.04 <= w['start'] < te - 0.04]
        if len(ws) == len(toks):                       # caption words line up with the transcript: use real times
            times = [w['start'] for w in ws]
        else:                                          # wording was corrected: spread evenly over the phrase
            last = min(te, ws[-1]['end']) if ws else te
            times = [t + max(0.2, last - t) * j / len(toks) for j in range(len(toks))]
        times[0] = t - 0.05
        out += [(tj - a, text, j) for j, tj in enumerate(times)]
    out = sorted((max(0.0, min(N / 30, t0)), text, act) for t0, text, act in out)
    tag = opts.get('tag')
    if tag:
        cur = [s for s in out if s[0] <= TAG_SECONDS]
        if cur and TAG_SECONDS < N / 30:
            out = sorted(out + [(TAG_SECONDS, cur[-1][1], cur[-1][2])])
    return [(t0, text, act, bool(tag) and t0 < TAG_SECONDS - 1e-6) for t0, text, act in out]


def render_shot(P, it, src, win, o, opts):
    a, d = it['in'], it['out'] - it['in']
    N = max(1, round(d * 30))
    wav = o[:-4] + '.wav'
    fades = ([] if opts.get('no_in') else ['afade=t=in:d=0.04']) + ([] if opts.get('no_out') else [f'afade=t=out:st={d - 0.06:.3f}:d=0.06'])
    af = ','.join([T.DENOISE, *fades, *(['volume=0'] if it.get('mute') else []), f'apad=whole_dur={N / 30:.4f}'])
    pic = it.get('picture')                         # cutaway: these frames, that voice
    vsrc, va = (opts['srcs'][pic['clip']], pic['in']) if pic else (src, a)
    T.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{a:.4f}', '-t', f'{d:.4f}', '-i', src, '-vn', '-af', af,
           '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', wav], cwd=T.ASSETS)
    # caption track for this shot
    sd = os.path.join(P, 'work', 'states'); os.makedirs(sd, exist_ok=True)
    st = caption_states(it, N, opts.get('words', []), opts)
    tf = o[:-4] + '.txt'
    with open(tf, 'w', encoding='utf-8') as f:
        last = None
        for (t0, text, act, tagged), nxt in zip(st, st[1:] + [(N / 30,)]):
            if nxt[0] - t0 < 0.005:
                continue
            tag = opts.get('tag') if tagged else None
            last = os.path.join(sd, 'cap-' + h8([text, act, tag, opts.get('hook'), win]) + '.png')
            if not os.path.exists(last):
                caption_png(last, win, text, act, tag, opts.get('hook'))
            f.write(f"file '{T.fp(last)}'\nduration {nxt[0] - t0:.4f}\n")
        f.write(f"file '{T.fp(last)}'\n")
    z = it.get('zoom', 1.0)
    w, hh = T.probe_size(vsrc)
    full = min(w, hh * CW / win['h'])             # zoom 1 = the widest window-shaped crop this footage allows (1080p or 4K)
    cw, ch = round(full / z / 2) * 2, round(full * win['h'] / CW / z / 2) * 2
    x = max(0, min(w - cw, round(it['cx'] - cw / 2)))
    y = max(0, min(hh - ch, round(it['cy'] - ch / 2)))
    push = it.get('push', 0.05)
    if opts.get('track'):                           # follow the speaker when they would walk out of this framing
        import track
        moving = track.path(vsrc, va, d, w, hh, cw, ch, x, y)
        if moving:
            x, y = f"'{moving[0]}'", f"'{moving[1]}'"
    vf = ([] if opts.get('no_in') else ['fade=t=in:d=0.12']) + ([] if opts.get('no_out') else [f'fade=t=out:st={N / 30 - 0.1:.3f}:d=0.1'])
    fc = (f"[0:v]fps=30,setsar=1,crop={cw}:{ch}:{x}:{y},scale={2 * CW}:{2 * win['h']}:flags=lanczos,"
          f"zoompan=z='1+{push}*on/{N}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={CW}x{win['h']}:fps=30,"
          f"{GRADE},pad={CW}:{CH}:0:{win['y']}:black[p];[2:v]fps=30,format=rgba[t];"
          f"[p][t]overlay=0:0:eof_action=pass,{','.join(vf + ['setsar=1', 'format=yuv420p'])}[v]")
    T.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{va:.4f}', '-t', f'{d:.4f}', '-i', vsrc, '-i', wav,
           '-f', 'concat', '-safe', '0', '-i', tf, '-filter_complex', fc, '-map', '[v]', '-map', '1:a',
           '-frames:v', str(N), '-t', f'{N / 30:.4f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-r', '30',
           '-c:a', 'aac', '-b:a', '192k', '-threads', T.THREADS, o])
    os.remove(wav)


def main():
    P = os.path.abspath(sys.argv[1])
    cfg = json.load(open(os.path.join(P, 'trailer.json'), encoding='utf-8'))
    src = json.load(open(os.path.join(P, 'sources.json'), encoding='utf-8'))
    win = cfg.get('window', {'y': 600, 'h': 640})
    items, budget = cfg['items'], cfg.get('budget', 60)
    shots = [i for i in items if i['type'] == 'shot']

    for i, it in enumerate(items[1:], 1):          # "cont": true = same take continues, only the framing changes
        prev = items[i - 1]
        if it['type'] == 'shot' and it.get('cont'):
            if prev['type'] != 'shot' or prev['clip'] != it['clip']:
                sys.exit(f"{it['id']}: \"cont\" needs the shot before it to be from the same clip")
            prev['out'] = round(prev['in'] + round((prev['out'] - prev['in']) * 30) / 30, 4)
            it['in'] = prev['out']
    for i, it in enumerate(items[1:], 1):          # "jcut": seconds of this line's voice that play over the card before it
        prev = items[i - 1]
        if it['type'] == 'shot' and it.get('jcut') and prev['type'] == 'card':
            x = round(min(it['jcut'], prev['seconds'] - 0.4, it['out'] - it['in'] - 0.6) * 30) / 30
            if x > 0.1:
                prev['_voice'] = {'clip': it['clip'], 'in': it['in'], 'dur': x}
                it['_lead'] = x
    problems = T.lint({'segments': shots})
    for it in shots:
        if it.get('_lead'):                         # after the lint, which checks caption times against the full line
            it['in'] = round(it['in'] + it['_lead'], 4)
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
    global HOT
    brand = cfg.get('brand') or {}
    use = brand.get('use', [])
    if 'color' in use and re.fullmatch(r'#[0-9a-fA-F]{6}', brand.get('color', '')):
        rgb = tuple(int(brand['color'][i:i + 2], 16) for i in (1, 3, 5))
        T.GOLD = HOT = rgb + (255,)                  # one accent: kickers, spoken word, progress line, name tag
    cards = [it for it in items if it['type'] == 'card']
    if cards and 'logo' in use and brand.get('logo'):
        cards[-1]['_logo'] = brand['logo']
    if cards and 'handle' in use and brand.get('handle'):
        cards[-1]['_handle'] = brand['handle']
    words = W.load(P)[1]
    first_shot = next((it for it in items if it['type'] == 'shot'), None)
    files = []
    for i, it in enumerate(items):
        if it['type'] == 'card':
            o = os.path.join(P, 'work', 'tr', f"{it.get('id', 'card')}-{h8([it, 'c3', list(T.GOLD)])}.mp4")
            if not os.path.exists(o):
                render_card(P, it, o, src)
        else:
            nxt = items[i + 1] if i + 1 < len(items) else {}
            opts = {'karaoke': cfg.get('karaoke', True), 'no_in': bool(it.get('cont') or it.get('_lead')),
                    'hook': cfg.get('hook') if it is first_shot else None, 'color': list(T.GOLD),
                    'track': bool(it.get('track', cfg.get('track', True))),
                    'no_out': nxt.get('type') == 'shot' and bool(nxt.get('cont')),
                    'tag': cfg.get('speaker') if it is first_shot and (cfg.get('speaker') or {}).get('name') else None}
            o = os.path.join(P, 'work', 'tr', f"{it.get('id', 'shot')}-{h8([it, win, opts, 's3'])}.mp4")
            if not os.path.exists(o):
                render_shot(P, it, src[it['clip']], win, o, {**opts, 'words': words.get(it['clip'], []), 'srcs': src})
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
    music = cfg.get('music')
    if music is None:                         # chosen on the web page
        mj = os.path.join(P, 'music.json')
        if os.path.exists(mj):
            with open(mj, encoding='utf-8') as f:
                music = json.load(f)
    has_music = bool(music and music.get('file') and os.path.exists(music['file']))
    if has_music:                             # the track swells on the cards and ducks under the voice
        inputs += ['-stream_loop', '-1', '-i', music['file']]
        fc[fc.index(f'[ac]loudnorm=I=-15:TP=-1.5:LRA=9,{AFMT}[voice]')] = (
            f'[ac]loudnorm=I=-15:TP=-1.5:LRA=9,{AFMT},asplit=2[voice][key]')
        drops = ''.join(f",volume=0:enable='between(t,{starts[i] - it['drop']:.3f},{starts[i]:.3f})'"
                        for i, it in enumerate(items) if it['type'] == 'card' and it.get('drop'))   # silence, then the hit
        fc.append(f'[{k}:a]atrim=0:{total:.3f},loudnorm=I=-21:TP=-2,{AFMT},volume={music.get("volume", 1.0)},'
                  f'afade=t=in:d=0.6,afade=t=out:st={max(0, total - 1.8):.3f}:d=1.8{drops}[mraw]')
        fc.append('[mraw][key]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=450[mus]')
        mix.append('[mus]')
        k += 1
    if not has_music and cfg.get('bed', True) and not (music and music.get('type') == 'none'):   # quiet low drone
        inputs += ['-f', 'lavfi', '-t', f'{total:.3f}', '-i',
                   'sine=f=55:r=48000[a];sine=f=110:r=48000[b];sine=f=164.81:r=48000[c];sine=f=82.4:r=48000[e];'
                   '[a][b][c][e]amix=inputs=4:normalize=0,tremolo=f=0.13:d=0.55,lowpass=f=420[out0]']
        fc.append(f'[{k}:a]volume={cfg.get("bed_volume", 0.022)},afade=t=in:d=2,afade=t=out:st={total - 2:.3f}:d=2,{AFMT}[bed]')
        mix.append('[bed]')
        k += 1
    if cfg.get('progress', True):             # thin line under the window that fills as the video plays (shots only)
        inputs += ['-f', 'lavfi', '-t', f'{total:.3f}', '-i', 'color=c=0x%02X%02X%02X:s=%dx3:r=30' % (*T.GOLD[:3], CW)]
        en = '+'.join(f'between(t,{starts[i]:.3f},{starts[i] + lens[i]:.3f})' for i, it in enumerate(items) if it['type'] == 'shot')
        vi = fc.index(f'[vc]fade=t=out:st={total - 0.5:.3f}:d=0.5[v]')
        fc[vi] = (f"[vc][{k}:v]overlay=x='-W+W*t/{total:.3f}':y={win['y'] + win['h']}:enable='{en}':shortest=1,"
                  f"fade=t=out:st={total - 0.5:.3f}:d=0.5[v]")
        k += 1
    fc.append(''.join(mix) + f'amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.75:attack=1:release=60:level=false[a]')
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
    stack = f'xstack=inputs={len(shots_png)}:layout={lay}:fill=black' if len(shots_png) > 1 else 'null'   # xstack needs 2+
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *[x for f in shots_png for x in ('-i', f)], '-filter_complex',
                    stack, '-frames:v', '1', '-update', '1', os.path.join(P, 'work', 'qa.jpg')], check=True)
    for f in shots_png:
        os.remove(f)
    print(f'DONE {out} ({total:.1f}s)\nPHONE {phone}\nQA {os.path.join(P, "work", "qa.jpg")}')


if __name__ == '__main__':
    main()
