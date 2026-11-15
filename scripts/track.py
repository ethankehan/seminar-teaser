"""Keep the speaker in frame: follow their face through a shot and return moving crop coordinates.

Only the speaker faces the camera when a talk is filmed from the seats (the audience shows the backs of their
heads), so a plain face detector finds them. The editor's framing stays untouched unless the speaker would leave
it: the crop moves only as far as needed to keep the face inside a safe zone, smoothed so it reads as a camera
operator following, not a jitter. Returns None (keep the fixed framing) when there is nothing to follow, the
speaker stays put, or OpenCV is not installed.
"""
import math


def path(src, a, d, w, h, cw, ch, x0, y0, step=0.4):
    """(x_expr, y_expr) for ffmpeg's crop, as functions of t (seconds from the start of the shot), or None."""
    try:
        import cv2
    except Exception:
        return None
    if w - cw < 8 and h - ch < 8:
        return None
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        return None
    front = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    side = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
    sc = 960 / max(w, h)
    ts = [i * step for i in range(int(d / step) + 1)]
    if d - ts[-1] > 0.15:
        ts.append(d)
    pts, prev = [], None
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, (a + t) * 1000)
        ok, fr = cap.read()
        if not ok:
            pts.append(None)
            continue
        if (fr.shape[1], fr.shape[0]) != (w, h):        # rotation not applied by this OpenCV build: do not guess
            cap.release()
            return None
        g = cv2.cvtColor(cv2.resize(fr, None, fx=sc, fy=sc), cv2.COLOR_BGR2GRAY)
        m = max(18, int(0.02 * 960))
        found = list(front.detectMultiScale(g, 1.1, 6, minSize=(m, m))) + list(side.detectMultiScale(g, 1.1, 6, minSize=(m, m)))
        cands = [((x + bw / 2) / sc, (y + bh / 2) / sc) for x, y, bw, bh in found]
        cands = [c for c in cands if y0 - 0.6 * ch <= c[1] <= y0 + 1.4 * ch]      # at stage height, not a face in the crowd
        ref, lim = ((x0 + cw / 2, y0 + ch * 0.4), 0.75 * cw) if prev is None else (prev, 0.22 * w)
        best = min(cands, key=lambda c: math.dist(c, ref)) if cands else None
        if best and math.dist(best, ref) <= lim:
            prev = best
            pts.append(best)
        else:
            pts.append(None)
    cap.release()
    if sum(p is not None for p in pts) < max(3, 0.35 * len(pts)):
        return None
    known = [i for i, p in enumerate(pts) if p is not None]            # fill gaps with the nearest sighting
    pts = [pts[min(known, key=lambda k: abs(k - i))] for i in range(len(pts))]

    def med3(v):
        return [sorted(v[max(0, i - 1):i + 2])[len(v[max(0, i - 1):i + 2]) // 2] for i in range(len(v))]

    fx, fy = med3([p[0] for p in pts]), med3([p[1] for p in pts])
    xs, ys = [], []
    for px, py in zip(fx, fy):                                         # move only when the face leaves the safe zone
        x = min(max(x0, px - cw * 0.78), px - cw * 0.22)
        y = min(max(y0, py - ch * 0.62), py - ch * 0.20)
        xs.append(min(max(0, x), w - cw))
        ys.append(min(max(0, y), h - ch))

    def smooth(v, k=2):
        return [sum(v[max(0, i - k):i + k + 1]) / len(v[max(0, i - k):i + k + 1]) for i in range(len(v))]

    xs, ys = smooth(xs), smooth(ys)
    if max(xs) - min(xs) < 0.02 * w and max(ys) - min(ys) < 0.02 * h and abs(xs[0] - x0) < 0.02 * w and abs(ys[0] - y0) < 0.02 * h:
        return None                                                    # the editor's fixed framing already holds

    def expr(v):
        e = f'{v[-1]:.1f}'
        for i in range(len(v) - 2, -1, -1):
            dt = ts[i + 1] - ts[i]
            e = f'if(lt(t,{ts[i + 1]:.3f}),{v[i]:.1f}+({v[i + 1] - v[i]:.2f})*(t-{ts[i]:.3f})/{dt:.3f},{e})'
        return e

    return expr(xs), expr(ys)
