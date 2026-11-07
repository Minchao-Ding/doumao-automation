"""Conservative detection of four-column, one- or two-row gallery views.

Unlike the v3.5 full-grid detector, this uses shorter card edges, and selects
actual card-height row boundaries rather than subdividing artwork into rows.
It is a fallback for the existing three-row detector, never a replacement.
"""
from __future__ import annotations

from itertools import combinations

import cv2
import numpy as np

from .grid_detector import GridDetectionError


def _clusters(lines, tolerance):
    groups = []
    for line in sorted(lines, key=lambda item: item[0]):
        if groups and abs(line[0] - np.median([v[0] for v in groups[-1]])) <= tolerance:
            groups[-1].append(line)
        else:
            groups.append([line])
    return [dict(coordinate=int(round(np.median([v[0] for v in group]))),
                 support=max(v[3] for v in group),
                 start=min(v[1] for v in group), end=max(v[2] for v in group))
            for group in groups]


def _choose(lines, count, min_step, max_step, max_cv, first_min, last_max, first_max=None):
    # Cap combinatorial search, as in the existing full-grid detector.
    if len(lines) > 22:
        lines = sorted(sorted(lines, key=lambda v: v['support'], reverse=True)[:22],
                       key=lambda v: v['coordinate'])
    best, selected = -float('inf'), None
    for group in combinations(lines, count):
        coords = [e['coordinate'] for e in group]
        steps = np.diff(coords)
        if (coords[0] < first_min or coords[-1] > last_max or
                (first_max is not None and coords[0] > first_max) or
                np.min(steps) < min_step or np.max(steps) > max_step):
            continue
        cv = float(np.std(steps) / np.mean(steps))
        if cv > max_cv:
            continue
        supports = [e['support'] for e in group]
        score = -cv * 10 + .8 * sum(supports) / (len(supports) * max(supports))
        if score > best:
            best, selected = score, coords
    return selected




def _align_visible_boundaries(edges, xs, ys, pitch):
    """Align candidate Hough rows with long, panel-spanning card boundaries.

    Shorter decorative/artwork lines sometimes move a Hough estimate by about
    10-20 source pixels between identical screenshots. Real card separators
    cross most of the four-column panel. If not uniquely supported, stop.
    """
    x0 = round(xs[0] + pitch * .08)
    x1 = round(xs[-1] - pitch * .08)
    width = x1 - x0
    radius = min(27, max(15, round(pitch * .065)))
    aligned = []
    for estimate in ys:
        lo = max(0, estimate - radius)
        hi = min(edges.shape[0], estimate + radius + 1)
        strength = np.count_nonzero(edges[lo:hi, x0:x1], axis=1)
        supported = np.flatnonzero(strength >= width * .60) + lo
        # Each physical Canny boundary can produce two neighboring edge lines.
        # An excessive number of candidates is ambiguous, not a reason to guess.
        if not 1 <= len(supported) <= 8:
            raise GridDetectionError('卡片横向边界不稳定，不推测点击位置')
        aligned.append(int(round(float(np.median(supported)))))
    if len(aligned) != len(set(aligned)) or any(
            not pitch * .90 < b - a < pitch * 1.40
            for a, b in zip(aligned, aligned[1:])):
        raise GridDetectionError('卡片行高与列宽不匹配，不推测点击位置')
    return aligned

def detect_partial_grid(frame: np.ndarray) -> list[dict]:
    """Find precisely 4 or 8 complete cards; reject ambiguous layouts.

    Layout evidence currently supports top-aligned search/filter results only.
    Partial final rows and arbitrary scroll offsets are not inferred. The
    normal three-row path remains owned by ``detect_visible_grid``.
    """
    if (not isinstance(frame, np.ndarray) or frame.ndim != 3 or
            frame.shape[2] != 3 or frame.dtype != np.uint8):
        raise GridDetectionError('截图格式异常')
    height, width = frame.shape[:2]
    if width < 900 or height < 700:
        raise GridDetectionError('屏幕分辨率不足以确认部分行网格')

    edges = cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 8, 30)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=max(55, round(min(width, height) * .035)),
        minLineLength=max(210, round(height * .12)),
        maxLineGap=max(12, round(height * .03)))
    if lines is None:
        raise GridDetectionError('无法识别候选卡片边界')
    vertical, horizontal = [], []
    for x0, y0, x1, y1 in np.asarray(lines).reshape(-1, 4):
        x0, y0, x1, y1 = map(int, (x0, y0, x1, y1))
        if abs(x1-x0) <= 3 and abs(y1-y0) >= .18 * height:
            vertical.append((round((x0+x1)/2), min(y0,y1), max(y0,y1), abs(y1-y0)))
        elif abs(y1-y0) <= 3 and abs(x1-x0) >= .30 * width:
            horizontal.append((round((y0+y1)/2), min(x0,x1), max(x0,x1), abs(x1-x0)))

    columns = _clusters(vertical, max(9, round(width*.012)))
    xs = _choose(columns, 5, round(width*.09), round(width*.20), .055, 0, width-3)
    if xs is None:
        raise GridDetectionError('无法确认部分行网格的五条等距列边界')
    pitch = float(np.median(np.diff(xs)))
    if xs[-1] - xs[0] < width*.43:
        raise GridDetectionError('候选列区域过窄')
    rows = _clusters(horizontal, max(8, round(height*.010)))
    usable = [e for e in rows if
              e['start'] <= xs[0]+pitch*.15 and
              e['end'] >= xs[-1]-pitch*.15 and
              e['support'] >= (xs[-1]-xs[0])*.75]

    # Find two complete rows before one: a one-row subset of an actual two-row
    # gallery must never silently omit its second row. Candidate row heights
    # must resemble the detected card width, not half-card artwork seams.
    for nrows in (2, 1):
        ys = _choose(usable, nrows+1,
                     round(pitch*.98), round(pitch*1.28), .06,
                     round(height*.33), round(height*.96), round(height*.46))
        if ys is None:
            continue
        ys = _align_visible_boundaries(edges, xs, ys, pitch)
        cards = []
        for row in range(nrows):
            top, bottom = ys[row], ys[row+1]
            dy = bottom-top
            for col in range(4):
                left, right = xs[col], xs[col+1]
                dx = right-left
                cx, cy = round(left+dx*.51), round(top+dy*.43)
                x0, x1 = round(left+dx*.17), round(right-dx*.17)
                y0, y1 = round(top+dy*.12), round(top+dy*.73)
                if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                    raise GridDetectionError('候选图纸坐标超出截图范围')
                crop = frame[y0:y1,x0:x1]
                grayscale = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                contrast = float(np.std(grayscale))
                a = grayscale.astype(np.float32)
                energy = (np.mean(abs(np.diff(a, axis=0))>12) +
                          np.mean(abs(np.diff(a, axis=1))>12))/2
                if contrast < 20 or energy < .04:
                    break
                fingerprint = cv2.resize(crop,(60,70),interpolation=cv2.INTER_AREA)
                cards.append({'col':col,'top':top,'click':(cx,cy),'fp':fingerprint})
            if len(cards) != (row+1)*4:
                break
        if len(cards) == nrows*4:
            return cards
        # Geometry implied this many rows. Never silently fall back to one row
        # when some of the second-row cards are unloaded, blocked or missing.
        raise GridDetectionError('候选网格存在空白或未加载的卡片；不降级为更少行')
    raise GridDetectionError('未确认完整的一排或两排图纸；不会猜测点击位置')
