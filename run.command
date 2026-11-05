#!/bin/zsh
# Finder double-click launcher; resolves its own location, not the working directory.
cd "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  echo '未发现 .venv/bin/python。请先在仓库中创建/配置虚拟环境。'
  read '?按回车退出...'
  exit 1
fi
"./.venv/bin/python" -m doumao visible-order
result=$?
echo "程序已结束（退出码 $result）。"
read '?按回车关闭此窗口...'
exit "$result"
