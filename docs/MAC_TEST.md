# Mac 实机测试说明（feature/search-queue-renaming）

## 0. 确保不影响 main

在现有项目根目录运行：

```bash
git status --short
git switch -c feature/search-queue-renaming
```

若分支已经存在，用 `git switch feature/search-queue-renaming`。先备份未提交的工作，不要在有冲突时执行覆盖复制。应用本次补丁前先用 `git apply --check /path/to/feature_search_queue.patch` 检查。以后要提交代码也只在该分支中执行。

## 1. 自动测试

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

## 2. 只读首张

在应用中打开目标文件夹，**手动输入搜索词**。以下字符串均为虚构示例。终端切换后无需再输入「开始」，脚本自动等待5秒。

```bash
python -m doumao search-queue --mode remove-prefix --search 'DRAFT-' --prefix 'DRAFT-' --limit 1
```

## 3. 实际修改 1 张

仅在只读输出与作品完全对应时执行；按 `--auto-save` 和 `--confirm-selection` 表示明确允许保存：

```bash
python -m doumao search-queue --mode remove-prefix --search 'DRAFT-' --prefix 'DRAFT-' --limit 1 --auto-save --confirm-selection
```

另一种方式是 `--mode replace --old 'draft' --new 'final' --search 'draft'`，但每张新标题必须完全不含搜索词。或者将虚构 JSON 复制到不上传 GitHub 的本地位置（如 `config/local.json`），再使用 `--config config/local.json`。**配置文件不能启用自动保存，仍须命令行显式提供两个保存确认参数**。

## 4. 连续运行和安全停止

单张实测确认保存后搜索列表自动退出、下一张正确顶到第一张，才将 `--limit 1` 改为 `3`。经过连续测试再使用 `--limit all`。达到设定数量或稳定空列表时正常结束；网络延迟、第一张未退出、图纸视觉上无法区分、错误弹窗时停止。停止后查看 `~/.doumao-automation/runtime/search_queue_rename.jsonl` 与 `search_queue_diagnostic.png`，先核对实际状态，**不要直接重跑保存**。

`--limit` 是**成功验证修改数量**，不是检查次数。搜索结果只有两张时，即使 `--limit 10` 也应在确认耗尽后正常结束并报告2张。
