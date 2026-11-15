#!/usr/bin/env python3
"""The whole /seminar-teaser flow as one local web page (127.0.0.1 only).

  PY app.py <project_dir> [--clips <folder or files ...>] [--no-open]

The page walks the person through: add videos -> audience / goal / length / speaker -> how to cut it (one video or
a series; skipped when there is only one sensible way) -> pick the lines (once per video) -> music -> review.
Between those steps the editor (Claude) does its part and moves the page on through flow.py. Stages, and who acts:
  upload (person) -> transcribing (this server) -> suggesting (Claude) -> brief (person) -> planning (Claude)
  -> plan (person) -> highlight (person, once per video) -> music (person) -> editing (Claude) -> review (person)
  -> editing ... -> done
Back on the page: plan -> brief, highlight -> previous video / plan / brief, music -> highlight, review -> music.
state.json carries `reason` for an editing stage: lines (first build, or lines changed), music, notes.

Files written for Claude: brief.json, videos.json (the chosen plan), v1/ v2/ ... (one folder per video, each a
complete project for draft.py / trailer.py: marks.json, music.json, brief.json, sources.json, words_*.json),
notes.json. Files Claude writes for the page: suggest.json {"audiences": [...]}, plan.json {"options": [...]}.
Start it in the background; it exits a few seconds after the person presses Done (or after 8 hours).
"""
import datetime
import glob
import json
import os
import re
import shutil
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
LOCK = threading.Lock()


def read_json(path, default=None):
    for attempt in range(8):                      # a writer may be replacing the file this very moment
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            time.sleep(0.05)
    return default


def write_json(path, obj):
    tmp = f'{path}.{os.getpid()}.{threading.get_ident()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    for attempt in range(40):                     # Windows refuses to replace a file another process has open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
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


VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.mkv', '.avi')
BRAND_DIR = os.environ.get('SEMINAR_BRAND_DIR') or os.path.join(os.path.expanduser('~'), 'seminar-videos', 'brand')


def brand_kit():
    """The brand lives on this computer, outside the skill folder: name, handle, colour, logo, vocabulary."""
    return read_json(os.path.join(BRAND_DIR, 'brand.json'))


def expand(inputs):
    files = []
    for p in inputs:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(VIDEO_EXT) and not f.startswith('.')]
        elif os.path.exists(p):
            files.append(p)
    return files


def resolution(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of',
                        'csv=p=0:s=x', path], capture_output=True, encoding='utf-8', errors='replace').stdout.strip().split('\n')[0]
    try:
        w, h = [int(x) for x in r.split('x')[:2]]
        return w, h
    except ValueError:
        return 0, 0


def chunk_index(project):
    src, words = W.load(project)
    fixes, edits = W.fixes(project), W.edits(project)
    clips, index = [], {}
    for cid in src:
        ch = W.chunks(words.get(cid, []), fixes)
        for c in ch:
            c['text'] = edits.get(f'{cid}:{c["k"]}', c['text'])
        for c in ch:
            index[f'{cid}:{c["k"]}'] = (cid, c)
        clips.append({'id': cid, 'chunks': [{k: c[k] for k in ('k', 'start', 'end', 'text', 'para')} for c in ch]})
    return clips, index


def vdir(project, i):
    return os.path.join(project, f'v{i + 1}')


def videos(project):
    return read_json(os.path.join(project, 'videos.json'), [])


def choose_option(project, oid=None):
    """Turn one option of plan.json into videos.json and go to the first highlight page."""
    plan = read_json(os.path.join(project, 'plan.json'), {'options': []})
    opts = plan.get('options', [])
    opt = next((o for o in opts if o.get('id') == oid), opts[0] if opts else None)
    if not opt:
        return set_state(project, 'error', 'plan.json has no options')
    st = get_state(project)
    if st.get('option') != opt['id'] or len(videos(project)) != len(opt['videos']):
        for d in glob.glob(os.path.join(project, 'v[0-9]*')):       # another way of cutting it: old choices do not apply
            m = os.path.join(d, 'marks.json')
            if os.path.exists(m):
                os.remove(m)
        write_json(os.path.join(project, 'videos.json'),
                   [{'title': v.get('title', ''), 'keys': v.get('keys', [])} for v in opt['videos']])
        return set_state(project, 'highlight', option=opt['id'], index=0, n=len(opt['videos']), dirty=True)
    return set_state(project, 'highlight', index=0)


def prep_video(project, i, title):
    """v<i+1>/ is a complete project folder for draft.py and trailer.py."""
    d = vdir(project, i)
    os.makedirs(os.path.join(d, 'work'), exist_ok=True)
    for f in ['sources.json', 'music.json'] + [os.path.basename(p) for p in glob.glob(os.path.join(project, 'words_*.json'))]:
        if os.path.exists(os.path.join(project, f)):
            shutil.copyfile(os.path.join(project, f), os.path.join(d, f))
    brief = read_json(os.path.join(project, 'brief.json'), {})
    brief['video_title'] = title
    write_json(os.path.join(d, 'brief.json'), brief)
    return d


def transcribe(project, inputs):
    lang = get_state(project).get('language', 'en')
    set_state(project, 'transcribing', 'Listening to the talk', inputs=inputs)
    terms = (brand_kit() or {}).get('terms', '')
    p = subprocess.Popen([sys.executable, os.path.join(HERE, 'ingest.py'), project, *inputs, '--language', lang,
                          *(['--terms', terms] if terms else [])], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, encoding='utf-8', errors='replace')
    last = ''
    for line in p.stdout:
        last = line.strip() or last
        m = re.match(r'c(\d+) transcribing', line)
        if m:
            total = len(read_json(os.path.join(project, 'sources.json'), {})) or '?'
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
.wrap{max-width:660px;margin:0 auto;padding:0 24px 140px;position:relative}
.back{position:absolute;left:24px;top:24px;color:var(--mute);font-size:14px;padding:4px 0}.back:hover{color:var(--ink)}
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
.bar{position:sticky;top:0;background:var(--bg);padding:14px 0 12px;margin:-14px 0 22px;z-index:3;display:flex;align-items:baseline;gap:16px;border-bottom:1px solid var(--line)}
.bar strong{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}.bar strong.over{color:var(--warn)}.bar button{color:var(--mute);font-size:14px}
.bar span{flex:1;color:var(--mute);font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.clip{font-size:12px;color:var(--mute);letter-spacing:.06em;text-transform:uppercase;margin:34px 0 14px;display:flex;align-items:center;gap:12px}.clip:after{content:"";flex:1;height:1px;background:var(--line)}
.para{display:grid;grid-template-columns:44px 1fr;gap:6px;margin-bottom:14px;line-height:1.85}.para time{font-size:12px;color:var(--mute);padding-top:6px;font-variant-numeric:tabular-nums}
.ch{cursor:pointer;border-radius:5px;padding:3px 2px;transition:background .12s}.editing .ch{cursor:text;box-shadow:inset 0 -1px 0 var(--line)}.ch[contenteditable=plaintext-only]{outline:0;background:var(--soft);box-shadow:inset 0 -2px 0 var(--ink)}.ch:hover{background:var(--soft)}.ch.on{background:var(--hl);color:var(--hlink)}
.row{display:flex;align-items:center;gap:14px;padding:16px 2px;border-bottom:1px solid var(--line);cursor:pointer}
.row.top{align-items:flex-start;padding:20px 2px}.row.top .rad{margin-top:4px}
.row .rad{width:20px;height:20px;border-radius:50%;box-shadow:inset 0 0 0 1.5px var(--line);flex:none;transition:.15s}.row.on .rad{box-shadow:inset 0 0 0 6px var(--ink)}
.row .t{flex:1}.row .play{width:38px;height:38px;border-radius:50%;box-shadow:inset 0 0 0 1px var(--line);font-size:12px;flex:none}
.row .t div{display:flex;justify-content:space-between;gap:16px;color:var(--mute);font-size:15px;margin-top:6px}.row .t div span:last-child{font-variant-numeric:tabular-nums}
.wait{min-height:52vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:26px;color:var(--mute);text-align:center}
.wait:before{content:"";width:150px;height:2px;border-radius:2px;background:linear-gradient(90deg,var(--line) 0 40%,var(--ink) 40% 60%,var(--line) 60%);background-size:250% 100%;animation:sl 1.5s linear infinite}
@keyframes sl{from{background-position:100% 0}to{background-position:-50% 0}}
video{display:block;width:100%;max-width:300px;margin:0 auto 26px;border-radius:16px;background:#000;aspect-ratio:9/16}
.pick{justify-content:center;margin-bottom:22px}
.path{font-size:13px;color:var(--mute);word-break:break-all;margin-top:10px}
</style></head><body><div class="wrap"><button class="back" id="back" hidden>Back</button><div class="dots" id="dots"></div><div id="app"></div></div>
<script>
const app=document.getElementById('app'),dots=document.getElementById('dots');let cur=null,rev=-1,idx=-1;
const STEP={upload:0,lowres:0,transcribing:0,suggesting:0,brief:1,planning:1,plan:2,highlight:2,music:3,editing:4,review:4,done:4,error:0};
const WAIT={transcribing:1,suggesting:1,planning:1,editing:1};const BACK={lowres:1,plan:1,highlight:1,music:1,review:1};
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
const data=async()=>(await fetch('/data',{cache:'no-store'})).json();
const go=(label,fn,alt)=>{let g=document.querySelector('.go');if(!g){g=el('div','go');app.append(g)}const b=el('button','btn'+(alt?' alt':''),label);b.onclick=()=>fn(b);g.append(b);return b};
const mb=n=>n>1e9?(n/1e9).toFixed(1)+' GB':Math.max(1,Math.round(n/1e6))+' MB';
const fmt=t=>Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');
const back=document.getElementById('back');back.onclick=()=>{back.hidden=true;document.querySelectorAll('audio,video').forEach(m=>m.pause());window.dispatchEvent(new Event('leave'));post('/back')};
function setDots(i){dots.innerHTML='';for(let k=0;k<5;k++)dots.append(el('i',k<=i?'on':''))}

const V={
 async upload(){const D=await data();const files=[];let lang=D.language||'en';app.append(el('h1','','Add your videos'));
  const d=el('div','drop','Drop videos here'),inp=el('input');inp.type='file';inp.multiple=true;inp.accept='video/*';inp.hidden=true;
  const list=el('div','files');app.append(d,inp,list);
  for(const f of D.files){const r=el('div','file');r.append(el('span','',f.name),el('span','',mb(f.size)));list.append(r)}
  app.append(el('div','lab','Language'));const lg=el('div','chips');app.append(lg);
  for(const [k,t] of [['en','English'],['zh','中文'],['mixed','English + 中文']]){const c=el('button','chip'+(k===lang?' on':''),t);c.onclick=()=>{lang=k;[...lg.children].forEach(x=>x.classList.toggle('on',x===c))};lg.append(c)}
  const add=fs=>{for(const f of fs)if(/\.(mp4|mov|m4v|mkv|avi)$/i.test(f.name)&&!files.some(x=>x.name===f.name)){files.push(f);const r=el('div','file');r.append(el('span','',f.name),el('span','',mb(f.size)),el('b'));f.row=r;list.append(r)}b.disabled=!(files.length||D.files.length)};
  d.onclick=()=>inp.click();inp.onchange=()=>add(inp.files);
  d.ondragover=e=>{e.preventDefault();d.classList.add('over')};d.ondragleave=()=>d.classList.remove('over');
  d.ondrop=e=>{e.preventDefault();d.classList.remove('over');add(e.dataTransfer.files)};
  const b=go('Continue',async()=>{b.disabled=true;d.style.pointerEvents='none';
   for(const f of files)await new Promise((ok,no)=>{const x=new XMLHttpRequest();x.open('PUT','/upload?name='+encodeURIComponent(f.name));
    x.upload.onprogress=e=>{f.row.lastChild.style.width=(100*e.loaded/e.total)+'%'};x.onload=()=>x.status===200?ok():no();x.onerror=no;x.send(f)});
   await post('/start',{language:lang})});b.disabled=!D.files.length},

 async lowres(){const D=await data();app.append(el('h1','','Low resolution'));
  for(const f of D.low){const r=el('div','file');r.append(el('span','',f.name),el('span','',f.size));app.append(r)}
  go('Continue anyway',async b=>{b.disabled=true;await post('/start',{force:true})})},

 async brief(){const D=await data();let aud=D.brief.audience||'',goal=D.brief.goal||'',len=D.brief.length_seconds||45;
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
  app.append(el('div','lab','Speaker'));const nm=el('input'),ti=el('input');nm.type=ti.type='text';nm.placeholder='Name';ti.placeholder='Title';
  nm.value=D.brief.speaker_name||'';ti.value=D.brief.speaker_title||'';nm.style.marginTop='0';app.append(nm,ti);
  app.append(el('div','lab','Branding'));const br=el('div','chips'),parts=el('div','chips'),kitBox=el('div');parts.style.marginTop='12px';app.append(br,parts,kitBox);
  let kit=D.kit,use=new Set(D.brief.brand||[]),on=use.size>0;
  const drawBrand=()=>{br.innerHTML='';parts.innerHTML='';
   const none=el('button','chip'+(on?'':' on'),'None');none.onclick=()=>{on=false;kitBox.innerHTML='';drawBrand()};br.append(none);
   const yes=el('button','chip'+(on?' on':''),kit&&kit.name?kit.name:'Add a brand');
   yes.onclick=()=>{on=true;if(!use.size)use=new Set(['logo','handle','color']);if(!(kit&&kit.name))editKit();drawBrand()};br.append(yes);
   if(on){for(const [k,t] of [['logo','Logo on the end card'],['handle','Account name on the end card'],['color','Brand colour']]){
     const c=el('button','chip'+(use.has(k)?' on':''),t);c.onclick=()=>{use.has(k)?use.delete(k):use.add(k);c.classList.toggle('on')};parts.append(c)}
    const e=el('button','','Edit');e.style.cssText='color:var(--mute);font-size:14px;padding:0 6px';e.onclick=editKit;parts.append(e)}};
  const editKit=()=>{kitBox.innerHTML='';const n=el('input'),h=el('input'),c=el('input'),f=el('input'),lr=el('div','row'),sv=el('button','chip','Save');
   n.type=h.type=c.type='text';n.placeholder='Brand name';h.placeholder='@account';c.placeholder='#D4AF37';f.type='file';f.accept='image/png,image/*';f.hidden=true;
   n.value=(kit&&kit.name)||'';h.value=(kit&&kit.handle)||'';c.value=(kit&&kit.color)||'';
   lr.append(el('span','t',kit&&kit.logo?'Replace the logo':'Add a logo (PNG, light version for dark backgrounds)'));lr.onclick=()=>f.click();
   f.onchange=async()=>{if(!f.files[0])return;lr.firstChild.textContent='Uploading…';await fetch('/brand-logo?name=logo.png',{method:'PUT',body:f.files[0]});kit=Object.assign(kit||{},{logo:true});lr.firstChild.textContent='Logo saved'};
   sv.style.marginTop='16px';sv.onclick=async()=>{await post('/brand-kit',{name:n.value.trim(),handle:h.value.trim(),color:c.value.trim()});
    kit=Object.assign(kit||{},{name:n.value.trim(),handle:h.value.trim(),color:c.value.trim()});kitBox.innerHTML='';drawBrand()};
   kitBox.append(n,h,c,lr,f,sv)};
  drawBrand();
  const b=go('Continue',async()=>{b.disabled=true;await post('/brief',{audience:aud,goal,length_seconds:len,speaker_name:nm.value.trim(),speaker_title:ti.value.trim(),brand:on&&kit&&kit.name?[...use]:[]})});
  if(aud)pick(chips,aud,v=>aud=v);if(goal)pick(goals,goal,v=>goal=v);ok()},

 async plan(){const D=await data();let id=D.option||D.options[0].id;app.append(el('h1','','How should we cut it?'));const rows=[];
  for(const o of D.options){const r=el('div','row top'+(o.id===id?' on':'')),t=el('div','t');t.append(el('span','',o.title));
   for(const v of o.videos){const l=el('div');l.append(el('span','',v.title),el('span','',v.seconds+'s'));t.append(l)}
   r.append(el('span','rad'),t);r.onclick=()=>{rows.forEach(x=>x.classList.remove('on'));r.classList.add('on');id=o.id};rows.push(r);app.append(r)}
  const b=go('Continue',async()=>{b.disabled=true;await post('/plan',{id})})},

 async highlight(){const D=await data();const on=new Set(D.selected),els=[];let last=null;
  app.append(el('h1','','Pick the lines'));const bar=el('div','bar'),n=el('strong'),nm=el('span','',D.n>1?(D.index+1)+' / '+D.n+'   '+D.title:''),ed=el('button','','Edit text'),rs=el('button','','Reset');bar.append(n,nm,ed,rs);app.append(bar);let editing=false;
  ed.onclick=()=>{editing=!editing;ed.textContent=editing?'Done editing':'Edit text';ed.style.color=editing?'var(--ink)':'';app.classList.toggle('editing',editing)};
  const multi=D.clips.length>1;
  D.clips.forEach((c,ci)=>{if(multi)app.append(el('div','clip','Clip '+(ci+1)));let p=null;
   for(const ch of c.chunks){if(ch.para||!p){p=el('div','para');p.append(el('time','',fmt(ch.start)),el('div'));app.append(p)}
    const e=el('span','ch',ch.text);e.dataset.key=c.id+':'+ch.k;e.dataset.d=ch.end-ch.start;e.dataset.i=els.length;if(on.has(e.dataset.key))e.classList.add('on');els.push(e);p.lastChild.append(e,' ')}});
  const draw=()=>{let s=0;for(const e of els)if(e.classList.contains('on'))s+=+e.dataset.d;n.textContent=Math.round(s)+'s / '+D.budget+'s';n.classList.toggle('over',s>D.budget)};
  app.onclick=ev=>{const e=ev.target.closest('.ch');if(!e)return;const i=+e.dataset.i;
   if(editing){if(e.isContentEditable)return;const before=e.textContent;e.contentEditable='plaintext-only';e.focus();
    e.onkeydown=k=>{if(k.key==='Enter'){k.preventDefault();e.blur()}if(k.key==='Escape'){e.textContent=before;e.blur()}};
    e.onblur=async()=>{e.contentEditable='false';const t=e.textContent.trim();if(t===before)return;
     try{const r=await (await post('/edit',{key:e.dataset.key,text:t})).json();e.textContent=r.text||before}catch(x){e.textContent=before}};return}
   if(ev.shiftKey&&last!==null){for(let k=Math.min(i,last);k<=Math.max(i,last);k++)els[k].classList.add('on')}else e.classList.toggle('on');last=i;draw()};
  rs.onclick=()=>{const rec=new Set(D.recommended);els.forEach(e=>e.classList.toggle('on',rec.has(e.dataset.key)));draw()};
  const b=go('Continue',async()=>{b.disabled=true;await post('/marks',{keys:els.filter(e=>e.classList.contains('on')).map(e=>e.dataset.key)})});draw();
  const first=els.find(e=>e.classList.contains('on'));if(first&&first.getBoundingClientRect().top>innerHeight*.7)first.scrollIntoView({block:'center'})},

 async music(){const D=await data();let choice=D.choice||{type:D.tracks.length?'track':'none',id:(D.tracks[0]||{}).id};const au=new Audio();let playing=null;
  window.addEventListener('leave',()=>au.pause(),{once:true});
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
  const b=go('Make the video'+(D.n>1?'s':''),async()=>{b.disabled=true;au.pause();await post('/music',choice)})},

 async review(){const D=await data();let i=0;const v=el('video');v.controls=true;v.playsInline=true;
  if(D.titles.length>1){const pk=el('div','chips pick');D.titles.forEach((t,k)=>{const c=el('button','chip'+(k?'':' on'),String(k+1));c.title=t;
    c.onclick=()=>{i=k;[...pk.children].forEach((x,j)=>x.classList.toggle('on',j===k));v.src='/video?i='+k+'&v='+D.rev;t2.placeholder='What should change in “'+t+'”?'};pk.append(c)});app.append(pk)}
  v.src='/video?i=0&v='+D.rev;app.append(v);
  const t2=el('textarea');t2.rows=2;t2.placeholder=D.titles.length>1?'What should change in “'+D.titles[0]+'”?':'What should change?';app.append(t2);
  const send=go('Send changes',async()=>{send.disabled=true;await post('/notes',{text:t2.value.trim(),index:i})},true);send.disabled=true;
  t2.oninput=()=>{send.disabled=!t2.value.trim();t2.style.height='auto';t2.style.height=t2.scrollHeight+'px'};
  go('Done',async b=>{b.disabled=true;await post('/done')})},

 async done(){const D=await data();app.append(el('h1','','Done'));for(const p of D.videos)app.append(el('div','path',p))},
 error(s){app.append(el('h1','','Something went wrong'),el('div','path',s.msg))}
};
async function tick(){try{const s=await (await fetch('/state',{cache:'no-store'})).json();
  if(s.stage!==cur||(s.stage==='highlight'&&s.index!==idx)||(s.stage==='review'&&s.rev!==rev)){cur=s.stage;rev=s.rev;idx=s.index;app.innerHTML='';app.onclick=null;app.className='';setDots(STEP[cur]??0);back.hidden=!BACK[cur];window.scrollTo(0,0);
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
    lang = args[args.index('--language') + 1] if '--language' in args else None
    if not os.path.exists(os.path.join(project, 'state.json')):
        set_state(project, 'upload', preset=clips, language=lang or 'en')    # the page still asks language and confirms
    elif get_state(project)['stage'] == 'transcribing':        # interrupted run: pick the transcription up again
        again = get_state(project).get('inputs') or clips or [os.path.join(project, 'clips')]
        threading.Thread(target=transcribe, args=(project, again), daemon=True).start()

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
            u = urllib.parse.urlparse(self.path)
            path, q = u.path, urllib.parse.parse_qs(u.query)
            st = get_state(project)
            if path == '/':
                body = PAGE.encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control', 'no-store'); self.end_headers()
                self.wfile.write(body)
            elif path == '/state':
                self.send_json({k: st.get(k) for k in ('stage', 'msg', 'rev', 'index')})
            elif path == '/data':
                brief = read_json(os.path.join(project, 'brief.json'), {})
                vs = videos(project)
                if st['stage'] == 'upload':
                    self.send_json({'language': st.get('language', 'en'), 'files': [
                        {'name': os.path.basename(f), 'size': os.path.getsize(f)} for f in expand(st.get('preset', []))]})
                elif st['stage'] == 'lowres':
                    self.send_json({'low': st.get('low', [])})
                elif st['stage'] == 'brief':
                    kit = brand_kit()
                    self.send_json({'audiences': read_json(os.path.join(project, 'suggest.json'), {}).get('audiences', []), 'brief': brief,
                                    'kit': kit and {'name': kit.get('name', ''), 'handle': kit.get('handle', ''), 'color': kit.get('color', ''),
                                                    'logo': bool(kit.get('logo') and os.path.exists(kit['logo']))}})
                elif st['stage'] == 'plan':
                    _, index = chunk_index(project)
                    opts = []
                    for o in read_json(os.path.join(project, 'plan.json'), {}).get('options', []):
                        opts.append({'id': o['id'], 'title': o.get('title', ''), 'videos': [
                            {'title': v.get('title', ''), 'seconds': round(sum(index[k][1]['end'] - index[k][1]['start'] for k in v.get('keys', []) if k in index))}
                            for v in o.get('videos', [])]})
                    self.send_json({'options': opts, 'option': st.get('option')})
                elif st['stage'] == 'highlight':
                    clips_, _ = chunk_index(project)
                    i = min(st.get('index', 0), max(0, len(vs) - 1))
                    marks = read_json(os.path.join(vdir(project, i), 'marks.json'))
                    rec = vs[i]['keys'] if vs else []
                    sel = [f"{m['clip']}:{m['k']}" for m in marks['marks']] if marks else rec
                    self.send_json({'clips': clips_, 'selected': sel, 'recommended': rec, 'budget': int(brief.get('length_seconds', 60)),
                                    'index': i, 'n': len(vs), 'title': vs[i]['title'] if vs else ''})
                elif st['stage'] == 'music':
                    self.send_json({'tracks': tracks(), 'choice': read_json(os.path.join(project, 'music.json')), 'n': len(vs)})
                else:
                    self.send_json({'rev': st.get('rev'), 'videos': st.get('videos', []),
                                    'titles': [v['title'] for v in vs][:len(st.get('videos', []))] or ['']})
            elif path.startswith('/track/'):
                tid = re.sub(r'[^\w\-]', '', path[7:])
                self.send_file(os.path.join(MUSIC_DIR, tid + '.mp3'), 'audio/mpeg')
            elif path == '/brand-logo':
                kit = brand_kit() or {}
                self.send_file(kit.get('logo'), 'image/png')
            elif path == '/video':
                vids = st.get('videos', [])
                i = int(q.get('i', ['0'])[0])
                self.send_file(vids[i] if 0 <= i < len(vids) else None, 'video/mp4')
            else:
                self.send_json({'error': 'not found'}, 404)

        def do_PUT(self):
            path = urllib.parse.urlparse(self.path).path
            if path == '/upload':
                self.save_stream(os.path.join(project, 'clips'))
                self.send_json({'ok': True})
            elif path == '/brand-logo':
                os.makedirs(BRAND_DIR, exist_ok=True)
                p, name = self.save_stream(BRAND_DIR)
                kit = brand_kit() or {}
                kit['logo'] = p.replace('\\', '/')
                write_json(os.path.join(BRAND_DIR, 'brand.json'), kit)
                self.send_json({'ok': True})
            elif path == '/music-upload':
                p, name = self.save_stream(os.path.join(project, 'music'))
                write_json(os.path.join(project, 'music.json'), {'type': 'own', 'name': name, 'file': p.replace('\\', '/')})
                self.send_json({'ok': True})
            else:
                self.send_json({'error': 'not found'}, 404)

        def do_POST(self):
            path, req = urllib.parse.urlparse(self.path).path, self.body_json()
            st = get_state(project)
            if path == '/start':
                inputs = list(st.get('preset', [])) + ([os.path.join(project, 'clips')] if os.path.isdir(os.path.join(project, 'clips')) else [])
                lang = req.get('language') or st.get('language', 'en')
                low = []
                if not req.get('force'):                         # below 1080p on the short side: ask before spending the time
                    for f in expand(inputs):
                        w, h = resolution(f)
                        if 0 < min(w, h) < 1080:
                            low.append({'name': os.path.basename(f), 'size': f'{w}×{h}'})
                if low:
                    set_state(project, 'lowres', language=lang, low=low)
                else:
                    set_state(project, 'transcribing', 'Listening to the talk', language=lang)
                    threading.Thread(target=transcribe, args=(project, inputs), daemon=True).start()
            elif path == '/edit':
                _, index = chunk_index(project)
                key, text = str(req.get('key', '')), ' '.join(str(req.get('text', '')).split())
                if key in index:
                    ed = W.edits(project)
                    if text:
                        ed[key] = text
                    else:
                        ed.pop(key, None)                        # emptied: back to the transcript's wording
                    write_json(os.path.join(project, 'edits.json'), ed)
                    set_state(project, st['stage'], st.get('msg', ''), dirty=True)
                    _, index = chunk_index(project)
                    return self.send_json({'ok': True, 'text': index[key][1]['text']})
            elif path == '/brand-kit':
                os.makedirs(BRAND_DIR, exist_ok=True)
                kit = brand_kit() or {}
                color = str(req.get('color', '')).strip()
                kit.update({'name': str(req.get('name', '')).strip()[:60], 'handle': str(req.get('handle', '')).strip()[:60],
                            'color': color if re.fullmatch(r'#[0-9a-fA-F]{6}', color) else kit.get('color', '')})
                write_json(os.path.join(BRAND_DIR, 'brand.json'), kit)
            elif path == '/brief':
                brief = read_json(os.path.join(project, 'brief.json'), {})
                old = dict(brief)
                brief.update({'audience': str(req.get('audience', '')).strip(), 'goal': str(req.get('goal', '')),
                              'length_seconds': max(15, min(60, int(req.get('length_seconds', 45)))),
                              'speaker_name': str(req.get('speaker_name', '')).strip()[:60],
                              'speaker_title': str(req.get('speaker_title', '')).strip()[:80],
                              'brand': [x for x in req.get('brand', []) if x in ('logo', 'handle', 'color')]})
                brief['brand_kit'] = (brand_kit() or {}) if brief['brand'] else {}
                write_json(os.path.join(project, 'brief.json'), brief)
                core = lambda x: [x.get(k) for k in ('audience', 'goal', 'length_seconds')]   # noqa: E731
                plan = read_json(os.path.join(project, 'plan.json'), {}).get('options', [])
                if core(brief) == core(old) and plan:            # came back without changing what the plan depends on
                    if len(plan) > 1:
                        set_state(project, 'plan', dirty=st.get('dirty', True) or brief != old)
                    else:
                        choose_option(project)
                        if brief != old:
                            set_state(project, 'highlight', dirty=True)
                else:                                            # new brief: plan and recommend again
                    for stale in ['plan.json', 'videos.json'] + glob.glob(os.path.join(project, 'v[0-9]*', 'marks.json')):
                        p = stale if os.path.isabs(stale) else os.path.join(project, stale)
                        if os.path.exists(p):
                            os.remove(p)
                    set_state(project, 'planning', 'Planning the cut', option=None)
            elif path == '/plan':
                choose_option(project, req.get('id'))
            elif path == '/marks':
                _, index = chunk_index(project)
                vs = videos(project)
                i = min(st.get('index', 0), max(0, len(vs) - 1))
                marks = []
                for key in req.get('keys', []):
                    if key in index:
                        cid, c = index[key]
                        marks.append({'clip': cid, **{k: c[k] for k in ('k', 'w0', 'w1', 'start', 'end', 'text')}})
                d = prep_video(project, i, vs[i]['title'] if vs else '')
                old = read_json(os.path.join(d, 'marks.json'))
                same = bool(old) and [(m['clip'], m['k']) for m in old['marks']] == [(m['clip'], m['k']) for m in marks]
                changed = not same or (old or {}).get('changed', True)      # stays set until this video is rendered again
                write_json(os.path.join(d, 'marks.json'), {'saved': datetime.datetime.now().isoformat(timespec='seconds'),
                                                           'note': '', 'changed': changed, 'marks': marks})
                dirty = st.get('dirty', True) or not same
                if i + 1 < len(vs):
                    set_state(project, 'highlight', index=i + 1, dirty=dirty)
                else:
                    set_state(project, 'music', dirty=dirty)
            elif path == '/music':
                if req.get('type') == 'own':
                    saved = read_json(os.path.join(project, 'music.json'), {})
                    req = saved if saved.get('type') == 'own' else {'type': 'none'}
                elif req.get('type') == 'track':
                    req = {'type': 'track', 'id': req.get('id'), 'file': os.path.join(MUSIC_DIR, f"{req.get('id')}.mp3").replace('\\', '/')}
                else:
                    req = {'type': 'none'}
                write_json(os.path.join(project, 'music.json'), req)
                for i in range(len(videos(project))):
                    if os.path.isdir(vdir(project, i)):
                        write_json(os.path.join(vdir(project, i), 'music.json'), req)
                set_state(project, 'editing', 'Editing', reason='lines' if st.get('dirty', True) else 'music')
            elif path == '/notes':
                notes = read_json(os.path.join(project, 'notes.json'), [])
                notes.append({'time': datetime.datetime.now().isoformat(timespec='seconds'), 'video': int(req.get('index', 0)) + 1,
                              'text': str(req.get('text', '')).strip(), 'handled': False})
                write_json(os.path.join(project, 'notes.json'), notes)
                set_state(project, 'editing', 'Editing', reason='notes')
            elif path == '/back':
                stage, n = st['stage'], len(videos(project))
                many = len(read_json(os.path.join(project, 'plan.json'), {}).get('options', [])) > 1
                if stage == 'lowres':
                    set_state(project, 'upload')
                elif stage == 'plan':
                    set_state(project, 'brief')
                elif stage == 'highlight':
                    if st.get('index', 0) > 0:
                        set_state(project, 'highlight', index=st['index'] - 1)
                    else:
                        set_state(project, 'plan' if many else 'brief')
                elif stage == 'music':
                    set_state(project, 'highlight', index=max(0, n - 1))
                elif stage == 'review':
                    set_state(project, 'music')
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
