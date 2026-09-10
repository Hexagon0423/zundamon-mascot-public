# zundamon-mascot

デスクトップに常駐する、ずんだもんの立ち絵/Live2Dマスコット。任意のアプリやスクリプトから
ローカルHTTP APIを叩くと、VOICEVOXの声で読み上げ、音声に合わせて口パクする。

- 常駐ウィンドウ: フレームレス・透過・常時最前面・ドラッグ移動・位置記憶
- 2種類の描画バックエンドを切り替え式で搭載
  - **PNG合成版**: パーツ(体・眉・目・口・腕...)を組み合わせて1枚に合成。表情・ポーズをプリセットとして持てる
  - **Live2D版**: Live2Dモデルを読み込んで描画。表情・ポーズはモデル側のexpression/motionを使う
- `POST /speak {"text": "..."}` で読み上げをキューに積める(母音タイムラインに基づく口パク付き)
- まばたき・アイドルポーズ・画面端での自動左右反転など、細かい「生きてる感」の作り込み

**このリポジトリにはコードだけが入っている。立ち絵・Live2Dモデルなどの素材は同梱していない**
(理由は下記「素材について」を参照)。素材が無くても、後述の仮素材生成スクリプトで
最小限の見た目のまま全部の機能を試せる。

> **このリポジトリは素体(テンプレート)として置いてあるもので、継続的な更新やサポートは
> 予定していない。** forkして自分の好きなように改造して使ってほしい。

## 用意しておくもの

### 必須

| もの | 用途 |
|---|---|
| Windows | 常時最前面・透過ウィンドウ・クリック透過などWin32寄りの実装のため、動作確認はWindowsのみ |
| Python 3.10+ | マスコット本体 |
| **[VOICEVOX](https://voicevox.hiroshiba.jp/)** | 音声合成。**インストールして、ローカルで起動しておくこと**(既定は`http://127.0.0.1:50021`。マスコットが自動では起動しない) |

VOICEVOXを入れ忘れたままマスコットを起動すると、見た目は動くのに何度喋らせても無音になる
(エラーも出にくい)。喋らない時はまずVOICEVOXが起動しているか確認すること。

### 任意(お好みで)

| もの | 用途 |
|---|---|
| 立ち絵PNG または Live2Dモデル | 無くても仮素材(緑の丸っこいプレースホルダー)で全機能を試せる。用意する場合は下記「素材について」参照 |
| Claude Code、その他好きな自動化ツール | マスコットは`POST /speak`というHTTP APIしか要求しないので、これを叩ける物なら何でも連携できる。**必須ではない** |
| `claude` CLI | `scripts/examples/weather_report.sh`が天気の文言をずんだもん口調に整形するのに使う(無くても固定文言にフォールバックするので無くても動く) |

なお、マスコットは外部サービスにデータを送らない。通信するのは自分のPCの中で動く
VOICEVOX(`127.0.0.1:50021`)だけで、例外は`weather_report.sh`を使ったときの天気API
([open-meteo](https://open-meteo.com/)、緯度経度を送るだけ)。アカウント登録もAPIキーも要らない。

## セットアップ

```bash
git clone https://github.com/Hexagon0423/zundamon-mascot-public.git zundamon-mascot
cd zundamon-mascot
pip install -e ".[dev]"

# 仮素材を生成する(実素材が無くてもここまでで動作確認できる)
python scripts/generate_placeholder_assets.py

pytest   # 全部通ることを確認

python -m mascot.app   # マスコットを起動
```

起動すると画面右下あたりに(仮素材の)マスコットが表示され、`http://127.0.0.1:50022/speak`
がリッスンされる。試しに喋らせるには:

```bash
curl -X POST http://127.0.0.1:50022/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "こんにちはなのだ", "expression": "happy"}'
```

VOICEVOXが起動していれば、その声で読み上げながら口パクする。`expression`は省略可能で、
指定すると該当する表情プリセットに切り替わる(使える名前は`src/mascot/window.py`の
`EXPRESSION_PRESETS`、または`src/mascot/live2d_expressions.py`の`EXPRESSION_PRESETS`を参照)。

## 素材について(立ち絵・Live2Dモデル)

**このリポジトリには本物の立ち絵PNGやLive2Dモデルを含めていない。** どちらも無償配布されている
ものだが、配布元の利用規約が「利用者本人が個別に同意して公式配布元から入手する」ことを
前提にしているため、リポジトリに同梱して再配布はしない方針にしている。自分で用意する場合は
以下を参照。

### PNG立ち絵セットを追加する

`assets/sets/<セット名>/` に `manifest.json` を置く。スキーマは`src/mascot/assets.py`の
docstringと、`scripts/generate_placeholder_assets.py`が生成する仮素材のmanifestを参照。
要点:
- パーツ(`body`/`brow`/`eyes`/`mouth`など)ごとに複数のレイヤー画像を持ち、1枚を選んで合成する
- 母音(あいうえお)をどのmouthレイヤーに対応させるかは`vowel_mouth_map`で指定する
  (アートによっては開き具合3段階しか無い場合もあるので、そこは柔軟にしてある)

坂本アヒル氏の「ずんだもん立ち絵素材改」のような既存の無償立ち絵素材を使う場合は、
配布元の利用規約に従って入手・利用すること。

### Live2Dモデルを追加する

`assets/live2d/<モデル名>/runtime/<モデル名>.model3.json` という配置にする
(Cubism SDKの標準的なランタイム出力構成)。`config.json`の`asset_set`を
`live2d:<モデル名>` にすると、そのモデルで起動する。

公式のずんだもんLive2Dモデルは
[Live2D公式サンプルデータ配布ページ](https://www.live2d.com/learn/sample/zundamon/)から、
`無償提供マテリアルの使用許諾契約書`への同意の上で入手できる。

## 外部ツールとの連携(Claude Codeなど)

マスコットは`POST /speak`というシンプルなHTTP APIしか要求しない。Claude CodeのHookや、
その他好きな自動化ツールから、上のcurl例と同じ形でリクエストを送ればよい。

## 定期的に喋らせるサンプル(任意)

`scripts/examples/` に、マスコットのHTTP APIを直接叩くだけの独立したスクリプトを2つ用意した
(どちらもClaude Code等には依存しない)。

```bash
bash scripts/examples/hourly_chime.sh          # 今の時刻を読み上げる(時報)

cp scripts/examples/weather_location.example.sh scripts/examples/weather_location.sh
# weather_location.sh を自分の場所(PLACE_NAME/LAT/LON)に書き換える

bash scripts/examples/weather_report.sh now    # 今の天気
bash scripts/examples/weather_report.sh today  # 今日の予報
bash scripts/examples/weather_report.sh tomorrow  # 明日の予報
```

`weather_location.sh`は`.gitignore`対象なので、書き換えても自分のリポジトリにコミットされない。

毎時・毎朝など定期実行したい場合は、Windowsのタスクスケジューラに登録する
(PowerShellの例):

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Program Files\Git\bin\bash.exe" `
    -Argument '"<リポジトリのパス>\scripts\examples\hourly_chime.sh"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName "ZundamonHourlyChime" -Action $action -Trigger $trigger
```

## テスト

```bash
pytest
```

`assets/sets/zundamon_kai`・`assets/sets/seihuku`・`assets/live2d/zundamon`のような
特定の実素材の名前に依存するテストは、その素材が無い環境では自動でskipされる
(仮素材`vowel_5`/`aperture_3`に依存するテストは常に実行される)。

見た目の実機検証スクリプト(マスコット起動中に`scripts/`から実行):

```bash
python scripts/verify_lipsync_visually.py   # 喋らせながら連写して口の形を確認
python scripts/verify_blink.py 20           # まばたきしているか確認
python scripts/verify_live2d_expressions.py [--presets]   # Live2Dの表情/プリセット一覧を画像化
```

## ライセンス

このリポジトリのコードは[MIT License](LICENSE)。同梱していない素材(立ち絵・Live2Dモデル)には
それぞれ別のライセンスが適用されるので、入手先の利用規約に従うこと。
