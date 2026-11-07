"""macOS GUI adapter for one title editor, independent of workflow selection.

Only this adapter knows how the old title dialog is operated.  Business rules,
queue advancement, visible-grid identity and logging belong to its callers.
All image thresholds, delays, clicks and keyboard sequences match v3.5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time

import numpy as np
import pyautogui

from . import card_picker, list_view, metadata_editor as cleaner
from . import navigation, tag_scanner as scanner


def find_title_only(im: np.ndarray, save: tuple | None):
    """Recognize the title input relative to Save; identical to v3.5."""
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
        if not (sy - .995 * sw < top < sy - .805 * sw):
            continue
        found.append((sx, top, sw, height))
    return found[0] if len(found) == 1 else None


def wait_for_title_editor():
    """Wait for title field; if needed scroll *inside* the editor, as v3.5."""
    last = None
    saw_save = False
    for _ in range(12):
        time.sleep(.45)
        scanner.assert_app()
        last = list_view.shot()
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
        frame = list_view.shot()
        save = cleaner.find_save(frame)
        if save is None:
            raise RuntimeError('向上滚动后未确认编辑页，未修改。')
        rect = find_title_only(frame, save)
        if rect is not None:
            print(f'向上调整 {attempt+1} 次后找到标题框。', flush=True)
            return frame, save, rect
    raise RuntimeError('已确认编辑页，但无法唯一识别标题框；未修改。')


def read_title_only(frame, rect, *, click_command: str):
    title = cleaner.read_field(rect, frame, click_command=click_command)
    if not title or len(title) > 64 or title.startswith('__DOUMAO_'):
        raise RuntimeError(f'读取原标题异常：{title!r}')
    if '\n' in title or '\r' in title:
        raise RuntimeError('原标题存在换行，停止，避免输入框误定位。')
    return title


@dataclass
class MacTitlePort:
    """Per-card TitleEditPort; no mutable workflow or backend globals."""

    click_command: str
    _initial: tuple[np.ndarray, tuple] | None = None
    _save_ready: tuple[np.ndarray, tuple] | None = field(default=None, init=False)

    def read_title(self) -> str:
        if self._initial is not None:
            frame, rect = self._initial
            self._initial = None
        else:
            frame = list_view.shot()
            rect = find_title_only(frame, cleaner.find_save(frame))
            if rect is None:
                raise RuntimeError('写入前无法唯一识别标题框，未修改。')
        return read_title_only(frame, rect, click_command=self.click_command)

    def replace_title(self, proposed_title: str) -> None:
        frame = list_view.shot()
        rect = find_title_only(frame, cleaner.find_save(frame))
        if rect is None:
            raise RuntimeError('粘贴前标题框定位失败，未修改。')
        x, y, w, h = rect
        cleaner.click_img(x+w*.30, y+h*.55, frame)
        cleaner.shell('/usr/bin/pbcopy', input_text=proposed_title)
        cleaner.press('kd:cmd', 't:a', 'ku:cmd', 'kd:cmd', 't:v', 'ku:cmd',
                      click_command=self.click_command)
        time.sleep(.65)
        scanner.assert_app()

    def read_back_title(self) -> str:
        frame, _, rect = wait_for_title_editor()
        return read_title_only(frame, rect, click_command=self.click_command)

    def verify_save_ready(self) -> None:
        frame = list_view.shot()
        button = cleaner.find_save(frame)
        if button is None or find_title_only(frame, button) is None:
            raise RuntimeError('保存前未能确认编辑页及标题框，未保存。')
        self._save_ready = frame, button

    def click_save(self) -> None:
        if self._save_ready is None:
            raise RuntimeError('尚未完成保存前验证，禁止点击。')
        frame, button = self._save_ready
        self._save_ready = None
        bx, by, bw, bh = button
        cleaner.click_img(bx+bw*.50, by+bh*.50, frame)

    def verify_list_return(self) -> None:
        frame = list_view.wait_for_list_after_save()
        list_view.check_list(frame)

    def close_without_save(self) -> None:
        list_view.go_back_to_list()


def open_title_port(target, frame: np.ndarray, *, click_command: str) -> MacTitlePort:
    """Open the *already selected* card. Never choose/identify cards here."""
    if not click_command:
        raise RuntimeError('未提供 cliclick 路径，未打开图纸。')
    cx, cy = target['click']
    scanner.assert_app()
    card_picker.screen_click(cx, cy, frame)
    detail, modal = card_picker.wait_for_detail()
    pen = navigation.find_pencil(detail, modal)
    if pen is None:
        raise RuntimeError('未能唯一定位详情弹窗中的蓝色铅笔，未编辑。')
    card_picker.screen_click(*pen[0], detail)
    editor, _, rect = wait_for_title_editor()
    return MacTitlePort(click_command=click_command, _initial=(editor, rect))
