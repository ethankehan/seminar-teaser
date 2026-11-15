#!/usr/bin/env python3
"""The whole /seminar-teaser flow as one local web page (127.0.0.1 only).

  PY app.py <project_dir> [--clips <folder or files ...>] [--no-open]

The page walks the person through: add videos -> audience / goal / length -> pick the lines -> music -> review.
Between those steps the editor (Claude) does its part and moves the page on by changing <project>/state.json
through flow.py. Stages, and who acts:
  upload (person) -> transcribing (this server) -> suggesting (Claude) -> brief (person) -> recommending (Claude)
  -> highlight (person) -> music (person) -> editing (Claude) -> review (person) -> editing ... -> done
Files written for Claude: brief.json, marks.json, music.json, notes.json. Files Claude writes for the page:
suggest.json {"audiences": [...]}, recommend.json {"keys": ["c1:4", ...]}.
Start it in the background; it exits a few seconds after the person presses Done (or after 8 hours).
"""
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import words as W  # noqa: E402

SK = os.path.dirname(HERE)
MUSIC_DIR = os.path.join(SK, 'assets', 'music')
VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.mkv', '.avi')
LOCK = threading.Lock()


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def get_state(project):
    return read_json(os.path.join(project, 'state.json'), {'stage': 'upload', 'msg': '', 'rev': 0})


def set_state(project, stage, msg='', **extra):
    with LOCK:
        s = get_state(project)
        s.update(extra)
        s.update({'stage': stage, 'msg': msg, 'rev': s.get('rev', 0) + 1})
        write_json(os.path.join(project, 'state.json'), s)
    return s


def tracks():
    cat = read_json(os.path.join(SK, 'assets', 'music.json'), [])
    return [{'id': t['id'], 'title': t['title']} for t in cat if os.path.exists(os.path.join(MUSIC_DIR, t['id'] + '.mp3'))]


def transcribe(project, inputs):
    n = len([f for f in inputs if not os.path.isdir(f)]) or '?'
    set_state(project, 'transcribing', 'Listening to the talk')
    p = subprocess.Popen([sys.executable, os.path.join(HERE, 'ingest.py'), project, *inputs], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, encoding='utf-8', errors='replace')
    last = ''
    for line in p.stdout:
        last = line.strip() or last
        m = re.match(r'c(\d+) transcribing', line)
        if m:
            total = len(read_json(os.path.join(project, 'sources.json'), {})) or n
            set_state(project, 'transcribing', f'Listening to clip {m.group(1)} of {total}')
    if p.wait() == 0:
        set_state(project, 'suggesting', 'Reading the talk')
    else:
        set_state(project, 'error', f'Transcription failed: {last}')


PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seminar teaser</title><style>
:root{--bg:#f7f5f0;--ink:#171614;--mute:#8d887f;--line:#e2ddd3;--soft:#efebe3;--hl:#ffe27a;--hlink:#171614;--btn:#171614;--btnink:#f7f5f0;--warn:#b8402f}
@media(prefers-color-scheme:dark){:root{--bg:#131211;--ink:#ece8e0;--mute:#8a857c;--line:#2b2926;--soft:#1d1b19;--hl:#e3c64a;--hlink:#131211;--btn:#ece8e0;--btnink:#131211;--warn:#ff8674}}
*{box-sizing:border-box;margin:0}html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--ink);font:17px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:660px;margin:0 auto;padding:0 24px 140px}
.dots{display:flex;gap:8px;justify-content:center;padding:34px 0 54px}.dots i{width:6px;height:6px;border-radius:50%;background:var(--line);transition:.3s}.dots i.on{background:var(--ink)}
h1{font-size:34px;line-height:1.15;font-weight:650;letter-spacing:-.025em;margin-bottom:34px}
.lab{font-size:13px;color:var(--mute);margin:34px 0 12px}
button{font:inherit;cursor:pointer;border:0;background:none;color:inherit}
.go{position:fixed;left:0;right:0;bottom:0;padding:18px 24px 26px;background:linear-gradient(transparent,var(--bg) 34%);display:flex;justify-content:center;gap:12px}
.btn{background:var(--btn);color:var(--btnink);font-weight:600;padding:15px 30px;border-radius:999px;min-width:190px;transition:opacity .2s}.btn:disabled{opacity:.28;cursor:default}
.btn.alt{background:none;color:var(--ink);box-shadow:inset 0 0 0 1px var(--line)}
.drop{border:1.5px dashed var(--line);border-radius:18px;padding:64px 20px;text-align:center;color:var(--mute);cursor:pointer;transition:.2s}.drop.over{border-color:var(--ink);color:var(--ink);background:var(--soft)}
.files{margin-top:18px}.file{display:flex;justify-content:space-between;gap:16px;padding:12px 2px;border-bottom:1px solid var(--line);font-size:15px;position:relative}
.file span:last-child{color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}.file b{position:absolute;left:0;bottom:-1px;height:1.5px;background:var(--ink);width:0;transition:width .2s}
.file span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chips{display:flex;flex-wrap:wrap;gap:10px}.chip{padding:11px 18px;border-radius:999px;box-shadow:inset 0 0 0 1px var(--line);font-size:16px;text-align:left;transition:.15s}
.chip.on{background:var(--btn);color:var(--btnink);box-shadow:none}
input[type=text],textarea{width:100%;font:inherit;color:inherit;background:none;border:0;border-bottom:1px solid var(--line);padding:12px 2px;outline:0;margin-top:14px;resize:none}
input[type=text]:focus,textarea:focus{border-color:var(--ink)}::placeholder{color:var(--mute)}
.len{display:flex;align-items:center;gap:22px}.len output{font-size:34px;font-weight:650;letter-spacing:-.02em;min-width:86px;font-variant-numeric:tabular-nums}
input[type=range]{flex:1;-webkit-appearance:none;appearance:none;height:2px;background:var(--line);border-radius:2px;outline:0}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:24px;height:24px;border-radius:50%;background:var(--ink);cursor:pointer}
input[type=range]::-moz-range-thumb{width:24px;height:24px;border:0;border-radius:50%;background:var(--ink);cursor:pointer}
.bar{position:sticky;top:0;background:var(--bg);padding:14px 0 12px;margin:-14px 0 22px;z-index:3;display:flex;align-items:baseline;justify-content:space-between;border-bottom:1px solid var(--line)}
.bar strong{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}.bar strong.over{color:var(--warn)}.bar button{color:var(--mute);font-size:14px}
.clip{font-size:12px;color:var(--mute);letter-spacing:.06em;text-transform:uppercase;margin:34px 0 14px;display:flex;align-items:center;gap:12px}.clip:after{content:"";flex:1;height:1px;background:var(--line)}
.para{display:grid;grid-template-columns:44px 1fr;gap:6px;margin-bottom:14px;line-height:1.85}.para time{font-size:12px;color:var(--mute);padding-top:6px;font-variant-numeric:tabular-nums}
.ch{cursor:pointer;border-radius:5px;padding:3px 2px;transition:background .12s}.ch:hover{background:var(--soft)}.ch.on{background:var(--hl);color:var(--hlink)}
.row{display:flex;align-items:center;gap:14px;padding:16px 2px;border-bottom:1px solid var(--line);cursor:pointer}
.row .rad{width:20px;height:20px;border-radius:50%;box-shadow:inset 0 0 0 1.5px var(--line);flex:none;transition:.15s}.row.on .rad{box-shadow:inset 0 0 0 6px var(--ink)}
.row .t{flex:1}.row .play{width:38px;height:38px;border-radius:50%;box-shadow:inset 0 0 0 1px var(--line);font-size:12px;flex:none}.row small{color:var(--mute)}
.wait{min-height:52vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:26px;color:var(--mute);text-align:center}
.wait:before{content:"";width:150px;height:2px;border-radius:2px;background:linear-gradient(90deg,var(--line) 0 40%,var(--ink) 40% 60%,var(--line) 60%);background-size:250% 100%;animation:sl 1.5s linear infinite}
@keyframes sl{from{background-position:100% 0}to{background-position:-50% 0}}
video{display:block;width:100%;max-width:300px;margin:0 auto 26px;border-radius:16px;background:#000;aspect-ratio:9/16}
.path{font-size:13px;color:var(--mute);text-align:center;word-break:break-all;margin-top:14px}
</style></head><body><div class="wrap"><div class="dots" id="dots"></div><div id="app"></div></div>
<script>
const app=document.getElementById('app'),dots=document.getElementById('dots');let cur=null,rev=-1;
const STEP={upload:0,transcribing:0,suggesting:0,brief:1,recommending:1,highlight:2,music:3,editing:4,review:4,done:4,error:0};
const WAIT={transcribing:1,suggesting:1,recommending:1,editing:1};
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
const go=(label,fn,alt)=>{let g=document.querySelector('.go');if(!g){g=el('div','go');app.append(g)}const b=el('button','btn'+(alt?' alt':''),label);b.onclick=()=>fn(b);g.append(b);return b};
const mb=n=>n>1e9?(n/1e9).toFixed(1)+' GB':Math.max(1,Math.round(n/1e6))+' MB';
const fmt=t=>Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');
function setDots(i){dots.innerHTML='';for(let k=0;k<5;k++)dots.append(el('i',k<=i?'on':''))}

const V={
 upload(){const files=[];app.append(el('h1','','Add your videos'));
  const d=el('div','drop','Drop videos here'),inp=el('input');inp.type='file';inp.multiple=true;inp.accept='video/*';inp.hidden=true;
  const list=el('div','files');app.append(d,inp,list);
  const add=fs=>{for(const f of fs)if(/\.(mp4|mov|m4v|mkv|avi)$/i.test(f.name)&&!files.some(x=>x.name===f.name)){files.push(f);const r=el('div','file');r.append(el('span','',f.name),el('span','',mb(f.size)),el('b'));f.row=r;list.append(r)}b.disabled=!files.length};
  d.onclick=()=>inp.click();inp.onchange=()=>add(inp.files);
  d.ondragover=e=>{e.preventDefault();d.classList.add('over')};d.ondragleave=()=>d.classList.remove('over');
  d.ondrop=e=>{e.preventDefault();d.classList.remove('over');add(e.dataTransfer.files)};
  const b=go('Continue',async()=>{b.disabled=true;d.style.pointerEvents='none';
   for(const f of files)await new Promise((ok,no)=>{const x=new XMLHttpRequest();x.open('PUT','/upload?name='+encodeURIComponent(f.name));
    x.upload.onprogress=e=>{f.row.lastChild.style.width=(100*e.loaded/e.total)+'%'};x.onload=()=>x.status===200?ok():no();x.onerror=no;x.send(f)});
   await post('/start')});b.disabled=true},

 async brief(){const D=await (await fetch('/data')).json();let aud=D.brief.audience||'',goal=D.brief.goal||'',len=D.brief.length_seconds||45;
  app.append(el('h1','','Who is it for?'));const chips=el('div','chips');app.append(chips);
  const own=el('input');own.type='text';own.placeholder='Someone else';app.append(own);
  const ok=()=>{b.disabled=!(aud&&goal)};
  const pick=(box,val,set)=>{[...box.children].forEach(c=>c.classList.toggle('on',c.textContent===val));set(val);ok()};
  for(const a of D.audiences){const c=el('button','chip',a);c.onclick=()=>{own.value='';pick(chips,a,v=>aud=v)};chips.append(c)}
  own.oninput=()=>{[...chips.children].forEach(c=>c.classList.remove('on'));aud=own.value.trim();ok()};
  if(aud&&!D.audiences.includes(aud))own.value=aud;
  app.append(el('div','lab','Goal'));const goals=el('div','chips');app.append(goals);
  for(const g of ['Follows','Likes and shares','Comments','Sign-ups']){const c=el('button','chip',g);c.onclick=()=>pick(goals,g,v=>goal=v);goals.append(c)}
  app.append(el('div','lab','Length'));const L=el('div','len'),o=el('output','',len+'s'),r=el('input');r.type='range';r.min=15;r.max=60;r.step=5;r.value=len;
  r.oninput=()=>{len=+r.value;o.textContent=len+'s'};L.append(o,r);app.append(L);
  const b=go('Continue',async()=>{b.disabled=true;await post('/brief',{audience:aud,goal,length_seconds:len})});
  if(aud)pick(chips,aud,v=>aud=v);if(goal)pick(goals,goal,v=>goal=v);ok()},

 async highlight(){const D=await (await fetch('/data')).json();const on=new Set(D.selected),els=[];let last=null;
  app.append(el('h1','','Pick the lines'));const bar=el('div','bar'),n=el('strong'),rs=el('button','','Reset');bar.append(n,rs);app.append(bar);
  const multi=D.clips.length>1;
  D.clips.forEach((c,ci)=>{if(multi)app.append(el('div','clip','Clip '+(ci+1)));let p=null;
   for(const ch of c.chunks){if(ch.para||!p){p=el('div','para');p.append(el('time','',fmt(ch.start)),el('div'));app.append(p)}
    const e=el('span','ch',ch.text);e.dataset.key=c.id+':'+ch.k;e.dataset.d=ch.end-ch.start;e.dataset.i=els.length;if(on.has(e.dataset.key))e.classList.add('on');els.push(e);p.lastChild.append(e,' ')}});
  const draw=()=>{let s=0;for(const e of els)if(e.classList.contains('on'))s+=+e.dataset.d;n.textContent=Math.round(s)+'s / '+D.budget+'s';n.classList.toggle('over',s>D.budget)};
  app.addEventListener('click',ev=>{const e=ev.target.closest('.ch');if(!e)return;const i=+e.dataset.i;
   if(ev.shiftKey&&last!==null){for(let k=Math.min(i,last);k<=Math.max(i,last);k++)els[k].classList.add('on')}else e.classList.toggle('on');last=i;draw()});
  rs.onclick=()=>{els.forEach(e=>e.classList.toggle('on',on.has(e.dataset.key)));draw()};
  const b=go('Continue',async()=>{b.disabled=true;await post('/marks',{keys:els.filter(e=>e.classList.contains('on')).map(e=>e.dataset.key)})});draw()},

 async music(){const D=await (await fetch('/data')).json();let choice=D.choice||{type:D.tracks.length?'track':'none',id:(D.tracks[0]||{}).id};const au=new Audio();let playing=null;
  app.append(el('h1','','Music'));const rows=[];
  const sel=(r,c)=>{rows.forEach(x=>x.classList.remove('on'));r.classList.add('on');choice=c};
  const row=(title,c,src)=>{const r=el('div','row');r.append(el('span','rad'),el('span','t',title));
   if(src){const p=el('button','play','▶');p.onclick=e=>{e.stopPropagation();if(playing===p){au.pause();p.textContent='▶';playing=null}else{if(playing)playing.textContent='▶';au.src=src;au.play();p.textContent='❚❚';playing=p}};r.append(p)}
   r.onclick=()=>sel(r,c);rows.push(r);app.append(r);return r};
  for(const t of D.tracks){const r=row(t.title,{type:'track',id:t.id},'/track/'+t.id);if(choice.type==='track'&&choice.id===t.id)r.classList.add('on')}
  const inp=el('input');inp.type='file';inp.accept='audio/*';inp.hidden=true;app.append(inp);
  const ownRow=row(choice.type==='own'?choice.name:'Use my own file',{type:'own'});ownRow.onclick=()=>inp.click();if(choice.type==='own')ownRow.classList.add('on');
  inp.onchange=async()=>{const f=inp.files[0];if(!f)return;ownRow.children[1].textContent='Uploading…';
   await fetch('/music-upload?name='+encodeURIComponent(f.name),{method:'PUT',body:f});ownRow.children[1].textContent=f.name;sel(ownRow,{type:'own',name:f.name})};
  const none=row('No music',{type:'none'});if(choice.type==='none')none.classList.add('on');
  au.onended=()=>{if(playing){playing.textContent='▶';playing=null}};
  const b=go('Make the video',async()=>{b.disabled=true;au.pause();await post('/music',choice)})},

 async review(){const D=await (await fetch('/data')).json();const v=el('video');v.src='/video?v='+D.rev;v.controls=true;v.playsInline=true;app.append(v);
  const t=el('textarea');t.rows=2;t.placeholder='What should change?';app.append(t);
  const send=go('Send changes',async()=>{send.disabled=true;await post('/notes',{text:t.value.trim()})},true);send.disabled=true;
  t.oninput=()=>{send.disabled=!t.value.trim();t.style.height='auto';t.style.height=t.scrollHeight+'px'};
  go('Done',async b=>{b.disabled=true;await post('/done')})},

 async done(){const D=await (await fetch('/data')).json();app.append(el('h1','','Done'));if(D.video)app.append(el('div','path',D.video)).style.textAlign='left'},
 error(s){app.append(el('h1','','Something went wrong'),el('div','path',s.msg))}
};
async function tick(){try{const s=await (await fetch('/state',{cache:'no-store'})).json();
  if(s.stage!==cur||(s.stage==='review'&&s.rev!==rev)){cur=s.stage;rev=s.rev;app.innerHTML='';setDots(STEP[cur]??0);window.scrollTo(0,0);
   if(WAIT[cur])app.append(el('div','wait',s.msg));else await V[cur](s)}
  else if(WAIT[cur]){const w=app.querySelector('.wait');if(w&&w.textContent!==s.msg)w.textContent=s.msg}
 }catch(e){}setTimeout(tick,1000)}
tick();
</script></body></html>'''


def main():
    args = sys.argv[1:]
    project = os.path.abspath(os.path.expanduser(args[0]))
    os.makedirs(os.path.join(project, 'work'), exist_ok=True)
    clips = []
    if '--clips' in args:
        i = args.index('--clips') + 1
        while i < len(args) and not args[i].startswith('--'):
            clips.append(os.path.abspath(os.path.expanduser(args[i]))); i += 1
    if not os.path.exists(os.path.join(project, 'state.json')):
        set_state(project, 'upload')
        if clips:
            threading.Thread(target=transcribe, args=(project, clips), daemon=True).start()
    elif get_state(project)['stage'] == 'transcribing':        # interrupted run: pick the transcription up again
        again = clips or [os.path.join(project, 'clips')]
        threading.Thread(target=transcribe, args=(project, again), daemon=True).start()

    def chunk_index():
        src, words = W.load(project)
        out, index = [], {}
        for cid in src:
            ch = W.chunks(words.get(cid, []))
            for c in ch:
                index[f'{cid}:{c["k"]}'] = (cid, c)
            out.append({'id': cid, 'chunks': [{k: c[k] for k in ('k', 'start', 'end', 'text', 'para')} for c in ch]})
        return out, index

    class H(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *a):
            pass

        def send_json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control', 'no-store'); self.end_headers()
            self.wfile.write(body)

        def send_file(self, path, ctype):
            if not path or not os.path.exists(path):
                return self.send_json({'error': 'not found'}, 404)
            size = os.path.getsize(path)
            a, b = 0, size - 1
            m = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else size - 1
                else:
                    a = max(0, size - int(m.group(2)))
                b = min(b, size - 1)
                self.send_response(206); self.send_header('Content-Range', f'bytes {a}-{b}/{size}')
            else:
                self.send_response(200)
            self.send_header('Content-Type', ctype); self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(b - a + 1)); self.send_header('Cache-Control', 'no-store'); self.end_headers()
            try:
                with open(path, 'rb') as f:
                    f.seek(a); left = b - a + 1
                    while left > 0:
                        buf = f.read(min(1 << 20, left))
                        if not buf:
                            break
                        self.wfile.write(buf); left -= len(buf)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def body_json(self):
            n = int(self.headers.get('Content-Length', 0))
            return json.loads(self.rfile.read(n) or b'{}') if n else {}

        def save_stream(self, folder):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            name = re.sub(r'[^\w.\- ()]', '_', os.path.basename(q.get('name', ['file'])[0])) or 'file'
            os.makedirs(folder, exist_ok=True)
            path, left = os.path.join(folder, name), int(self.headers.get('Content-Length', 0))
            with open(path, 'wb') as f:
                while left > 0:
                    buf = self.rfile.read(min(1 << 20, left))
                    if not buf:
                        break
                    f.write(buf); left -= len(buf)
            return path, name

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            st = get_state(project)
            if path == '/':
                body = PAGE.encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control', 'no-store'); self.end_headers()
                self.wfile.write(body)
            elif path == '/state':
                self.send_json({k: st.get(k) for k in ('stage', 'msg', 'rev')})
            elif path == '/data':
                brief = read_json(os.path.join(project, 'brief.json'), {})
                if st['stage'] == 'brief':
                    self.send_json({'audiences': read_json(os.path.join(project, 'suggest.json'), {}).get('audiences', []), 'brief': brief})
                elif st['stage'] == 'highlight':
                    clips_, _ = chunk_index()
                    marks = read_json(os.path.join(project, 'marks.json'))
                    sel = ([f"{m['clip']}:{m['k']}" for m in marks['marks']] if marks else
                           read_json(os.path.join(project, 'recommend.json'), {}).get('keys', []))
                    self.send_json({'clips': clips_, 'selected': sel, 'budget': int(brief.get('length_seconds', 60))})
                elif st['stage'] == 'music':
                    self.send_json({'tracks': tracks(), 'choice': read_json(os.path.join(project, 'music.json'))})
                else:
                    self.send_json({'rev': st.get('rev'), 'video': st.get('video', '')})
            elif path.startswith('/track/'):
                tid = re.sub(r'[^\w\-]', '', path[7:])
                self.send_file(os.path.join(MUSIC_DIR, tid + '.mp3'), 'audio/mpeg')
            elif path == '/video':
                self.send_file(st.get('video'), 'video/mp4')
            else:
                self.send_json({'error': 'not found'}, 404)

        def do_PUT(self):
            path = urllib.parse.urlparse(self.path).path
            if path == '/upload':
                self.save_stream(os.path.join(project, 'clips'))
                self.send_json({'ok': True})
            elif path == '/music-upload':
                p, name = self.save_stream(os.path.join(project, 'music'))
                write_json(os.path.join(project, 'music.json'), {'type': 'own', 'name': name, 'file': p.replace('\\', '/')})
                self.send_json({'ok': True})
            else:
                self.send_json({'error': 'not found'}, 404)

        def do_POST(self):
            path, req = urllib.parse.urlparse(self.path).path, self.body_json()
            if path == '/start':
                folder = os.path.join(project, 'clips')
                threading.Thread(target=transcribe, args=(project, [folder]), daemon=True).start()
                set_state(project, 'transcribing', 'Listening to the talk')
            elif path == '/brief':
                brief = read_json(os.path.join(project, 'brief.json'), {})
                brief.update({'audience': str(req.get('audience', '')).strip(), 'goal': str(req.get('goal', '')),
                              'length_seconds': max(15, min(60, int(req.get('length_seconds', 45))))})
                write_json(os.path.join(project, 'brief.json'), brief)
                for stale in ('marks.json', 'recommend.json'):       # a new brief means a new recommendation
                    if os.path.exists(os.path.join(project, stale)):
                        os.remove(os.path.join(project, stale))
                set_state(project, 'recommending', 'Choosing the lines')
            elif path == '/marks':
                _, index = chunk_index()
                marks = []
                for key in req.get('keys', []):
                    if key in index:
                        cid, c = index[key]
                        marks.append({'clip': cid, **{k: c[k] for k in ('k', 'w0', 'w1', 'start', 'end', 'text')}})
                write_json(os.path.join(project, 'marks.json'), {'saved': datetime.datetime.now().isoformat(timespec='seconds'),
                                                                 'note': '', 'marks': marks})
                set_state(project, 'music')
            elif path == '/music':
                if req.get('type') == 'own':
                    saved = read_json(os.path.join(project, 'music.json'), {})
                    req = saved if saved.get('type') == 'own' else {'type': 'none'}
                elif req.get('type') == 'track':
                    req = {'type': 'track', 'id': req.get('id'), 'file': os.path.join(MUSIC_DIR, f"{req.get('id')}.mp3").replace('\\', '/')}
                else:
                    req = {'type': 'none'}
                write_json(os.path.join(project, 'music.json'), req)
                set_state(project, 'editing', 'Editing')
            elif path == '/notes':
                notes = read_json(os.path.join(project, 'notes.json'), [])
                notes.append({'time': datetime.datetime.now().isoformat(timespec='seconds'), 'text': str(req.get('text', '')).strip(),
                              'handled': False})
                write_json(os.path.join(project, 'notes.json'), notes)
                set_state(project, 'editing', 'Editing')
            elif path == '/done':
                set_state(project, 'done')
            else:
                return self.send_json({'error': 'not found'}, 404)
            self.send_json({'ok': True})

    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    srv.daemon_threads = True
    url = f'http://127.0.0.1:{srv.server_address[1]}/'
    set_state(project, get_state(project)['stage'], get_state(project).get('msg', ''), url=url)
    print(f'APP {url}', flush=True)
    if '--no-open' not in args:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    deadline = time.time() + 8 * 3600
    while time.time() < deadline:
        time.sleep(1)
        if get_state(project)['stage'] == 'done':
            time.sleep(4)                    # let the page fetch its last screen
            break
    srv.shutdown()
    print(f"CLOSED at stage {get_state(project)['stage']}", flush=True)


if __name__ == '__main__':
    main()
