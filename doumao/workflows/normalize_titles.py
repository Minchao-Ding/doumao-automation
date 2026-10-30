#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豆猫 · 标题规范化：基于准确标题读取的通用规则框架，当前只配置饮品。

核心策略：
* 不按标签、字距筛选；遍历可见卡片并读取真实原标题，保证不因字距筛选漏报。
* 当前规则仅处理恰好一个 ASCII 空格；后续规则由独立配置控制，无需输入作品名。
* 仅将恰好一个内部 ASCII 空格（无 ｜ / \n / \t）的标题改为「｜」。
* 绝不调用旧的清备注或清标签流程；旧模块仅复用界面定位/导航。
* 根据图纸缩略图像素指纹去重，不受标题被修改后卡片文本变化影响。
* 只处理完整进入屏幕的卡片；每次小幅滚动，并检测疑似到底。
* 操作失败时保留截图与 JSONL 日志，未确认成功不继续下一张。
* 本版对「仓库 → 食物 → 饮品」专用，用户必须确认在正确文件夹。
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import pyautogui

from ..core import metadata_editor as cleaner
from ..core import navigation as nav
from ..core import batch_cleaner as proven
from ..core import scrolling as scroll_util
from ..core import tag_scanner as scanner

ROOT = Path.home() / 'doumao-automation'
LOG = ROOT / 'logs' / 'refactored_title_reader.jsonl'
DIAGNOSTIC = ROOT / 'screenshots' / 'refactored_title_diagnostic.png'
PREVIEW = ROOT / 'screenshots' / 'refactored_title_cards.png'
EXPECTED_CARDS = 30
pyautogui.FAILSAFE = True
pyautogui.PAUSE = .18


def emit(event: str, **fields):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    data = {'time': datetime.now().isoformat(timespec='seconds'), 'event': event, **fields}
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')


def shot():
    scanner.assert_app()
    return proven.screenshot()


def check_list(frame):
    if cleaner.find_save(frame) is not None:
        raise RuntimeError('检测到编辑弹窗，请关闭后回到饮品列表。')
    if nav.find_detail_modal(frame) is not None:
        raise RuntimeError('检测到作品详情弹窗，请先关闭。')
    h, w = frame.shape[:2]
    if w < 1300 or h < 800 or not (1.38 < w / h < 1.65):
        raise RuntimeError('当前截图比例与已验证的 Mac 界面不一致，不自动点击。')


def card_rows(frame):
    """通过各列卡片内的浅蓝背景识别完整卡片，支持末排只剩两张。

    不是 OCR，也不是根据标签识别。基于用户实机截图验证的四列网格。
    返回列表 (列号, 行顶部Y, 像素指纹)。指纹只取图像，不取卡片标题。
    """
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
                # 下半截在屏幕外，继续滚动后再处理，绝不点击被截断的卡片。
                continue
            # 防止侧边栏、弹窗、列表以外的宽大浅色区域误检。
            if not (.78*step < bottom-top < 1.25*step):
                continue
            x0, x1 = round(left+(col+.12)*step), round(left+(col+.90)*step)
            y0, y1 = round(top+.06*step), round(top+.73*step)
            art = frame[y0:y1, x0:x1]
            if art.size == 0 or np.std(art) < 9:
                # 未加载或全白的空卡片不处理。
                continue
            fp = cv2.resize(art, (60, 70), interpolation=cv2.INTER_AREA)
            cx, cy = round(left+(col+.50)*step), round(top+.43*step)
            if not (.13*w < cx < .70*w and .17*h < cy < .90*h):
                continue
            detected.append({'col': col, 'top': top, 'click': (cx,cy), 'fp': fp})
    detected.sort(key=lambda c: (c['top'], c['col']))
    # 正常四列网格中，每一排各列的 top 差距通常小于 2 px。
    if len(detected) > 12:
        raise RuntimeError(f'视觉识别到 {len(detected)} 张卡片，超过预期，停止。')
    return detected


def score_fp(a, b):
    return float(np.mean(cv2.absdiff(a, b)))


def previously_seen(fp, known):
    return any(score_fp(fp, prev) < 7.5 for prev in known)


from ..title_rules import DEFAULT_RULE, load_rule, proposal


def find_title_only(im, save):
    """只识别标题框：不依赖备注高度、备注内容或标签栏。

    用保存按钮作编辑弹窗的尺度锚点，找基本信息区内唯一的浅色短输入框。
    标题位置以用户实际编辑窗口截图的相对位置进行离线校准。
    """
    if save is None:
        return None
    sx, sy, sw, _ = save
    H, W = im.shape[:2]
    x0 = max(0, sx + round(sw * .30))
    x1 = min(W, sx + round(sw * .80))
    y0 = max(0, sy - round(sw * 1.04))
    y1 = min(H, sy - round(sw * .79))
    if x1 <= x0 or y1 <= y0:
        return None
    rgb = im[y0:y1, x0:x1, ::-1].astype(np.int16)
    r, g, b = [rgb[:, :, k] for k in range(3)]
    pale = ((244 <= r) & (r <= 251) & (g >= 248) & (b >= 250))
    dense = (pale.mean(axis=1) > .78).astype(np.int16)
    trans = np.diff(np.r_[0, dense, 0])
    found = []
    for a, z in zip(np.where(trans == 1)[0], np.where(trans == -1)[0]):
        top, bottom = y0 + int(a), y0 + int(z)
        height = bottom - top
        if not (.050 * sw < height < .125 * sw):
            continue
        # 原有编辑窗口中标题顶距保存按钮约为 0.88 个按钮宽度。
        # 排除下方备注框与上方封面选择区；宁可停止也不点击不确定位置。
        if not (sy - .995 * sw < top < sy - .805 * sw):
            continue
        found.append((sx, top, sw, height))
    return found[0] if len(found) == 1 else None


def wait_for_title_editor():
    """只等待标题框出现；不再调用旧版要求标题+备注成对存在的函数。"""
    last = None
    saw_save = False
    for _ in range(12):
        time.sleep(.45)
        scanner.assert_app()
        last = shot()
        save = cleaner.find_save(last)
        if save is None:
            continue
        saw_save = True
        title_rect = find_title_only(last, save)
        if title_rect is not None:
            return last, save, title_rect
    if not saw_save:
        raise RuntimeError('没有确认进入编辑页，未修改。')
    print('已确认编辑弹窗，但标题尚未出现；尝试在弹窗内部向上滚动。', flush=True)
    frame = last
    for attempt in range(8):
        scanner.assert_app()
        save = cleaner.find_save(frame)
        if save is None:
            raise RuntimeError('滚动恢复时丢失编辑页保存按钮，未修改。')
        sx, sy, sw, _ = save
        px, py = cleaner.img_to_screen(sx + .52*sw, sy - .26*sw, frame)
        pyautogui.moveTo(px, py, duration=.12)
        pyautogui.scroll(7)
        time.sleep(.60)
        frame = shot()
        save = cleaner.find_save(frame)
        if save is None:
            raise RuntimeError('向上滚动后未确认编辑页，未修改。')
        rect = find_title_only(frame, save)
        if rect is not None:
            print(f'向上调整 {attempt+1} 次后找到标题框。', flush=True)
            return frame, save, rect
    raise RuntimeError('已确认编辑页，但无法唯一识别标题框；未修改。')


def read_title_only(frame, rect):
    title = cleaner.read_field(rect, frame)
    if not title or len(title) > 64 or title.startswith('__DOUMAO_'):
        raise RuntimeError(f'读取原标题异常：{title!r}')
    if '\n' in title or '\r' in title:
        raise RuntimeError('原标题存在换行，停止，避免输入框误定位。')
    return title


def title_gap_candidate(frame, card):
    """对列表标题做字间距筛选；返回 (bool, 最大间距, 正常间距中位数)。

    此处不读标题内容，也不认为字距检测是准确的 OCR。只是减少需要打开的卡片。
    是否真的包含 1 个 ASCII 空格，必须进入编辑页用剪贴板读取原标题确认。
    """
    H, W = frame.shape[:2]
    step = (.691 - .115) * W / 4
    start = (.115 * W) + card['col'] * step
    x0, x1 = round(start + .02*step), round(start + .72*step)
    y0, y1 = round(card['top'] + .956*step), round(card['top'] + 1.065*step)
    if min(x0, y0) < 0 or x1 > W or y1 > H:
        return False, 0, 0
    roi = frame[y0:y1, x0:x1]
    if roi.size == 0:
        return False, 0, 0
    blue, green, red = cv2.split(roi)
    ink = ((red < 90) & (green < 125) & (blue < 155) &
           (blue.astype(np.int16) > red.astype(np.int16) + 5))
    occupied = (ink.sum(axis=0) >= 2).astype(np.int16)
    transition = np.diff(np.r_[0, occupied, 0])
    runs = list(zip(np.where(transition == 1)[0], np.where(transition == -1)[0]))
    if len(runs) < 3 or ink.sum() < 80:
        return False, 0, 0
    gaps = [int(runs[i+1][0] - runs[i][1]) for i in range(len(runs)-1)]
    largest = max(gaps)
    typical = float(np.median(gaps))
    # 在 2047 px 的实际截图里，普通字间距约 3–5px，有空格的目标约 8px。
    # 按屏幕宽度缩放阈值；模糊或无明显空格的标题不会自动打开。
    min_gap = max(6.5, 7.0 * W / 2047)
    likely = largest >= min_gap and largest >= typical + 3.5
    return bool(likely), largest, typical


def go_back_to_list():
    """只使用 Escape 返回；如果弹窗没关闭，不猜测 X 的位置。"""
    for _ in range(3):
        scanner.assert_app()
        f = shot()
        if cleaner.find_save(f) is None and nav.find_detail_modal(f) is None:
            return f
        pyautogui.press('esc')
        time.sleep(.75)
    f = shot()
    if cleaner.find_save(f) is not None or nav.find_detail_modal(f) is not None:
        raise RuntimeError('Esc 未能关闭弹窗，请手动关闭后再继续；不盲目点击。')
    return f


def diagnostics(reason, frame=None):
    if frame is None:
        try:
            frame = shot()
        except Exception:
            frame = None
    if frame is not None:
        DIAGNOSTIC.parent.mkdir(parents=True, exist_ok=True)
        view = frame.copy()
        cv2.putText(view, 'v1.1 TITLE DIAGNOSTIC', (14,52),
                    cv2.FONT_HERSHEY_SIMPLEX,.8,(0,0,255),2)
        cv2.imwrite(str(DIAGNOSTIC), view)
    emit('stopped', reason=str(reason))


def preview(frame, cards, opened_count):
    vis = frame.copy()
    flagged = 0
    for c in cards:
        x, y = c['click']
        suspicious, gap, _ = title_gap_candidate(frame, c)
        col = (0, 185, 0) if suspicious else (165, 165, 165)
        if suspicious:
            flagged += 1
        cv2.circle(vis, (x,y), 12, col, 3)
        cv2.putText(vis, f'G{gap}', (x-20,y-25),
                    cv2.FONT_HERSHEY_SIMPLEX,.6,col,2)
    cv2.putText(vis, f'REFAC checked={opened_count}, visual_hints={flagged}',(12,60),
                cv2.FONT_HERSHEY_SIMPLEX,.75,(0,0,255),2)
    PREVIEW.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(PREVIEW), vis)


def handle_card(target, frame, number, do_save, rule):
    """仅打开作品/修改标题，不调用 cleaner.main（后者会清备注与标签）。"""
    cx, cy = target['click']
    scanner.assert_app()
    proven.v08.screen_click(cx, cy, frame)
    detail, modal = proven.v08.wait_for_detail()
    pen = nav.find_pencil(detail, modal)
    if pen is None:
        raise RuntimeError('未能唯一定位详情弹窗中的蓝色铅笔，未编辑。')
    proven.v08.screen_click(*pen[0], detail)
    editor, _, title_rect = wait_for_title_editor()
    old = read_title_only(editor, title_rect)
    new = proposal(old, rule)
    emit('inspected', index=number, old=old, proposed=new)

    if new is None:
        print(f'  [{number}] {old!r}：标题不符合转换规则，跳过保存。', flush=True)
        go_back_to_list()
        emit('skipped', index=number, old=old)
        return 'skipped', old, old

    print(f'  [{number}] {old!r} → {new!r}', flush=True)
    if not do_save:
        print('  预览模式：不修改输入框，不保存。', flush=True)
        go_back_to_list()
        emit('would_change', index=number, old=old, new=new)
        return 'preview', old, new

    # 只识别标题字段。此前已经清空的备注无需读取或参与编辑框定位。
    now = shot()
    title_rect = find_title_only(now, cleaner.find_save(now))
    if title_rect is None:
        raise RuntimeError('写入前无法唯一识别标题框，未修改。')
    original_again = read_title_only(now, title_rect)
    if original_again != old:
        raise RuntimeError(f'写入前标题不同：{old!r} → {original_again!r}，未修改。')
    current = shot()
    title_rect = find_title_only(current, cleaner.find_save(current))
    if title_rect is None:
        raise RuntimeError('粘贴前标题框定位失败，未修改。')
    x, y, w, h = title_rect
    cleaner.click_img(x+w*.30, y+h*.55, current)
    cleaner.shell('/usr/bin/pbcopy', input_text=new)
    cleaner.press('kd:cmd', 't:a', 'ku:cmd', 'kd:cmd', 't:v', 'ku:cmd')
    time.sleep(.65)
    scanner.assert_app()

    after, _, after_rect = wait_for_title_editor()
    actual = read_title_only(after, after_rect)
    if actual != new:
        raise RuntimeError(f'写入后标题回读不一致：{actual!r} ≠ {new!r}；未保存。')
    print('  新标题回读准确；本功能未操作备注、标签、分类；准备保存。', flush=True)
    latest = shot()
    button = cleaner.find_save(latest)
    if button is None or find_title_only(latest, button) is None:
        raise RuntimeError('保存前未能确认编辑页及标题框，未保存。')
    bx, by, bw, bh = button
    # 保存前不滚动、不操作标签或分类。
    cleaner.click_img(bx+bw*.50, by+bh*.50, latest)
    emit('save_clicked', index=number, old=old, new=new)
    print('  已点击保存；正在等待返回列表。', flush=True)
    back = proven.wait_for_list_after_save()
    check_list(back)
    emit('save_returned_list', index=number, old=old, new=new)
    print('  已确认编辑弹窗关闭并返回列表。', flush=True)
    return 'saved', old, new


def scroll_once(before, scroll, xy):
    scanner.assert_app()
    pyautogui.moveTo(*xy, duration=.12)
    pyautogui.scroll(-scroll)
    time.sleep(.85)
    after = shot()
    check_list(after)
    if before.shape != after.shape:
        raise RuntimeError('滚动后截图尺寸改变。')
    return after, scroll_util.change_fraction(before, after)


def run(args):
    rule = load_rule(args.rule_config)
    print('豆猫 · 标题规范化：通用标题读取与规则转换框架；目前仅启用饮品命名规则。')
    print(f'目标文件夹：{rule["folder"]}；必须由用户预先打开正确文件夹。')
    print('⚠ 不会自动读取或核对文件夹名称；运行前请人工确认。')
    print('为避免漏检，会打开完整可见的图纸读取真实标题；不符合规则绝不保存。')
    print('列表按缩略图去重；不依赖标签、作品名、字间距或手工指定位置。')
    print(f'本轮最多检查 {args.limit} 张不同图纸；每次列表滚动 {args.scroll} 格。')
    print('模式：' + ('自动保存' if args.auto_save else '只读预览，不输入/保存'))
    print('请把目标文件夹列表滚到最顶部、关闭弹窗。5 秒内切到豆猫。',flush=True)
    time.sleep(5)
    first = shot()
    check_list(first)
    sw, sh = pyautogui.size()
    scroll_xy = (round(sw*.365), round(sh*.57))
    initial_cards = card_rows(first)
    first_flagged = sum(title_gap_candidate(first, c)[0] for c in initial_cards)
    print(f'首屏完整卡片 {len(initial_cards)} 张；视觉字距提示 {first_flagged} 张（仅供诊断，不参与跳过）。', flush=True)
    if args.expect_visible is not None and len(initial_cards) != args.expect_visible:
        raise RuntimeError(f'首屏检测到 {len(initial_cards)} 张卡片，不等于预期的 {args.expect_visible} 张；未修改。')
    preview(first, initial_cards, 0)
    if args.list_preview:
        print(f'只读列表预览已完成（未打开作品）：{PREVIEW}', flush=True)
        return
    emit('session_started', limit=args.limit, auto_save=args.auto_save,
         first_visible=first_flagged, current_screen_only=args.current_screen_only)
    seen = []  # 已打开检查的缩略图指纹
    scanned = []  # 已在列表识别的缩略图指纹（包括未打开的卡片）
    inspected = changed = skips = nscrolls = 0
    stable = 0
    bottom = False
    while inspected < args.limit:
        frame = shot()
        check_list(frame)
        if frame.shape != first.shape:
            raise RuntimeError('运行期间截图分辨率变化，停止。')
        cards = card_rows(frame)
        for c in cards:
            if not previously_seen(c['fp'], scanned):
                scanned.append(c['fp'])
        # 所有卡片都必须通过真实文本检查；视觉字距只能用于优先级排序。
        new_cards = [c for c in cards if not previously_seen(c['fp'], seen)]
        new_cards.sort(key=lambda c: (not title_gap_candidate(frame,c)[0], c['top'], c['col']))
        preview(frame, cards, inspected)
        if new_cards:
            target = new_cards[0]
            print(f'本屏 {len(cards)} 张完整卡片，尚未读取真实标题 {len(new_cards)} 张；'
                  f'现在检查第 {inspected+1} 张。',flush=True)
            status, old, new = handle_card(target, frame, inspected+1, args.auto_save, rule)
            seen.append(target['fp'])
            inspected += 1
            if status == 'saved':
                changed += 1
            elif status == 'skipped':
                skips += 1
            stable = 0
            print(f'进度：已检查 {inspected}，已改名 {changed}，跳过 {skips}。',flush=True)
            time.sleep(.45)
            continue
        if args.current_screen_only:
            print('当前屏幕可见的不同作品已检查；按参数不滚动到下一屏。',flush=True)
            break
        if nscrolls >= args.max_scrolls:
            print('达到滚动安全上限，未确认全部扫描完成。',flush=True)
            break
        after, change = scroll_once(frame, args.scroll, scroll_xy)
        nscrolls += 1
        stable = stable+1 if change < .006 else 0
        print(f'  列表滚动 {nscrolls}：变化 {change:.2%}，连续静止 {stable}/3。',flush=True)
        emit('scroll', index=nscrolls, difference=round(change,5), stable=stable)
        if stable >= 3:
            time.sleep(1.4)
            check = shot()
            check_list(check)
            if scroll_util.change_fraction(after, check) < .006:
                bottom = True
                break
            stable = 0

    print(f'\n结果：列表发现约 {len(scanned)} 张不同缩略图，'
          f'核对实际标题 {inspected} 张；实际改名 {changed} 张；无需改名 {skips} 张；滚动 {nscrolls} 轮。')
    print('扫描状态：'+('疑似抵达列表底部' if bottom else '本次检查上限/当前屏幕模式/滚动上限'))
    if len(scanned) < EXPECTED_CARDS:
        print(f'提示：目前识别到约 {len(scanned)}/{EXPECTED_CARDS} 张不同缩略图。'
              '不足 30 张时不能断言所有标题均已筛查；缩略图去重本身也有误差。')
    else:
        print('列表视觉扫描见到约 30 张不同缩略图。需核对已检查数量与列表覆盖范围。')
    if inspected < EXPECTED_CARDS:
        print(f'已读取原标题 {inspected}/{EXPECTED_CARDS} 张；尚不能声称整个饮品文件夹标题全部检查完成。')
    if args.expected_changes is not None and changed != args.expected_changes:
        print(f'提醒：本轮实际改名 {changed}，与预期 {args.expected_changes} 不同；请检查日志或是否分轮执行。')
    print('重要：仅通过编辑框真实文本核对过的作品计入检查完成；缩略图指纹去重可能存在误差。')
    emit('session_finished', inspected=inspected, changed=changed, skipped=skips,
         scan_unique=len(scanned), scrolls=nscrolls, bottom_likely=bottom)
    print(f'日志：{LOG}\n识别预览：{PREVIEW}',flush=True)


