"""Shared: load a project's word timestamps and split them into phrase-sized chunks.

A chunk is the unit a person highlights on the marking page and the unit a caption is built from, so it must end
where the speaker's phrase ends: at punctuation, at a pause, or (failing both) after ~14 words.
"""
import json
import os
import re


def load(project):
    with open(os.path.join(project, 'sources.json'), encoding='utf-8') as f:
        src = json.load(f)
    words = {}
    for cid in src:
        p = os.path.join(project, f'words_{cid}.json')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                words[cid] = tidy(json.load(f))
    return src, words


def fixes(project):
    """<project>/fixes.json: [["BTOQ", "BTO queue"], ...]  mis-heard words and their correction, applied to every
    phrase the person sees and to the captions made from them. Whole words only, case-sensitive."""
    p = os.path.join(project, 'fixes.json')
    if not os.path.exists(p):
        return []
    with open(p, encoding='utf-8') as f:
        return [(a, b) for a, b in json.load(f) if a]


def tidy(ws):
    """Whisper splits "$130 ,000" and "3 %" into two tokens: glue the stray piece back onto the word before it."""
    out = []
    for w in ws:
        if out and re.match(r'^[,.%][\w%]*[.,?!]?$', w['text']) and w['start'] - out[-1]['end'] < 0.6:
            out[-1] = {'text': out[-1]['text'] + w['text'], 'start': out[-1]['start'], 'end': w['end']}
        else:
            out.append(dict(w))
    return out


def corrected(text, fix):
    for a, b in fix:
        text = re.sub(r'(?<![\w$])' + re.escape(a) + r'(?![\w%])', lambda m: b, text)
    return text


def chunks(ws, fix=()):
    """[{k, w0, w1, start, end, text, para}]  (w1 inclusive; para=True starts a new paragraph on the page)"""
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(i)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        gap = (nxt['start'] - w['end']) if nxt else 9
        n = len(cur)
        stop = r'[.?!]["\')]?$'
        near_end = any(re.search(stop, x['text']) for x in ws[i + 1:i + 3])      # do not strand "is." on its own
        end = (nxt is None or re.search(stop, w['text']) or (w['text'].endswith(',') and n >= 4)
               or (gap > 0.6 and n >= 2) or (n >= 14 and not near_end) or n >= 17)
        if end:
            a, b = cur[0], cur[-1]
            prev_end = ws[a - 1]['end'] if a else -9
            out.append({'k': len(out), 'w0': a, 'w1': b, 'start': ws[a]['start'], 'end': ws[b]['end'],
                        'text': corrected(' '.join(ws[j]['text'] for j in cur), fix),
                        'para': a == 0 or ws[a]['start'] - prev_end > 1.2 or bool(re.search(r'[.?!]$', ws[a - 1]['text']))
                        and len(out) % 4 == 0})
            cur = []
    return out
