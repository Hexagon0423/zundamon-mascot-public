#!/usr/bin/env bash
# 毎時の時報。Windowsのタスクスケジューラから直接呼ぶことを想定した、完全に機械的な
# スクリプト(LLMや外部ツールを一切介さない)。マスコット(mascot.app)が起動している
# 必要がある(HTTP APIにPOSTするだけなので、未起動なら黙って失敗する)。
#
# 使い方:
#   1. マスコットを起動しておく(python -m mascot.app)
#   2. bash scripts/examples/hourly_chime.sh を毎時0分に叩くタスクを登録する
#      (Windowsタスクスケジューラの例は README を参照)
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/speak.sh"

HOUR=$(date +%-H)  # 先頭ゼロなし(0-23)

if [ "$HOUR" -eq 0 ]; then
    TEXT="日付が変わって、ゼロ時になったのだ"
elif [ "$HOUR" -eq 12 ]; then
    TEXT="お昼の12時になったのだ"
else
    TEXT="${HOUR}時になったのだ"
fi

speak "$TEXT" normal
