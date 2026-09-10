#!/usr/bin/env bash
# 汎用の発話ヘルパー。マスコット(mascot.app)のHTTP APIに直接POSTするだけの
# 薄いラッパーで、Claude Codeなど特定ツールには依存しない。
#
# 使い方: source scripts/examples/speak.sh してから speak "テキスト" [expression]
#
# ポートは環境変数 MASCOT_PORT で上書きできる(既定は50022、config.jsonの既定値と同じ)。
MASCOT_PORT="${MASCOT_PORT:-50022}"

speak() {
    local text="$1" expression="${2:-}"
    python -c "
import sys, json, urllib.request

text = sys.argv[1]
expression = sys.argv[2] or None
payload = {'text': text}
if expression:
    payload['expression'] = expression
data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(
    'http://127.0.0.1:${MASCOT_PORT}/speak',
    data=data,
    headers={'Content-Type': 'application/json'},
    method='POST',
)
try:
    with urllib.request.urlopen(req, timeout=3) as resp:
        sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
" "$text" "$expression"
}
