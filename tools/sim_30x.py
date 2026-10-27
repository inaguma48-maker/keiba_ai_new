"""
資金の目標倍率到達シミュレーション (NotebookLM資料用)
期待値(EV = 的中確率 x オッズ)と賭け方ごとに「破産前に目標倍率へ届く確率」をモンテカルロで推定する。
実行: python3 tools/sim_30x.py                  (30倍, 最大1000回/3000回)
      python3 tools/sim_30x.py 300 3000 10000   (300倍, 最大3000回/10000回)
"""

import sys
import numpy as np

TARGET = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0   # 目標倍率
HORIZONS = [int(a) for a in sys.argv[2:]] or [1000, 3000]   # 最大賭け回数
RUIN = 0.01        # 初期資金の1%未満で破産扱い
TRIALS = 20000
SEED = 42


def one_shot(ev: float, odds: float = TARGET) -> float:
    """全額を1回、オッズ=目標倍率の馬券に賭ける"""
    return ev / odds


def parlay(ev: float, stages: int) -> float:
    """全額転がし: 各段のオッズは TARGET^(1/stages)、全段的中で目標倍率"""
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


def bets_needed(ev: float, odds: float, f: float = 0.02) -> float:
    """毎回 現資金のf を賭けた時、資金の中央値が目標倍率に届くまでの回数の目安 (1回あたりの対数成長率から計算)"""
    p = ev / odds
    g = p * np.log(1 + f * (odds - 1)) + (1 - p) * np.log(1 - f)
    return np.log(TARGET) / g if g > 0 else float("inf")


def main():
    evs = [0.725, 0.80, 1.00, 1.05, 1.10, 1.20]
    t = f"{TARGET:g}倍"
    print(f"## A. 一発勝負 / 転がし: {t}到達 (到達確率 %)")
    print(f"| EV | {t}1点 | 2段転がし(約{TARGET ** 0.5:.1f}倍x2) | 3段転がし(約{TARGET ** (1 / 3):.1f}倍x3) |")
    print("|---|---|---|---|")
    for ev in evs:
        print(f"| {ev:.3f} | {one_shot(ev)*100:.2f} | {parlay(ev,2)*100:.2f} | {parlay(ev,3)*100:.2f} |")

    for max_bets in HORIZONS:
        print(f"\n## B. 繰り返し賭け: 最大{max_bets}回で{t}到達 (到達確率 %, {TRIALS}試行)")
        print("| EV | オッズ | 毎回2% | 1/4ケリー |")
        print("|---|---|---|---|")
        for ev in evs:
            for odds in (3.0, 10.0):
                a = repeated(ev, odds, "flat2", max_bets) * 100
                k = repeated(ev, odds, "kelly25", max_bets) * 100
                print(f"| {ev:.3f} | {odds:.0f}倍 | {a:.2f} | {k:.2f} |")

    print(f"\n## C. 毎回2%賭けで{t}に届くまでの回数の目安 (資金の中央値)")
    print("| EV | オッズ3倍 | オッズ10倍 |")
    print("|---|---|---|")
    for ev in evs:
        cells = []
        for odds in (3.0, 10.0):
            n = bets_needed(ev, odds)
            cells.append("届かない" if n == float("inf") else f"{n:,.0f}回")
        print(f"| {ev:.3f} | {cells[0]} | {cells[1]} |")


if __name__ == "__main__":
    main()
