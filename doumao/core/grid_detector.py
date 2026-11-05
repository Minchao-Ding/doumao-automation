"""Detect a 4-column visible artwork grid from *structure*, not UI colors.

The screenshot may include other desktop windows. Detect five aligned vertical
card-column boundaries and four horizontal row boundaries, then locate the
artwork within each geometrical cell. A guessed/missing cell is never emitted.
All coordinates refer to the original screenshot (not the Mac logical display).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

import cv2
import numpy as np


class GridDetectionError(RuntimeError):
    """Cannot prove a complete, unambiguous visible grid."""


@dataclass(frozen=True)
class _Line:
    axis: int
    lo: int
    hi: int
    span: int


def _extract_lines(frame: np.ndarray) -> tuple[list[_Line], list[_Line]]:
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 8, 30)
    hough = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=max(55, round(min(w, h) * .055)),
        minLineLength=max(120, round(min(w, h) * .21)),
        maxLineGap=max(12, round(min(w, h) * .032)),
    )
    vert: list[_Line] = []
    horiz: list[_Line] = []
    if hough is None:
        return vert, horiz
    # OpenCV may return (N, 1, 4) or (N, 4) depending on the build.
    for x0, y0, x1, y1 in np.asarray(hough).reshape(-1, 4):
        x0, y0, x1, y1 = (int(x0), int(y0), int(x1), int(y1))
        if abs(x1 - x0) <= 3 and abs(y1 - y0) >= .37 * h:
            vert.append(_Line(round((x0 + x1)/2), min(y0, y1), max(y0, y1), abs(y1 - y0)))
        elif abs(y1 - y0) <= 3 and abs(x1 - x0) >= .33 * w:
            horiz.append(_Line(round((y0 + y1)/2), min(x0, x1), max(x0, x1), abs(x1 - x0)))
    return vert, horiz


def _clusters(lines: Iterable[_Line], *, tolerance: int) -> list[dict]:
    """Combine parallel line segments from both sides of the same border."""
    groups: list[list[_Line]] = []
    for line in sorted(lines, key=lambda x: x.axis):
        if groups and abs(line.axis - np.median([e.axis for e in groups[-1]])) <= tolerance:
            groups[-1].append(line)
        else:
            groups.append([line])
    return [{
        'coordinate': int(round(np.median([e.axis for e in group]))),
        'support': max(e.span for e in group),
        'start': min(e.lo for e in group),
        'end': max(e.hi for e in group),
    } for group in groups]


def _choose_grid(lines: list[dict], count: int, *, minimum_step: int,
                 maximum_step: int, max_cv: float, first_min: int,
                 last_max: int) -> tuple[list[int], float] | None:
    selected = None
    best = -1e9
    # Real screens ordinarily have <20 high-support line clusters. Reject
    # overloaded detections instead of combinatorially guessing a grid.
    if len(lines) > 18:
        lines = sorted(lines, key=lambda e: e['support'], reverse=True)[:18]
        lines.sort(key=lambda e: e['coordinate'])
    for group in combinations(lines, count):
        coords = [v['coordinate'] for v in group]
        if coords[0] < first_min or coords[-1] > last_max:
            continue
        steps = np.diff(coords)
        if np.min(steps) < minimum_step or np.max(steps) > maximum_step:
            continue
        cv = float(np.std(steps) / np.mean(steps))
        if cv > max_cv:
            continue
        lengths = [e['support'] for e in group]
        # Prefer aligned, nearly equal intervals, and strong full-height/width
        # boundaries. Do not prefer larger screens or absolute origin.
        score = -cv * 10 + .8 * sum(lengths) / (len(lengths) * max(lengths))
        if score > best:
            best = score
            selected = coords
    return (selected, best) if selected is not None else None


def _activity(frame: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> float:
    sample = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    if sample.size == 0:
        return 0.0
    gy = np.abs(np.diff(sample.astype(np.float32), axis=0))
    gx = np.abs(np.diff(sample.astype(np.float32), axis=1))
    return float((np.mean(gx > 12) + np.mean(gy > 12)) / 2)


def detect_visible_grid(frame: np.ndarray, *, diagnostics: dict | None = None) -> list[dict]:
    """Return exactly twelve row-major cards only for a verified 4x3 grid.

    False completeness is more dangerous than a conservative stop. Rows or
    columns beyond the visible screenshot are not inferred. Partial/less-than-12
    views can be supported after a separate image-backed calibration.
    """
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        raise GridDetectionError('截图格式异常')
    h, w = frame.shape[:2]
    if w < 900 or h < 700:
        raise GridDetectionError('屏幕分辨率不足以校验四列网格')
    vertical, horizontal = _extract_lines(frame)
    vs = _clusters(vertical, tolerance=max(9, round(w * .012)))
    hs = _clusters(horizontal, tolerance=max(8, round(h * .010)))
    if diagnostics is not None:
        diagnostics.update(vertical_candidates=vs, horizontal_candidates=hs,
                           screenshot_shape=[h, w])
    xres = _choose_grid(vs, 5, minimum_step=round(w*.09),
                        maximum_step=round(w*.35), max_cv=.075,
                        first_min=0, last_max=w-3)
    if xres is None:
        raise GridDetectionError('无法确定四列卡片的五条等距垂直边界')
    xs, _ = xres
    # Horizontal lines must actually span most of the selected four columns.
    # This blocks unrelated browser/toolbars outside the artwork panel.
    usable_hs = [e for e in hs if e['start'] <= xs[1] - 10 and
                 e['end'] >= xs[3] + 10 and e['support'] >= (xs[-1]-xs[0])*.6]
    yres = _choose_grid(usable_hs, 4, minimum_step=round(h*.13),
                        maximum_step=round(h*.42), max_cv=.065,
                        first_min=round(h*.045), last_max=h-2)
    if yres is None:
        raise GridDetectionError('无法确定三行卡片的四条等距水平边界；请确认底行卡片标题完整可见')
    ys, _ = yres
    if diagnostics is not None:
        diagnostics.update(selected_columns=xs, selected_rows=ys)
    # Bounds must cover significant panel area, without spanning unrelated UI.
    if xs[-1] - xs[0] < w * .43 or ys[-1] - ys[0] < h*.5:
        raise GridDetectionError('候选网格范围异常')
    cards = []
    for row in range(3):
        top, bottom = ys[row], ys[row + 1]
        dy = bottom - top
        for col in range(4):
            left, right = xs[col], xs[col+1]
            dx = right - left
            cx = round(left + dx * .51)
            cy = round(top + dy * .43)
            # Interior artwork crop excludes gutters and caption area. It is
            # fixed for the entire batch and independent of text or theme.
            x0, x1 = round(left+dx*.17), round(right-dx*.17)
            y0, y1 = round(top+dy*.12), round(top+dy*.73)
            if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h and
                    0 < cx < w and 0 < cy < h):
                raise GridDetectionError('卡片点击/缩略图坐标超出屏幕')
            art = frame[y0:y1, x0:x1]
            contrast = float(np.std(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY)))
            energy = _activity(frame, x0, y0, x1, y1)
            if contrast < 12 or energy < .012:
                raise GridDetectionError(f'第 {row*4+col+1} 张卡片内容不足，可能为空白/遮挡/尚未加载')
            fp = cv2.resize(art, (60, 70), interpolation=cv2.INTER_AREA)
            cards.append({'col': col, 'top': top, 'click': (cx, cy), 'fp': fp})
    return cards
