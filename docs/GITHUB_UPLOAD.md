# 第一次上传到 GitHub：适合初学者

1. 点击 GitHub 右上角 **+** → **New repository**。仓库名称填 `doumao-automation`；选 **Private**（先不公开）；仓库描述可用 `macOS GUI automation for managing perler bead pattern metadata`。
2. 如果准备通过网页直接上传，创建仓库时选择 **Add a README**，点击 **Create repository**。这样页面上会显示文件列表与 **Add file → Upload files**。
3. 在 Mac Finder 中双击解压 ZIP，打开 `doumao_automation_refactored` 文件夹。把 `doumao/`、`tests/`、`docs/` 三个文件夹，以及 `README.md`、`requirements.txt`、`pyproject.toml` 拖进 GitHub 的上传区域。GitHub 支持拖入文件或文件夹。
4. `.gitignore` 是 Mac Finder 的隐藏文件；Finder 按 `⌘ + Shift + .` 显示隐藏文件，然后也上传 `.gitignore`。不要上传 `.venv`、`logs/`、`screenshots/` 或个人图纸。
5. 在网页的 commit message 填 `Add refactored Doumao automation`，点击 **Commit changes**（按钮文字有时因分支设置略有不同）。
6. 点击仓库的 **Code** 标签，确保顶层看到 `doumao/`、`tests/`、`docs/`、`README.md` 等，而不是被多嵌套了一个 `doumao_automation_refactored/` 文件夹。若多套了一层，需调整位置。

> 如果决定使用命令行方式，应先新建**空仓库（不要初始化 README）**，然后使用 `git init`, `git add`, `git commit`, `git remote add origin`, `git push`；不要同时混用两套初始仓库流程。GitHub 不会自动解压你上传的 ZIP，因此不要只上传压缩包。

**发布前隐私检查**：即使是 Private 仓库，尽量只上传脱敏源代码与简化的开发记录。账号、个人作品、详细本机截图、私人路径及历史 JSONL 日志应留在本地。
