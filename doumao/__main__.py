"""Single entrypoint. No GUI action occurs unless a command is chosen."""
from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

RULE_FILE = Path(__file__).resolve().parent / 'rules' / 'drinks.json'


def build_parser():
    parser=argparse.ArgumentParser(prog='python -m doumao', description='豆猫 Mac 图纸维护自动化（目前仅针对饮品布局验证）')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor',help='检查 Python 依赖与本地工具；不打开豆猫')
    prev=sub.add_parser('preview',help='只截图检查当前列表图纸，不打开、不保存')
    prev.add_argument('--expect-visible',type=int,default=None)
    clean=sub.add_parser('clean',help='清空饮品备注及选中标签（仅操作标签候选）')
    clean.add_argument('--auto-save',action='store_true',help='允许实际删除备注、标签并保存')
    clean.add_argument('--confirm-folder',choices=['drinks'],help='人工确认当前已打开「仓库→食物→饮品」')
    clean.add_argument('--limit',type=int,default=1)
    clean.add_argument('--scan-scroll',type=int,default=3)
    clean.add_argument('--edge-scroll',type=int,default=4)
    clean.add_argument('--max-scrolls',type=int,default=100)
    title=sub.add_parser('titles',help='自动读原标题，按饮品规则转换；默认只读')
    title.add_argument('--auto-save',action='store_true',help='允许实际写入新标题并保存')
    title.add_argument('--confirm-folder',choices=['drinks'],help='人工确认当前已打开「仓库→食物→饮品」')
    title.add_argument('--limit',type=int,default=1)
    title.add_argument('--scroll',type=int,default=3)
    title.add_argument('--max-scrolls',type=int,default=100)
    title.add_argument('--current-screen-only',action='store_true')
    title.add_argument('--expect-visible',type=int,default=None)
    title.add_argument('--expected-changes',type=int,default=None)
    return parser


def doctor():
    import importlib.util, platform, shutil, sys
    print(f'Python: {sys.version.split()[0]} | System: {platform.system()}')
    for m in ('numpy','cv2','PIL','pyautogui'):
        print(f'{m}: '+('OK' if importlib.util.find_spec(m) else 'NOT INSTALLED'))
    exe=Path('/opt/homebrew/bin/cliclick')
    print('cliclick: '+ ('OK '+str(exe) if exe.exists() else 'NOT FOUND (Apple Silicon default path)'))
    print('osascript: '+('OK' if shutil.which('osascript') else 'NOT FOUND'))
    print('规则文件: '+('OK' if RULE_FILE.is_file() else 'MISSING'))
    print('此检查不会运行 GUI 自动化，也不会验证豆猫当前文件夹。')


def main():
    parser=build_parser()
    args=parser.parse_args()
    if args.command=='doctor':
        doctor(); return
    if args.command=='preview':
        if args.expect_visible is not None and not (0<=args.expect_visible<=12):
            parser.error('--expect-visible 必须在 0–12 之间。')
        from .workflows import normalize_titles
        readargs=SimpleNamespace(rule_config=str(RULE_FILE), auto_save=False,
            limit=1, scroll=3, max_scrolls=1, current_screen_only=True,
            expect_visible=args.expect_visible, expected_changes=None,
            list_preview=True)
        return guarded(lambda: normalize_titles.run(readargs), normalize_titles.diagnostics)
    if not args.confirm_folder and args.auto_save:
        parser.error('真实保存必须增加 --confirm-folder drinks，表示已人工确认当前饮品文件夹。')
    if args.command=='clean':
        if not args.auto_save:
            parser.error('清理备注与标签会改变资料；必须明确提供 --auto-save 和 --confirm-folder drinks。')
        if not (1<=args.limit<=200 and 1<=args.max_scrolls<=150 and 2<=args.scan_scroll<=4 and 2<=args.edge_scroll<=6):
            parser.error('清理参数超出安全范围。')
        from .workflows import clean_metadata
        return guarded(lambda: clean_metadata.run(args.limit,args.max_scrolls,args.edge_scroll,args.scan_scroll),
                       clean_metadata.diagnostic, cleanup=True)
    if args.command=='titles':
        if not (1<=args.limit<=30 and 1<=args.scroll<=5 and 1<=args.max_scrolls<=150):
            parser.error('标题参数超出目前饮品文件夹已验证范围。')
        if args.expected_changes is not None and not(0<=args.expected_changes<=30):
            parser.error('--expected-changes 必须在 0–30 之间。')
        if args.expect_visible is not None and not (0<=args.expect_visible<=12):
            parser.error('--expect-visible 必须在 0–12 之间。')
        from .workflows import normalize_titles
        readargs=SimpleNamespace(rule_config=str(RULE_FILE), auto_save=args.auto_save,
            limit=args.limit, scroll=args.scroll, max_scrolls=args.max_scrolls,
            current_screen_only=args.current_screen_only, expect_visible=args.expect_visible,
            expected_changes=args.expected_changes, list_preview=False)
        return guarded(lambda: normalize_titles.run(readargs), normalize_titles.diagnostics)


def guarded(fn, diagnostic, cleanup=False):
    try:
        fn()
    except (KeyboardInterrupt, SystemExit) as error:
        if isinstance(error,SystemExit): raise
        print('用户已终止。关闭任何未保存的编辑弹窗以放弃更改。')
        raise SystemExit(130) from error
    except Exception as error:
        if cleanup:
            try:
                from .core.batch_cleaner import screenshot
                diagnostic(screenshot(), str(error))
            except Exception: pass
        else:
            try: diagnostic(str(error))
            except Exception: pass
        raise SystemExit(f'安全停止：{error}。如已点击保存，请人工核对，不要直接重跑。') from error


if __name__=='__main__':
    main()
