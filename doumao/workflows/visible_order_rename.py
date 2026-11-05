"""Interactive visible-grid renamer: no search, no scrolling, no artwork inference.

GUI operations intentionally delegate to the existing validated title editor.
A successful save returns to the list without reopening the card.
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from ..core.grid_detector import GridDetectionError, detect_visible_grid
from ..core.visible_order_state import (
    BatchState, VisibleOrderUncertain, ensure_stable,
    ordered_cards, parse_line, verify_mapping, fit_visible_assignments,
)

RUNTIME = Path.home() / '.doumao-automation' / 'runtime'
LOG = RUNTIME / 'visible_order_events.jsonl'
DIAGNOSTIC = RUNTIME / 'visible_order_diagnostic.png'


def emit(event, **fields):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as file:
        file.write(json.dumps({'time':datetime.now().astimezone().isoformat(timespec='seconds'),
                               'event':event, **fields}, ensure_ascii=False)+'\n')


def frontend():
    from . import normalize_titles as ui
    return ui


def save_capture_failure(frame, exc, *, detected=None):
    """Keep the unmodified screenshot when visual detection fails.

    The ordinary workflow diagnostic is a marked image and may run after a
    failure; the raw screenshot is intentionally a different local-only file.
    No screenshot is placed inside the source repository.
    """
    import cv2

    RUNTIME.mkdir(parents=True, exist_ok=True)
    path = RUNTIME / 'visible_order_capture_failed.png'
    saved = cv2.imwrite(str(path), frame)
    emit('capture_failed', reason=str(exc), image_shape=list(frame.shape),
         detected=detected, screenshot=str(path) if saved else None)
    if saved:
        print(f'已保存失败时的原始截图（未点击、未保存）：{path}', flush=True)


def capture(ui):
    frame = ui.shot()  # Still requires the actual app to be in front.
    detected = None
    try:
        ui.check_list(frame)
        try:
            raw_cards = detect_visible_grid(frame)
        except GridDetectionError:
            # Keep the previously supported incomplete final row. The legacy
            # detector is limited by theme and can only serve as a conservative
            # fallback for <12 observed cards; it must pass row/column checks.
            raw_cards = ui.card_rows(frame)
            if not 1 <= len(raw_cards) < 12:
                raise
        detected = len(raw_cards)
        cards = ordered_cards(raw_cards, frame.shape[1])
    except Exception as exc:
        try:
            save_capture_failure(frame, exc, detected=detected)
        except Exception:
            # Diagnostics must never replace the original safety exception.
            pass
        raise
    return frame, cards


def check_snapshot(ui, reference, *, fingerprint_positions=None):
    # All twelve slots must retain their geometry; only assigned artwork
    # fingerprints are relevant to a partial batch (e.g. positions 3-12).
    _, cards = capture(ui)
    ensure_stable(reference, cards, fingerprint_positions=fingerprint_positions)
    time.sleep(.35)
    frame, cards = capture(ui)
    ensure_stable(reference, cards, fingerprint_positions=fingerprint_positions)
    return frame, cards


def configure(ui):
    cli = shutil.which('cliclick') or next(
        (x for x in ('/opt/homebrew/bin/cliclick','/usr/local/bin/cliclick') if Path(x).exists()), None)
    if not cli:
        raise RuntimeError('未发现 cliclick，请先运行 doctor 检查本地环境')
    ui.cleaner.CLICK = cli
    ui.LOG = LOG
    ui.DIAGNOSTIC = DIAGNOSTIC


def process_batch(ui, assignments, *, sleep=time.sleep, trim_to_visible=False):
    """One frozen visible snapshot. Stop on any uncertain save or list movement."""
    frame, baseline = capture(ui)
    if trim_to_visible:
        assignments, dropped = fit_visible_assignments(assignments, len(baseline))
        if dropped:
            print(f'当前只识别 {len(baseline)} 张完整可见卡片；额外 {dropped} 个名称本批忽略，不保存、不顺延。', flush=True)
    verify_mapping(assignments, len(baseline))
    target_positions = tuple(a.position for a in assignments)
    # Check the original frame once more before the first GUI click.
    frame, _ = check_snapshot(ui, baseline, fingerprint_positions=target_positions)
    state = BatchState(list(assignments))
    emit('batch_started', slots=[{'position':a.position,'new':a.title} for a in assignments],
         visible=len(baseline))
    for assignment in assignments:
        pos, title = assignment.position, assignment.title
        try:
            # Re-detect and validate before each click. Use the CURRENT card
            # center, rather than a stale point from the first screenshot.
            frame, current_cards = check_snapshot(
                ui, baseline, fingerprint_positions=target_positions)
            target = current_cards[pos-1]
            state.begin(pos)
            emit('position_started', position=pos, new=title)
            # Exact replacement is a rule, not a derived title or search query.
            rule = {'rule_type':'replace_entire_title', 'new':title, 'max_length':64}
            status, old, proposed = ui.handle_card(target, frame, pos, True, rule)
            if status not in ('saved','skipped'):
                raise VisibleOrderUncertain(f'第 {pos} 张未返回明确的操作结果：{status}')
            if status == 'skipped' and old != title:
                raise VisibleOrderUncertain('原名称不等于目标名称，但编辑器跳过了保存')
            # ui.handle_card already rereads the editor title BEFORE Save,
            # then waits for the edit modal to close and verifies the list.
            # Do not reopen the same card: the next item starts with another
            # complete layout/assigned-artwork check, without a GUI click.
            state.verified(pos)
            emit('position_verified', position=pos, old=old, new=title, status=status,
                 verification='editor_readback_and_list_return')
            print(f'  第 {pos} 张：{"原标题已相同，未保存" if status == "skipped" else "已保存并返回列表"} ({len(state.completed)}/{len(assignments)})',flush=True)
        except Exception as exc:
            state.status = 'stopped'
            emit('batch_stopped', reason=repr(exc), completed=state.completed,
                 pending=state.pending,
                 remaining=[{'position':a.position,'new':a.title} for a in state.remaining])
            try:
                ui.diagnostics(str(exc))
            except Exception:
                pass
            raise VisibleOrderUncertain(
                f'批次停止；已核验位置 {state.completed}；待核对位置 {state.pending}；'
                f'未完成位置 {[a.position for a in state.remaining]}。原因：{exc}') from exc
    emit('batch_finished', verified=len(state.completed))
    return state


def preview_batch(ui, assignments, *, trim_to_visible=False):
    """Read-only diagnostic: capture the fixed grid without opening a card."""
    frame, cards = capture(ui)
    if trim_to_visible:
        assignments, dropped = fit_visible_assignments(assignments, len(cards))
        if dropped:
            print(f'当前只识别 {len(cards)} 张完整可见卡片；额外 {dropped} 个名称本批忽略，不保存、不顺延。', flush=True)
    verify_mapping(assignments, len(cards))
    check_snapshot(ui, cards, fingerprint_positions=tuple(a.position for a in assignments))
    # Screenshots are private local diagnostics and never part of the public Git tree.
    import cv2
    image = frame.copy()
    for i, card in enumerate(cards, 1):
        x, y = card['click']
        cv2.circle(image, (x, y), 15, (0, 160, 0), 3)
        cv2.putText(image, str(i), (x-14, y-20),
                    cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 220), 2)
    output = RUNTIME / 'visible_order_preview.png'
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), image):
        raise VisibleOrderUncertain('无法写入本地定位预览截图')
    emit('preview', visible=len(cards),
         slots=[{'position':a.position,'new':a.title} for a in assignments])
    print(f'只读定位完成：识别 {len(cards)} 张；没有打开或保存图纸。')
    print(f'位置标注图：{output}')
    return assignments


def run(*, input_func=input, sleep=time.sleep, preview_only=False):
    ui = frontend()
    configure(ui)
    print('可视区域顺序重命名：每批仅处理当前完整可见的卡片，不搜索、不自动滚动。')
    print('输入：每批可粘贴超过12个名称；仅处理当前可见位置，多出的忽略、不顺延。可用 3: 指定起点。')
    print('输入「退出」结束。每次提交有效名字后有5秒切回豆猫。', flush=True)
    print('模式：'+ ('只读定位测试（无点击、无保存）' if preview_only else '真实重命名（会保存）'))
    batch_number = 0
    while True:
        try:
            line = input_func('\n请输入本批名字（或输入「退出」）：')
        except (EOFError, KeyboardInterrupt):
            print('\n会话已结束；等待输入期间没有操作豆猫。')
            return
        if line.strip() == '退出':
            print('正常退出。')
            return
        try:
            assignments, ignored = parse_line(line, truncate_excess=True, return_ignored=True)
        except ValueError as exc:
            print(f'输入无效：{exc}。请重新输入。', flush=True)
            continue
        if ignored:
            print(f'本次输入 {len(assignments)+len(ignored)} 个名称；当前网格最多处理 {len(assignments)} 个；'
                  f'多出的 {len(ignored)} 个已忽略，不保存、不留待下一批。', flush=True)
        print('本批位置映射（实际完整可见数量以截图为准）：')
        for a in assignments:
            print(f'  {a.position:>2} → {a.title}')
        print('5秒后检查豆猫当前可见卡片；请切回豆猫，保持列表静止。', flush=True)
        sleep(5)
        batch_number += 1
        try:
            result = None if preview_only else process_batch(ui, assignments, sleep=sleep, trim_to_visible=True)
            if preview_only:
                result = preview_batch(ui, assignments, trim_to_visible=True)
        except ValueError as exc:
            # Input exceeds actually visible cards: no editor opened.
            print(f'本批未开始：{exc}；请重新输入。', flush=True)
            continue
        except Exception as exc:
            emit('session_stopped', batch=batch_number, reason=str(exc))
            print(f'安全停止：{exc}\n请人工检查最后一个待核对位置，不会自动重试。')
            raise
        print(f'本批完成：{len(result)}个位置已定位（未保存）' if preview_only else
              f'本批完成：{len(result.completed)}/{len(result.assignments)}张')
        print('可在当前屏幕继续指定后续位置；需要下一屏时再手动滚动。', flush=True)


def diagnostic(reason):
    emit('command_failed', reason=str(reason))
