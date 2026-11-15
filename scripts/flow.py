#!/usr/bin/env python3
"""The editor's side of the web flow (see app.py for the stages).

  PY flow.py wait <project> <stage> [<stage> ...]   block until the page reaches one of these stages; prints STAGE <name>
  PY flow.py set <project> <stage> [message] [--video <path>]   move the page on
  PY flow.py transcript <project>                   every phrase with its key, start time and length (for recommend.json)
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
                print(f"STAGE {st['stage']}{why}", flush=True)
                return
            time.sleep(1)
        sys.exit('TIMEOUT: the person did not finish this step. Ask them, then wait again.')
    elif cmd == 'set':
        extra = {}
        if '--video' in rest:
            i = rest.index('--video')
            extra['video'] = os.path.abspath(rest[i + 1]).replace('\\', '/')
            del rest[i:i + 2]
        if rest[0] == 'review':
            extra['dirty'] = False                 # the render on screen matches the saved lines
        st = A.set_state(project, rest[0], rest[1] if len(rest) > 1 else '', **extra)
        print(f"STAGE {st['stage']}", flush=True)
    elif cmd == 'transcript':
        src, words = W.load(project)
        brief = A.read_json(os.path.join(project, 'brief.json'), {})
        if brief:
            print('BRIEF', json.dumps(brief, ensure_ascii=False))
        for cid in src:
            print(f'\n== {cid}  {os.path.basename(src[cid])}')
            for c in W.chunks(words.get(cid, [])):
                print(f"{cid}:{c['k']:<4} {c['start']:7.2f}  {c['end'] - c['start']:4.1f}s  {c['text']}")
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
