#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豆猫 · 元数据清理（稳定流程移植） — 饮品文件夹：多格跨屏滚动，清空「带标签」图纸的备注和标签。

专用规则：只在用户已经进入「仓库 / 食物 / 饮品」后运行。
标签显示 = 待清理；无标签 = 直接跳过，不打开作品。

基于在用户 Mac 上成功的 v0.9b (自动处理两张、保存并在列表验证标签消失)
以及 v1.0b (自动滚动至疑似底部)。两个程序仍作为独立模块保留。

重要限制：v0.7b 标签检测主要识别同一行至少两枚标签；单标签、换行或遮挡
可能漏检，不能把程序输出的“疑似到底”理解为 100% 全部整理完毕。
此工具会真实删除当前作品的备注和关联标签并自动保存，不可逆。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pyautogui

from ..core import batch_cleaner as proven_batch
from ..core import scrolling as scroll_lib
from ..core import tag_scanner as scanner
from ..core import metadata_editor as cleaner
from ..core import navigation as navigator
from ..core import card_picker as selector

ROOT = Path.home() / 'doumao-automation'
LOG = ROOT / 'logs' / 'refactored_clean_metadata.jsonl'
DIAGNOSTIC = ROOT / 'screenshots' / 'refactored_clean_diagnostic.png'
pyautogui.FAILSAFE = True
pyautogui.PAUSE = .18


def emit(event: str, **values):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    row = dict(time=datetime.now().isoformat(timespec='seconds'), event=event, **values)
    with LOG.open('a', encoding='utf-8') as file:
        file.write(json.dumps(row, ensure_ascii=False) + '\n')


def frame() -> np.ndarray:
    scanner.assert_app()
    return proven_batch.screenshot()


def ensure_clean_list(img: np.ndarray):
    if cleaner.find_save(img) is not None or navigator.find_detail_modal(img) is not None:
        raise RuntimeError('当前有作品详情或编辑弹窗。请关闭全部弹窗，返回饮品图纸列表。')


def ensure_layout(img: np.ndarray):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = scroll_lib.grid_region(img)
    sw, sh = pyautogui.size()
    if w < 900 or h < 600 or x1 - x0 < 280 or y1 - y0 < 300:
        raise RuntimeError('当前分辨率或列表区域与已测试的 Mac 布局差异过大。')
    if not (.55 <= w / sw <= 3.1 and .55 <= h / sh <= 3.1):
        raise RuntimeError('截图坐标与屏幕坐标比例异常，停止。')
    return (round(sw * .365), round(sh * .57))


def diagnostic(img: np.ndarray, reason: str):
    try:
        DIAGNOSTIC.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(DIAGNOSTIC), img)
        print(f'诊断截图（每次覆盖）：{DIAGNOSTIC}')
    except Exception:
        pass
    emit('stopped', reason=reason)


def edge_recovery_direction(groups: list, img: np.ndarray) -> int:
    """如果所有无法安全点击的标签都位于屏幕边缘，返回应小步滚动的方向。

    -1: 向下，露出屏幕底边被裁切的图纸；
    +1: 向上，让屏幕顶边被裁切的图纸回到可点击位置；
     0: 横向位置/布局有歧义，必须停止。

    注意这里优先修复顶部标签，避免连续大步滚动后跳过某一行。
    """
    if not groups:
        return 0
    h, w = img.shape[:2]
    delta_y = min(round(h * .085), round(w * .08))
    positions = []
    for x0, y0, x1, y1 in groups:
        cx = (x0+x1)/2
        cy = y1 + delta_y
        # 点击点横向范围异常不属于滚动裁切，严禁盲目恢复。
        if not (.13*w < cx < .76*w):
            return 0
        positions.append(cy)
    too_high = [cy for cy in positions if cy <= .17*h]
    too_low  = [cy for cy in positions if cy >= .90*h]
    if len(too_high) + len(too_low) != len(positions):
        # 存在中间区域的标签却无法安全点击：可能是识别不一致。
        return 0
    # 优先救回顶边被裁切的图纸，否则向下露出底边的图纸。
    return 1 if too_high else (-1 if too_low else 0)


def safety_check_candidates(img: np.ndarray, groups: list):
    """返回 (候选, 应对边缘裁切的滚动方向)。不在不确定位置点击。"""
    if len(groups) > 12:
        raise RuntimeError(f'当前屏幕检测到 {len(groups)} 组标签，超过已验证上限 12。')
    if not groups:
        return None, 0
    try:
        count, candidate = selector.find_first_candidate(img)
    except RuntimeError as e:
        direction = edge_recovery_direction(groups, img)
        if direction:
            return None, direction
        raise RuntimeError(
            f'检测到 {len(groups)} 组标签但没有安全点击点；无法确认是上下边缘裁切，停止：{e}'
        ) from e
    if count != len(groups):
        raise RuntimeError('候选总数前后不一致，停止。')
    return candidate, 0


def maybe_bottom(prev: np.ndarray, cur: np.ndarray, stable: int) -> bool:
    if stable < 3:
        return False
    # 惰性加载可能发生在滚动停止后：再等待并检查一次，避免把网络延迟误判为底部。
    time.sleep(1.6)
    check = frame()
    ensure_clean_list(check)
    if scroll_lib.change_fraction(cur, check) >= .006:
        return False
    if scanner.scan_tag_groups(check):
        return False
    return True


def run(limit: int, max_scrolls: int, edge_scroll: int, scan_scroll: int):
    print('\n豆猫 · 元数据清理（稳定流程移植） — 饮品文件夹批量清理（不修改标题）。')
    print('仅适用于「仓库 → 食物 → 饮品」。本版不会自动检查文件夹名称，请务必人工确认！')
    print('只有在图纸卡片上识别到 2–5 个同行标签才会打开，没标签的图纸直接跳过。')
    print('会清空符合条件的作品备注和全部已选标签，并自动点击保存；不会修改标题/分类/文件夹/图纸。')
    print(f'本次最多保存 {limit} 张，最多滚动 {max_scrolls} 次。')
    print('请自行备份重要资料。运行中遇到识别异常会立即停止。')
    print(f'5 秒内切回豆猫饮品列表，关闭弹窗。边缘修正每次 {edge_scroll} 格，常规下滑每次 {scan_scroll} 格。鼠标到左上角可停止。', flush=True)
    time.sleep(5)

    first = frame()
    ensure_clean_list(first)
    scroll_xy = ensure_layout(first)
    n_saved, n_scrolls, stable, last_img, bottom = 0, 0, 0, first, False
    edge_retries = 0
    emit('start', limit=limit, max_scrolls=max_scrolls, edge_scroll=edge_scroll, scan_scroll=scan_scroll)

    while n_saved < limit:
        screen = frame()
        ensure_clean_list(screen)
        if screen.shape != first.shape:
            raise RuntimeError('屏幕分辨率变化，停止。')
        groups = scanner.scan_tag_groups(screen)
        candidate, edge_direction = safety_check_candidates(screen, groups) if groups else (None, 0)
        if edge_direction:
            if edge_retries >= 18:
                raise RuntimeError('已尝试 18 次分组滚动调整边缘位置，仍无法安全点击；请查看诊断截图。')
            if n_scrolls >= max_scrolls:
                raise RuntimeError('已达到滚动上限，边缘图纸尚未进入安全点击范围。')
            # 豆猫滚动不够灵敏，一次发送多格再检查；每组滚动后必须重新截图识别。
            before = screen
            scanner.assert_app()
            pyautogui.moveTo(*scroll_xy, duration=.12)
            pyautogui.scroll(edge_direction * edge_scroll)
            time.sleep(.8)
            after = frame()
            ensure_clean_list(after)
            change = scroll_lib.change_fraction(before, after)
            n_scrolls += 1
            edge_retries += 1
            stable = 0
            print(f'边缘修正 {edge_retries}/18：{"向上" if edge_direction > 0 else "向下"}滚动 {edge_scroll} 格后重新检查；画面变化 {change:.2%}。', flush=True)
            emit('edge_reframe', direction=edge_direction, attempt=edge_retries, scroll=n_scrolls, change=round(change,5))
            if change < .003:
                raise RuntimeError('边缘修正时画面几乎未移动；可能滚动容器不对，停止。')
            continue
        if candidate is not None:
            print(f'\n[{n_saved + 1}/{limit}] 当前视图识别到 {len(groups)} 组待整理标签，开始处理最靠上、最靠左的一张。', flush=True)
            old_log_size = proven_batch.LOG.stat().st_size if proven_batch.LOG.exists() else 0
            # 直接运行已经在 Mac 上验证成功的完整单张流程；里面会：
            # 自动开图、识别铅笔、验证原标题、清备注、清标签、自动保存、
            # 确认返回列表且标签组减一。任何步骤失败都抛异常并停止。
            ok = proven_batch.run_one(n_saved + 1, limit)
            if not ok:
                raise RuntimeError('识别到待整理标签但单张流程未处理，状态不明确。')
            n_saved += 1
            stable = 0
            edge_retries = 0
            last_img = frame()
            # v0.9b 成功记录包含具体标题，避免依赖屏幕 OCR 猜测。
            title = ''
            try:
                with proven_batch.LOG.open('rb') as file:
                    file.seek(old_log_size)
                    new_rows = [json.loads(t) for t in file.read().decode('utf-8').splitlines() if t.strip()]
                done_rows = [t for t in new_rows if t.get('result') == 'verified_on_list']
                if len(done_rows) != 1:
                    raise ValueError('新操作日志中没有唯一成功记录')
                title = done_rows[0]['title']
            except Exception as error:
                raise RuntimeError('已执行保存，但无法可靠读取本次已保存的标题；停止以避免重复处理。') from error
            emit('saved_verified', title=title, index=n_saved, scrolls=n_scrolls)
            print(f'本次已成功保存 {n_saved} 张；刚完成：{title}。', flush=True)
            time.sleep(.85)
            continue

        # 当前画面没有识别到标签，保守地小幅滚动，保持跨屏重叠。
        edge_retries = 0
        # 不再把“下沿标签尚不可点”当作致命错误。
        if n_scrolls >= max_scrolls:
            print(f'已达到安全滚动上限 {max_scrolls} 次，不能确认整个文件夹已完成。')
            emit('max_scrolls', saved=n_saved, scrolls=n_scrolls)
            break
        before = screen
        scanner.assert_app()
        pyautogui.moveTo(*scroll_xy, duration=.12)
        pyautogui.scroll(-scan_scroll)
        time.sleep(.72)
        after = frame()
        ensure_clean_list(after)
        if after.shape != before.shape:
            raise RuntimeError('滚动后截图尺寸改变，停止。')
        change = scroll_lib.change_fraction(before, after)
        n_scrolls += 1
        stable = stable + 1 if change < .006 else 0
        print(f'下滑第 {n_scrolls} 组（每组 {scan_scroll} 格），内容变化 {change:.2%}，连续静止 {stable}/3。', flush=True)
        emit('scrolled', scroll=n_scrolls, change=round(change, 5), stable=stable)
        if stable >= 3:
            # 若仍有标签，即便点击位置不安全，也不能宣称整个文件夹已完成。
            remaining_edge_groups = scanner.scan_tag_groups(after)
            if remaining_edge_groups:
                raise RuntimeError(
                    f'连续 3 次滚动后画面不再移动，但仍看到 {len(remaining_edge_groups)} 组标签；'
                    '可能被遮挡或滚动容器异常。已停止，请检查诊断截图。'
                )
            if maybe_bottom(before, after, stable):
                bottom = True
                print('已连续三次检测到页面无变化，且延迟复查没有发现新的标签；疑似到达底部。')
                emit('bottom_likely', saved=n_saved, scrolls=n_scrolls)
                break
            stable = 0
        last_img = after

    status = '疑似滚动到底' if bottom else ('达到本次处理数量上限' if n_saved >= limit else '尚未确认到底')
    emit('finished', saved=n_saved, scrolls=n_scrolls, status=status)
    print(f'\n本轮完成：自动保存 {n_saved} 张，列表下滑 {n_scrolls} 次，状态：{status}。')
    print('无标签图纸已跳过且未打开；标题未修改。')
    print('注意：目前图像识别可能漏掉单个标签、换行或被遮挡的标签。')
    print('操作明细：', LOG)
    print('抽查保存后的作品；如发生异常，先不要重复运行。')



def edge_test(edge_scroll: int):
    """只读边缘滚动检查；不进入详情、不编辑、不保存。"""
    print('豆猫 · 元数据清理（稳定流程移植） 边缘检查：只读取画面并小步滚动，不点击、不修改、不保存。', flush=True)
    print(f'保持豆猫在刚才卡住的饮品列表、关闭弹窗。每次连续滚动 {edge_scroll} 格才重新识别。5 秒内切回豆猫。', flush=True)
    time.sleep(5)
    img = frame()
    ensure_clean_list(img)
    scroll_xy = ensure_layout(img)
    start = img.copy()
    result = '未找到安全候选'
    n = 0
    for n in range(19):
        img = frame()
        ensure_clean_list(img)
        groups = scanner.scan_tag_groups(img)
        candidate, direction = safety_check_candidates(img, groups) if groups else (None, 0)
        print(f'检查 {n}: 可见标签组 {len(groups)}，安全候选 {bool(candidate)}，边缘方向 {direction}', flush=True)
        if candidate is not None:
            x0,y0,x1,y1,cx,cy = candidate
            cv2.rectangle(img,(x0-5,y0-5),(x1+5,y1+5),(30,180,20),3)
            cv2.circle(img,(round(cx),round(cy)),14,(0,0,255),3)
            result='找到可安全点击的候选（本测试不会点击）'
            break
        if n >= 18:
            result='18 轮分组滚动后仍未找到候选；请检查截图'
            break
        # 每次连续滚动多个滚轮刻度，之后才拍一张图；默认 4 格。
        step = (direction if direction else -1) * edge_scroll
        if groups and not direction:
            result='检测到标签但无法判定安全滚动方向，停止'
            break
        before = img
        scanner.assert_app()
        pyautogui.moveTo(*scroll_xy, duration=.12)
        pyautogui.scroll(step)
        time.sleep(.8)
        changed = frame()
        ensure_clean_list(changed)
        diff=scroll_lib.change_fraction(before, changed)
        print(f'   {"向上" if step>0 else "向下"}连续滚动 {abs(step)} 格后检查；内容变化 {diff:.2%}', flush=True)
        img=changed
        if diff<.003:
            result='滚动后画面未移动，停止；请检查是否已到边界'
            break
    out=ROOT/'screenshots'/'preview_v10g_edge.png'
    out.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(out), img)
    print(f'边缘检查结果：{result}')
    print(f'最后画面：{out}（如果仍卡住，把这张图片和终端最后几行发给我。）')
    print('没有点击任何图纸，也没有修改或保存数据。')
    try:
        import subprocess
        subprocess.run(['/usr/bin/open',str(out)],check=False)
    except Exception:
        pass


