"""
Evaluate against REAL win odds (odds_history), which exist only for recent races.

Compares: uniform / popularity-only proxy / real-odds market / Stage1 / Stage2(proxy) /
Stage1 x real odds (blend weights fitted out-of-fold). Also tests EV-based win bets.

usage: python keiba/eval_odds.py <path-to-keiba.db> [--train-end ...] [--valid-end ...]
Read-only on the DB. Report goes to data/reports/.
"""

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd

from keiba import dataset as ds
from keiba import model as md
from keiba.train import ROOT, bootstrap_ci, fit_all, win_payouts

THETAS = (1.0, 1.1, 1.2)  # fixed in advance; all are reported


def load_odds(db_path):
    con = ds.connect_ro(db_path)
    try:
        odds = pd.read_sql_query(
            "select race_id, horse_number, recorded_at, snapshot_label, win_odds from odds_history "
            "where win_odds is not null", con)
        posts = pd.read_sql_query("select race_id, race_date, post_time from races", con)
    finally:
        con.close()
    odds["win_odds"] = pd.to_numeric(odds["win_odds"], errors="coerce")
    odds = odds[odds["win_odds"] > 0]
    odds["recorded_at"] = pd.to_datetime(odds["recorded_at"], errors="coerce")
    odds["label_dt"] = pd.to_datetime(odds["snapshot_label"], format="%Y-%m-%dT%H:%M", errors="coerce")
    posts["post_dt"] = pd.to_datetime(posts["race_date"].astype(str) + " " + posts["post_time"].astype(str).str[:5],
                                      errors="coerce")
    return odds, posts


def last_snapshot(odds: pd.DataFrame) -> pd.DataFrame:
    """Latest recorded odds per horse (close to the final odds)."""
    o = odds.dropna(subset=["recorded_at"]).sort_values("recorded_at")
    return o.drop_duplicates(["race_id", "horse_number"], keep="last")[["race_id", "horse_number", "win_odds"]]


def snapshot_before_post(odds: pd.DataFrame, posts: pd.DataFrame, minutes: int = 30) -> pd.DataFrame:
    """Latest labelled snapshot taken at least `minutes` before the post time (label assumed local time)."""
    o = odds.merge(posts[["race_id", "post_dt"]], on="race_id").dropna(subset=["label_dt", "post_dt"])
    o = o[(o["label_dt"] <= o["post_dt"] - pd.Timedelta(minutes=minutes)) & (o["label_dt"].dt.date == o["post_dt"].dt.date)]
    latest = o.groupby("race_id")["label_dt"].transform("max")
    return o[o["label_dt"] == latest].drop_duplicates(["race_id", "horse_number"], keep="last")[
        ["race_id", "horse_number", "win_odds"]]


def complete_races(test: pd.DataFrame, snap: pd.DataFrame, pay: dict) -> pd.DataFrame:
    """Races where every starter has odds and a win payout exists."""
    d = test.merge(snap, on=["race_id", "horse_number"], how="left")
    ok = d.groupby("race_id")["win_odds"].transform(lambda s: s.notna().all())
    d = d[ok].copy()
    with_pay = {r for (r, _h) in pay}
    return d[d["race_id"].isin(with_pay)].reset_index(drop=True)


def oof_blend(d: pd.DataFrame, p1: np.ndarray, q: np.ndarray, folds: int = 5, seed: int = 0) -> np.ndarray:
    ids = d["race_id"].to_numpy()
    races = np.array(sorted(set(ids)))
    fold = dict(zip(np.random.default_rng(seed).permutation(races), np.arange(len(races)) % folds))
    f = np.array([fold[r] for r in ids])
    out = np.zeros(len(d))
    for k in range(folds):
        te, tr = f == k, f != k
        a, b, _ = md.fit_blend(d[tr], p1[tr], q[tr])
        out[te] = md.blend(ids[te], p1[te], q[te], a, b)
    return out


def ev_bets(d: pd.DataFrame, p: np.ndarray, pay: dict, theta: float) -> str:
    sel = d.assign(p=p)
    sel = sel[sel["p"] * sel["win_odds"] >= theta]
    if sel.empty:
        return f"  期待値 {theta:.1f}以上: 該当なし"
    sel = sel.assign(ret=[pay.get((r, int(h)), 0) / 100.0 for r, h in zip(sel["race_id"], sel["horse_number"])])
    per_race = sel.groupby("race_id").agg(stake=("ret", "size"), ret=("ret", "sum"))
    rng = np.random.default_rng(0)
    st, rt = per_race["stake"].to_numpy(), per_race["ret"].to_numpy()
    boots = [(rt[i].sum() / st[i].sum()) for i in (rng.integers(0, len(st), len(st)) for _ in range(2000))]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (f"  期待値 {theta:.1f}以上: {len(sel)}点 / {len(per_race)}レース  回収率 {rt.sum() / st.sum() * 100:.1f}% "
            f"(95%信頼区間 {lo * 100:.1f}〜{hi * 100:.1f}%)  的中率 {(sel['ret'] > 0).mean() * 100:.1f}%")


def evaluate(d: pd.DataFrame, models, pay, title: str) -> list:
    m1, rank_table, alpha, beta, feats = models
    ids = d["race_id"].to_numpy()
    p1 = md.predict_stage1(m1, d, feats)
    pr = md.predict_rank(rank_table, d)
    q = md.normalize(ids, 1.0 / d["win_odds"].to_numpy())
    p2 = md.blend(ids, p1, pr, alpha, beta)
    p3 = oof_blend(d, p1, q)
    uni = md.normalize(ids, np.ones(len(d)))
    ll = {"一様": md.race_logloss(d, uni), "人気順位のみ(代用)": md.race_logloss(d, pr), "実オッズの市場": md.race_logloss(d, q),
          "Stage1(能力のみ)": md.race_logloss(d, p1), "Stage2(能力×人気順位)": md.race_logloss(d, p2),
          "能力×実オッズ(重みは交差検証)": md.race_logloss(d, p3)}
    idx = ll["実オッズの市場"].index
    diff = (ll["実オッズの市場"].loc[idx] - ll["能力×実オッズ(重みは交差検証)"].loc[idx]).to_numpy()
    m, lo, hi = bootstrap_ci(diff)
    inv_sum = d.assign(i=1.0 / d["win_odds"]).groupby("race_id")["i"].sum()
    all_ret = np.array([pay.get((r, int(h)), 0) for r, h in zip(d["race_id"], d["horse_number"])]) / 100.0
    lines = [f"## {title}  ({d['race_id'].nunique()}レース / {len(d)}頭)",
             "  勝ち馬に付けた確率の質（対数損失。小さいほど良い）:",
             *[f"    {k}: {v.mean():.4f}" for k, v in ll.items()],
             f"  実オッズの市場に対する改善量（能力×実オッズ）: 平均 {m:+.4f}  95%信頼区間 {lo:+.4f}〜{hi:+.4f}  →  "
             + ("改善を確認" if lo > 0 else "改善は確認できない（信頼区間が0を含む、または負）"),
             f"  オッズの点検: 1/オッズの合計の平均 {inv_sum.mean():.3f}（払戻率80%なら理論値は約1.25）",
             f"  全頭に100円ずつ買った回収率 {all_ret.mean() * 100:.1f}%（払戻率80%に近いほど、オッズと払戻が整合）",
             "  能力×実オッズの確率で、期待値が基準以上の馬の単勝を100円ずつ買った場合:",
             *[ev_bets(d, p3, pay, t) for t in THETAS]]
    return lines


def run(db_path, train_end, valid_end, out_dir=None) -> str:
    out_dir = out_dir or os.path.join(ROOT, "data", "reports")
    raw, fv = ds.load_raw(db_path)
    df, feats, _ = ds.prepare(raw)
    train, valid, test = ds.split_by_date(df, train_end, valid_end)
    if train["race_id"].nunique() < 20 or valid["race_id"].nunique() < 20:
        raise ValueError("学習または検証期間のレースが少なすぎます。")
    m1, rank_table, alpha, beta = fit_all(train, valid, feats)

    odds, posts = load_odds(db_path)
    pay = win_payouts(db_path)
    lag = (odds["recorded_at"] - odds["label_dt"]).dropna().dt.total_seconds().div(60)
    lines = ["# 実オッズでの検証レポート", f"作成: {datetime.now():%Y-%m-%d %H:%M}  学習 〜{train_end} / 検証 〜{valid_end}",
             f"  モデルは学習期間のデータだけで作成。実オッズの期間は、モデル作成後のレースです。",
             f"  odds_history の記録時刻とラベル時刻の差（中央値）: {lag.median():.0f}分" if len(lag) else "  記録時刻とラベルの比較: データなし",
             "  ※ この差が約540分なら、記録時刻はUTC（日本時間と9時間ずれ）の可能性があります。", ""]

    models = (m1, rank_table, alpha, beta, feats)
    shown = False
    for title, snap in (("確定に近いオッズ（各馬の最後の記録）", last_snapshot(odds)),
                        ("発走30分前のオッズ（ラベル時刻が日本時間と仮定）", snapshot_before_post(odds, posts, 30))):
        d = complete_races(test, snap, pay)
        if d["race_id"].nunique() < 30:
            lines += [f"## {title}", f"  対象が{d['race_id'].nunique()}レースしかなく、評価できません。", ""]
            continue
        lines += evaluate(d, models, pay, title) + [""]
        shown = True
    if not shown:
        lines.append("実オッズで評価できるレースが不足しています。")
    lines += ["## 注意",
              "  ・対象は数百レースで少なく、結果はぶれやすいです。信頼区間を必ず見てください。",
              "  ・「確定に近いオッズ」は発走前に買える価格ではありません。実際に買える価格に近いのは30分前のほうです。",
              "  ・期待値の基準(1.0/1.1/1.2)は事前に決めた3通りで、すべて表示しています。良い結果だけを選ばないでください。"]
    report = "\n".join(lines)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"eval_odds_{datetime.now():%Y%m%d-%H%M%S}.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--train-end", default="2024-08-31")
    ap.add_argument("--valid-end", default="2025-08-31")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    try:
        print(run(a.db, a.train_end, a.valid_end, a.out_dir))
    except (FileNotFoundError, ValueError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
