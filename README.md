# 高精度 AI競馬的中予想システム (Precision Horse Racing AI)

機械学習（LightGBM / Random Forest）と期待値（EV）算出アルゴリズムを統合した競馬的中予想アプリケーションです。

## 主な機能

1. **AI勝率・複勝率予測**
   - 過去走スピード指数、騎手/調教師勝率、斤量、馬場適性などの多角的なデータから勝ち馬確率および複勝確率を算出します。

2. **期待値（EV）に基づく推奨買い目生成**
   - 単勝 (Win)、複勝 (Place)、馬単 (Exacta)、3連複 (Trio) の期待値を自動計算し、収益性の高い買い目を自動提案します。

3. **直感的なWeb UI & インタラクティブ操作**
   - サンプルG1レース（ジャパンカップ、有馬記念など）の切り替え。
   - 出走馬データの手動追加・条件調整機能。
   - ワンクリックでのAIモデル再学習機能。

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
pip install pandas numpy scikit-learn lightgbm flask pytest
```

### 2. アプリケーションの起動
```bash
python3 app.py
```
ブラウザで `http://localhost:5000` にアクセスします。

### 3. テストの実行
```bash
PYTHONPATH=. pytest -v
```
