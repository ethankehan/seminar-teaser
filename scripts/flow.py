#!/usr/bin/env python3
"""The editor's side of the web flow (see app.py for the stages).

  PY flow.py wait <project> <stage> [<stage> ...]   block until the page reaches one of these stages; prints STAGE <name>
  PY flow.py set <project> <stage> [message] [--video <path> ...]   move the page on (one --video per finished video)
  PY flow.py transcript <project>                   every phrase with its key, start time and length (for plan.json)
  PY flow.py videos <project>                       the videos to make: folder, title, highlighted seconds, changed?
Run `wait` in the background and act when it exits; never poll.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A  # noqa: E402
import words as W  # noqa: E402


def main():
    cmd, project = sys.argv[1], os.path.abspath(os.path.expanduser(sys.argv[2]))
    rest = sys.argv[3:]
    if cmd == 'wait':
        deadline = time.time() + 8 * 3600
        while time.time() < deadline:
            st = A.get_state(project)
            if st['stage'] in rest or st['stage'] == 'error':
                why = f" reason={st.get('reason', 'lines')}" if st['stage'] == 'editing' else ''
                msg = f" {st.get('msg', '')}" if st['stage'] == 'error' else ''
                print(f"STAGE {st['stage']}{why}{msg}", flush=True)
                return
            time.sleep(1)
        sys.exit('TIMEOUT: the person did not finish this step. Ask them, then wait again.')
    elif cmd == 'set':
        extra, vids = {}, []
        while '--video' in rest:
            i = rest.index('--video')
            vids.append(os.path.abspath(rest[i + 1]).replace('\\', '/'))
            del rest[i:i + 2]
        if vids:
            extra['videos'] = vids
        if rest[0] == 'plan':                      # one option only: nothing to choose, go straight to the lines
            opts = A.read_json(os.path.join(project, 'plan.json'), {}).get('options', [])
            if len(opts) <= 1:
                st = A.choose_option(project)
                print(f"STAGE {st['stage']}", flush=True)
                return
        if rest[0] == 'review':
            extra['dirty'] = False                 # the renders on screen match the saved lines
            for i in range(len(A.videos(project))):
                mp = os.path.join(A.vdir(project, i), 'marks.json')
                marks = A.read_json(mp)
                if marks:
                    marks['changed'] = False
                    A.write_json(mp, marks)
        st = A.set_state(project, rest[0], rest[1] if len(rest) > 1 else '', **extra)
        print(f"STAGE {st['stage']}", flush=True)
    elif cmd == 'transcript':
        src, words = W.load(project)
        brief = A.read_json(os.path.join(project, 'brief.json'), {})
        if brief:
            print('BRIEF', json.dumps(brief, ensure_ascii=False))
        total = 0
        for cid in src:
            print(f'\n== {cid}  {os.path.basename(src[cid])}')
            for c in W.chunks(words.get(cid, [])):
                total += c['end'] - c['start']
                print(f"{cid}:{c['k']:<4} {c['start']:7.2f}  {c['end'] - c['start']:4.1f}s  {c['text']}")
        print(f'\nTOTAL SPEECH {total:.0f}s in {len(src)} clips')
    elif cmd == 'videos':
        for i, v in enumerate(A.videos(project)):
            d = A.vdir(project, i)
            marks = A.read_json(os.path.join(d, 'marks.json'), {'marks': []})
            secs = sum(m['end'] - m['start'] for m in marks['marks'])
            print(f"{d}  |  {v['title']}  |  {secs:.0f}s highlighted  |  {'CHANGED' if marks.get('changed', True) else 'same lines as last time'}")
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
