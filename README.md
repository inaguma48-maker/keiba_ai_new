# 競馬 出馬表・オッズ ビューア / 予測検証ツール

JRA公式サイトの出馬表とオッズを取得し、オッズから計算した**市場確率**を表示します。

**AIの予測は表示していません。** 過去の実データ（約3.7万レース）で検証した結果、予測モデルは実際のオッズを上回れなかったためです
（`keiba/eval_odds.py` の結果と `docs/DESIGN.md` を参照）。検証用のコード（`keiba/`）と、旧予測モジュール（`src/predictor.py` `src/strategy.py`）は残してあり、
実オッズで改善が確認できた時点で表示を戻します。

## 主な機能

1. JRA公式サイトの出馬表・単勝オッズの自動取得（1タップ）と市場確率の表示
2. 出馬表の貼り付け・URL指定での取り込み（オッズが読めない行は取り込まず、推測で補いません）
3. 過去データ(keiba.db)での学習・評価（`keiba/train.py`）と、実オッズでの検証（`keiba/eval_odds.py`）

## ディレクトリ構造

```
├── app.py                 # Flask API サーバー
├── src/
│   ├── models.py          # レース・馬データモデル定義
│   ├── data.py            # データ抽出・特徴量生成・シミュレーションデータ作成
│   ├── predictor.py       # LightGBM / Random Forest 予想エンジン
│   └── strategy.py        # 期待値・推奨買い目計算モジュール
├── templates/
│   └── index.html         # メイン画面テンプレート
├── static/
│   └── app.js             # UI制御 & API連携スクリプト
└── tests/
    └── test_app.py        # ユニット・統合テスト
```

## 起動方法

### 1. 依存ライブラリのインストール
```bash
pip install -r requirements.txt
```

### 2. アプリケーションの起動
```bash
python3 app.py
```
ブラウザで `http://localhost:5000` にアクセスします。

### Windowsで自動起動する
`tools\install_autostart.bat` をダブルクリックします（Pythonが入っていること）。
- アプリを `%USERPROFILE%\keiba_app` にコピーし、Windowsにログインするたびに裏で自動起動します（画面は出ません）。
- デスクトップに `keiba-viewer`（`http://localhost:5000` へのショートカット）が作られます。
- 更新したいときは、新しいZIPを解凍して、同じバッチをもう一度実行します（保存済みのレースは残ります）。
- 解除は `tools\uninstall_autostart.bat`。記録は `%USERPROFILE%\keiba_app\data\viewer.log` に出ます。
- 既定ではこのPCからのみ接続できます。スマホなど同じネットワークの機器から見たい場合は、環境変数 `KEIBA_HOST` に `0.0.0.0` を設定します。

### レースリプレイ
- 過去レースの**実際のタイムと上がり3F**（`keiba.db`）を、**JRA公式の寸法**（1周・直線・幅員）に合わせたコース上で再生します。
- 横から見る走行シーン、実寸のコース上のミニマップ、順位、実況（データから生成）を表示します。
- `keiba.db` は既定で `%USERPROFILE%\.keiba\db\keiba.db` を読みます（別の場所なら環境変数 `KEIBA_DB`）。結果が無いレース（これから行われるレース）は、コースと出走馬だけを表示します。
- 馬どうしの間隔と走るコース（内外）は、タイムから計算した表示です。コースの形は、1周距離と直線距離に合わせた簡易形状です。
- 寸法の出典と確認: `src/course_specs.py`、`python tools/verify_course_specs.py`（JRAのページと全数値を照合）。

### シミュレーション（層1／層2）
- 層1: 能力のみ（オッズも人気順位も使いません）／ 層2: 能力×人気順位（人気順位は画面のオッズの低い順）。画面右上で選びます。
- 選んだ層の勝率でサイコロを振って着順とタイムを作り、リプレイと同じ画面で走らせます（押すたびに変わる架空のレースです。予想ではありません）。
- 使う能力モデルは、先に一度、学習が必要です（数分）:
  `python keiba\train.py "%USERPROFILE%\.keiba\db\keiba.db"` → モデルは `%USERPROFILE%\.keiba\models` に保存され、ZIPを入れ替えても残ります。
- これから行われるレースは、出走馬の特徴量が `keiba.db` に作られた後でないと予測できません（その旨を画面に表示します）。
- 過去の検証では、層1の1番手の1着率は27.0%で、人気1位(33.3%)を下回りました。

### JRA公式サイトからの取得について
- 「1タップでJRA最新レース・オッズ自動取得」は、アプリを実行しているPCから `www.jra.go.jp` に直接接続します（インターネット接続が必要）。
- 取得したHTMLは `data/raw/jra/` に保存されます（git管理外）。
- 接続や解析に失敗したときは、固定データを使わずエラーを表示します。
- JRAの出馬表には過去成績が含まれないため、スピード指数などは仮の固定値です。予測値は参考になりません（`docs/DESIGN.md` §2）。

### 3. テストの実行
```bash
PYTHONPATH=. pytest -v
```

## 過去データでの学習・評価（既存の keiba.db を読み取り専用で使用）
```bash
pip install -r requirements.txt
python tools/profile_keiba_db.py "C:\Users\<ユーザー名>\.keiba\db\keiba.db"   # DBの形式を集計表示
python keiba/train.py "C:\Users\<ユーザー名>\.keiba\db\keiba.db"              # 学習・評価（レポートは data/reports/）
```
- 学習 〜2024-08-31 / 検証 〜2025-08-31 / テスト それ以降（`--train-end` `--valid-end` で変更可）。
- 過去のオッズが無いため、市場の代わりに確定人気順位を使います。詳細は `docs/DESIGN.md` §7。
