#!/bin/sh
# 启用仓库内的 git hooks：sh scripts/setup-git-hooks.sh（等价 git config core.hooksPath .githooks）。
# 相对路径按工作区根解析，每个 worktree 用自己的 .githooks/。
set -eu

cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

printf '已启用 .githooks（core.hooksPath=%s）\n' "$(git config core.hooksPath)"
