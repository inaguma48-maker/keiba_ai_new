"""
Train Stage1, fit Stage2, evaluate on a held-out period and write a report.

usage: python keiba/train.py <path-to-keiba.db> [--train-end 2024-08-31] [--valid-end 2025-08-31]

The DB is opened read-only. Outputs go to data/reports/ and models/ (both git-ignored).
"""

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import joblib
import numpy as np
import pandas as pd

from keiba import dataset as ds
from keiba import model as md

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def bootstrap_ci(values: np.ndarray, n_boot: int = 2000, seed: int = 0):
    v = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(n_boot)])
    return float(v.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def win_payouts(db_path) -> dict:
    con = ds.connect_ro(db_path)
    try:
        rows = con.execute("select race_id, combination, amount_yen from payouts where bet_type='win'").fetchall()
    finally:
        con.close()
    out = {}
    for rid, comb, amt in rows:
        try:
            out[(rid, int(str(comb).strip()))] = out.get((rid, int(str(comb).strip())), 0) + int(amt)
        except (TypeError, ValueError):
            continue
    return out


def pick_top(df: pd.DataFrame, by: str, ascending: bool) -> pd.DataFrame:
    return df.sort_values([by, "horse_number"], ascending=[ascending, True]).drop_duplicates("race_id")


def roi_row(name, picks, pay, race_ids_with_pay):
    p = picks[picks["race_id"].isin(race_ids_with_pay)]
    ret = np.array([pay.get((r, int(h)), 0) for r, h in zip(p["race_id"], p["horse_number"])], dtype=float)
    if len(ret) == 0:
        return f"  {name}: 対象レースなし"
    m, lo, hi = bootstrap_ci(ret / 100.0)
    return f"  {name}: 回収率 {m * 100:.1f}% (95%信頼区間 {lo * 100:.1f}〜{hi * 100:.1f}%)  的中率 {np.mean(ret > 0) * 100:.1f}%  {len(ret)}レース"


def leak_canary(train: pd.DataFrame, feature_cols, limit: float = 0.72):
    """Single features that predict the winner suspiciously well (possible leakage)."""
    from sklearn.metrics import roc_auc_score
    flagged = []
    for c in feature_cols:
        if not pd.api.types.is_numeric_dtype(train[c]):
            continue
        v = train[[c, "is_win"]].dropna()
        if len(v) < 1000 or v[c].nunique() < 2 or v["is_win"].nunique() < 2:
            continue
        auc = roc_auc_score(v["is_win"], v[c])
        if max(auc, 1 - auc) > limit:
            flagged.append((c, max(auc, 1 - auc)))
    return flagged


def calibration(df, p, bins=10):
    d = pd.DataFrame({"p": p, "y": df["is_win"].to_numpy()})
    d["bin"] = pd.qcut(d["p"].rank(method="first"), bins, labels=False)
    g = d.groupby("bin").agg(pred=("p", "mean"), actual=("y", "mean"), n=("y", "size"))
    return [f"  {int(i) + 1:>2}分位  予測 {r.pred * 100:5.1f}%  実際 {r.actual * 100:5.1f}%  (n={int(r.n)})" for i, r in g.iterrows()]


def run(db_path, train_end, valid_end, out_dir=None, model_dir=None, feature_version=None) -> str:
    out_dir = out_dir or os.path.join(ROOT, "data", "reports")
    model_dir = model_dir or os.path.join(ROOT, "models")
    raw, fv = ds.load_raw(db_path, feature_version)
    df, feature_cols, cat_cols = ds.prepare(raw)
    train, valid, test = ds.split_by_date(df, train_end, valid_end)
    for name, part in (("学習", train), ("検証", valid), ("テスト", test)):
        if part["race_id"].nunique() < 20:
            raise ValueError(f"{name}期間のレースが少なすぎます({part['race_id'].nunique()}件)。期間の指定を見直してください。")

    m1 = md.fit_stage1(train, valid, feature_cols)
    rank_table = md.fit_rank_table(train)

    p1_v, pr_v = md.predict_stage1(m1, valid, feature_cols), md.predict_rank(rank_table, valid)
    alpha, beta, _ = md.fit_blend(valid, p1_v, pr_v)

    ids_t = test["race_id"].to_numpy()
    p1_t = md.predict_stage1(m1, test, feature_cols)
    pr_t = md.predict_rank(rank_table, test)
    p2_t = md.blend(ids_t, p1_t, pr_t, alpha, beta)
    uni_t = md.normalize(ids_t, np.ones(len(test)))

    ll = {k: md.race_logloss(test, p) for k, p in
          (("一様(全頭同じ確率)", uni_t), ("人気順位のみ(市場の代用)", pr_t), ("Stage1(能力モデル)", p1_t), ("Stage2(統合)", p2_t))}
    hit = {"人気順位のみ(市場の代用)": md.top1_hit_rate(test, pr_t), "Stage1(能力モデル)": md.top1_hit_rate(test, p1_t),
           "Stage2(統合)": md.top1_hit_rate(test, p2_t)}
    common = ll["Stage2(統合)"].index.intersection(ll["人気順位のみ(市場の代用)"].index)
    diff = (ll["人気順位のみ(市場の代用)"].loc[common] - ll["Stage2(統合)"].loc[common]).to_numpy()
    d_mean, d_lo, d_hi = bootstrap_ci(diff)

    pay = win_payouts(db_path)
    with_pay = {r for (r, _h) in pay}
    t = test.assign(p1=p1_t, p2=p2_t)

    canary = leak_canary(train, feature_cols)
    imp = pd.Series(m1.booster_.feature_importance("gain"), index=feature_cols).sort_values(ascending=False)

    lines = [
        "# 学習・評価レポート", f"作成: {datetime.now():%Y-%m-%d %H:%M}  DB: {os.path.basename(str(db_path))}  特徴量バージョン: {fv}",
        "",
        "## データ",
        f"  対象: 平地レースのみ（障害は除外）。出走取消・除外は除く。特徴量 {len(feature_cols)} 列",
        f"  学習  〜{train_end}: {train['race_id'].nunique()}レース / {len(train)}頭",
        f"  検証  〜{valid_end}: {valid['race_id'].nunique()}レース / {len(valid)}頭",
        f"  テスト {valid_end}より後: {test['race_id'].nunique()}レース / {len(test)}頭 （最終評価にだけ使用）",
        "",
        "## 勝ち馬に付けた確率の質（対数損失。小さいほど良い）", *[f"  {k}: {v.mean():.4f}" for k, v in ll.items()],
        "",
        "## 1番手に選んだ馬の1着率", *[f"  {k}: {v * 100:.1f}%" for k, v in hit.items()],
        "",
        f"## Stage2の重み（検証期間で決定）  能力モデル α={alpha:.1f}  人気順位 β={beta:.1f}",
        "  αが0なら、能力モデルは人気順位以上の情報を持たない。",
        "",
        "## 市場の代用（人気順位のみ）との差（対数損失の改善量。正なら Stage2 が良い）",
        f"  平均 {d_mean:+.4f}  95%信頼区間 {d_lo:+.4f}〜{d_hi:+.4f}  →  "
        + ("信頼区間が0を含まない: 改善を確認" if d_lo > 0 else "信頼区間が0を含む（または負）: 改善は確認できない"),
        "",
        "## 単勝を各レース100円で買った場合の実績（テスト期間・確定払戻）",
        roi_row("人気1位", pick_top(t, "popularity", True), pay, with_pay),
        roi_row("Stage1の1番手", pick_top(t, "p1", False), pay, with_pay),
        roi_row("Stage2の1番手", pick_top(t, "p2", False), pay, with_pay),
        "  ※ 過去のオッズが無いため、期待値で買い目を選ぶ検証はできていません。回収率は上の3通りの買い方だけの結果です。",
        "",
        "## 校正（Stage2・テスト期間。予測と実際が近いほど良い）", *calibration(test, p2_t),
        "",
        "## 重要度の高い特徴量（Stage1・上位15）", *[f"  {k}: {v:.0f}" for k, v in imp.head(15).items()],
        "",
        "## 情報漏れ(リーク)の点検: 1列だけで勝ち馬をよく当てる特徴量（AUC 0.72超）",
        *(["  なし"] if not canary else [f"  要確認: {c} (AUC {a:.2f})" for c, a in canary]),
        "",
        "## 注意",
        "  ・人気順位は発走直前に確定する値です。予測時点（発走の数十分前）の人気とは多少ずれます。",
        "  ・上の結果は過去のテスト期間での実績で、将来の利益を保証しません。",
    ]
    report = "\n".join(lines)

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(model_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with open(os.path.join(out_dir, f"train_report_{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    joblib.dump({"model": m1, "feature_cols": feature_cols, "cat_cols": cat_cols,
                 "categories": {c: list(df[c].cat.categories) for c in cat_cols}, "rank_table": rank_table,
                 "alpha": alpha, "beta": beta, "feature_version": fv, "train_end": train_end,
                 "valid_end": valid_end, "trained_at": stamp}, os.path.join(model_dir, f"keiba_stage12_{stamp}.joblib"))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--train-end", default="2024-08-31")
    ap.add_argument("--valid-end", default="2025-08-31")
    ap.add_argument("--feature-version", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--model-dir", default=None)
    a = ap.parse_args(argv)
    try:
        print(run(a.db, a.train_end, a.valid_end, a.out_dir, a.model_dir, a.feature_version))
    except (FileNotFoundError, ValueError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
