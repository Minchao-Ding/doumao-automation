"""Shared v3.5 list-view guards for the title editing GUI adapter.

This module does not choose cards, inspect title rules or advance workflows.
No layout thresholds, screenshot conversion or Escape behavior are changed.
"""
from __future__ import annotations

import time

import pyautogui
import cv2
import numpy as np

from . import card_picker, metadata_editor as cleaner
from . import navigation, tag_scanner as scanner


def shot():
    scanner.assert_app()
    return card_picker.screenshot()


def check_list(frame):
    if cleaner.find_save(frame) is not None:
        raise RuntimeError('检测到编辑弹窗，请关闭后回到饮品列表。')
    if navigation.find_detail_modal(frame) is not None:
        raise RuntimeError('检测到作品详情弹窗，请先关闭。')
    h, w = frame.shape[:2]
    if w < 1300 or h < 800 or not (1.38 < w / h < 1.65):
        raise RuntimeError('当前截图比例与已验证的 Mac 界面不一致，不自动点击。')


def go_back_to_list():
    """Escape up to three times without guessing a dialog-close position."""
    for _ in range(3):
        scanner.assert_app()
        frame = shot()
        if cleaner.find_save(frame) is None and navigation.find_detail_modal(frame) is None:
            return frame
        pyautogui.press('esc')
        time.sleep(.75)
    frame = shot()
    if cleaner.find_save(frame) is not None or navigation.find_detail_modal(frame) is not None:
        raise RuntimeError('Esc 未能关闭弹窗，请手动关闭后再继续；不盲目点击。')
    return frame


def wait_for_list_after_save():
    """Wait for editor close; at most one Escape from the detail modal."""
    for _ in range(7):
        time.sleep(.5)
        scanner.assert_app()
        frame = shot()
        if cleaner.find_save(frame) is None:
            break
    else:
        raise RuntimeError('保存后仍检测到编辑页按钮；未确认退出编辑页，不再处理下一张。')

    if navigation.find_detail_modal(frame) is not None:
        print('保存后仍在作品详情页；尝试一次 Esc 返回列表。', flush=True)
        scanner.assert_app()
        pyautogui.press('esc')
        time.sleep(.95)
        scanner.assert_app()
        frame = shot()
        if navigation.find_detail_modal(frame) is not None:
            raise RuntimeError('Esc 后详情弹窗仍存在；请手动关闭。为避免误点，不自动继续。')
    if cleaner.find_save(frame) is not None:
        raise RuntimeError('返回列表时仍检测到编辑窗口；已安全停止。')
    return frame


def card_rows(frame):
    """Detect fully visible cards with the established v3.5 four-column grid."""
    h, w = frame.shape[:2]
    left, step = .115 * w, (.691 - .115) * w / 4
    detected = []
    for col in range(4):
        xs = [round(left + (col + offset) * step) for offset in (.04, .075)]
        if xs[-1] >= w:
            raise RuntimeError('卡片定位列超过屏幕宽度。')
        rgb = frame[:, xs, ::-1]
        plausible = ((rgb[:, :, 0] >= 245) & (rgb[:, :, 0] <= 251)
                     & (rgb[:, :, 1] >= 249) & (rgb[:, :, 2] >= 251))
        smooth = np.convolve(plausible.mean(axis=1), np.ones(21) / 21, mode='same')
        flags = (smooth >= .55).astype(np.int8)
        transitions = np.diff(np.r_[0, flags, 0])
        runs = zip(np.where(transitions == 1)[0], np.where(transitions == -1)[0])
        for top, bottom in runs:
            top, bottom = int(top), int(bottom)
            if not (.16*h < top < .86*h and (bottom-top) > .67*step):
                continue
            if (top + .94*step) > (.955*h):
                continue
            if not (.78*step < bottom-top < 1.25*step):
                continue
            x0, x1 = round(left+(col+.12)*step), round(left+(col+.90)*step)
            y0, y1 = round(top+.06*step), round(top+.73*step)
            art = frame[y0:y1, x0:x1]
            if art.size == 0 or np.std(art) < 9:
                continue
            fp = cv2.resize(art, (60, 70), interpolation=cv2.INTER_AREA)
            cx, cy = round(left+(col+.50)*step), round(top+.43*step)
            if not (.13*w < cx < .70*w and .17*h < cy < .90*h):
                continue
            detected.append({'col': col, 'top': top, 'click': (cx,cy), 'fp': fp})
    detected.sort(key=lambda c: (c['top'], c['col']))
    if len(detected) > 12:
        raise RuntimeError(f'视觉识别到 {len(detected)} 张卡片，超过预期，停止。')
    return detected


def save_title_diagnostic(output, frame=None):
    """Write the established annotated title failure image to a local path.

    A diagnostic failure must never replace a safety exception or write into
    the source tree. The calling workflow records the reason in its own log.
    """
    frame = shot() if frame is None else frame
    view = frame.copy()
    cv2.putText(view, 'v1.1 TITLE DIAGNOSTIC', (14, 52),
                cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), view)
