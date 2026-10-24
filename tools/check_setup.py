"""
Self-check of a running setup: which app version answers, keiba.db, the trained model, and one real race end to end.
Read-only. Prints [OK]/[NG] lines.

usage: python tools/check_setup.py
"""

import json
import os
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


def run_checks(root=ROOT, app_url="http://127.0.0.1:5000"):
    out = []
    ok = lambda m: out.append(("OK", m))
    ng = lambda m: out.append(("NG", m))

    # 1. libraries
    for mod in ("flask", "pandas", "numpy", "lightgbm", "sklearn", "joblib", "bs4"):
        try:
            __import__(mod)
        except Exception as e:
            ng(f"ライブラリ {mod} が使えません: {e}")
    if not any(s == "NG" for s, _ in out):
        ok("必要なライブラリがそろっています")

    # 2. which app answers on the port, and is it this folder's version
    from src.version import code_version
    here = code_version(root)
    try:
        with urllib.request.urlopen(app_url + "/api/version", timeout=4) as r:
            v = json.loads(r.read().decode("utf-8"))
        if v["version"] == here:
            ok(f"動いているアプリは最新版です（版 {v['version']}、フォルダ {v['folder']}）")
        else:
            ng(f"古い版が動いています（動作中: 版 {v['version']} / フォルダ {v['folder']}、ここ: 版 {here}）。"
               "インストール用バッチをもう一度実行してください。")
    except Exception:
        ng(f"アプリが応答しません（{app_url}）。起動直後なら、少し待ってからもう一度試してください。")

    # 3. keiba.db
    from src.replay import keiba_db_path, load_replay
    db = keiba_db_path()
    if not os.path.isfile(db):
        ng(f"keiba.db が見つかりません: {db}")
        return out
    from keiba.dataset import connect_ro
    con = connect_ro(db)
    try:
        n, last = con.execute("select count(*), max(race_date) from races").fetchone()
        ok(f"keiba.db: {n}レース、最新の開催日 {last}（{os.path.getsize(db) // 1_000_000}MB）")
        races = con.execute("select race_id, venue, race_number from races where race_date = ? order by venue, race_number", (last,)).fetchall()
        pick = next((r for r in races if r[2] == 11), races[0] if races else None)
        entries, horse_id = [], None
        if pick:
            entries = [r[0] for r in con.execute("select horse_number from race_entries where race_id=? and popularity is not null order by horse_number", (pick[0],))]
            row = con.execute("select horse_id from race_entries where race_id=? and horse_id is not null limit 1", (pick[0],)).fetchone()
            horse_id = str(row[0]) if row and len(str(row[0])) == 11 and str(row[0]).isdigit() else None
    finally:
        con.close()

    # 4. trained model
    from keiba.predict import AbilityError, latest_bundle, stage_probs
    bundle = None
    try:
        bundle = latest_bundle()
        ok(f"能力モデル: あり（学習日 {bundle.get('trained_at')}、学習期間の終わり {bundle.get('train_end')}）")
    except AbilityError as e:
        ng(str(e))

    # 5. one race end to end
    if pick:
        label = f"{last} {pick[1]}{pick[2]}R"
        try:
            rp = load_replay(db, pick[0])
            ok(f"{label}: 結果の再生ができます（{len(rp['runners'])}頭、{rp['course']['venue']}{rp['race']['distance_m']}m）")
        except Exception as e:
            ng(f"{label}: 結果の再生ができません: {e}")
        if bundle and entries:
            horses = [{"horse_number": n, "odds": 2.0 + i} for i, n in enumerate(entries)]
            for stage in (1, 2):
                try:
                    p = stage_probs(db, pick[0], horses, stage, bundle)
                    top = sorted(p.items(), key=lambda kv: -kv[1])[:3]
                    ok(f"{label}: 層{stage}の予測ができます（上位 " + "、".join(f"{k}番 {v * 100:.1f}%" for k, v in top) + "）")
                except Exception as e:
                    ng(f"{label}: 層{stage}の予測ができません: {e}")
        from keiba.trends import TrendError, race_trends
        from src.models import HorseEntry, RaceInfo
        try:
            race = RaceInfo(pick[0], label, pick[1], "", 0, "", "",
                            [HorseEntry(n, f"{n}番", "", "", 0, 0, 0, 0, 0, 0, 0, 0, 0) for n in entries])
            t = race_trends(db, race, pick[0])
            h = t["history"]
            ok(f"{label}: 過去の同レースの傾向を出せます（{h['label']}・{h['years']}の{h['n_races']}回、条件{len(t['rules'])}件）")
        except TrendError as e:
            ok(f"{label}: 過去の同レースの傾向の集計は動きます（このレースは: {e}）")
        except Exception as e:
            ng(f"{label}: 過去の同レースの傾向を出せません: {e}")

    # 6. JRA site: reachable, and the racecard list can still be read
    try:
        urllib.request.urlopen(urllib.request.Request("https://www.jra.go.jp/", headers={"User-Agent": "keiba_ai_new/0.1"}), timeout=6).read(100)
        ok("JRA公式サイトに接続できます")
        from src.jra_site import JraClient, pick_target_date
        meetings = JraClient(min_interval=0).fetch_meetings()
        dates = sorted({m.date for m in meetings})
        ok(f"JRA出馬表の開催を取得できます（{len(meetings)}開催、対象日 {pick_target_date(meetings)}）")
    except Exception as e:
        ng(f"JRA公式サイトからの取得に失敗しました: {e}")
        return out
    if horse_id:
        try:
            from src.jra_site import JraClient, horse_cname, parse_horse_profile
            p = parse_horse_profile(JraClient(min_interval=0).post("accessU.html", horse_cname(horse_id)), horse_id)
            ok(f"JRAの競走馬ページを読めます（例: {p.horse_name} 生産牧場 {p.breeder or '記載なし'}・所属 {p.center or '記載なし'}）")
        except Exception as e:
            ng(f"JRAの競走馬ページ（生産牧場・所属）を読めません: {e}")
    return out


def main() -> int:
    lines = run_checks()
    for status, msg in lines:
        print(f"[{status}] {msg}")
    bad = sum(1 for s, _ in lines if s == "NG")
    print("\n" + ("すべて正常です。" if not bad else f"{bad}件の問題があります。上の [NG] の行を、そのまま貼ってください。"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
