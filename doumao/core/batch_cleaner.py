#!/usr/bin/env python3
"""豆猫 v0.9b：当前饮品列表，同一屏最多自动清理并保存 2 张带标签的作品。

建立在用户已经成功测试的模块上：
- v0.7b 当前列表图纸标签扫描
- v0.8 自动打开作品并从编辑框读取标题
- v0.4.1 清备注、清标签、最终保存

严格限制：只有使用 --auto-save 才会执行；每次处理后必须返回列表并确认
标签组从当前屏幕减少一组，才允许处理下一张。无滚动、无批量扩散。

失败时可能有未保存的修改，也可能已经点过保存；请根据终端日志判断，
切勿在失败时盲目重跑。只适用于「食物 → 饮品」用户约定的专用规则。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pyautogui

from . import card_picker as v08
from . import tag_scanner as scanner
from . import navigation as navigator
from . import metadata_editor as cleaner
from .title_edit_contract import SaveStage

ROOT = Path.home() / 'doumao-automation'
LOG = ROOT / 'logs' / 'refactored_batch_cleaner.jsonl'
PREVIEW = ROOT / 'screenshots' / 'refactored_batch_candidate.png'
DIAGNOSTIC = ROOT / 'screenshots' / 'refactored_editor.png'
MAX_CARDS = 2
pyautogui.FAILSAFE = True
pyautogui.PAUSE = .18


def screenshot() -> np.ndarray:
    return cv2.cvtColor(np.asarray(pyautogui.screenshot().convert('RGB')),
                        cv2.COLOR_RGB2BGR)


def record(title: str, result: str, extra: dict | None = None):
    """Best-effort audit; a file error must not decide GUI operation status."""
    payload = {'time': datetime.now().isoformat(timespec='seconds'),
               'title': title, 'result': result}
    if extra:
        payload.update(extra)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f:
            f.write(json.dumps(payload, ensure_ascii=False) + '\n')
    except OSError as exc:
        print(f'警告：单张操作日志写入失败：{exc}；继续依据操作结果判断。', flush=True)


@dataclass(frozen=True)
class MetadataCardResult:
    """One card is verified on the list, not merely clicked in the editor."""
    title: str
    save_stage: SaveStage
    note_before_length: int | None
    removed_tags: int
    tag_groups_before: int
    tag_groups_after: int


class MetadataCardFailure(RuntimeError):
    """A post-click check failed; the caller can inspect the attempted Save."""
    def __init__(self, result: cleaner.MetadataCleanResult, reason: str):
        self.result = result
        self.save_stage = result.save_stage
        super().__init__(reason)


class MetadataCardInterrupted(KeyboardInterrupt):
    """An interrupted post-click check retains the attempted Save stage."""
    def __init__(self, result: cleaner.MetadataCleanResult):
        self.result = result
        self.save_stage = result.save_stage
        super().__init__('保存后验证被中断；状态待人工核对')


def verify_editor_result(result: cleaner.MetadataCleanResult, title: str) -> None:
    """Only an observed Save attempt + closed editor permits list verification."""
    if not isinstance(result, cleaner.MetadataCleanResult):
        raise RuntimeError('元数据清理器未返回结构化保存结果；状态不明确，停止。')
    if result.title != title:
        raise RuntimeError('返回的作品标题与实际读取的原标题不同；停止。')
    if result.save_stage is not SaveStage.ATTEMPTED:
        raise RuntimeError('清理器未报告本次保存尝试；停止。')
    if result.edit_dialog_disappeared is not True:
        raise RuntimeError('保存后未确认编辑弹窗消失；停止，不重复保存。')
    if (not isinstance(result.removed_tags, int) or isinstance(result.removed_tags, bool)
            or not 1 <= result.removed_tags <= cleaner.MAX_TAGS):
        raise RuntimeError('清理器报告的标签删除数量不符合已验证规则；停止。')


def save_preview(im: np.ndarray, candidate: tuple, index: int, num: int, limit: int):
    x0, y0, x1, y1, cx, cy = candidate
    vis = im.copy()
    cv2.rectangle(vis, (x0-5, y0-5), (x1+5, y1+5), (0,180,0), 3)
    cv2.circle(vis, (round(cx), round(cy)), 14, (0,0,255), 3)
    cv2.putText(vis, f'v0.9b CARD {index}/{limit} - {num} TAGGED GROUPS',
                (max(12, x0-40), max(35, y0-20)),
                cv2.FONT_HERSHEY_SIMPLEX, .6, (0,0,220), 2, cv2.LINE_AA)
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(PREVIEW), vis)  # 每次覆盖，避免积累测试截图



def save_editor_diagnostic(frame: np.ndarray, message: str):
    """单独保存失败时的画面；每次覆盖，不累积截图。"""
    DIAGNOSTIC.parent.mkdir(parents=True, exist_ok=True)
    marked = frame.copy()
    save = cleaner.find_save(frame)
    if save is not None:
        x, y, w, h = save
        cv2.rectangle(marked, (x,y), (x+w,y+h), (0,0,255), 3)
    cv2.putText(marked, 'EDITOR DIAGNOSTIC (NO CHANGES)', (12,55),
                cv2.FONT_HERSHEY_SIMPLEX, .8, (0,0,230), 2)
    cv2.imwrite(str(DIAGNOSTIC), marked)
    print(f'{message}；诊断截图：{DIAGNOSTIC}', flush=True)


def wait_for_editor_robust():
    """先等 Flutter 弹窗稳定，再校验输入框；必要时只在已确认编辑页中向上滚动。

    原 v0.9 只有约 2.5 秒且直接要求 title/note 一次成功，连续处理时
    可能因弹窗动画或记住了上次滚动位置而误判。此函数不重按铅笔、
    不点击保存、不输入文字，也不会在无法确认编辑页时盲目滚动。
    """
    last = None
    first_save_frame = None
    for attempt in range(12):
        time.sleep(.45)
        scanner.assert_app()
        frame = screenshot()
        last = frame
        save = cleaner.find_save(frame)
        if save is None:
            continue
        if first_save_frame is None:
            first_save_frame = frame
            print('已看到编辑窗口保存按钮；等待标题及备注输入框稳定…', flush=True)
        fields = cleaner.form_rects(frame, save)
        if fields is not None:
            return frame, save

    if first_save_frame is None:
        assert last is not None
        save_editor_diagnostic(last, '未检测到编辑页底部保存按钮；未进行修改')
        raise RuntimeError('点击铅笔后没有确认进入编辑页；没有进行任何资料修改。')

    # 只有明确看到编辑页的蓝色固定保存按钮，才允许尝试把内部内容滚到顶部。
    print('编辑窗口已打开，但标题/备注暂不可见；尝试在编辑窗口内向上滚动定位。', flush=True)
    frame = last
    assert frame is not None
    for attempt in range(10):
        scanner.assert_app()
        save = cleaner.find_save(frame)
        if save is None:
            save_editor_diagnostic(frame, '向上滚动时编辑页面状态改变，已停止')
            raise RuntimeError('向上滚动时失去编辑页锚点；没有进行资料修改。')
        # 与此前验证成功的编辑页滚动位置一致，不点击任何按钮。
        sx, sy, sw, sh = save
        px, py = cleaner.img_to_screen(sx + .52*sw, sy - .26*sw, frame)
        pyautogui.moveTo(px, py, duration=.12)
        scanner.assert_app()
        pyautogui.scroll(7)
        time.sleep(.60)
        scanner.assert_app()
        frame = screenshot()
        new_save = cleaner.find_save(frame)
        if new_save is None:
            save_editor_diagnostic(frame, '滚动后未找到编辑页保存按钮')
            raise RuntimeError('未确认编辑窗口仍然打开；没有修改资料。')
        if cleaner.form_rects(frame, new_save) is not None:
            print(f'向上滚动 {attempt+1} 次后，已识别标题与备注框。', flush=True)
            return frame, new_save

    save_editor_diagnostic(frame, '尝试向上滚动后仍无法识别标题/备注框')
    raise RuntimeError('已打开编辑窗口但输入框仍无法识别；未修改资料。请发送诊断截图。')

def wait_for_list_after_save():
    """验证编辑已关闭，必要时尝试一次 Escape 关闭详情页；不猜测点击背景。"""
    for _ in range(7):
        time.sleep(.5)
        scanner.assert_app()
        frame = screenshot()
        if cleaner.find_save(frame) is None:
            break
    else:
        raise RuntimeError('保存后仍检测到编辑页按钮；未确认退出编辑页，不再处理下一张。')

    detail = navigator.find_detail_modal(frame)
    if detail is not None:
        print('保存后仍在作品详情页；尝试一次 Esc 返回列表。', flush=True)
        scanner.assert_app()
        pyautogui.press('esc')
        time.sleep(.95)
        scanner.assert_app()
        frame = screenshot()
        if navigator.find_detail_modal(frame) is not None:
            raise RuntimeError('Esc 后详情弹窗仍存在；请手动关闭。为避免误点，不自动继续。')
    if cleaner.find_save(frame) is not None:
        raise RuntimeError('返回列表时仍检测到编辑窗口；已安全停止。')
    return frame


def verify_tag_disappeared(before: np.ndarray, after: np.ndarray, group: tuple, old_count: int):
    """必须明确确认同屏标签组减一且原位置不再有标签；否则停止。"""
    if before.shape != after.shape:
        raise RuntimeError('返回列表后屏幕尺寸变化；无法比较结果。')
    after_groups = scanner.scan_tag_groups(after)
    after_count = len(after_groups)
    if after_count != old_count - 1:
        raise RuntimeError(
            f'保存前检测到 {old_count} 组标签，返回列表后检测到 {after_count} 组，'
            '未能确认恰好减少 1 组。请人工检查，停止。'
        )
    x0, y0, x1, y1, *_ = group
    original_center = ((x0+x1)/2, (y0+y1)/2)
    tol_x = max(26, (x1-x0)*.28)
    tol_y = max(22, (y1-y0)*1.6)
    for xa, ya, xb, yb in after_groups:
        center = ((xa+xb)/2, (ya+yb)/2)
        if (abs(center[0]-original_center[0]) < tol_x and
                abs(center[1]-original_center[1]) < tol_y):
            raise RuntimeError('原卡片位置仍检测到标签；可能保存未刷新或列表重新排序，停止。')
    return after_count


def run_one(index: int, limit: int) -> MetadataCardResult | None:
    scanner.assert_app()
    before = screenshot()
    if cleaner.find_save(before) is not None or navigator.find_detail_modal(before) is not None:
        raise RuntimeError('当前不是干净的饮品图纸列表；请先关闭所有弹窗。')
    groups = scanner.scan_tag_groups(before)
    if not groups:
        print('当前屏幕没有识别到待整理的标签组，结束本次测试。', flush=True)
        return None
    old_count, target = v08.find_first_candidate(before)
    save_preview(before, target, index, old_count, limit)
    x0, y0, x1, y1, cx, cy = target
    print(f'\n[{index}/{limit}] 当前屏幕有 {old_count} 组候选；自动选择最上方最左边的一张。', flush=True)
    print(f'点击截图坐标 ({round(cx)}, {round(cy)})，打开图纸详情。', flush=True)
    v08.screen_click(cx, cy, before)
    detail, modal = v08.wait_for_detail()
    pen = navigator.find_pencil(detail, modal)
    if pen is None:
        raise RuntimeError('详情弹窗打开了，但无法唯一找到右上角蓝色铅笔。')
    v08.screen_click(*pen[0], detail)
    edit, save = wait_for_editor_robust()
    fields = cleaner.form_rects(edit, save)
    if fields is None:
        raise RuntimeError('已点击铅笔，但无法识别标题和备注输入框。')
    title = cleaner.read_field(fields[0], edit).strip()
    if (not title or len(title) > 64 or '\n' in title or '\r' in title
            or title.startswith('__DOUMAO_')):
        raise RuntimeError(f'读取的原标题异常：{title!r}；停止。')
    print(f'已打开作品：{title!r}，开始清空备注和标签，并自动保存。', flush=True)
    record(title, 'started', {'card': index, 'tag_groups_before': old_count})

    # A nested failure already carries MetadataCleanResult via Batch 1;
    # never replay clean_current, even when its Save click may have occurred.
    cleaned = cleaner.clean_current(title=title, auto_save=True)
    try:
        verify_editor_result(cleaned, title)
        frame = wait_for_list_after_save()
        remaining = verify_tag_disappeared(before, frame, target, old_count)
    except KeyboardInterrupt as exc:
        if isinstance(cleaned, cleaner.MetadataCleanResult):
            raise MetadataCardInterrupted(cleaned) from exc
        raise
    except Exception as exc:
        if isinstance(cleaned, cleaner.MetadataCleanResult):
            raise MetadataCardFailure(cleaned, str(exc)) from exc
        raise

    result = MetadataCardResult(
        title=cleaned.title,
        save_stage=SaveStage.LIST_RETURN_CONFIRMED,
        note_before_length=cleaned.note_before_length,
        removed_tags=cleaned.removed_tags,
        tag_groups_before=old_count,
        tag_groups_after=remaining,
    )
    record(title, 'verified_on_list',
           {'card': index, 'tag_groups_after': remaining,
            'removed_tags': result.removed_tags})
    print(f'[{index}/{limit}] {title}：已自动点击保存，并在列表确认标签组消失；剩余 {remaining} 组。', flush=True)
    return result
