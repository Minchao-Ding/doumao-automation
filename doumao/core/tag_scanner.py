#!/usr/bin/env python3
"""豆猫 v0.7b：饮品列表「有标签才待整理」的视觉筛选预览（排除左侧导航误报）。

只截图、识别、画框；不会点击、进入详情、清理或保存。

本次专用规则：
- 对「食物 → 饮品」：右上角可见至少两枚同行蓝色标签的卡片 = 待整理。
- 没识别到标签的卡片不打开、不查看备注（用户已确认这一批都是整理过的）。
- 单枚标签、遮挡、不同布局可能暂时识别不到；这种情况先不操作。

运行：python doumao_v07_scan_tagged.py
生成：~/doumao-automation/screenshots/preview_scan_tags.png （每次覆盖；仅预览）
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

OUT = Path.home() / 'doumao-automation' / 'screenshots' / 'preview_scan_tags.png'


def assert_app():
    cmd = [
        '/usr/bin/osascript', '-e',
        'tell application "System Events" to get name of first application process whose frontmost is true',
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    name = p.stdout.strip()
    if p.returncode or name not in ('Runner', '豆猫'):
        raise RuntimeError(f'豆猫不是当前前台应用（检测到：{name or "未知"}）。')


def scan_tag_groups(im):
    """在当前画面上找「同一行相邻的蓝色小标签」，不匹配具体标签名。"""
    height, width = im.shape[:2]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (95, 90, 155), (130, 255, 255))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, round(width * .0045)), 3)
    )
    merged = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, kernel)
    n, _, stats, _ = cv2.connectedComponentsWithStats(merged, 8)
    items = []
    for x, y, w, h, area in stats[1:n]:
        x, y, w, h, area = map(int, (x, y, w, h, area))
        if not (
            .14 * height < y < .94 * height
            and max(13, .008 * width) <= w <= .085 * width
            and max(7, .005 * width) <= h <= min(32, max(16, .018 * width))
            and 12 <= area <= .003 * width * width
        ):
            continue
        pad = max(2, round(width * .002))
        crop = im[
            max(0, y - pad):min(height, y + h + pad),
            max(0, x - pad):min(width, x + w + pad),
        ]
        # 标签蓝色文字通常位于浅色胶囊中；容忍第一枚标签与像素画重叠。
        if crop.size == 0 or np.mean(np.min(crop, axis=2) >= 232) < .10:
            continue
        items.append((x, y, w, h))

    rows = []
    for item in sorted(items, key=lambda a: a[1] + a[3] / 2):
        cy = item[1] + item[3] / 2
        for row in rows:
            avg = np.mean([r[1] + r[3] / 2 for r in row])
            if abs(cy - avg) <= max(6, width * .006):
                row.append(item)
                break
        else:
            rows.append([item])

    groups = []
    for row in rows:
        row.sort(key=lambda a: a[0])
        current = []
        for item in row:
            if current and item[0] - (current[-1][0] + current[-1][2]) > max(18, width * .033):
                if 2 <= len(current) <= 5:
                    groups.append(current)
                current = []
            current.append(item)
        if 2 <= len(current) <= 5:
            groups.append(current)

    # 删除因微小颜色变化而可能重复出现的标记，仅保留在同一区域出现的一组。
    boxes = []
    for group in groups:
        x0 = min(g[0] for g in group)
        y0 = min(g[1] for g in group)
        x1 = max(g[0] + g[2] for g in group)
        y1 = max(g[1] + g[3] for g in group)
        heights = [g[3] for g in group]
        if max(heights) - min(heights) > max(4, np.median(heights) * .28):
            continue
        if (x1 - x0) > .23 * width:
            continue
        boxes.append((x0, y0, x1, y1))
    # 本版修复：原版可能将左侧「仓库」按钮的蓝色图标/文字
    # 误认为一组标签。排除左侧导航区域，只保留主内容区域的候选。
    # 这是当前 Mac 豆猫布局的保守范围；若将来窗口布局改变，
    # 应先重新跑只读预览确认，不能直接用于自动点击。
    content_left = round(width * 0.10)
    boxes = [b for b in boxes if b[0] >= content_left]
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes



