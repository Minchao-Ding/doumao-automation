"""Search-result queue renaming; reuses the existing validated title editor.

The user prepares the folder and exact search filter. One card is saved once;
only an observed list advance (or stable empty results) permits another edit.
No title text is used as an item ID. No private collection data is embedded.
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.queue_state import QueueCounter, QueueUncertain, queue_transition, looks_like_same_art
from ..title_rules import proposal

RUNTIME = Path.home() / '.doumao-automation' / 'runtime'
LOG = RUNTIME / 'search_queue_rename.jsonl'
DIAGNOSTIC = RUNTIME / 'search_queue_diagnostic.png'


def emit(event: str, **values):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'time': datetime.now().astimezone().isoformat(timespec='seconds'),
                            'event': event, **values}, ensure_ascii=False) + '\n')


def _frontend():
    # Import GUI automation only when a command is actually run on macOS.
    from . import normalize_titles as ui
    return ui


def _list(ui):
    frame = ui.shot()
    ui.check_list(frame)
    return frame


def scroll_to_top(ui):
    """Reuses existing screenshot and scrolling helpers; never assumes scroll=0."""
    import pyautogui
    sw, sh = pyautogui.size()
    xy = (round(sw * .365), round(sh * .57))
    stable = 0
    for _ in range(9):
        before = _list(ui)
        ui.scanner.assert_app()
        pyautogui.moveTo(*xy, duration=.12)
        pyautogui.scroll(20)
        time.sleep(.55)
        after = _list(ui)
        if after.shape != before.shape:
            raise QueueUncertain('Screen size changed while locating search head')
        fraction = ui.scroll_util.change_fraction(before, after)
        stable = stable + 1 if fraction < .004 else 0
        if stable >= 2:
            return after
    raise QueueUncertain('Cannot confirm search results are scrolled to top')


def snapshot(ui):
    """For zero cards, require multiple stable observations to avoid false exhaustion."""
    frame = scroll_to_top(ui)
    cards = ui.card_rows(frame)
    if cards:
        if cards[0]['col'] != 0:
            raise QueueUncertain('First grid column cannot be reliably identified')
        return frame, cards
    previous = frame
    for _ in range(4):
        time.sleep(.9)
        frame = _list(ui)
        cards = ui.card_rows(frame)
        if cards:
            if cards[0]['col'] != 0:
                raise QueueUncertain('First card cannot be reliably identified')
            return frame, cards
        if ui.scroll_util.change_fraction(previous, frame) > .006:
            raise QueueUncertain('Empty result view still changing; loading may be underway')
        previous = frame
    return frame, []


def await_advance(ui, before_cards, *, attempts: int = 7):
    """Don't retry a save. Check a settled queue head with two observations."""
    for _ in range(attempts):
        frame, after_cards = snapshot(ui)
        state = queue_transition(before_cards, after_cards)
        if state in ('advanced', 'empty'):
            # A second observation guards against a one-frame render transition.
            time.sleep(.55)
            stable_frame, stable_cards = snapshot(ui)
            if state == 'empty' and not stable_cards:
                return stable_frame, stable_cards, 'empty'
            if (state == 'advanced' and stable_cards and
                    looks_like_same_art(after_cards[0]['fp'], stable_cards[0]['fp']) and
                    queue_transition(before_cards, stable_cards) == 'advanced'):
                return stable_frame, stable_cards, 'advanced'
        time.sleep(.65)
    raise QueueUncertain('Post-save search result did not show a stable confirmed advance; never retrying same card')


def run(*, rule: dict[str, Any], limit: int | None, auto_save: bool, search: str):
    import pyautogui
    ui = _frontend()
    cli = shutil.which('cliclick') or next((p for p in
             ('/opt/homebrew/bin/cliclick', '/usr/local/bin/cliclick') if Path(p).exists()), None)
    if not cli:
        raise RuntimeError('cliclick not found; install it via Homebrew')
    ui.cleaner.CLICK = cli
    # The established editor emits to its module-local JSONL file. Redirect
    # for this workflow, not to the public repository.
    ui.LOG = LOG
    ui.DIAGNOSTIC = DIAGNOSTIC
    counter = QueueCounter(limit)
    was_saved = False
    print('请先在豆猫中打开目标文件夹并设置搜索，确认首项完整可见。')
    print('搜索关键词：' + repr(search))
    print('模式：' + ('自动保存（严格核验列表刷新）' if auto_save else '仅预览首张，不保存'))
    print('5秒后开始，立即切回豆猫；无需输入“开始”。', flush=True)
    time.sleep(5)
    try:
        frame, cards = snapshot(ui)
        emit('session_started', rule_type=rule['rule_type'], search=search,
             limit='all' if limit is None else limit, auto_save=auto_save)
        if not cards:
            emit('session_finished', result='exhausted', saved=0, inspected=0)
            print('已多次确认搜索结果为空；成功修改 0 张。')
            return
        while cards:
            if counter.limit is not None and counter.changed >= counter.limit:
                break
            current = cards[0]
            counter.start()
            # This method reads the entire actual title, checks the proposed
            # replacement and readback, clicks Save once and returns to list.
            # Existing notes, tags, classification and artwork are untouched.
            was_saved = False
            status, old, new = ui.handle_card(current, frame, counter.inspected, auto_save, rule)
            if not auto_save:
                counter.pending = False
                emit('preview', old=old, new=new, status=status)
                print(f'只读预览：{old!r} -> {new!r}；未保存。')
                return
            if status != 'saved':
                raise QueueUncertain(f'First result is not eligible: {old!r}; no save performed')
            # The pre-save title rule enforces that the search text disappears.
            # There is intentionally no 'seen titles' set: equal-name distinct
            # works must still be editable independently.
            was_saved = True
            emit('save_returned_waiting_refresh', old=old, new=new,
                 verified_count=counter.changed)
            frame, cards, transition = await_advance(ui, [current, *cards[1:]])
            counter.verified(transition)
            was_saved = False
            emit('queue_advance_verified', old=old, new=new, changed=counter.changed,
                 transition=transition)
            print(f'队列前进已确认：{counter.changed} 张。', flush=True)
            if not cards:
                break
        result = counter.finished(queue_empty=not bool(cards))
        emit('session_finished', result=result.outcome, saved=result.changed,
             inspected=result.inspected)
        print(f'结束：{result.outcome}；已核验修改 {result.changed} 张；检查 {result.inspected} 张。')
        print(f'本机运行日志：{LOG}')
    except (KeyboardInterrupt, pyautogui.FailSafeException):
        emit('stopped', reason='user_interrupted', verified=counter.changed,
             pending=counter.pending)
        raise
    except Exception as e:
        try:
            ui.diagnostics(str(e))
        except Exception:
            pass
        emit('stopped', reason=str(e), verified=counter.changed,
             pending=counter.pending, save_returned=was_saved)
        raise QueueUncertain(f'{e}；已验证 {counter.changed} 张，'
                             '当前编辑状态可能需要人工核对，不自动重试') from e


def diagnostic(reason: str):
    # Only invoked for a failure prior to/around workflow setup; if the app is
    # not safely reachable there may be no screenshot, but the JSONL remains.
    emit('command_failed', reason=str(reason))
