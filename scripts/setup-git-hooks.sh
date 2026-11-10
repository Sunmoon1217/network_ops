#!/bin/sh
# 启用仓库内的 git hooks（.githooks/），每台机器 clone 后跑一次：
#
#   sh scripts/setup-git-hooks.sh
#
# 等价于 git config core.hooksPath .githooks（PowerShell 里直接敲这句也行）。
# 相对路径按「工作区根目录」解析，所以 .worktrees/ 下的每个 worktree 都会用
# 各自 checkout 出来的 .githooks/，新拉的分支自动带检查。
set -eu

cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

printf '已启用 .githooks（core.hooksPath=%s）\n' "$(git config core.hooksPath)"
