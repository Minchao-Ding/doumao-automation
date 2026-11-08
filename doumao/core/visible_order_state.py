"""Pure parsing, row-major mapping and conservative layout invariants."""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Sequence

import cv2
import numpy as np

from .queue_state import looks_like_same_art


class VisibleOrderUncertain(RuntimeError):
    """No further GUI action is safe without a fresh user-selected batch."""


@dataclass(frozen=True)
class Assignment:
    position: int
    title: str


@dataclass
class BatchState:
    assignments: list[Assignment]
    completed: list[int] = field(default_factory=list)
    pending: int | None = None
    status: str = 'ready'

    @property
    def remaining(self):
        return [a for a in self.assignments if a.position not in self.completed]

    def begin(self, position):
        if self.pending is not None:
            raise VisibleOrderUncertain('上一位置仍有待核对的保存')
        if position in self.completed:
            raise VisibleOrderUncertain('同一批次的位置不能重复执行')
        self.pending = position
        self.status = 'pending'

    def verified(self, position):
        if self.pending != position:
            raise VisibleOrderUncertain('被核验的位置与等待中的位置不一致')
        self.completed.append(position)
        self.pending = None
        self.status = 'running'


def parse_line(line: str, capacity: int = 12, *, truncate_excess: bool = False,
               return_ignored: bool = False):
    """Parse names; interactive callers may discard beyond the visible grid.

    The legacy two-argument call still raises on overflow.  The interactive
    CLI explicitly opts in to ignoring excess and receives the ignored names
    so the omission is transparent before any GUI action.
    """
    if not 1 <= capacity <= 12:
        raise ValueError('可处理位置数量必须为 1–12')
    content = line.strip()
    if not content:
        raise ValueError('请输入至少一个名称')
    prefix = re.match(r'^(\d+)\s*[:：]\s*(.*)$', content, flags=re.S)
    start = int(prefix.group(1)) if prefix else 1
    body = prefix.group(2) if prefix else content
    if not 1 <= start <= capacity:
        raise ValueError(f'起始位置必须为 1–{capacity}')
    try:
        names = shlex.split(body, posix=True)
    except ValueError as exc:
        raise ValueError('引号不成对，请重新输入') from exc
    if not names:
        raise ValueError('没有识别到名称')
    available = capacity - start + 1
    if len(names) > available and not truncate_excess:
        raise ValueError(f'从第 {start} 张开始最多可输入 {available} 个名称')
    if any(len(x) > 64 or any(ch in x for ch in '\n\r\x00') for x in names):
        raise ValueError('名称不得超过64字符或包含换行/空字符')
    if any(not x.strip() for x in names):
        raise ValueError('名称不能为空')
    selected, ignored = names[:available], names[available:]
    assignments = [Assignment(i, name) for i, name in enumerate(selected, start)]
    return (assignments, ignored) if return_ignored else assignments


def fit_visible_assignments(assignments: Sequence[Assignment], visible_count: int):
    """Use only complete on-screen slots, never carry names into a later batch."""
    selected = [a for a in assignments if a.position <= visible_count]
    ignored_count = len(assignments) - len(selected)
    if not selected:
        raise ValueError(f'起始位置超过当前 {visible_count} 张完整可见卡片；本批未修改')
    verify_mapping(selected, visible_count)
    return selected, ignored_count


def ordered_cards(cards: Sequence[dict], image_width: int):
    """Anchor each row by a tight top-coordinate cluster, then sort by col."""
    if not 1 <= len(cards) <= 12:
        raise VisibleOrderUncertain(f'识别到 {len(cards)} 张完整卡片，数量不安全')
    tolerance = max(5, round(image_width * .004))
    rows: list[list[dict]] = []
    for card in sorted(cards, key=lambda c: (c['top'], c['col'])):
        if card['col'] not in range(4) or 'fp' not in card or 'click' not in card:
            raise VisibleOrderUncertain('卡片缺少有效列号、位置或图片指纹')
        if rows and abs(card['top'] - rows[-1][0]['top']) <= tolerance:
            rows[-1].append(card)
        else:
            rows.append([card])
    if len(rows) > 3:
        raise VisibleOrderUncertain('检测到超过三行完整卡片')
    output = []
    for row_index, row in enumerate(rows):
        by_col = sorted(row, key=lambda c: c['col'])
        cols = [c['col'] for c in by_col]
        if len(cols) != len(set(cols)) or cols != list(range(len(cols))):
            raise VisibleOrderUncertain(f'第 {row_index+1} 行存在缺列或重复列')
        if row_index < len(rows)-1 and len(cols) != 4:
            raise VisibleOrderUncertain('非最后一行卡片数量不足，可能遗漏识别')
        output.extend(by_col)
    return output


def artwork_matches_with_small_drift(before: np.ndarray, after: np.ndarray) -> bool:
    """Compare visible-order artwork without requiring nearly identical pixels.

    The grid detector can crop the same pixel art 1-2 source pixels apart
    when Hough edges vary between screenshots. A light blur and shift-tolerant
    central template absorb that difference. Obviously different artwork
    still fails. Search-queue keeps its separate, stricter identity rule.
    """
    if looks_like_same_art(before, after):
        return True
    if (not isinstance(before, np.ndarray) or not isinstance(after, np.ndarray)
            or before.ndim != 3 or before.shape != after.shape
            or before.shape[2] != 3 or min(before.shape[:2]) < 25):
        return False
    inner = before[5:-5, 5:-5]
    if inner.size == 0:
        return False
    raw = float(cv2.minMaxLoc(
        cv2.matchTemplate(after, inner, cv2.TM_SQDIFF_NORMED))[0])
    # Original search-queue's .012 is too strict for pixel art shifted by
    # 1-2 pixels. The direct score accepts moderate translation/crop jitter.
    if raw < .08:
        return True
    # For changed anti-aliasing, use blurred structure too, but require the
    # original image to remain somewhat similar: blur alone treats unrelated
    # noisy images as identical and can conflate visually similar characters.
    if raw >= .20:
        return False
    a = cv2.GaussianBlur(before, (5, 5), 1.2)
    b = cv2.GaussianBlur(after, (5, 5), 1.2)
    softened = float(cv2.minMaxLoc(cv2.matchTemplate(
        b, a[5:-5, 5:-5], cv2.TM_SQDIFF_NORMED))[0])
    return softened < .04


def ensure_stable(baseline: Sequence[dict], observed: Sequence[dict], *,
                  pixel_tolerance: int = 8, fingerprint_positions: Sequence[int] | None = None):
    """Validate geometry for every slot; thumbnails for selected one-based slots.

    None keeps the original all-thumbnails behavior for backwards compatibility.
    GUI operations that edit only a subset of the visible slots pass exactly
    those positions: changes to unrelated thumbnails must not abort the batch.
    """
    if len(baseline) != len(observed):
        raise VisibleOrderUncertain('保存后完整可见卡片数发生变化')
    positions = set(range(1, len(baseline) + 1)) if fingerprint_positions is None else set(fingerprint_positions)
    if not positions or any(type(p) is not int or not 1 <= p <= len(baseline) for p in positions):
        raise ValueError('图像核验位置超出当前可见范围')
    # A structural re-detection may choose slightly different border lines,
    # which moves the *safe click point* inside the same card. This is not a
    # changed work. Tolerate bounded drift relative to the actual grid pitch;
    # retain row/column checks and assigned thumbnail identity checks.
    column_steps = [
        baseline[i+1]['click'][0] - baseline[i]['click'][0]
        for i in range(len(baseline)-1)
        if baseline[i]['col'] < 3 and baseline[i+1]['col'] == baseline[i]['col']+1
        and baseline[i]['top'] == baseline[i+1]['top']
    ]
    # Synthetic / older scanners may report 1-2px top jitter within a row.
    if not column_steps:
        column_steps = [
            baseline[i+1]['click'][0] - baseline[i]['click'][0]
            for i in range(len(baseline)-1)
            if baseline[i]['col'] < 3 and baseline[i+1]['col'] == baseline[i]['col']+1
            and abs(baseline[i]['top']-baseline[i+1]['top']) <= pixel_tolerance
        ]
    row_steps = [
        baseline[i+4]['top'] - baseline[i]['top']
        for i in range(len(baseline)-4)
        if baseline[i+4]['col'] == baseline[i]['col']
    ]
    x_tolerance = max(pixel_tolerance, int(min(column_steps)*.28)) if column_steps else pixel_tolerance
    y_tolerance = max(pixel_tolerance, int(min(row_steps)*.22)) if row_steps else pixel_tolerance
    for slot, (a, b) in enumerate(zip(baseline, observed), 1):
        if a['col'] != b['col'] or abs(a['top']-b['top']) > pixel_tolerance:
            raise VisibleOrderUncertain(f'第 {slot} 张卡片的位置改变')
        if (abs(a['click'][0]-b['click'][0]) > x_tolerance or
                abs(a['click'][1]-b['click'][1]) > y_tolerance):
            raise VisibleOrderUncertain(f'第 {slot} 张卡片点击位置大幅改变')
        if slot in positions and not artwork_matches_with_small_drift(a['fp'], b['fp']):
            raise VisibleOrderUncertain(f'第 {slot} 张图像不再匹配，可能发生重新排列或滚动')


def verify_mapping(assignments: Sequence[Assignment], visible_count: int):
    if not assignments:
        raise ValueError('空批次')
    if max(a.position for a in assignments) > visible_count:
        raise ValueError(f'当前仅识别 {visible_count} 张完整卡片，输入涉及不存在的位置；请重新输入')
