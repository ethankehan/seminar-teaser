"""Shared: load a project's word timestamps and split them into phrase-sized chunks.

A chunk is the unit a person highlights on the marking page and the unit a caption is built from, so it must end
where the speaker's phrase ends: at punctuation, at a pause, or (failing both) after ~14 words.
"""
import json
import os
import re


CJK = '\u3400-\u4dbf\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'
CJK_PUNCT = '，。！？、；：」』）》…'


def has_cjk(s):
    return bool(re.search(f'[{CJK}]', s or ''))


def tokens(text):
    """Display units: a Latin word, or one Chinese character (punctuation stays glued to what precedes it)."""
    out = []
    for t in re.findall(f'[{CJK}]|[^\\s{CJK}]+', text or ''):
        if out and t in CJK_PUNCT:
            out[-1] += t
        else:
            out.append(t)
    return out


def join(toks):
    """Put tokens back together: a space between Latin words, none next to Chinese."""
    out = ''
    for i, t in enumerate(toks):
        if i and not (has_cjk(t[0]) or has_cjk(toks[i - 1][-1])):
            out += ' '
        out += t
    return out


def language(project):
    p = os.path.join(project, 'language.txt')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            return f.read().strip() or 'en'
    return 'en'


def edits(project):
    """<project>/edits.json: {"c1:14": "text the person typed on the page"}; wins over the transcript and fixes."""
    p = os.path.join(project, 'edits.json')
    if not os.path.exists(p):
        return {}
    with open(p, encoding='utf-8') as f:
        return json.load(f)


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
        stray = re.match(r'^[,.%][\w%]*[.,?!]?$', w['text']) and out and w['start'] - out[-1]['end'] < 0.6
        piece = w.get('j') and out and not has_cjk(w['text'][:1]) and not has_cjk(out[-1]['text'][-1:])   # "t"+"od"+"ay"
        if stray or piece:
            out[-1] = {'text': out[-1]['text'] + w['text'], 'start': out[-1]['start'], 'end': w['end']}
        else:
            out.append({'text': w['text'], 'start': w['start'], 'end': w['end']})
    for w in out:                                   # Chinese sentences get Chinese punctuation
        if has_cjk(w['text']) and w['text'][-1:] in ',?!;:':
            w['text'] = w['text'][:-1] + {',': '，', '?': '？', '!': '！', ';': '；', ':': '：'}[w['text'][-1]]
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
        cap = 22 if any(has_cjk(ws[j]['text']) for j in cur) else 14      # Chinese tokens are one or two characters
        stop = r'[.?!。？！]["\')」』]?$'
        near_end = any(re.search(stop, x['text']) for x in ws[i + 1:i + 4])      # do not strand "is." on its own
        end = (nxt is None or re.search(stop, w['text']) or (w['text'].endswith((',', '，', '、', '；')) and n >= 4)
               or (gap > 0.6 and n >= 2) or (n >= cap and not near_end) or n >= cap + 4)
        if end:
            a, b = cur[0], cur[-1]
            prev_end = ws[a - 1]['end'] if a else -9
            out.append({'k': len(out), 'w0': a, 'w1': b, 'start': ws[a]['start'], 'end': ws[b]['end'],
                        'text': corrected(join([ws[j]['text'] for j in cur]), fix),
                        'para': a == 0 or ws[a]['start'] - prev_end > 1.2 or bool(re.search(r'[.?!。？！]$', ws[a - 1]['text']))
                        and len(out) % 4 == 0})
            cur = []
    return out
