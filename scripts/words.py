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
                words[cid] = json.load(f)
    return src, words


def chunks(ws):
    """[{k, w0, w1, start, end, text, para}]  (w1 inclusive; para=True starts a new paragraph on the page)"""
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(i)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        gap = (nxt['start'] - w['end']) if nxt else 9
        n = len(cur)
        end = (nxt is None or re.search(r'[.?!]["\')]?$', w['text']) or (w['text'].endswith(',') and n >= 4)
               or (gap > 0.6 and n >= 2) or n >= 14)
        if end:
            a, b = cur[0], cur[-1]
            prev_end = ws[a - 1]['end'] if a else -9
            out.append({'k': len(out), 'w0': a, 'w1': b, 'start': ws[a]['start'], 'end': ws[b]['end'],
                        'text': ' '.join(ws[j]['text'] for j in cur),
                        'para': a == 0 or ws[a]['start'] - prev_end > 1.2 or bool(re.search(r'[.?!]$', ws[a - 1]['text']))
                        and len(out) % 4 == 0})
            cur = []
    return out
