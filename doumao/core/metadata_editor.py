#!/usr/bin/env python3
"""豆猫 Mac 图纸整理助手 v0.4.1：单张清备注、清标签，在底部直接保存。

工作方式：
  1. 用户手动打开「仓库 → 作品 → 铅笔 → 编辑作品资料」，页面置顶。
  2. 命令行指定预期标题，以防误操作其他作品。
  3. 视觉定位输入框、标签栏及「选择作品标签」弹窗。
  4. 自动清备注、逐一清掉最多 5 个已选标签，每次重新识别。
  5. 关闭标签弹窗后停留底部，确认底部标签栏与保存按钮。仅在明确使用 --auto-save 时点击一次最终保存。

重要：仅支持已选标签单行展示的 1～5 枚短标签；0 枚或跨行标签会安全停止。
      基于用户已验证的豆猫 Mac v1.0.41 视觉样式。版本变化、缩放或布局变化会影响识别。
      失败时不会自动回滚。若已经点击保存，须重新打开作品核对；若尚未点击保存，可关闭编辑窗口放弃修改。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys
import time

import cv2
import numpy as np
import pyautogui
from PIL import Image

ROOT = Path.home() / "doumao-automation"
PREVIEW = ROOT / "screenshots" / "preview_clean_one.png"
DIAGNOSTIC = ROOT / "screenshots" / "diagnostic_tag.png"
LOG = ROOT / "logs" / "operations.jsonl"
CLICK = "/opt/homebrew/bin/cliclick"
MAX_TAGS = 5
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.18


def shell(*args, input_text=None):
    p = subprocess.run(args, input=input_text, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(f"命令失败：{args[0]} {p.stderr.strip()}")
    return p.stdout


def assert_doumao():
    front = shell('/usr/bin/osascript', '-e',
        'tell application "System Events" to get name of first application process whose frontmost is true').strip()
    if front not in {'Runner', '豆猫'}:
        raise RuntimeError(f"豆猫不在前台（当前：{front!r}）。")


def capture() -> np.ndarray:
    return cv2.cvtColor(np.array(pyautogui.screenshot().convert('RGB')), cv2.COLOR_RGB2BGR)


def img_to_screen(x, y, im):
    ih, iw = im.shape[:2]
    sw, sh = pyautogui.size()
    return round(x * sw / iw), round(y * sh / ih)


def click_img(x, y, im):
    assert_doumao()
    sx, sy = img_to_screen(x, y, im)
    sw, sh = pyautogui.size()
    if not (8 < sx < sw - 8 and 8 < sy < sh - 8):
        raise RuntimeError("点击点接近屏幕边缘，停止。")
    pyautogui.click(sx, sy)


def rect_center(rect):
    x, y, w, h = rect
    return x + w / 2, y + h / 2


def find_blue(im):
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (95, 95, 140), (122, 255, 255))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    for x, y, w, h, area in stats[1:n]:
        x, y, w, h, area = map(int, (x, y, w, h, area))
        if w and h:
            yield (x, y, w, h, area / (w * h))


def find_save(im):
    H, W = im.shape[:2]
    choices = [(x, y, w, h) for x, y, w, h, frac in find_blue(im)
               if w > .15 * W and h >= 20 and w / h > 4
               and y > .40 * H and frac > .45 and x < .75 * W]
    return choices[0] if len(choices) == 1 else None


def find_finish(im):
    H, W = im.shape[:2]
    choices = [(x, y, w, h) for x, y, w, h, frac in find_blue(im)
               if .035 * W < w < .12 * W and .015 * H < h < .065 * H
               and 2 < w / h < 8 and y > .49 * H
               and x < .75 * W and frac > .65]
    return choices[0] if len(choices) == 1 else None


def form_rects(im, save):
    """v1.0g: search the modal's *visible full height*, not a narrow band.

    The original implementation used y in [save_y - .75*button_w,
    save_y - .34*button_w]; depending on the dialog scroll state the title
    can be ABOVE that range. This patch uses the fixed save button as a modal
    anchor, searches the vertical content area, and demands exactly one
    ordered (short title, taller note) pair with the expected color/spacing.
    It never treats a lone rectangle as sufficient evidence to edit.
    """
    if save is None:
        return None
    sx, sy, sw, _ = save
    H, W = im.shape[:2]
    # Keep sample columns inside the modal, away from outer app/content.
    xlo, xhi = max(0, sx + round(sw * .30)), min(W, sx + round(sw * .80))
    # Look through the editor's entire visible scroll content. In a narrow
    # window previous code would miss an otherwise fully visible title.
    ylo = max(0, sy - round(sw * 1.80))
    yhi = min(H, sy - round(sw * .18))
    if xhi <= xlo or yhi <= ylo:
        return None
    rgb = im[ylo:yhi, xlo:xhi, ::-1].astype(np.int16)
    r, g, b = [rgb[:, :, j] for j in range(3)]
    pale = (r >= 244) & (r <= 251) & (g >= 248) & (g <= 255) & (b >= 250)
    runs, start = [], None
    for idx, yes in enumerate(np.r_[np.mean(pale, axis=1) > .78, False]):
        if yes and start is None:
            start = idx
        elif not yes and start is not None:
            if idx - start >= round(sw * .03):
                runs.append((ylo + start, ylo + idx))
            start = None
    pairs = []
    for (ty0, ty1), (ny0, ny1) in zip(runs, runs[1:]):
        title_h = ty1 - ty0
        note_h = ny1 - ny0
        gap = ny0 - ty1
        # Require the complete title-and-note pair, rather than relying on
        # the last two pale rectangles (which might be categories/tag bar).
        if not (.035 * sw < title_h < .13 * sw):
            continue
        if not (.07 * sw < note_h < .19 * sw):
            continue
        if not (0 < gap < .08 * sw):
            continue
        if not (.35 * sw < sy - ny1 < 1.10 * sw):
            continue
        pairs.append(((sx, ty0, sw, title_h), (sx, ny0, sw, note_h)))
    # A second plausible pair means ambiguous UI: stop before reading/typing.
    return pairs[0] if len(pairs) == 1 else None


def find_tag_bar(im, save):
    """沿用已通过测试 06 的浅蓝色标签栏检测。"""
    if not save:
        return None
    sx, sy, sw, _ = save
    H, W = im.shape[:2]
    x0, x1 = max(0, sx + round(sw * .25)), min(W, sx + round(sw * .80))
    y0, y1 = max(0, sy - round(sw * .58)), min(H, sy - round(sw * .26))
    if x1 <= x0 or y1 <= y0:
        return None
    rgb = im[y0:y1, x0:x1, ::-1]
    r, g, b = [rgb[:, :, j] for j in range(3)]
    pale = ((r >= 245) & (r <= 250) & (g >= 249) & (g <= 255) &
            (b >= 252) & (b <= 255))
    dense = (pale.mean(axis=1) > .73).astype(np.uint8).reshape(-1, 1)
    dense = cv2.morphologyEx(dense, cv2.MORPH_CLOSE, np.ones((5, 1), np.uint8))[:, 0].astype(bool)
    runs, start = [], None
    for idx, yes in enumerate(np.r_[dense, False]):
        if yes and start is None:
            start = idx
        elif not yes and start is not None:
            if .045 * sw <= idx - start <= .13 * sw:
                runs.append((y0 + start, y0 + idx))
            start = None
    runs = [it for it in runs if sy - .53 * sw <= sum(it) / 2 <= sy - .28 * sw]
    if len(runs) != 1:
        return None
    top, bottom = runs[0]
    middle = (top + bottom) // 2
    good = 0
    for f in (.25, .48, .74, .90):
        x = min(W - 1, sx + round(sw * f))
        blue, green, red = map(int, im[middle, x])
        good += (245 <= red <= 251 and 248 <= green <= 255 and 251 <= blue <= 255)
    if good < 3:
        return None
    return (sx, top, sw, bottom - top)


def all_chip_rows(im):
    """沿用测试 08/09 的浅蓝已选 chip 识别。"""
    rgb = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.int16)
    r, g, b = [rgb[:, :, j] for j in range(3)]
    mask = ((r >= 232) & (r <= 246) & (g >= 239) & (g <= 250) &
            (b >= 249) & ((b-r) >= 7) & ((b-g) >= 2)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    candidates = []
    for x, y, w, h, area in stats[1:n]:
        x, y, w, h, area = map(int, (x, y, w, h, area))
        if 18 <= h <= 105 and w >= 42 and 1.6 <= w / h <= 7 and area >= 450 and .47 <= area/(w*h) <= .96:
            candidates.append((x, y, w, h))
    groups = []
    for chip in sorted(candidates, key=lambda c: (c[1]+c[3]/2, c[0])):
        cy = chip[1]+chip[3]/2
        for group in groups:
            avg_y = np.mean([a[1]+a[3]/2 for a in group])
            if abs(cy-avg_y) <= max(9, chip[3]*.35):
                group.append(chip)
                break
        else:
            groups.append([chip])
    for group in groups:
        group.sort(key=lambda c:c[0])
    return groups


def selected_chips(im, finish, previous=None):
    """以标签弹窗的小号完成按钮为锚，选出唯一一组已选 chips。"""
    if finish is None:
        return None
    fx, fy, fw, fh = finish
    matches = []
    for row in all_chip_rows(im):
        if len(row) < 1 or len(row) > MAX_TAGS:
            continue
        mid_y = float(np.mean([y+h/2 for x,y,w,h in row]))
        # 标签栏在弹窗的上半段，通常高于右下角完成按钮约 6–11 个按钮高度。
        if not (fy - 12*fh <= mid_y <= fy - 4*fh):
            continue
        if not (fx-5*fw < row[0][0] < fx-1.5*fw):
            continue
        if max(c[1] for c in row) - min(c[1] for c in row) > 6:
            continue
        if previous is not None:
            px, py, pw, ph = previous[0]
            if abs(mid_y-(py+ph/2)) > max(14, ph*.75):
                continue
            if abs(row[0][0]-px) > max(30, ph*1.5):
                continue
        matches.append(row)
    return matches[0] if len(matches) == 1 else None


def cross(chip):
    x,y,w,h=chip
    return round(x+w-h*.52), round(y+h/2)


def press(*actions):
    assert_doumao()
    shell(CLICK, '-w', '130', *actions)


def read_field(rect, im):
    """复制选中字段回读；清空字段时剪贴板哨兵不会被替换。"""
    x, y, w, h = rect
    click_img(x+w*.30, y+h*.55, im)
    time.sleep(.2)
    shell('/usr/bin/pbcopy', input_text='__DOUMAO_CLIPBOARD_SENTINEL__')
    press('kd:cmd','t:a','ku:cmd','kd:cmd','t:c','ku:cmd')
    time.sleep(.25)
    value = shell('/usr/bin/pbpaste')
    return '' if value == '__DOUMAO_CLIPBOARD_SENTINEL__' else value


def normalize_title(title):
    return re.sub(r'\s+', '', title)


def mark(im, boxes, note_text):
    frame = im.copy()
    for rect, color in boxes:
        x, y, w, h=rect
        cv2.rectangle(frame, (x,y), (x+w,y+h), color, 3)
    cv2.putText(frame, note_text, (15, 55), cv2.FONT_HERSHEY_SIMPLEX,
                .78, (0,0,220), 2, cv2.LINE_AA)
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(PREVIEW), frame)


def save_tag_diagnostic(im, message):
    """将标签弹窗识别失败时的全屏画面保存为一张可覆盖的诊断图。"""
    DIAGNOSTIC.parent.mkdir(parents=True, exist_ok=True)
    result = im.copy()
    finish = find_finish(im)
    if finish:
        x, y, w, h = finish
        cv2.rectangle(result, (x,y), (x+w,y+h), (0,0,255), 3)
    for group in all_chip_rows(im):
        for x,y,w,h in group:
            cv2.rectangle(result, (x,y), (x+w,y+h), (0,185,225), 2)
    cv2.putText(result, 'TAG DIAGNOSTIC - NOT SAVED', (15,54),
                cv2.FONT_HERSHEY_SIMPLEX, .9, (0,0,255), 2)
    cv2.imwrite(str(DIAGNOSTIC),result)
    print(f'标签识别诊断：{message}；找到完成按钮={finish is not None}；候选标签行长度={[len(g) for g in all_chip_rows(im)]}',flush=True)
    print(f'请发送诊断图：{DIAGNOSTIC}',flush=True)


def scroll_to_tags(im):
    """必须先完整滚到编辑弹窗底部，再定位已选标签栏。

    使用已在测试 05 验证的「连续两次画面无明显变化」判断到底。
    不能因为浅蓝色条提前出现，就直接点击——这正是 v0.2 的问题。
    """
    save = find_save(im)
    if save is None:
        raise RuntimeError('无法检测底部保存按钮，确认在「编辑作品资料」页面。')
    sx, sy, sw, sh = save
    H, W = im.shape[:2]
    x0, x1 = max(0, sx + round(.10*sw)), min(W, sx + round(.90*sw))
    y0, y1 = max(0, sy - round(1.10*sw)), sy - round(.09*sw)
    if x1 <= x0 or y1 <= y0 or y1 >= H:
        raise RuntimeError('滚动区域位置异常，停止。')

    # 鼠标移入编辑弹窗内部，而不是浏览器/桌面或底部固定保存按钮。
    scroll_pt = img_to_screen(sx + sw*.52, sy - sw*.26, im)
    assert_doumao()
    pyautogui.moveTo(*scroll_pt, duration=.2)
    previous = im
    stable = 0
    at_bottom = False
    for step in range(16):
        assert_doumao()
        pyautogui.scroll(-8)
        time.sleep(.65)
        current = capture()
        if current.shape != im.shape or find_save(current) is None:
            raise RuntimeError('滚动时编辑窗口或屏幕尺寸变化，已停止。')
        before = previous[y0:y1, x0:x1]
        after = current[y0:y1, x0:x1]
        change = float(np.mean(np.max(cv2.absdiff(before, after), axis=2) > 30))
        print(f'向下滚动 {step+1} 次：画面变化 {change:.2%}', flush=True)
        stable = stable + 1 if change < .006 else 0
        previous = current
        if stable >= 2:
            at_bottom = True
            break
    if not at_bottom:
        save_tag_diagnostic(previous, '未能确认已经滚动到底部')
        raise RuntimeError('滚动到底部失败；为避免误点，不展开标签。')
    save = find_save(previous)
    bar = find_tag_bar(previous, save)
    if bar is None:
        save_tag_diagnostic(previous, '已滚到底部，但没有识别到已选标签栏')
        raise RuntimeError('已滚到底部，但没找到标签栏。请发送 diagnostic_tag.png。')
    print('确认滚到底部，找到标签栏，准备展开。', flush=True)
    return previous, bar


def clean_current(title: str, auto_save: bool = True):
    """Clean the already-open editor. Called only after the parent workflow has checked title.

    This is the validated single-card algorithm, without sys.argv mutation or a
    second command-line argument parser. All UI validation is kept intact.
    """
    from types import SimpleNamespace
    args = SimpleNamespace(title=title, auto_save=auto_save)
    if not title.strip():
        raise RuntimeError('原标题不可为空。')
    if not Path(CLICK).exists():
        raise RuntimeError('未检测到 cliclick，需先通过 Homebrew 安装。')
    print('\n豆猫图纸整理 v0.4.1：清备注、清标签；留在底部检查并保存。')
    print('最终保存：' + ('自动点击一次（若全部检查通过）' if args.auto_save else '不会自动保存'))
    print(f'仅允许修改标题为「{args.title}」的当前作品。')
    print('已在自动化流程中进入编辑窗口；请保持豆猫在前台。')
    print('紧急停止：把鼠标移到左上角。若尚未点击保存，可关闭编辑窗口放弃修改。', flush=True)
    time.sleep(.25)
    assert_doumao()
    original = capture()
    save = find_save(original)
    boxes = form_rects(original, save)
    if not boxes:
        raise RuntimeError('没有找到标题和备注输入框。请先让编辑页面回到顶部。')
    title_rect, note_rect = boxes
    observed_title = read_field(title_rect, original).strip()
    if normalize_title(observed_title) != normalize_title(args.title):
        raise RuntimeError(f'标题不匹配：预期「{args.title}」，实际复制得到「{observed_title}」。未修改。')
    note_before = read_field(note_rect, original)
    if len(note_before) > 256:
        raise RuntimeError('备注长度异常，停止。')
    print(f'标题验证成功；备注现有长度 {len(note_before)}。')
    if note_before:
        click_img(note_rect[0]+note_rect[2]*.30, note_rect[1]+note_rect[3]*.55, original)
        press('kd:cmd','t:a','ku:cmd','kp:delete')
        time.sleep(.6)
        assert_doumao()
        after_clear = capture()
        if after_clear.shape != original.shape or not find_save(after_clear):
            raise RuntimeError('删除备注后编辑页面发生变化，停止。')
        # 读取原来的备注框位置：避免像测试 10C 那样被小幅布局变化误触发停止。
        read_note = read_field(note_rect, after_clear)
        if read_note != '':
            raise RuntimeError('备注未成功清空，安全停止（未保存）。')
    print('备注已清空（尚未保存）。')

    assert_doumao()
    frame = capture()
    frame, bar = scroll_to_tags(frame)
    print('正在点击底部已选标签栏，展开「选择作品标签」…', flush=True)
    click_img(*rect_center(bar), frame)
    # 豆猫 Flutter 弹窗首次出现时有动画；短暂等待并最多观察 4 次。
    modal = None
    finish = None
    chips = None
    for _ in range(4):
        time.sleep(.55)
        assert_doumao()
        modal = capture()
        finish = find_finish(modal)
        if finish is not None:
            chips = selected_chips(modal, finish)
            if chips is not None:
                break
    if finish is None:
        save_tag_diagnostic(modal, '未找到「完成」按钮，可能标签弹窗没有展开')
        raise RuntimeError('标签弹窗未确认打开；未处理任何标签。截图见 diagnostic_tag.png')
    if chips is None:
        save_tag_diagnostic(modal, '已识别「完成」，但未唯一识别已选标签（也可能本来是 0 个）')
        raise RuntimeError('标签弹窗已打开，但标签识别失败；为避免误删已停止。截图见 diagnostic_tag.png')
    expected = len(chips)
    print(f'已检测到同一行的 {expected} 枚选中标签，开始逐个清空。')
    first = chips[:]
    for n in range(expected, 0, -1):
        assert_doumao()
        current = capture()
        finish_now = find_finish(current)
        candidates = selected_chips(current, finish_now, previous=first)
        if candidates is None or len(candidates) != n:
            save_tag_diagnostic(current, f'预期剩余 {n} 枚，无法唯一识别')
            raise RuntimeError(f'预期还有 {n} 枚标签，视觉识别失败，停止。')
        click_img(*cross(candidates[0]), current)
        time.sleep(.75)
        if n > 1:
            assert_doumao()
            remaining = capture()
            after_chips = selected_chips(remaining, find_finish(remaining), previous=first)
            if after_chips is None or len(after_chips) != n-1:
                save_tag_diagnostic(remaining, f'删除后预期 {n-1} 枚')
                raise RuntimeError('删除标签后没有识别到预期数量，停止。')
        else:
            # 最后一次只验证目标已选标签行不再出现；用户仍要目测弹窗 0/5。
            assert_doumao()
            remaining = capture()
            if selected_chips(remaining, find_finish(remaining), previous=first) is not None:
                save_tag_diagnostic(remaining, '最后一次删除后仍识别到疑似标签')
                raise RuntimeError('最后一次删除后仍可能有标签，停止。')
        print(f'已删除一个；估计剩余 {n-1} 枚。', flush=True)

    assert_doumao()
    complete = capture()
    final_btn = find_finish(complete)
    if final_btn is None:
        raise RuntimeError('未找到标签弹窗「完成」，请自行检查，不保存。')
    click_img(*rect_center(final_btn), complete)
    time.sleep(.7)
    assert_doumao()
    current = capture()
    save_now = find_save(current)
    if save_now is None or find_finish(current) is not None:
        raise RuntimeError('未能确认标签弹窗关闭，请手动检查。')
    # v0.4.1: 不再向上滚动查找标题/备注。顶部时已经核对标题，
    # 备注删除后也已经回读为空；弹窗内逐步删除标签，最后确认已选 chip 消失。
    # 现在只检查：标签弹窗确实关闭、已回到原先底部的标签栏、保存按钮没有移动。
    bottom_bar = find_tag_bar(current, save_now)
    if bottom_bar is None:
        save_tag_diagnostic(current, '关闭弹窗后未找到底部标签栏，禁止保存')
        raise RuntimeError('标签弹窗关闭后未找到底部标签栏；本次未保存。')
    old_center = rect_center(bar)
    new_center = rect_center(bottom_bar)
    if abs(old_center[0] - new_center[0]) > 18 or abs(old_center[1] - new_center[1]) > 18:
        raise RuntimeError('底部标签栏位置发生明显变化，禁止保存。')
    original_save = rect_center(find_save(original))
    check_save = rect_center(save_now)
    if max(abs(a-b) for a,b in zip(original_save, check_save)) > 14:
        raise RuntimeError('底部固定保存按钮位置变化，禁止保存。')
    # 注意：当前只通过图像确认标签 chip 已全部移除；尚不具备独立 OCR 读取“0/5”。
    # 先前的清空操作和位置验证都通过之后，才能执行自动保存。
    checked_frame = capture()
    checked_save = find_save(checked_frame)
    checked_bar = find_tag_bar(checked_frame, checked_save)
    if checked_save is None or checked_bar is None or find_finish(checked_frame) is not None:
        raise RuntimeError('最终底部状态异常，禁止保存。')
    if max(abs(a-b) for a,b in zip(rect_center(checked_save), check_save)) > 14:
        raise RuntimeError('保存按钮位置不稳定，禁止保存。')
    mark(checked_frame, [(checked_bar, (0, 210, 240)),
                         (checked_save, (0, 0, 255))],
         'BOTTOM CHECK - READY' if args.auto_save else 'BOTTOM CHECK - NOT SAVED')
    if not args.auto_save:
        print('\n清理动作完成，已在底部检测到标签栏及保存按钮；本次未点击保存。')
        print('请核对：标题未改变，备注为空，已选标签 0/5，作品分类与来源未改变，再手动保存。')
        print('预览图：', PREVIEW)
        return

    # 单张自动保存：需要 --auto-save，且前面的标题、备注、标签识别检查均通过。
    # 不会重复点击；点击不等于已经成功同步，仍需用户重新打开核对。
    assert_doumao()
    current_screen = capture()
    current_save = find_save(current_screen)
    if (current_save is None or find_finish(current_screen) is not None
            or find_tag_bar(current_screen, current_save) is None):
        raise RuntimeError('保存前最后检查失败（底部标签栏或保存按钮未识别），未点击保存。')
    center_before = check_save
    center_after = rect_center(current_save)
    if max(abs(a-b) for a,b in zip(center_before, center_after)) > 14:
        raise RuntimeError('保存按钮移动，未点击保存。')
    print('顶部标题及备注已验证、底部标签清理通过；正在单击一次保存按钮…', flush=True)
    click_img(*center_after, current_screen)
    time.sleep(1.8)
    front_after = capture()
    # 日志明确记录“已点击”，不将它误说成云端同步成功。
    LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {'time': datetime.now().isoformat(timespec='seconds'),
             'title': args.title, 'note_before_length': len(note_before),
             'removed_tags': expected, 'save_clicked': True,
             'edit_dialog_disappeared': find_save(front_after) is None}
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')
    print('\n已自动点击一次「保存并同步作品详情」。')
    if event['edit_dialog_disappeared']:
        print('编辑窗口的保存按钮已消失（界面已变化）。')
    else:
        print('仍检测到保存按钮；可能在同步、保存失败或页面未关闭，请人工检查。程序不会重复点击。')
    print('请手动重新打开本图纸，核对标题、备注为空、标签 0/5、分类未变。')
    print('操作日志：', LOG)


