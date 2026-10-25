#!/usr/bin/env bash
# 改完 data/trip.toml → 跑這支 → 產 index.html＋sw.js → commit → push 到 GitHub Pages
# 私密字串清單放 data/private.local（不進 git）；沒有它 build 會拒絕執行。
set -euo pipefail
cd "$(dirname "$0")"
STAMP="$(date +%m%d-%H%M)"

# 本機有兩個 gh 帳號時，用環境變數指定站台那個（帳號名不寫進 repo）
if [ -n "${BKK_GH_USER:-}" ]; then
  gh auth switch --user "$BKK_GH_USER" >/dev/null
fi

# 1) 泰語表：找得到 vault 的 06-泰語對照表.md 就重產 data/lang.toml，找不到就沿用
python3 -I gen_lang.py

# 2) build 先跑：失敗就 exit，不會產出半套（也不會蓋掉舊的 index.html）
python3 -I build.py

# 3) 只加站台需要的檔，不用 -A（避免夾帶雜物；data/private.local 在 .gitignore）
git add index.html sw.js build.py gen_lang.py update.sh .gitignore data/trip.toml data/lang.toml assets/
git commit -q -m "$STAMP" || true
git push
echo "✓ 已發布 · 版本戳 $(date +%Y-%m-%d\ %H:%M)"
