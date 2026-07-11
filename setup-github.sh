#!/usr/bin/env bash
# 一鍵 push 上 GitHub
# 用法：解壓 hk-youth-hub.zip，cd 入去，然後 bash setup-github.sh
set -e

REPO="hk-youth-hub"
USER="gracelaucheuknam"

echo "▶ 檢查有冇 git…"
command -v git >/dev/null || { echo "✖ 冇裝 git。行：xcode-select --install"; exit 1; }

echo "▶ 初始化 repo…"
git init -q
git add .
git commit -qm "青年機會匯：6 個來源的活動聚合網站" || true
git branch -M main

if command -v gh >/dev/null; then
  echo "▶ 見到 GitHub CLI，直接開 repo 同 push…"
  gh auth status >/dev/null 2>&1 || gh auth login
  gh repo create "$USER/$REPO" --public --source=. --remote=origin --push
  echo "▶ 開 GitHub Pages（/docs）…"
  gh api -X POST "repos/$USER/$REPO/pages" \
    -f "source[branch]=main" -f "source[path]=/docs" 2>/dev/null || \
    echo "  （Pages 可能已經開咗，或者要去 Settings 手動開）"
  echo "▶ 畀 Actions 寫入權限…"
  gh api -X PUT "repos/$USER/$REPO/actions/permissions/workflow" \
    -f default_workflow_permissions=write >/dev/null
  echo "▶ 即刻跑一次抓取…"
  gh workflow run "update-data.yml" 2>/dev/null || echo "  （去 Actions 分頁手動撳 Run workflow）"
else
  echo "▶ 冇 GitHub CLI。兩個做法："
  echo
  echo "  A. 裝 gh（最方便）：brew install gh，然後再行一次呢個腳本"
  echo
  echo "  B. 手動："
  echo "     1. 去 https://github.com/new 開一個叫 $REPO 嘅 public repo（唔好剔任何 init 選項）"
  echo "     2. 行："
  echo "        git remote add origin https://github.com/$USER/$REPO.git"
  echo "        git push -u origin main"
  exit 0
fi

echo
echo "✅ 完成！"
echo "   Repo:  https://github.com/$USER/$REPO"
echo "   網站:  https://$USER.github.io/$REPO/   （首次 build 約 1-2 分鐘）"
echo "   Actions: https://github.com/$USER/$REPO/actions"
