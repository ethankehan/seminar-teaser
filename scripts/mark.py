#!/usr/bin/env python3
"""Open the transcript in the browser so the person can highlight the points they want in the video.

  PY mark.py <project_dir> [--budget 60] [--no-open] [--timeout-min 180]

Serves one local page (127.0.0.1 only) showing every clip's transcript as clickable phrases plus the brief from
<project_dir>/brief.json. Clicking a phrase highlights it; the bar at the top adds up the highlighted seconds
against the budget. "Done" writes <project_dir>/marks.json and this script exits with a line starting SAVED.
Run it in the background and wait for it to exit; do not poll.
"""
import datetime
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import words as W  # noqa: E402

PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mark the transcript</title><style>
:root{--bg:#faf8f4;--fg:#1d1b18;--mute:#77716a;--line:#e4dfd6;--hl:#ffe36e;--hlfg:#1d1b18;--card:#fff;--acc:#1f6f5c;--over:#c0392b}
@media(prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece8e1;--mute:#9a938a;--line:#2e2b27;--hl:#e8c93a;--hlfg:#161513;--card:#1e1c1a;--acc:#5fc2a8;--over:#ff7a6b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.75 -apple-system,"Segoe UI",Inter,Helvetica,Arial,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 20px}
.row{max-width:860px;margin:0 auto;display:flex;align-items:center;gap:16px}
.meter{flex:1}.meter b{font-size:20px}.meter span{color:var(--mute);font-size:14px;margin-left:8px}
.bar{height:6px;border-radius:3px;background:var(--line);margin-top:6px;overflow:hidden}.bar i{display:block;height:100%;width:0;background:var(--acc)}
.over .bar i{background:var(--over)}.over b{color:var(--over)}
button{font:600 16px/1 inherit;padding:13px 22px;border-radius:10px;border:0;background:var(--acc);color:#fff;cursor:pointer}
button.ghost{background:transparent;color:var(--mute);border:1px solid var(--line);padding:12px 14px}
main{max-width:860px;margin:0 auto;padding:22px 20px 120px}
h1{font-size:26px;line-height:1.25;margin:6px 0 6px}.how{color:var(--mute);margin:0 0 18px}
.brief{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-bottom:26px;font-size:15px;line-height:1.6}
.brief div{display:flex;gap:10px}.brief div span:first-child{color:var(--mute);min-width:110px}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin:34px 0 8px;border-top:1px solid var(--line);padding-top:18px}
p{margin:0 0 12px;display:grid;grid-template-columns:52px 1fr;gap:8px}p time{color:var(--mute);font-size:13px;padding-top:4px;font-variant-numeric:tabular-nums}
.ch{cursor:pointer;border-radius:4px;padding:2px 1px}.ch:hover{background:color-mix(in srgb,var(--hl) 35%,transparent)}
.ch.on{background:var(--hl);color:var(--hlfg)}
textarea{width:100%;min-height:84px;margin-top:8px;padding:12px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg);font:inherit;font-size:15px}
#done{position:fixed;inset:0;background:var(--bg);display:none;align-items:center;justify-content:center;text-align:center;z-index:9;padding:24px}
#done h1{font-size:30px}
</style></head><body>
<header><div class="row"><div class="meter" id="meter"><b id="sec">0s</b><span id="lab"></span><div class="bar"><i id="fill"></i></div></div>
<button class="ghost" id="clear">Clear</button><button id="save">Done</button></div></header>
<main><h1>Highlight what you want in the video</h1>
<p class="how" style="display:block">Click a phrase to highlight it, click again to remove it. Hold Shift and click to highlight everything in between. Highlight only the lines that must be in the video; the counter above shows how much time they take.</p>
<div class="brief" id="brief"></div><div id="clips"></div>
<h2>Anything else?</h2><textarea id="note" placeholder="Optional: a line that must come first, something to avoid, the next seminar's date or link ..."></textarea>
</main><div id="done"><div><h1>Saved.</h1><p style="display:block;color:var(--mute)">You can close this tab and go back to Claude.</p></div></div>
<script>
const D=__DATA__;const on=new Set(D.selected);let last=null;const els=[];
const fmt=t=>Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');
const brief=document.getElementById('brief');
for(const [k,v] of D.brief){const d=document.createElement('div');const a=document.createElement('span');a.textContent=k;const b=document.createElement('span');b.textContent=v;d.append(a,b);brief.append(d)}
if(!D.brief.length)brief.style.display='none';
const root=document.getElementById('clips');
for(const c of D.clips){const h=document.createElement('h2');h.textContent=c.label;root.append(h);let p=null;
 for(const ch of c.chunks){if(ch.para||!p){p=document.createElement('p');const t=document.createElement('time');t.textContent=fmt(ch.start);const s=document.createElement('span');p.append(t,s);root.append(p)}
  const e=document.createElement('span');e.className='ch';e.textContent=ch.text;e.dataset.key=c.id+':'+ch.k;e.dataset.d=ch.end-ch.start;e.dataset.i=els.length;
  if(on.has(e.dataset.key))e.classList.add('on');els.push(e);p.lastChild.append(e,' ')}}
function draw(){let s=0;for(const e of els)if(e.classList.contains('on'))s+=+e.dataset.d;
 document.getElementById('sec').textContent=Math.round(s)+'s';
 document.getElementById('lab').textContent=s>D.budget?'highlighted, over the '+D.budget+'s video length: we will ask which lines to drop':'highlighted of a '+D.budget+'s video';
 document.getElementById('fill').style.width=Math.min(100,100*s/D.budget)+'%';document.getElementById('meter').classList.toggle('over',s>D.budget)}
root.addEventListener('click',ev=>{const e=ev.target.closest('.ch');if(!e)return;const i=+e.dataset.i;
 if(ev.shiftKey&&last!==null){const [a,b]=[Math.min(i,last),Math.max(i,last)];for(let j=a;j<=b;j++)els[j].classList.add('on')}
 else e.classList.toggle('on');last=i;draw()});
document.getElementById('clear').onclick=()=>{if(confirm('Remove all highlights?')){els.forEach(e=>e.classList.remove('on'));draw()}};
document.getElementById('save').onclick=async()=>{const keys=els.filter(e=>e.classList.contains('on')).map(e=>e.dataset.key);
 if(!keys.length&&!confirm('Nothing is highlighted. Save anyway and let Claude pick the lines?'))return;
 try{const r=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keys,note:document.getElementById('note').value})});
  if(!r.ok)throw 0;document.getElementById('done').style.display='flex'}catch(e){alert('Could not save. Is Claude still running? Keep this tab open and tell Claude.')}};
draw();
</script></body></html>'''


def main():
    args = sys.argv[1:]
    project = os.path.abspath(os.path.expanduser(args[0]))
    budget = int(args[args.index('--budget') + 1]) if '--budget' in args else 60
    minutes = int(args[args.index('--timeout-min') + 1]) if '--timeout-min' in args else 180
    src, words = W.load(project)
    brief = {}
    bp = os.path.join(project, 'brief.json')
    if os.path.exists(bp):
        with open(bp, encoding='utf-8') as f:
            brief = json.load(f)
    budget = int(brief.get('length_seconds', budget))
    mp = os.path.join(project, 'marks.json')
    selected = []
    if os.path.exists(mp):
        with open(mp, encoding='utf-8') as f:
            selected = [f"{m['clip']}:{m['k']}" for m in json.load(f).get('marks', [])]
    clips, index = [], {}
    for n, (cid, path) in enumerate(src.items(), 1):
        ch = W.chunks(words.get(cid, []))
        for c in ch:
            index[f'{cid}:{c["k"]}'] = (cid, c)
        clips.append({'id': cid, 'label': f'Clip {n} of {len(src)}  ·  {os.path.basename(path)}',
                      'chunks': [{k: c[k] for k in ('k', 'start', 'end', 'text', 'para')} for c in ch]})
    labels = [('Audience', 'audience'), ('Goal', 'goal'), ('Length', 'length_seconds'), ('Call to action', 'cta')]
    data = {'clips': clips, 'budget': budget, 'selected': selected,
            'brief': [[lab, f"{brief[k]}s" if k == 'length_seconds' else str(brief[k])] for lab, k in labels if brief.get(k)]}
    page = PAGE.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
    state = {'saved': None}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = page.encode('utf-8')
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control', 'no-store'); self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != '/save':
                self.send_response(404); self.end_headers(); return
            req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            marks = []
            for key in req.get('keys', []):
                if key in index:
                    cid, c = index[key]
                    marks.append({'clip': cid, 'k': c['k'], 'w0': c['w0'], 'w1': c['w1'], 'start': c['start'],
                                  'end': c['end'], 'text': c['text']})
            with open(mp, 'w', encoding='utf-8') as f:
                json.dump({'saved': datetime.datetime.now().isoformat(timespec='seconds'),
                           'note': str(req.get('note', '')).strip(), 'marks': marks}, f, indent=1, ensure_ascii=False)
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(b'{"ok":true}')
            state['saved'] = marks

    srv = HTTPServer(('127.0.0.1', 0), H)
    url = f'http://127.0.0.1:{srv.server_address[1]}/'
    print(f'MARK PAGE {url}', flush=True)
    if '--no-open' not in args:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    srv.timeout = 1
    deadline = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
    while state['saved'] is None and datetime.datetime.now() < deadline:
        srv.handle_request()
    srv.server_close()
    if state['saved'] is None:
        sys.exit(f'TIMEOUT: nothing was saved in {minutes} minutes. Run mark.py again when the person is ready.')
    total = sum(m['end'] - m['start'] for m in state['saved'])
    print(f"SAVED {len(state['saved'])} phrases, {total:.0f}s highlighted (budget {budget}s) -> {mp}", flush=True)


if __name__ == '__main__':
    main()
