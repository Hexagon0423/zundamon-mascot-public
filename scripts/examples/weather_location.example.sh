# weather_report.sh が読む場所の設定。
# scripts/examples/weather_location.sh という名前でコピーして、自分の場所に書き換えること
# (weather_location.sh はgitignore対象なので、書き換えてもコミットされない)。
#
#   cp scripts/examples/weather_location.example.sh scripts/examples/weather_location.sh
#
# 緯度経度は https://www.google.com/maps などで自分の場所を右クリックすると出てくる値でよい。
PLACE_NAME="東京"
LAT=35.6812
LON=139.7671
