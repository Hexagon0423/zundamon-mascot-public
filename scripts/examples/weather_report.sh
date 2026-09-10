#!/usr/bin/env bash
# 天気の読み上げ。open-meteo APIで生データを取り、文言だけ(claude CLIがあれば)
# ずんだもん口調で作らせる。claude CLIが無い/失敗した場合は、WMO天気コード→固定文言の
# 対応表にフォールバックする(定期実行される以上、喋らないより固定文言でも喋る方を優先)。
#
# 使い方:
#   1. cp scripts/examples/weather_location.example.sh scripts/examples/weather_location.sh
#      してPLACE_NAME/LAT/LONを自分の場所に書き換える
#   2. マスコットを起動しておく(python -m mascot.app)
#   3. bash scripts/examples/weather_report.sh [now|today|tomorrow]  (省略時はnow)
#
# 依存はcurlのみ(Windows標準のcurl.exe / Git Bash同梱のどちらでも動く)。jq等は使わない。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/speak.sh"

LOCATION_CONFIG="$SCRIPT_DIR/weather_location.sh"
if [ ! -f "$LOCATION_CONFIG" ]; then
    echo "$LOCATION_CONFIG が無いのだ。weather_location.example.sh をコピーして場所を設定するのだ:" >&2
    echo "  cp $SCRIPT_DIR/weather_location.example.sh $LOCATION_CONFIG" >&2
    exit 2
fi
# shellcheck source=/dev/null
source "$LOCATION_CONFIG"

MODE=${1:-now}
case "$MODE" in
    now|today|tomorrow) ;;
    *) echo "usage: $(basename "$0") [now|today|tomorrow]" >&2; exit 2 ;;
esac

fail() {
    speak "$1" worried
    exit 1
}

# VOICEVOXは生の数字を不自然に読むので、読み言葉のかなに直してから渡す
kana_number() {
    local n=$1 out="" ones=(ゼロ いち に さん よん ご ろく なな はち きゅう)
    if [ "$n" -lt 0 ]; then out="マイナス"; n=$(( -n )); fi
    local t=$(( n / 10 )) o=$(( n % 10 ))
    case "$t" in
        0) ;;
        1) out="${out}じゅう" ;;
        *) out="${out}${ones[$t]}じゅう" ;;
    esac
    if [ "$o" -ne 0 ] || [ "$n" -eq 0 ]; then out="${out}${ones[$o]}"; fi
    printf '%s' "$out"
}

# WMO天気コード→名詞(実況にも予報にも使えるよう「〜してる」等の活用は付けない)
sky_noun() {
    case "$1" in
        0)        printf '快晴' ;;
        1)        printf '晴れ' ;;
        2)        printf '薄曇り' ;;
        3)        printf '曇り' ;;
        45|48)    printf '霧' ;;
        51|53|55) printf '霧雨' ;;
        56|57)    printf '凍りそうな霧雨' ;;
        61|63)    printf '雨' ;;
        65)       printf '強い雨' ;;
        66|67)    printf '凍りそうな雨' ;;
        71|73|75) printf '雪' ;;
        77)       printf '細かい雪' ;;
        80|81)    printf 'にわか雨' ;;
        82)       printf '激しいにわか雨' ;;
        85|86)    printf 'にわか雪' ;;
        95)       printf '雷雨' ;;
        96|99)    printf '雹まじりの雷雨' ;;
        *)        printf 'なぞの天気' ;;
    esac
}

sky_expression() {
    case "$1" in
        0|1)            printf 'happy' ;;
        65|82|95|96|99) printf 'worried' ;;
        *)              printf 'normal' ;;
    esac
}

# PATHに無くてもネイティブインストール先を直接見に行く(タスクスケジューラから起動された
# 場合にPATHが痩せていることがあるため)。claude CLIが無くても動作に支障は無い
# (文言強化が効かず、下の固定文言だけになる)。
resolve_claude() {
    if command -v claude >/dev/null 2>&1; then
        command -v claude
        return 0
    fi
    local exe="$HOME/.local/bin/claude.exe"
    [ -x "$exe" ] && printf '%s' "$exe"
}

# 天気の要点($1)からずんだもん口調の一言を作らせる。失敗したら何も出力せず非ゼロで返る
llm_text() {
    local exe out
    exe=$(resolve_claude) || return 1
    [ -n "$exe" ] || return 1

    out=$(timeout 60 "$exe" --restricted --tools "" -p "次の天気を、ずんだもんの口調で一言にして。条件: 語尾は「のだ」、40文字以内、一文だけ、前置きや説明や記号は付けない、数字はひらがなの読みにする(例: 21度→にじゅういちど)。天気: $1" 2>/dev/null) || return 1

    out=$(printf '%s' "$out" | tr '\n' ' ' | sed 's/  */ /g; s/^ //; s/ $//')

    case "$out" in
        *のだ*) printf '%s' "$out" ;;
        *) return 1 ;;
    esac
}

# JSON配列 "key":[a,b] からn番目(0始まり)の値を取り出す。小数は切り捨てる
pick_from_array() {
    local key=$1 idx=$2
    printf '%s' "$DAILY" \
        | sed -n "s/.*\"${key}\":\[\([^]]*\)\].*/\1/p" \
        | cut -d, -f$(( idx + 1 )) \
        | sed 's/\..*//; s/[^0-9-]//g'
}

if [ "$MODE" = now ]; then
    WEATHER=$(curl -s "https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&current=temperature_2m,weather_code&timezone=Asia%2FTokyo")
    [ -n "$WEATHER" ] || fail "天気が取れなかったのだ…"

    CURRENT=${WEATHER##*\"current\":}
    TEMP=$(printf '%s' "$CURRENT" | sed -n 's/.*"temperature_2m":\(-\{0,1\}[0-9]*\).*/\1/p')
    CODE=$(printf '%s' "$CURRENT" | sed -n 's/.*"weather_code":\([0-9]*\).*/\1/p')
    [ -n "$TEMP" ] && [ -n "$CODE" ] || fail "天気のデータがうまく読めなかったのだ…"

    TEXT="今の${PLACE_NAME}は、$(kana_number "$TEMP")どで、$(sky_noun "$CODE")なのだ"
    FACTS="今の${PLACE_NAME}、$(sky_noun "$CODE")、気温${TEMP}度"
else
    WEATHER=$(curl -s "https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=2&timezone=Asia%2FTokyo")
    [ -n "$WEATHER" ] || fail "天気が取れなかったのだ…"

    DAILY=${WEATHER##*\"daily\":}
    if [ "$MODE" = today ]; then IDX=0; WHEN="今日"; else IDX=1; WHEN="明日"; fi

    CODE=$(pick_from_array weather_code "$IDX")
    TMAX=$(pick_from_array temperature_2m_max "$IDX")
    TMIN=$(pick_from_array temperature_2m_min "$IDX")
    [ -n "$CODE" ] && [ -n "$TMAX" ] && [ -n "$TMIN" ] || fail "天気のデータがうまく読めなかったのだ…"

    TEXT="${WHEN}の${PLACE_NAME}は、$(sky_noun "$CODE")の見込みなのだ。最高$(kana_number "$TMAX")ど、最低$(kana_number "$TMIN")どなのだ"
    FACTS="${PLACE_NAME}の${WHEN}の予報、$(sky_noun "$CODE")、最高気温${TMAX}度、最低気温${TMIN}度"
fi

LLM=$(llm_text "$FACTS") && TEXT=$LLM

speak "$TEXT" "$(sky_expression "$CODE")"
