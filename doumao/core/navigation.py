#!/usr/bin/env python3
# 豆猫 Mac 自动化 v0.5b：识别作品详情弹窗内的蓝色铅笔，进入编辑页面。
# 仅导航测试：不输入文字、不删除标签、不点击保存。
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path.home() / 'doumao-automation'
OUTPUT = ROOT / 'screenshots' / 'preview_navigation.png'


def find_detail_modal(frame):
    """从屏幕截图里找居中的白色作品详情弹窗，而不是固定屏幕区域。"""
    h, w = frame.shape[:2]
    whites = cv2.inRange(frame, (245, 245, 245), (255, 255, 255))
    n, labels, stats, centers = cv2.connectedComponentsWithStats(whites, 8)
    candidates = []
    for x, y, ww, hh, pixels in stats[1:n]:
        x, y, ww, hh, pixels = map(int, (x, y, ww, hh, pixels))
        if not (.12*w < ww < .65*w and .2*h < hh < .85*h):
            continue
        if not (.07*h < y < .8*h and x > .02*w and x + ww < .79*w):
            continue
        if (pixels / (ww*hh)) < .43:
            continue
        if (x + ww/2) > .61*w:
            continue
        candidates.append((pixels, (x, y, ww, hh)))
    if len(candidates) != 1:
        return None
    return candidates[0][1]


def find_pencil(frame, modal):
    """蓝色像素分组 + 弹窗相对位置，避免旧版模板缩放误差。"""
    x, y, w, h = modal
    x1, x2 = x + int(.70*w), x + w
    y1, y2 = y + int(.035*h), y + int(.33*h)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (90, 80, 110), (130, 255, 255))
    n, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    found = []
    for xx, yy, ww, hh, area in stats[1:n]:
        xx, yy, ww, hh, area = map(int, (xx, yy, ww, hh, area))
        cx, cy = x1 + xx + ww/2, y1 + yy + hh/2
        if not (.82 <= (cx-x)/w <= .985 and .065 <= (cy-y)/h <= .25):
            continue
        if area < 9 or ww < 4 or hh < 4 or ww > .095*w or hh > .095*h:
            continue
        if not (.50 <= ww/hh <= 2.0):
            continue
        found.append((area, (round(cx), round(cy)), (x1+xx, y1+yy, ww, hh)))
    # 如果存在两个不同的候选，绝不猜测点击。
    if len(found) != 1:
        return None
    return found[0][1], found[0][2]


def find_save_button(frame):
    """只用于检测编辑窗口是否出现；绝不点击保存。"""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (95, 95, 140), (122, 255, 255))
    n, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    found = []
    for xx, yy, ww, hh, area in stats[1:n]:
        xx, yy, ww, hh, area = map(int, (xx, yy, ww, hh, area))
        if (ww > .15*w and hh >= 20 and ww/hh > 4 and yy > .45*h
                and area/(ww*hh) > .45 and xx < .75*w):
            found.append((xx, yy, ww, hh))
    return found[0] if len(found) == 1 else None


def save_preview(frame, modal=None, pencil=None, after=None, msg='DETECTION'):
    before = frame.copy()
    if modal:
        x, y, w, h = modal
        cv2.rectangle(before, (x,y), (x+w,y+h), (40,210,230), 3)
    if pencil:
        center, box = pencil
        x, y, w, h = box
        pad = max(6, round(w*0.8))
        cv2.rectangle(before, (x-pad,y-pad), (x+w+pad,y+h+pad), (0,190,0), 3)
        cv2.circle(before, center, 7, (0,0,255), 2)
    cv2.putText(before, msg, (16, min(75, before.shape[0]-10)),
                cv2.FONT_HERSHEY_SIMPLEX, .85, (0,0,230), 2)
    if after is not None:
        target_w = 770
        frames = []
        for f in (before, after):
            frames.append(cv2.resize(f, (target_w, round(f.shape[0]*target_w/f.shape[1]))))
        out = np.full((max(a.shape[0] for a in frames), target_w*2, 3),255,np.uint8)
        for i, f in enumerate(frames):
            out[:f.shape[0], i*target_w:(i+1)*target_w] = f
    else:
        out = before
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUTPUT), out)
    print('诊断预览：', OUTPUT, flush=True)


def assert_doumao_front():
    r = subprocess.run(['/usr/bin/osascript', '-e',
        'tell application "System Events" to get name of first application process whose frontmost is true'],
        capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() not in ('Runner','豆猫'):
        raise RuntimeError('豆猫未位于前台，已安全停止。当前前台：'+r.stdout.strip())



