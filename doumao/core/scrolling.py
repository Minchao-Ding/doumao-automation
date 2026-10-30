#!/usr/bin/env python3
"""豆猫 Mac v1.0b：仅扫描饮品文件夹，自动滚动直到疑似底部。

完全只读：不点击作品、不改备注/标签/标题、不保存。
使用之前通过测试的 v0.7b 标签组检测与 v1.0a 网格区域和滚轮坐标。

限制说明：
  - "BOTTOM LIKELY" 只表示连续三次滚动后可见网格几乎未变，
    并不能证明所有加载内容均已读取；如有动态加载/网络延迟，需人工核对。
  - 标签扫描目前可能漏掉只有 1 个标签的作品。
"""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui

from . import tag_scanner as scanner

ROOT = Path.home() / 'doumao-automation'
OUT = ROOT / 'screenshots' / 'preview_v10b_scroll_to_end.png'
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.18


def screenshot() -> np.ndarray:
    scanner.assert_app()
    return cv2.cvtColor(np.asarray(pyautogui.screenshot().convert('RGB')),
                        cv2.COLOR_RGB2BGR)


def grid_region(frame: np.ndarray) -> tuple[int, int, int, int]:
    h, w = frame.shape[:2]
    # 保留 v1.0a 经用户验证的主区域，排除应用侧栏和浏览器。
    return round(w*.115), round(h*.17), round(w*.691), round(h*.865)


def change_fraction(a: np.ndarray, b: np.ndarray) -> float:
    x0,y0,x1,y1 = grid_region(a)
    aa = cv2.GaussianBlur(a[y0:y1, x0:x1], (5,5), 0)
    bb = cv2.GaussianBlur(b[y0:y1, x0:x1], (5,5), 0)
    return float(np.mean(np.max(cv2.absdiff(aa,bb), axis=2)>22))


def jpeg_frame(im: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode('.jpg', im, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not ok:
        raise RuntimeError('内部截图压缩失败')
    return encoded.tobytes()


def annotate(im: np.ndarray, index: int) -> np.ndarray:
    x0,y0,x1,y1 = grid_region(im)
    crop = im[y0:y1, x0:x1].copy()
    groups = scanner.scan_tag_groups(im)
    valid_count = 0
    for xa,ya,xb,yb in groups:
        if xa<x0 or xb>x1 or ya<y0 or yb>y1:
            continue
        valid_count += 1
        cv2.rectangle(crop, (xa-x0-4,ya-y0-4),(xb-x0+4,yb-y0+4),(20,185,40),3)
    header = np.full((52,crop.shape[1],3),247,np.uint8)
    cv2.putText(header, f'VIEW {index} | {valid_count} VISIBLE TAG GROUPS',
                (10,34), cv2.FONT_HERSHEY_SIMPLEX,.66,(45,45,45),2,cv2.LINE_AA)
    return np.vstack([header,crop])


def save_preview(saved: list[tuple[int,bytes]], status: str, scrolls: int):
    # 截图保留 JPEG 压缩数据，而非几十/上百张全分辨率图片，避免占内存。
    if len(saved)>8:
        chosen = sorted({round(i*(len(saved)-1)/7) for i in range(8)})
    else:
        chosen = list(range(len(saved)))
    panels=[]
    for i in chosen:
        number, data = saved[i]
        frame = cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError('内存中的截图解码失败')
        tile = annotate(frame,number)
        width=520
        tile=cv2.resize(tile,(width,max(1,round(tile.shape[0]*width/tile.shape[1]))),
                        interpolation=cv2.INTER_AREA)
        panels.append(tile)
    if not panels: return
    height = max(x.shape[0] for x in panels)
    panels=[cv2.copyMakeBorder(x,0,height-x.shape[0],0,0,
                              cv2.BORDER_CONSTANT,value=(255,255,255)) for x in panels]
    if len(panels)%2:
        panels.append(np.full((height,520,3),255,np.uint8))
    sheet=np.vstack([np.hstack(panels[i:i+2]) for i in range(0,len(panels),2)])
    footer=np.full((74,sheet.shape[1],3),249,np.uint8)
    cv2.putText(footer, f'{status} | {scrolls} SCROLLS | NO CLICKS / NO SAVES',
                (12,42),cv2.FONT_HERSHEY_SIMPLEX,.58,(40,40,40),2,cv2.LINE_AA)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(OUT),np.vstack([sheet,footer])):
        raise RuntimeError('无法保存预览图')



