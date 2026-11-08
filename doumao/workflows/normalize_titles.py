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

from datetime import datetime
import json
from pathlib import Path
import time

import cv2
import numpy as np
import pyautogui

from ..core import scrolling as scroll_util
from ..core import list_view
from ..core.title_editor import edit_selected_card, resolve_click_command
from ..core.title_edit_contract import EditOutcome, EditResult
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


def score_fp(a, b):
    return float(np.mean(cv2.absdiff(a, b)))


def previously_seen(fp, known):
    return any(score_fp(fp, prev) < 7.5 for prev in known)


from ..title_rules import load_rule


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


def diagnostics(reason, frame=None):
    try:
        list_view.save_title_diagnostic(DIAGNOSTIC, frame=frame)
    except Exception:
        # Diagnostics must not mask the original workflow error.
        pass
    emit('stopped', reason=str(reason))


def edit_event(name: str, **values):
    """Preserve the established title-command messages with a shared editor."""
    emit(name, **values)
    index = values.get('index')
    old = values.get('old')
    new = values.get('proposed') if name == 'inspected' else values.get('new')
    if name == 'inspected' and new is not None:
        print(f'  [{index}] {old!r} → {new!r}', flush=True)
    elif name == 'skipped':
        print(f'  [{index}] {old!r}：标题不符合转换规则，跳过保存。', flush=True)
    elif name == 'would_change':
        print('  预览模式：不修改输入框，不保存。', flush=True)
    elif name == 'save_prepared':
        print('  新标题回读准确；本功能未操作备注、标签、分类；准备保存。', flush=True)
    elif name == 'save_clicked':
        print('  已点击保存；正在等待返回列表。', flush=True)
    elif name == 'save_returned_list':
        print('  已确认编辑弹窗关闭并返回列表。', flush=True)


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


def scroll_once(before, scroll, xy):
    scanner.assert_app()
    pyautogui.moveTo(*xy, duration=.12)
    pyautogui.scroll(-scroll)
    time.sleep(.85)
    after = list_view.shot()
    list_view.check_list(after)
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
    first = list_view.shot()
    list_view.check_list(first)
    sw, sh = pyautogui.size()
    scroll_xy = (round(sw*.365), round(sh*.57))
    initial_cards = list_view.card_rows(first)
    first_flagged = sum(title_gap_candidate(first, c)[0] for c in initial_cards)
    print(f'首屏完整卡片 {len(initial_cards)} 张；视觉字距提示 {first_flagged} 张（仅供诊断，不参与跳过）。', flush=True)
    if args.expect_visible is not None and len(initial_cards) != args.expect_visible:
        raise RuntimeError(f'首屏检测到 {len(initial_cards)} 张卡片，不等于预期的 {args.expect_visible} 张；未修改。')
    preview(first, initial_cards, 0)
    if args.list_preview:
        print(f'只读列表预览已完成（未打开作品）：{PREVIEW}', flush=True)
        return
    click_command = resolve_click_command()
    emit('session_started', limit=args.limit, auto_save=args.auto_save,
         first_visible=first_flagged, current_screen_only=args.current_screen_only)
    seen = []  # 已打开检查的缩略图指纹
    scanned = []  # 已在列表识别的缩略图指纹（包括未打开的卡片）
    inspected = changed = skips = nscrolls = 0
    stable = 0
    bottom = False
    while inspected < args.limit:
        frame = list_view.shot()
        list_view.check_list(frame)
        if frame.shape != first.shape:
            raise RuntimeError('运行期间截图分辨率变化，停止。')
        cards = list_view.card_rows(frame)
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
            edit = edit_selected_card(
                target, frame, inspected+1, args.auto_save, rule,
                click_command=click_command, emit=edit_event)
            if not isinstance(edit, EditResult):
                raise RuntimeError('共享编辑器没有返回结构化结果，已停止。')
            if edit.outcome is EditOutcome.RETURNED_TO_LIST and args.auto_save:
                changed += 1
            elif edit.outcome is EditOutcome.SKIPPED:
                skips += 1
            elif edit.outcome is EditOutcome.PREVIEW and not args.auto_save:
                pass
            else:
                raise RuntimeError(f'标题编辑状态不符合当前模式：{edit.outcome.value}，已停止。')
            seen.append(target['fp'])
            inspected += 1
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
            check = list_view.shot()
            list_view.check_list(check)
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


