"""Unified image-backed 4-column gallery layout recognition.

A card may be safely clickable when its caption is clipped. A partially shown
thumbnail is eligible only with sufficient visible artwork, observed structural
edges, a safe click target and stable identity. No GUI calls or private files.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import cv2
import numpy as np

from .grid_detector import GridDetectionError


class UnsafeGalleryLayout(GridDetectionError):
    """A structured grid is present but its cards cannot safely be verified.

    Callers must not fall back to a weaker scanner on this error, as it might
    silently return only a subset of a damaged row.
    """


@dataclass(frozen=True)
class _Segment:
    coordinate: int
    start: int
    end: int
    support: int


def _cluster(segments: list[_Segment], tolerance: int) -> list[_Segment]:
    groups: list[list[_Segment]] = []
    for segment in sorted(segments, key=lambda p: p.coordinate):
        if groups and abs(segment.coordinate - np.median(
                [p.coordinate for p in groups[-1]])) <= tolerance:
            groups[-1].append(segment)
        else:
            groups.append([segment])
    return [_Segment(
        int(round(float(np.median([p.coordinate for p in group])))),
        min(p.start for p in group), max(p.end for p in group),
        max(p.support for p in group),
    ) for group in groups]


def _lines(frame: np.ndarray) -> tuple[list[_Segment], list[_Segment]]:
    h, w = frame.shape[:2]
    edges = cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 8, 30)
    raw = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=max(55, round(min(w, h) * .035)),
        minLineLength=max(180, round(h * .12)),
        maxLineGap=max(12, round(h * .03)),
    )
    if raw is None:
        return [], []
    vertical, horizontal = [], []
    for x0, y0, x1, y1 in np.asarray(raw).reshape(-1, 4):
        x0, y0, x1, y1 = map(int, (x0, y0, x1, y1))
        if abs(x1-x0) <= 3 and abs(y1-y0) >= .18*h:
            vertical.append(_Segment(round((x0+x1)/2), min(y0,y1), max(y0,y1), abs(y1-y0)))
        elif abs(y1-y0) <= 3 and abs(x1-x0) >= .30*w:
            horizontal.append(_Segment(round((y0+y1)/2), min(x0,x1), max(x0,x1), abs(x1-x0)))
    return (_cluster(vertical, max(9, round(w * .012))),
            _cluster(horizontal, max(8, round(h * .010))))


def _column_candidates(lines: list[_Segment], width: int) -> list[tuple[float, tuple[_Segment, ...]]]:
    # Generate several hypotheses; the first numerically uniform grid is not
    # necessarily the gallery when a terminal or sidebar is also visible.
    if len(lines) > 20:
        lines = sorted(sorted(lines, key=lambda p:p.support, reverse=True)[:20],
                       key=lambda p:p.coordinate)
    results = []
    for group in combinations(lines, 5):
        xs = [p.coordinate for p in group]
        steps = np.diff(xs)
        if (min(steps) < width * .09 or max(steps) > width * .20
                or xs[-1] - xs[0] < width * .43):
            continue
        cv = float(np.std(steps) / np.mean(steps))
        if cv > .075:
            continue
        strength = sum(p.support for p in group) / (5 * max(p.support for p in group))
        results.append((cv * 10 - .8 * strength, group))
    return sorted(results, key=lambda item:item[0])[:6]


def _boundaries_for(xs: tuple[_Segment, ...], horizontal: list[_Segment],
                    height: int) -> list[_Segment]:
    start, end = xs[0].coordinate, xs[-1].coordinate
    pitch = float(np.median(np.diff([p.coordinate for p in xs])))
    # A real row border may start just inside the first internal divider:
    # Hough does not promise to reach the line intersection. Scale this
    # allowance with column width, rather than requiring a fixed overhang.
    # Keep the far-side coverage requirement strict: a row containing only
    # three cards must not masquerade as a complete four-column row.
    start_slack = max(12, round(pitch * .06))
    return [p for p in horizontal
            if p.start <= xs[1].coordinate + start_slack
            and p.end >= xs[3].coordinate + 10
            and p.support >= .60 * (end-start)
            and height * .04 <= p.coordinate <= height - 8]


def _candidate_score(column_score: float, row_cv: float, anchor_penalty: float) -> float:
    """Rank validated grids by column evidence, row rhythm, then row anchor.

    Hough can pick up header/text horizontal strokes that accidentally align
    with two real rows. A nearly uniform gallery pitch is stronger evidence
    than the first observed vertical segment's start, which is often clipped.
    """
    return column_score + 12 * row_cv + 3 * anchor_penalty


def _first_complete_row_edge(xs: tuple[_Segment, ...],
                             border: _Segment) -> bool:
    """Require a claimed complete row's top border to span all four columns.

    Image/caption separators can span most of a gallery and pass Hough's
    permissive candidate filter, but do not reach the outer sides of four
    actual cards. A *complete* row must have both outer ends observed within
    a quarter of a column width; clipped rows use separate verification.
    """
    pitch = float(np.median(np.diff([p.coordinate for p in xs])))
    slack = .25 * pitch
    return (border.start <= xs[0].coordinate + slack
            and border.end >= xs[-1].coordinate - slack)


def _vertical_support(xs: tuple[_Segment, ...], first: int, last: int,
                      pitch: float) -> float | None:
    # An upper UI control line is not a gallery boundary merely because it
    # is horizontal and equally spaced. Inner columns must physically span
    # the whole claimed gallery, from the first row boundary to the last.
    slack = max(12, min(28, round(pitch * .06)))
    inner = xs[1:4]
    if any(p.start > first + slack or p.end < last - slack for p in inner):
        return None
    # For a gallery start, the internal column borders normally begin at the
    # first row. Prefer the closest observed anchor over decorative edges.
    # An already-scrolled gallery may have clipped borders: it will remain
    # eligible, but the uncertainty penalty discourages false row origins.
    return float(np.median([abs(p.start-first) for p in inner])) / max(1., pitch)


def _validated_cell(frame: np.ndarray, col: int,
                    left: int, right: int, top: int, bottom: int) -> dict | None:
    h, w = frame.shape[:2]
    dx, dy = right-left, bottom-top
    cx, cy = round(left+dx*.51), round(top+dy*.43)
    x0, x1 = round(left+dx*.17), round(right-dx*.17)
    y0, y1 = round(top+dy*.12), round(top+dy*.73)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h
            and 0 < cx < w and 0 < cy < h):
        return None
    art = frame[y0:y1, x0:x1]
    gray = cv2.cvtColor(art, cv2.COLOR_BGR2GRAY)
    if float(np.std(gray)) < 14:
        return None
    a = gray.astype(np.float32)
    energy = (np.mean(abs(np.diff(a,axis=0)) > 12)
              + np.mean(abs(np.diff(a,axis=1)) > 12)) / 2
    if energy < .012:
        return None
    return {'col':col, 'top':top, 'click':(cx,cy),
            'fp':cv2.resize(art,(60,70),interpolation=cv2.INTER_AREA)}


def _validated_cards(frame: np.ndarray, xs: tuple[_Segment, ...],
                     ys: tuple[_Segment, ...]) -> list[dict] | None:
    cards = []
    for row in range(len(ys)-1):
        for col in range(4):
            card = _validated_cell(frame, col, xs[col].coordinate,
                                   xs[col+1].coordinate,
                                   ys[row].coordinate, ys[row+1].coordinate)
            if card is None:
                return None
            cards.append(card)
    return cards


def _artwork_content_center_y(frame: np.ndarray, left: int, right: int,
                              top: int, bottom: int) -> int | None:
    """Estimate a click row in the visible thumbnail's actual graphic.

    Some artwork is much shorter than its card. The old proportional center
    can lie in empty thumbnail background even when the card is clickable.
    Contrast against a narrow upper-background sample, and use only a
    sustained band of non-background pixels to place the cursor. Return None
    when the evidence is weak; never fabricate a content region.
    """
    h, w = frame.shape[:2]
    dx, dy = right-left, bottom-top
    if dx <= 0 or dy <= 0:
        return None
    x0, x1 = round(left+dx*.17), round(right-dx*.17)
    y0, y1 = round(top+dy*.12), round(top+dy*.73)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        return None
    art = frame[y0:y1, x0:x1]
    sample_height = max(5, round(art.shape[0]*.08))
    background = np.median(art[:sample_height], axis=(0, 1))
    deviation = np.max(abs(art.astype(np.int16)-background),axis=2)
    density = np.mean(deviation > 35, axis=1)
    eligible = np.flatnonzero(density >= .20)
    if len(eligible) < max(8, round(art.shape[0]*.08)):
        return None
    candidate = round(y0+float(np.median(eligible)))
    margin = max(8, round(dy*.035))
    return candidate if y0+margin < candidate < y1-margin else None


def _trailing_cards(frame: np.ndarray, xs: tuple[int, ...],
                    ys: tuple[int, ...]) -> list[dict]:
    """Verify a possible last row with 1-3 finished cards, without guessing.

    A local bottom edge and *both* local card sides must be observable. An
    unfinished row below the screen has no bottom and is intentionally ignored.
    If a missing position precedes a proven card, the layout is unsafe.
    """
    h, w = frame.shape[:2]
    if len(ys) >= 4:
        return []
    row_pitch = float(np.median(np.diff(ys)))
    top = ys[-1]
    bottom = int(round(top + row_pitch))
    # The whole caption/bottom boundary must be on screen; a partly exposed
    # thumbnail at the viewport bottom can never be promoted into a card.
    if bottom >= h-8:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 8, 30)
    result = []
    missing_seen = False
    for col in range(4):
        left,right = xs[col],xs[col+1]
        dx = right-left
        x0,x1 = round(left + dx*.13),round(right-dx*.13)
        y0 = max(top+8, int(round(top+row_pitch*.18)))
        y1 = min(h-8,int(round(bottom-row_pitch*.17)))
        if not (0 < x0 < x1 < w and 0 < y0 < y1 < h):
            raise UnsafeGalleryLayout('末排卡片边界超出截图；无法验证')
        # Search a narrow region near the predicted bottom. The prediction
        # is used as a *search window*, never as evidence of a card by itself.
        by0,by1=max(0,bottom-round(row_pitch*.065)),min(h,bottom+round(row_pitch*.065))
        band=edges[by0:by1,x0:x1]
        local_line = (np.count_nonzero(band,axis=1).max(initial=0)/(x1-x0)
                      if band.size else 0.)
        def side_support(x):
            a,b=max(0,x-9),min(w,x+10)
            cut=edges[y0:y1,a:b]
            return float(np.mean(np.any(cut > 0,axis=1))) if cut.size else 0.
        supported = (local_line >= .58 and
                     side_support(left) >= .42 and side_support(right) >= .42)
        if not supported:
            missing_seen=True
            continue
        if missing_seen:
            raise UnsafeGalleryLayout('末排出现跳列，不推测缺失图纸')
        card=_validated_cell(frame,col,left,right,top,bottom)
        if card is None:
            raise UnsafeGalleryLayout(f'末排第 {col+1} 列存在边界但内容未验证')
        content_y = _artwork_content_center_y(frame, left, right, top, bottom)
        if content_y is not None:
            card['click'] = (card['click'][0], content_y)
        result.append(card)
    return result



# Sample the same interior-artwork band used by the established cell reader.
# This is a geometric approximation to thumbnail visibility (not a claim that
# the complete card or its title must be on screen). Keep the threshold explicit
# so boundary tests cannot accidentally turn a one-pixel fragment into a card.
MIN_VISIBLE_THUMBNAIL_FRACTION = 0.75
_THUMB_TOP = .12
_THUMB_BOTTOM = .73


def _gallery_viewport(xs: tuple[_Segment, ...], height: int) -> tuple[int, int]:
    """Observed vertical gallery separators bound the scrollable content.

    The application header can cover cards while the gallery is scrolled. A
    screenshot's top pixel is therefore NOT necessarily visible gallery space.
    Use the independent internal separators instead of absolute screen offsets.
    """
    inner = xs[1:4]
    top = max(0, min(p.start for p in inner))
    bottom = min(height, max(p.end for p in inner) + 1)
    return top, bottom


def _anchored_side_border(edges: np.ndarray, x: int,
                          cropped_band: tuple[int, int],
                          reference_band: tuple[int, int],
                          row_width: int) -> bool:
    """Prove the same physical border in a cropped and a complete row.

    Hough candidates are clustered using a screen-relative tolerance, so their
    center coordinate may be offset from the actual 1–3 px border. A narrower
    check at the *predicted* x would produce false negatives at Retina sizes.
    Look for a single coherent vertical edge at the SAME x in both bands;
    merely finding random edges at different x in each row is not evidence.
    """
    h, w = edges.shape[:2]
    c0, c1 = cropped_band
    a0, a1 = reference_band
    if not (0 <= c0 < c1 <= h and 0 <= a0 < a1 <= h):
        return False
    # This bound is tied to both the observed column width and the existing
    # Hough-clustering tolerance; it is never an unconstrained border search.
    max_shift = max(6, round(min(row_width * .05, w * .012 * .60)))
    x0, x1 = max(1, x-max_shift), min(w-2, x+max_shift)
    if x1 <= x0:
        return False
    # A three-pixel lateral allowance compensates for edge rasterization.
    crop = (edges[c0:c1, x0-1:x1+2] > 0).astype(np.uint8)
    anchor = (edges[a0:a1, x0-1:x1+2] > 0).astype(np.uint8)
    crop = cv2.dilate(crop, np.ones((1, 3), dtype=np.uint8))
    anchor = cv2.dilate(anchor, np.ones((1, 3), dtype=np.uint8))
    cropped_support = crop[:, 1:-1].mean(axis=0)
    anchor_support = anchor[:, 1:-1].mean(axis=0)
    return bool(np.max(np.minimum(cropped_support, anchor_support)) >= .55)


def _cropped_cell(frame: np.ndarray, edges: np.ndarray, col: int,
                  left: int, right: int, top: int, bottom: int,
                  viewport: tuple[int, int]) -> dict | None:
    """Prove a clipped artwork can be clicked without using missing pixels.

    The inferred cell geometry comes from *other observed complete rows*;
    inference alone is not evidence. Verify the visible artwork and match the
    physical side boundaries against the adjacent complete row. A clipped bitmap never
    bypasses the same contrast/activity checks as a complete one.
    """
    h, w = frame.shape[:2]
    dx, dy = right-left, bottom-top
    if dx <= 0 or dy <= 0 or not (0 < left < right < w):
        return None
    art_top = round(top + dy * _THUMB_TOP)
    art_bottom = round(top + dy * _THUMB_BOTTOM)
    available_top = max(art_top, viewport[0], 0)
    available_bottom = min(art_bottom, viewport[1], h)
    nominal = art_bottom-art_top
    if nominal <= 0 or (available_bottom-available_top)/nominal + 1e-8 < MIN_VISIBLE_THUMBNAIL_FRACTION:
        return None
    cx, cy = round(left + dx*.51), round(top + dy*.43)
    # A visible fingerprint alone is not enough: the original click must still
    # fall inside the visible artwork with a margin, not in an obscuring header.
    inset = max(8, round(min(dx, dy) * .035))
    if not (viewport[0]+inset < cy < viewport[1]-inset and
            available_top+inset < cy < available_bottom-inset):
        return None
    x0, x1 = round(left + dx*.17), round(right-dx*.17)
    if not (0 <= x0 < x1 <= w and 0 <= available_top < available_bottom <= h):
        return None

    # The cropped row is admitted only when its actual card borders match the
    # borders of an adjacent *complete* row at the same horizontal coordinates.
    # Never promote a narrow artwork stripe into a card edge just because it
    # happens to lie somewhere near the predicted Hough coordinate.
    if top < viewport[0]:
        reference_top = bottom  # leading crop: next row is complete
    else:
        reference_top = top - dy  # trailing crop: previous row is complete
    ref0 = max(0, round(reference_top + dy * _THUMB_TOP))
    ref1 = min(h, round(reference_top + dy * _THUMB_BOTTOM))
    crop_band = (available_top, available_bottom)
    reference_band = (ref0, ref1)
    if not (_anchored_side_border(edges, left, crop_band, reference_band, dx)
            and _anchored_side_border(edges, right, crop_band, reference_band, dx)):
        return None

    art = frame[available_top:available_bottom, x0:x1]
    gray = cv2.cvtColor(art, cv2.COLOR_BGR2GRAY)
    if float(np.std(gray)) < 14:
        return None
    a = gray.astype(np.float32)
    energy = (np.mean(abs(np.diff(a,axis=0)) > 12)
              + np.mean(abs(np.diff(a,axis=1)) > 12))/2
    if energy < .012:
        return None
    return {'col': col, 'top': top, 'click': (cx,cy),
            'fp':cv2.resize(art,(60,70),interpolation=cv2.INTER_AREA)}


def _clipped_full_row(frame: np.ndarray, xs: tuple[_Segment, ...],
                      top: int, bottom: int, viewport: tuple[int, int]) -> list[dict]:
    """Return a proved 4-column clipped row, or reject an ambiguous one.

    Partial rows of 1–3 *actual artworks* still use `_trailing_cards` when the
    bottom boundary is visible. Without an observed bottom boundary we cannot
    distinguish an empty slot from an unloaded card, so fail closed.
    """
    if bottom <= top:
        return []
    dy = bottom-top
    nominal_y0 = round(top+dy*_THUMB_TOP)
    nominal_y1 = round(top+dy*_THUMB_BOTTOM)
    frac = (min(nominal_y1, viewport[1], frame.shape[0])
            - max(nominal_y0, viewport[0], 0))/max(1, nominal_y1-nominal_y0)
    if frac + 1e-8 < MIN_VISIBLE_THUMBNAIL_FRACTION:
        return []
    edges = cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 8, 30)
    result = []
    for col in range(4):
        card = _cropped_cell(frame, edges, col,
                             xs[col].coordinate, xs[col+1].coordinate,
                             top, bottom, viewport)
        if card is None:
            raise UnsafeGalleryLayout(
                f'裁切行第 {col+1} 列缺少可验证图像或边界；不跳过、不降级')
        result.append(card)
    return result


def detect_gallery_layout(frame: np.ndarray, *, diagnostics: dict | None = None) -> list[dict]:
    """Recognize up to twelve proven clickable thumbnails, including clipped rows.

    A caption or card bottom need not be visible. The artwork evidence, click
    target, repeated geometry and thumbnail visibility must still be sufficient.
    Ambiguous candidates fail closed instead of guessing missing artwork.
    """
    if (not isinstance(frame, np.ndarray) or frame.ndim != 3 or
            frame.shape[2] != 3 or frame.dtype != np.uint8):
        raise GridDetectionError('截图像素格式异常')
    h, w = frame.shape[:2]
    if w < 900 or h < 700:
        raise GridDetectionError('屏幕尺寸不足以安全识别四列图纸')
    vertical, horizontal = _lines(frame)
    cols = _column_candidates(vertical, w)
    if diagnostics is not None:
        diagnostics.update(columns=[p.coordinate for p in vertical],
                           horizontal=[p.coordinate for p in horizontal])
    if not cols:
        raise GridDetectionError('未确认图纸区域的四列结构')

    candidates: list[tuple[int,float,list[dict],tuple[int,...],tuple[int,...]]] = []
    structural_row_count = 0
    for col_score, xs in cols:
        pitch = float(np.median(np.diff([p.coordinate for p in xs])))
        horizontal_ok = _boundaries_for(xs, horizontal, h)
        for nrows in (3, 2, 1):
            for ys in combinations(horizontal_ok, nrows+1):
                coords = [p.coordinate for p in ys]
                steps = np.diff(coords)
                if (min(steps) < pitch*.88 or max(steps) > pitch*1.46):
                    continue
                cv = float(np.std(steps)/np.mean(steps))
                if cv > .075:
                    continue
                if not _first_complete_row_edge(xs, ys[0]):
                    continue
                anchor_penalty = _vertical_support(xs, coords[0], coords[-1], pitch)
                if anchor_penalty is None:
                    continue
                structural_row_count = max(structural_row_count, nrows)
                # Check image content only once the proposed layout has enough
                # support from independent vertical and horizontal borders.
                cards = _validated_cards(frame, xs, ys)
                if cards is None:
                    continue
                score = _candidate_score(col_score, cv, anchor_penalty)
                candidates.append((nrows,score,cards,
                                   tuple(p.coordinate for p in xs),tuple(coords)))
    if not candidates:
        if structural_row_count:
            raise UnsafeGalleryLayout('已检测到卡片结构，但部分图纸内容为空白、遮挡或未加载；不降低行数')
        raise GridDetectionError('未找到由实际卡片边界和缩略图共同支持的完整可见网格')
    # A known multi-row structure with an unverified cell must not be silently
    # reduced to a valid-looking one-row suffix or prefix.
    if max(c[0] for c in candidates) < structural_row_count:
        raise UnsafeGalleryLayout('网格结构包含更多行，但存在未验证卡片；不跳过完整行')
    # More verified complete rows is preferable to silently dropping loaded
    # cards. Compare same-size hypotheses for inconsistent positioning.
    best_rows = max(c[0] for c in candidates)
    candidates = sorted([c for c in candidates if c[0] == best_rows],
                        key=lambda c:c[1])
    best = candidates[0]
    if len(candidates) > 1:
        alternate = candidates[1]
        # Disagreement in crop / click origin is an ambiguity unless the
        # second hypothesis is substantially weaker on structure evidence.
        if (alternate[1]-best[1] < .08 and
                any(abs(a['click'][i]-b['click'][i]) > 8
                    for a,b in zip(best[2],alternate[2]) for i in (0,1))):
            raise UnsafeGalleryLayout('存在两个难以区分的网格位置候选；不猜测点击坐标')
    # Derive a scrollable viewport from physically observed column dividers.
    # Card captions may be clipped; a >=75% visible *artwork* is eligible if
    # both side edges, image content and its click point remain safely visible.
    selected_xs = next(xs for _, xs in cols
                       if tuple(x.coordinate for x in xs) == best[3])
    viewport = _gallery_viewport(selected_xs, h)
    pitch = int(round(float(np.median(np.diff(best[4])))))
    leading = _clipped_full_row(
        frame, selected_xs, best[4][0]-pitch, best[4][0], viewport)
    if leading and best_rows == 3:
        raise UnsafeGalleryLayout('截图内可能超过12个可操作位置，无法安全编号')
    # A final row with 1-3 *complete* cards retains the old observed-bottom
    # validation. A bottom-cropped row cannot prove missing end slots, so it
    # must verify all four visible artworks or safely reject the layout.
    tail = _trailing_cards(frame, best[3], best[4])
    cropped_tail = []
    if not tail:
        cropped_tail = _clipped_full_row(
            frame, selected_xs, best[4][-1], best[4][-1]+pitch, viewport)
    if cropped_tail and best_rows + (1 if leading else 0) >= 3:
        raise UnsafeGalleryLayout('截图内可能超过12个可操作位置，无法安全编号')
    result = leading + best[2] + tail + cropped_tail
    if len(result) > 12:
        raise UnsafeGalleryLayout('可操作卡片超过当前工作流的12张上限，不推测位置')
    if diagnostics is not None:
        diagnostics.update(selected_columns=list(best[3]), selected_rows=list(best[4]),
                           verified_cards=len(result), candidate_count=len(candidates),
                           verified_trailing=len(tail)+len(cropped_tail),
                           verified_leading=len(leading),
                           visible_artwork_threshold=MIN_VISIBLE_THUMBNAIL_FRACTION)
    return result
