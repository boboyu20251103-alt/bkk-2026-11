#!/usr/bin/env bash
# 改完 行程.toml → 跑這支 → 產 index.html → commit → push 到 Pages
set -euo pipefail

VAULT="$HOME/ai合作開發專案/曼谷行程-2026-11"
WEB="$HOME/ai合作開發專案/曼谷行程-web"
STAMP="$(date +%m%d-%H%M)"

# 本機有兩個 gh 帳號，釘住站台那個（免得推到錯的地方）
gh auth switch --user boboyu20251103-alt >/dev/null

# 1) build 先跑：失敗就 exit，不會產出半套
python3 -I "$WEB/build.py"

# 2) vault 本機版控（只在本機，不推遠端）
if [ -d "$VAULT/.git" ]; then
  git -C "$VAULT" add -A
  git -C "$VAULT" commit -q -m "$STAMP" || true
fi

# 3) 站台 repo：只加產物，不用 -A（避免夾帶雜物）
cd "$WEB"
git add index.html update.sh build.py gen_lang.py
git commit -q -m "$STAMP" || true
git push
echo "✓ 已發布 · 版本戳 $(date +%Y-%m-%d\ %H:%M)"
