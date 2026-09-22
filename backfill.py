#!/usr/bin/env python3
"""CHARON 섹터 모니터 v3.1 — 과거 데이터 채우기 + 백테스트

Actions 탭에서 'backfill'을 수동 실행하면:
1. 섹터 코인들의 과거 1년 일간 가격·거래량을 CoinGecko에서 받음 (코인당 1회 호출)
2. data/volume.json에 최근 거래량을 채움 -> 모니터의 '거래량 급증' 판단이 첫날부터 작동
3. 깔때기 규칙을 과거 1년에 적용해 성적을 계산 -> data/backtest.json
받은 원본은 histcache/에 보관하고, 7일 안에 받은 코인은 다시 받지 않음(재실행 시 빠름).
"""
import datetime as dt
import json
import os
import random
import statistics
import time

import monitor as m

HIST_DIR = os.path.join(m.ROOT, "histcache")
HIST_PATH = os.path.join(HIST_DIR, "hist.json")
MAX_COINS = 900             # 받을 코인 수 상한 (시총 큰 순)
REFETCH_S = 7 * 86400       # 이보다 최근에 받은 코인은 건너뜀
FETCH_BUDGET_S = 80 * 60    # 수집에 쓸 최대 시간 (워크플로 제한 110분 안에서)


def utc_date(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def compact(x):
    return None if x is None else float(f"{x:.6g}")


def fetch_hist(cid):
    d = m.cg(f"/coins/{cid}/market_chart?vs_currency=usd&days=365")
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    cols = {}
    for key, name in (("prices", "p"), ("market_caps", "m"), ("total_volumes", "v")):
        byday = {}
        for ts, v in d.get(key, []):
            byday[utc_date(ts)] = v          # 같은 날은 마지막 값
        byday.pop(today, None)               # 오늘(진행 중인 날)은 제외
        cols[name] = byday
    days = sorted(cols["p"])
    return {"d": days, "p": [compact(cols["p"][x]) for x in days],
            "m": [compact(cols["m"].get(x)) for x in days], "v": [compact(cols["v"].get(x)) for x in days]}


def mock_hist(cid):
    rnd = random.Random(cid)
    start = dt.date(2025, 9, 15)
    days = [(start + dt.timedelta(days=i)).isoformat() for i in range(365)]
    px, p, v = [], rnd.uniform(0.1, 50), rnd.uniform(1e6, 5e7)
    drift = rnd.uniform(-0.002, 0.004)
    for _ in days:
        p *= 1 + drift + rnd.gauss(0, 0.04)
        px.append(p)
    supply = rnd.uniform(1e7, 1e9)
    vols = [v * rnd.uniform(0.4, 2.5) for _ in days]
    return {"d": days, "p": px, "m": [x * supply for x in px], "v": vols}


# ═════════════════════════ 백테스트 ═════════════════════════
def backtest(cats, hist):
    btc = hist.get("bitcoin")
    if not btc:
        return None
    dates = btc["d"]
    N = len(dates)
    pos = {d: i for i, d in enumerate(dates)}

    def aligned(h):
        out = {k: [None] * N for k in ("p", "m", "v")}
        for j, d in enumerate(h["d"]):
            i = pos.get(d)
            if i is not None:
                for k in ("p", "m", "v"):
                    out[k][i] = h[k][j]
        return out

    A = {cid: aligned(h) for cid, h in hist.items()}
    B = A["bitcoin"]["p"]
    info = {}
    members = {}
    for key, rows in cats.items():
        ids = []
        for c in rows:
            if c["id"] in A and not m.excluded(c):
                ids.append(c["id"])
                info[c["id"]] = c
        members[key] = ids
    names = {s["key"]: s["name"] for s in m.SECTORS}

    def ret(p, i, j):
        return (p[j] / p[i] - 1) * 100 if p[i] and p[j] else None

    trades, last_pick = [], {}
    for i in range(30, N - 7):
        if not (B[i] and B[i - 7] and B[i - 30]):
            continue
        b7, b30 = ret(B, i - 7, i), ret(B, i - 30, i)
        cands = []
        for key, ids in members.items():
            q = []
            for cid in ids:
                a = A[cid]
                p, mc, v = a["p"], a["m"][i], a["v"][i]
                if not (p[i] and p[i - 7] and p[i - 30] and mc and v):
                    continue
                turn = v / mc
                if mc < m.TH["minor_mcap"] or v < m.TH["min_volume"] or not (m.TH["turnover_min"] <= turn <= m.TH["turnover_max"]):
                    continue
                q.append((cid, ret(p, i - 30, i), ret(p, i - 7, i)))
            if len(q) < 3:
                continue
            med30 = statistics.median(x[1] for x in q)
            med7 = statistics.median(x[2] for x in q)
            rs7, rs30 = med7 - b7, med30 - b30
            if not (rs7 > 0 and rs30 > 0):   # 과거엔 온체인·선물 신호가 없어 '강한 섹터'를 가격 기준으로만 판정
                continue
            fwd7 = [ret(A[cid]["p"], i, i + 7) for cid, _, _ in q]
            fwd7 = [x for x in fwd7 if x is not None]
            sec7 = statistics.median(fwd7) if fwd7 else None
            sec30 = None
            if i + 30 < N:
                f30 = [x for x in (ret(A[cid]["p"], i, i + 30) for cid, _, _ in q) if x is not None]
                sec30 = statistics.median(f30) if f30 else None
            for cid, c30, c7 in q:
                lag = med30 - c30
                if lag < m.TH["lag_min"]:
                    continue
                p = A[cid]["p"]
                win = [x for x in p[i - 6:i + 1] if x]
                above = len(win) >= 5 and p[i] > statistics.mean(win)
                prev = [x for x in A[cid]["v"][i - 7:i] if x]
                vr = A[cid]["v"][i] / statistics.mean(prev) if len(prev) >= 5 and statistics.mean(prev) > 0 else None
                vol_ok = vr is not None and vr >= m.TH["vol_surge"]
                if not (above or vol_ok):
                    continue
                grade = "red" if above and vol_ok else "yellow"
                score = min(lag, 40) + ((min(vr, 3) - 1) * 10 if vr and vr > 1 else 0) + max(min(rs30, 20), 0)
                cands.append({"cid": cid, "sec": key, "grade": grade, "score": score, "low7": min(win) if win else None,
                              "sec7": sec7, "sec30": sec30})
        # 하루 단위 선정 (실전과 같은 규칙: 코인당 최고 점수 섹터, 상한, 7일 중복 방지)
        best = {}
        for c in cands:
            if c["cid"] not in best or c["score"] > best[c["cid"]]["score"]:
                best[c["cid"]] = c
        ranked = sorted(best.values(), key=lambda c: -c["score"])
        red = [c for c in ranked if c["grade"] == "red"][: m.TH["red_max"]]
        rid = {c["cid"] for c in red}
        yellow = [c for c in ranked if c["cid"] not in rid][: m.TH["yellow_max"]]
        for grade, picks in (("red", red), ("yellow", yellow)):
            for c in picks:
                k = (c["cid"], grade)
                if k in last_pick and i - last_pick[k] < 7:
                    continue
                last_pick[k] = i
                p = A[c["cid"]]["p"]
                r7 = ret(p, i, i + 7)
                r30 = ret(p, i, i + 30) if i + 30 < N else None
                future = [x for x in p[i + 1:i + 8] if x]
                trades.append({
                    "date": dates[i], "id": c["cid"], "sym": info[c["cid"]]["sym"], "sec": names.get(c["sec"], c["sec"]),
                    "g": grade, "r7": r7, "x7": None if r7 is None or c["sec7"] is None else r7 - c["sec7"],
                    "r30": r30, "x30": None if r30 is None or c["sec30"] is None else r30 - c["sec30"],
                    "stop": bool(c["low7"] and future and min(future) < c["low7"]),
                })

    def summ(rows):
        x7 = [t["x7"] for t in rows if t["x7"] is not None]
        x30 = [t["x30"] for t in rows if t["x30"] is not None]
        return {"n7": len(x7), "win7": sum(1 for x in x7 if x > 0) / len(x7) * 100 if x7 else None,
                "avg7": statistics.mean(x7) if x7 else None, "med7": statistics.median(x7) if x7 else None,
                "n30": len(x30), "win30": sum(1 for x in x30 if x > 0) / len(x30) * 100 if x30 else None,
                "avg30": statistics.mean(x30) if x30 else None,
                "stop": sum(1 for t in rows if t["stop"]) / len(rows) * 100 if rows else None}

    by_sec = {}
    for t in trades:
        by_sec.setdefault(t["sec"], []).append(t)
    return {"ts": m.NOW_TS, "start": dates[30] if N > 30 else None, "end": dates[N - 8] if N > 8 else None,
            "coins": len(hist) - 1, "sectors": sum(1 for v in members.values() if v),
            "summary": {g: summ([t for t in trades if t["g"] == g]) for g in ("red", "yellow")},
            "by_sector": {k: summ(v) for k, v in sorted(by_sec.items(), key=lambda kv: -len(kv[1]))},
            "recent": [t for t in trades if t["g"] == "red"][-30:]}


# ═════════════════════════ 실행 ═════════════════════════
def main():
    t0 = time.time()
    notes = []
    cache = m.load(os.path.join(m.CACHE_DIR, "cache.json"), {})
    hist_store = m.load(HIST_PATH, {"meta": {}, "h": {}})
    cats = cache.get("cats") or {}

    if m.MOCK:
        cats = cats or m.mock_world(1)[2]
    elif not cats:
        print("섹터 데이터가 캐시에 없어 새로 받습니다")
        cl = m.fetch_catlist()
        ids, _ = m.resolve_ids(cl)
        for s in m.SECTORS:
            if s["key"] in ids:
                try:
                    cats[s["key"]] = m.fetch_category(ids[s["key"]])
                except Exception as e:
                    notes.append(f"섹터 {s['name']}: {e}")

    pool = {}
    for rows in cats.values():
        for c in rows:
            if not m.excluded(c) and c["mc"] >= m.TH["minor_mcap"] and c["vol"] >= 1e6:
                pool[c["id"]] = c
    targets = ["bitcoin"] + [c["id"] for c in sorted(pool.values(), key=lambda c: -c["mc"])][:MAX_COINS]
    print(f"대상 코인 {len(targets)}개")

    fetched = skipped = failed = 0
    for n, cid in enumerate(targets, 1):
        if m.NOW_TS - hist_store["meta"].get(cid, 0) < REFETCH_S and cid in hist_store["h"]:
            skipped += 1
            continue
        if time.time() - t0 > FETCH_BUDGET_S:
            notes.append(f"시간 제한으로 {len(targets) - n + 1}개는 다음 실행에서 받습니다")
            break
        try:
            hist_store["h"][cid] = mock_hist(cid) if m.MOCK else fetch_hist(cid)
            hist_store["meta"][cid] = m.NOW_TS
            fetched += 1
        except Exception as e:
            failed += 1
            if failed <= 5:
                notes.append(f"{cid}: {type(e).__name__} {str(e)[:80]}")
        if n % 50 == 0:
            m.save(HIST_PATH, hist_store)
            print(f"  {n}/{len(targets)} (새로 받음 {fetched}, 건너뜀 {skipped}, 실패 {failed})")
    m.save(HIST_PATH, hist_store)
    hist = {cid: h for cid, h in hist_store["h"].items() if cid in pool or cid == "bitcoin"}

    # 1) 거래량 기록 채우기 (최근 8일)
    dvol = m.load(os.path.join(m.DATA_DIR, "volume.json"), {})
    seeded = 0
    for cid, h in hist.items():
        if cid == "bitcoin":
            continue
        past = [[d, v] for d, v in zip(h["d"], h["v"]) if v][-8:]
        if len(past) >= 5:
            merged = {d: v for d, v in past}
            merged.update({d: v for d, v in dvol.get(cid, [])})   # 모니터가 이미 쌓은 값이 있으면 우선
            dvol[cid] = sorted(([d, v] for d, v in merged.items()), key=lambda x: x[0])[-8:]
            seeded += 1
    m.save(os.path.join(m.DATA_DIR, "volume.json"), dvol)

    # 2) 백테스트
    bt = backtest(cats, hist)
    if bt:
        bt["notes"] = notes
        m.save(os.path.join(m.DATA_DIR, "backtest.json"), bt)
    s = (bt or {}).get("summary", {}).get("red", {})
    print(f"완료: 새로 받음 {fetched}, 건너뜀 {skipped}, 실패 {failed}, 거래량 채움 {seeded}개")
    if bt:
        print(f"백테스트 {bt['start']}~{bt['end']} | 지금 볼 것 7일: n={s.get('n7')}, "
              f"섹터보다 좋았던 비율={s.get('win7') and round(s['win7'], 1)}%")
    for x in notes:
        print(" -", x)


if __name__ == "__main__":
    main()
