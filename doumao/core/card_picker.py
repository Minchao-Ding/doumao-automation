#!/usr/bin/env python3
"""豆猫 v0.8：从饮品列表中自动选一张「有标签」的作品，导航并清理（不保存）。

依赖（请与本文件放在同一文件夹）：
    doumao_v07b_scan_tagged.py
    doumao_v05b_navigation.py
    doumao_v041_clean_one.py

只处理当前可见列表中最上方、最靠左的一个已识别标签组。
只支持已经验证的 2～5 个同行标签场景。遇到异常不猜测、不保存。
正式运行前必须在「仓库 → 食物 → 饮品」列表，且没有打开弹窗。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui

from . import tag_scanner as scanner
from . import navigation as navigator
from . import metadata_editor as cleaner

ROOT = Path.home() / 'doumao-automation'
PREVIEW = ROOT / 'screenshots' / 'preview_v08_candidate.png'
pyautogui.FAILSAFE = True
pyautogui.PAUSE = .18


def screenshot():
    return cv2.cvtColor(np.asarray(pyautogui.screenshot().convert('RGB')), cv2.COLOR_RGB2BGR)


def screen_click(x, y, frame):
    scanner.assert_app()
    h, w = frame.shape[:2]
    sw, sh = pyautogui.size()
    px, py = int(round(x * sw / w)), int(round(y * sh / h))
    if not (10 < px < sw-10 and 10 < py < sh-10):
        raise RuntimeError('候选图纸的点击位置超出安全范围，已停止。')
    pyautogui.click(px, py)


def find_first_candidate(im):
    h, w = im.shape[:2]
    groups = scanner.scan_tag_groups(im)
    if not (1 <= len(groups) <= 12):
        raise RuntimeError(f'识别到 {len(groups)} 组标签；候选数量异常，停止。')

    # 顶部优先、左侧优先，保证只处理第一张，不循环处理整个文件夹。
    # 标签通常位于图纸图片的上沿，点击标签行下方的图片内部，避免点中标签本身。
    safe = []
    delta_y = min(round(h * .085), round(w * .08))
    for x0, y0, x1, y1 in groups:
        cx = (x0+x1)/2
        cy = y1 + delta_y
        if not (.13*w < cx < .76*w and .17*h < cy < .90*h):
            continue
        safe.append((x0, y0, x1, y1, cx, cy))
    if not safe:
        raise RuntimeError('已识别标签，但图纸图片点击位置不够安全，停止。')
    safe.sort(key=lambda a: (a[1], a[0]))
    return len(groups), safe[0]


def save_candidate_preview(im, candidate, total):
    x0,y0,x1,y1,cx,cy = candidate
    vis = im.copy()
    cv2.rectangle(vis,(x0-6,y0-6),(x1+6,y1+6),(10,200,10),3)
    cv2.circle(vis,(round(cx),round(cy)), 14,(0,0,255),3)
    cv2.putText(vis,f'ONE CARD ONLY / {total} TAGGED GROUPS',
                (max(15,x0-30),max(40,y0-20)),cv2.FONT_HERSHEY_SIMPLEX,
                .65,(0,0,215),2,cv2.LINE_AA)
    PREVIEW.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(PREVIEW),vis)


def wait_for_detail():
    for _ in range(5):
        time.sleep(.5)
        scanner.assert_app()
        frame = screenshot()
        modal = navigator.find_detail_modal(frame)
        if modal is not None:
            return frame, modal
    raise RuntimeError('点击后未确认打开作品详情；没有修改任何资料。')


def wait_for_editor():
    for _ in range(5):
        time.sleep(.5)
        scanner.assert_app()
        frame = screenshot()
        save = cleaner.find_save(frame)
        if save is not None and cleaner.form_rects(frame, save) is not None:
            return frame, save
    raise RuntimeError('点击铅笔后未确认进入编辑作品资料；没有修改任何资料。')



