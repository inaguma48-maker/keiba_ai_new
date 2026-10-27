"""
資金30倍到達シミュレーション (NotebookLM資料用)
期待値(EV = 的中確率 x オッズ)と賭け方ごとに「破産前に30倍へ届く確率」をモンテカルロで推定する。
実行: python3 tools/sim_30x.py
"""

import numpy as np

TARGET = 30.0      # 目標倍率
RUIN = 0.01        # 初期資金の1%未満で破産扱い
TRIALS = 20000
SEED = 42


def one_shot(ev: float, odds: float = 30.0) -> float:
    """全額を1回、オッズ30倍の馬券に賭ける"""
    return ev / odds


def parlay(ev: float, stages: int) -> float:
    """全額転がし: 各段のオッズは 30^(1/stages)、全段的中で30倍"""
    odds = TARGET ** (1.0 / stages)
    p = min(1.0, ev / odds)
    return p ** stages


def repeated(ev: float, odds: float, mode: str, max_bets: int) -> float:
    """
    同じ条件の馬券を最大 max_bets 回繰り返す。
    mode: "flat2"  = 毎回 現資金の2%
          "kelly25" = 1/4ケリー (エッジが無い時は最低2%で賭ける。アプリの compute_kelly_stake と同じ下限)
    """
    rng = np.random.default_rng(SEED)
    p = ev / odds
    b = odds - 1.0
    kelly = max(0.0, (b * p - (1 - p)) / b)
    if mode == "flat2":
        f = 0.02
    else:
        f = min(0.20, max(0.02, kelly * 0.25))

    bank = np.ones(TRIALS)
    done = np.zeros(TRIALS, dtype=bool)
    reached = np.zeros(TRIALS, dtype=bool)
    for _ in range(max_bets):
        active = ~done
        if not active.any():
            break
        win = rng.random(TRIALS) < p
        stake = bank * f
        bank = np.where(active, bank - stake + np.where(win, stake * odds, 0.0), bank)
        hit = active & (bank >= TARGET)
        ruin = active & (bank < RUIN)
        reached |= hit
        done |= hit | ruin
    return reached.mean()


def main():
    evs = [0.725, 0.80, 1.00, 1.05, 1.10, 1.20]
    print("## A. 一発勝負 / 転がし (到達確率 %)")
    print("| EV | 30倍1点 | 2段転がし(約5.5倍x2) | 3段転がし(約3.1倍x3) |")
    print("|---|---|---|---|")
    for ev in evs:
        print(f"| {ev:.3f} | {one_shot(ev)*100:.2f} | {parlay(ev,2)*100:.2f} | {parlay(ev,3)*100:.2f} |")

    for max_bets in (1000, 3000):
        print(f"\n## B. 繰り返し賭け: 最大{max_bets}回で30倍到達 (到達確率 %, {TRIALS}試行)")
        print("| EV | オッズ | 毎回2% | 1/4ケリー |")
        print("|---|---|---|---|")
        for ev in evs:
            for odds in (3.0, 10.0):
                a = repeated(ev, odds, "flat2", max_bets) * 100
                k = repeated(ev, odds, "kelly25", max_bets) * 100
                print(f"| {ev:.3f} | {odds:.0f}倍 | {a:.2f} | {k:.2f} |")


if __name__ == "__main__":
    main()
