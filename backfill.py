#!/usr/bin/env python3
"""섹터 모니터 v4.0 — 과거 1년 백테스트 (Project Charon for Team All Street · Made by Tyler)

Actions 탭에서 'backfill'을 수동 실행하면:
1. 섹터 코인들의 과거 1년 일간 가격·시총·거래량을 CoinGecko에서 받음 (코인당 1회, 7일 안에 받은 코인은 건너뜀)
2. 4.0 규칙(섹터 4상태·순환 후보·Top 3·3.0 대조군·초입 후보·소형 도전·눌림목·재돌파·익절 경보)을 매일 적용해
   '7일 뒤 시장 지수(추적 코인 중간값)보다 더 올랐나'로 채점 -> data/backtest.json
한계: 섹터 구성은 지금 기준(사라진 코인 없음), 상장·펀딩·업비트 조건은 과거 기록이 없어 제외
"""
import math
import os
import random
import statistics
import time

import monitor as m

HIST_DIR = os.path.join(m.ROOT, "histcache")
HIST_PATH = os.path.join(HIST_DIR, "hist.json")
MAX_COINS = 700
REFETCH_S = 7 * 86400
FETCH_BUDGET_S = 80 * 60
TH = m.TH


def fetch_hist(cid):
    """0시(UTC) 값 = 전날 종가 → 날짜를 하루 당겨서 트레이딩뷰 일봉과 맞춤 (2.0 날짜 밀림 수정)"""
    d = m.cg(f"/coins/{cid}/market_chart?vs_currency=usd&days=365&interval=daily")
    today = m.utc_day(m.NOW_TS)
    cols = {}
    for key, name in (("prices", "p"), ("market_caps", "m"), ("total_volumes", "v")):
        byday = {}
        for ts, v in d.get(key, []):
            day = m.utc_day(ts / 1000 - m.DAY_S)
            if day < today:
                byday[day] = v
        cols[name] = byday
    days = sorted(cols["p"])
    return {"d": days, "p": [m.rnd6(cols["p"][x]) for x in days], "m": [m.rnd6(cols["m"].get(x)) for x in days],
            "v": [m.rnd6(cols["v"].get(x)) for x in days]}


def mock_hist(cid):
    w = m.mock_universe()
    c = w["coins"].get(cid)
    days = w["days"][-366:-1]
    if c:
        p = c["p"][-366:-1]
        return {"d": days, "p": p, "m": [x * c["mc0"] for x in p], "v": c["v"][-366:-1]}
    r = random.Random(cid)
    p, x = [], r.uniform(0.1, 50)
    for _ in days:
        x *= 1 + r.gauss(0.001, 0.04)
        p.append(x)
    return {"d": days, "p": p, "m": [v * 1e7 for v in p], "v": [r.uniform(1e6, 5e7) for _ in days]}


def pct(a, b):
    return None if a is None or not b else (a - b) / b * 100


def rsi_series(p, n=14):
    """날마다의 Wilder RSI (빠진 날은 직전 값으로 채움)"""
    out, last, ag, al, k = [None] * len(p), None, 0.0, 0.0, 0
    for i, x in enumerate(p):
        if x is None:
            x = last
        if x is None or last is None:
            last = x
            continue
        g, lo = max(x - last, 0), max(last - x, 0)
        k += 1
        if k <= n:
            ag, al = ag + g / n, al + lo / n
        else:
            ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + lo) / n
        if k >= n:
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        last = x
    return out


def summ(rows):
    x7 = [r["x7"] for r in rows if r.get("x7") is not None]
    x30 = [r["x30"] for r in rows if r.get("x30") is not None]
    if not x7:
        return None
    s = sorted(x7)
    return {"n7": len(x7), "win7": sum(1 for v in x7 if v > 0) / len(x7) * 100, "avg7": statistics.mean(x7),
            "med7": statistics.median(x7), "p90_7": s[int(len(s) * 0.9)] if len(s) >= 10 else None,
            "n30": len(x30), "win30": sum(1 for v in x30 if v > 0) / len(x30) * 100 if x30 else None,
            "avg30": statistics.mean(x30) if x30 else None, "med30": statistics.median(x30) if x30 else None,
            "stop": sum(1 for r in rows if r.get("stop")) / len(rows) * 100}


def backtest(members, hist):
    """members: 섹터키 -> [코인 id], hist: 코인 id -> {d,p,m,v}"""
    if "bitcoin" not in hist:
        return None
    grid = hist["bitcoin"]["d"]
    N = len(grid)
    idx = {d: i for i, d in enumerate(grid)}
    A = {}
    for cid, h in hist.items():
        p, mc, v = [None] * N, [None] * N, [None] * N
        for d, a, b, c in zip(h["d"], h["p"], h["m"], h["v"]):
            if d in idx:
                p[idx[d]], mc[idx[d]], v[idx[d]] = a, b, c
        A[cid] = {"p": p, "m": mc, "v": v, "rsi": rsi_series(p)}
    secs = {s["key"]: s for s in m.SECTORS}
    coin_secs = {}
    for k, ids in members.items():
        for cid in ids:
            if cid in A and cid != "bitcoin":
                coin_secs.setdefault(cid, []).append(k)
    # 섹터 지수 (하루 중간값 수익률 누적) → 상대강도선 실험용
    sidx = {}
    for k, ids in members.items():
        ids = [c for c in ids if c in A]
        val, series = 100.0, [None] * N
        for i in range(1, N):
            r = [pct(A[c]["p"][i], A[c]["p"][i - 1]) for c in ids if A[c]["p"][i] and A[c]["p"][i - 1]]
            r = [x for x in r if x is not None and abs(x) < 80]
            if len(r) >= 3:
                val *= 1 + statistics.median(r) / 100
            series[i] = val
        sidx[k] = series
    # 4.0: 시장 지수(모든 코인 중간값)와 섹터 RRG
    bidx = m.chain_index([A[c]["p"] for c in coin_secs])
    RR = {}
    for k, si in sidx.items():
        rsr, rsm = m.rrg(si, bidx)
        qs = [m.quad(a, b) for a, b in zip(rsr, rsm)]
        qd, qp = [0] * N, [None] * N
        for j in range(N):
            if qs[j] is None:
                continue
            if j and qs[j - 1] == qs[j]:
                qd[j], qp[j] = qd[j - 1] + 1, qp[j - 1]
            else:
                qd[j], qp[j] = 1, qs[j - 1] if j else None
        RR[k] = {"rsm": rsm, "q": qs, "qd": qd, "qp": qp}
    BR = {}   # 섹터별 날짜별 20일선 위 비율 (폭 개선 판단)

    def win(xs, a, b):
        return [x for x in xs[a:b] if x]

    T = {k: [] for k in ("top", "lag30", "early", "small", "pull", "reclaim_turn", "reclaim_bounce", "rsi_dip", "lead", "tp", "fall", "rsi_hot")}
    X = {k: [] for k in ("imp_only", "no_move", "no_conf", "lag_sec", "per1")}
    Q = {k: [] for k in ("rotsec", "q_imp", "q_lead", "q_weak", "q_lag", "hot30")}
    ALT = {"25 이하": [], "25~50": [], "50~75": [], "75 이상": []}
    BYS = {}
    last = {}
    top_dates = []
    start = 35
    skipped = []
    for i in range(start, N - 7):
        try:
            # 코인별 그날 지표
            rows = {}
            for cid, ks in coin_secs.items():
                p, mc, v = A[cid]["p"], A[cid]["m"], A[cid]["v"]
                if not (p[i] and p[i - 30] and p[i - 7] and p[i + 7] and mc[i] and v[i]) or mc[i] < TH["minor_mcap"] or v[i] < TH["min_volume"]:
                    continue
                r = {"id": cid, "ks": ks, "px": p[i], "mc": mc[i], "vol": v[i], "c3": pct(p[i], p[i - 3]), "c7": pct(p[i], p[i - 7]),
                     "c30": pct(p[i], p[i - 30]), "r7": pct(p[i + 7], p[i]), "r30": pct(p[i + 30], p[i]) if i + 30 < N and p[i + 30] else None}
                for n in (20, 60, 100, 200):
                    w = win(p, i - n + 1, i + 1)
                    r[f"ma{n}"] = sum(w) / n if i - n + 1 >= 0 and len(w) == n else None
                vv = win(v, i - 22, i - 2)
                r["vx"] = statistics.mean(win(v, i - 2, i + 1)) / statistics.mean(vv) if len(vv) >= 15 and statistics.mean(vv) > 0 else None
                past = win(p, i - 30, i)
                r["brk"] = len(past) >= 25 and p[i] > max(past)
                r["hi30"] = pct(p[i], max(win(p, i - 29, i + 1)))
                r["low7"] = min(win(p, i - 6, i + 1))
                fut = win(p, i + 1, i + 8)
                r["stop"] = bool(fut and min(fut) < r["low7"])
                w90 = win(p, max(0, i - 89), i + 1)
                r["run"], r["offpk"] = pct(p[i], min(w90)), pct(p[i], max(w90))
                tp = None
                if i >= 180:
                    body = win(p, i - 179, i - 4)
                    if body:
                        j1 = max(range(len(body)), key=lambda j: body[j])
                        p1, trough = body[j1], min(body[j1:] + [p[i]])
                        if pct(trough, p1) <= TH["wave_dd"] and p[i] >= p1 * 0.9 and p[i] >= trough * 1.25:
                            tp = "wave"
                if not tp and r["run"] >= TH["tp_run"] and r["offpk"] >= TH["tp_near"]:
                    tp = "run"
                r["tp"] = tp
                r["fall"] = r["run"] >= TH["brk_run"] and r["offpk"] <= TH["brk_off"] and not tp
                r["rsi"] = A[cid]["rsi"][i]
                trend = r["ma200"] or r["ma100"] or r["ma60"]
                r["dip"] = r["rsi"] is not None and TH["rsi_dip_lo"] <= r["rsi"] <= TH["rsi_dip_hi"] and bool(trend) and p[i] > trend
                below = 0
                for k in range(1, 15):
                    j = i - k
                    if j < 20 or not p[j]:
                        break
                    mj = win(p, j - 19, j + 1)
                    if len(mj) == 20 and p[j] < sum(mj) / 20:
                        below += 1
                    else:
                        break
                r["rc"] = below if (r["ma20"] and p[i] > r["ma20"] and below >= TH["reclaim_days"]) else 0
                rows[cid] = r
            if len(rows) < 30:
                continue
            mk7 = statistics.median(r["c7"] for r in rows.values())
            mk30 = statistics.median(r["c30"] for r in rows.values())
            mk3 = statistics.median([r["c3"] for r in rows.values() if r["c3"] is not None] or [0])
            bf7 = pct(bidx[i + 7], bidx[i]) if bidx[i] and bidx[i + 7] else None
            bf30 = pct(bidx[i + 30], bidx[i]) if i + 30 < N and bidx[i] and bidx[i + 30] else None
            mf7 = statistics.median(r["r7"] for r in rows.values())   # 코인 채점 기준: 같은 날 모든 코인 7일 뒤 수익률 중간값
            r30s = [r["r30"] for r in rows.values() if r["r30"] is not None]
            mf30 = statistics.median(r30s) if len(r30s) >= 30 else None
            S = {}
            for k in members:
                ms = [r for r in rows.values() if k in r["ks"]]
                if len(ms) < 3:
                    continue
                c7 = [r["c7"] for r in ms]
                s = {"k": k, "m3": statistics.median([r["c3"] for r in ms if r["c3"] is not None] or [0]), "m7": statistics.median(c7), "m30": statistics.median(r["c30"] for r in ms),
                     "br": sum(1 for x in c7 if x > 0) / len(c7) * 100, "ms": ms,
                     "ok": len(ms) >= TH["sec_min"] and not secs.get(k, {}).get("watch")}
                s["x7"], s["x30"] = s["m7"] - mk7, s["m30"] - mk30
                s["score"] = s["x7"] * 2 + s["x30"] * .5 + (s["br"] - 50) * .3
                si = sidx.get(k)
                s["f7"] = pct(si[i + 7], si[i]) if si and si[i] and si[i + 7] else None
                s["f30"] = pct(si[i + 30], si[i]) if si and i + 30 < N and si[i] and si[i + 30] else None
                rr = RR.get(k)
                s["q"], s["qd"], s["qp"] = (rr["q"][i], rr["qd"][i], rr["qp"][i]) if rr else (None, 0, None)
                s["rsm"] = rr["rsm"][i] if rr else None
                a20 = [r for r in ms if r["ma20"]]
                brn = sum(1 for r in a20 if r["px"] > r["ma20"]) / len(a20) * 100 if a20 else None
                BR.setdefault(k, {})[i] = brn
                brp = BR[k].get(i - 7)
                vx = [r["vx"] for r in ms if r["vx"] is not None]
                big2 = sorted(a20, key=lambda r: -r["mc"])[:2]
                conf = [bool(vx) and statistics.median(vx) >= TH["rot_vol"],
                        brn is not None and brp is not None and brn >= TH["rot_br"] and brn - brp >= TH["rot_brd"],
                        len(big2) == 2 and all(r["px"] > r["ma20"] for r in big2), s["m3"] > mk3]
                s["nconf"] = sum(conf)
                s["rot"] = s["q"] == "imp" or (s["q"] == "lead" and s["qd"] <= TH["rot_fresh"] and s["qp"] == "imp")
                s["rotc0"] = s["rot"] and s["ok"] and s["x30"] <= TH["rot_x30"]
                s["rotc"] = s["rotc0"] and s["nconf"] >= TH["rot_conf"]
                s["rotscore"] = ((s["rsm"] or 100) - 100) * 2 + s["nconf"] * 3 - max(s["x30"], 0) * 0.2
                S[k] = s
            order = sorted(S.values(), key=lambda s: -s["score"])
            for s in order:
                s["top"] = False
            for s in [s for s in order if s["ok"] and s["x7"] > 0 and s["x30"] > 0 and s["br"] >= TH["breadth_min"]][:TH["top_sec"]]:
                s["top"] = True
            keep = {s["k"] for s in sorted([s for s in S.values() if s["rotc"]], key=lambda s: -s["rotscore"])[:TH["rot_max"]]}
            for s in S.values():
                s["rotc"] = s["k"] in keep
            for s in S.values():
                c30s, c7s = [r["c30"] for r in s["ms"]], [r["c7"] for r in s["ms"]]
                byret = sorted(s["ms"], key=lambda r: -r["c30"])
                for r in s["ms"]:
                    z30, z7 = m.rz(r["c30"], c30s), m.rz(r["c7"], c7s)
                    r.setdefault("zs", {})[s["k"]] = (z30, z7)
                    pri = (s["rotc"], s["top"] and z30 <= TH["z30"], s["top"], s["score"])
                    if "sec" not in r or pri > r["_pri"]:
                        r.update(sec=s["k"], _pri=pri, z30=z30, z7=z7, srank=byret.index(r) + 1, sn=len(s["ms"]))
            # 알트시즌 지수 (그날 시총 상위 50개 알트 중 90일 BTC보다 더 오른 비율)
            alt = None
            bp = A["bitcoin"]["p"]
            if i >= 90 and bp[i] and bp[i - 90]:
                b90 = pct(bp[i], bp[i - 90])
                big = sorted([r for r in rows.values()], key=lambda r: -r["mc"])[:50]
                r90 = [pct(A[r["id"]]["p"][i], A[r["id"]]["p"][i - 90]) for r in big if A[r["id"]]["p"][i - 90]]
                r90 = [x for x in r90 if x is not None]
                if len(r90) >= 25:
                    alt = sum(1 for x in r90 if x > b90) / len(r90) * 100

            def rec(track, r, store, key=None):
                kk = (track, r["id"])
                if kk in last and i - last[kk] < 7:
                    return None
                last[kk] = i
                row = {"x7": r["r7"] - mf7, "x30": (r["r30"] - mf30) if (r["r30"] is not None and mf30 is not None) else None, "stop": r["stop"], "i": i}
                store.append(row)
                return row

            def rec_sec(track, s, store):
                kk = (track, "sec:" + s["k"])
                if (kk in last and i - last[kk] < 7) or bf7 is None or s["f7"] is None:
                    return
                last[kk] = i
                store.append({"x7": s["f7"] - bf7, "x30": (s["f30"] - bf30) if (s["f30"] is not None and bf30 is not None) else None, "stop": False, "i": i})
            for s in S.values():
                if not s["ok"]:
                    continue
                if s["q"]:
                    rec_sec("q_" + s["q"], s, Q["q_" + s["q"]])
                if s["rotc"]:
                    rec_sec("rotsec", s, Q["rotsec"])
                if s["top"]:
                    rec_sec("hot30", s, Q["hot30"])
            for r in rows.values():
                if "sec" not in r:
                    continue
                s = S[r["sec"]]
                r["under"] = r["z30"] <= TH["z30"] and r["z7"] <= TH["z7"] and r["c30"] <= TH["cap30"] and r["c7"] <= TH["cap7"]
                r["hard"] = r["mc"] >= TH["pick_mcap"] and r["vol"] >= TH["pick_volume"]
                r["a20"] = bool(r["ma20"] and r["px"] > r["ma20"])
                r["cvol"] = r["vx"] is not None and r["vx"] >= TH["vol_x"]
                r["cfirst"] = (r["c3"] if r["c3"] is not None else -999) > s["m3"]
                r["hot"] = r["rsi"] is not None and r["rsi"] >= TH["rsi_hot"]
                r["cool"] = r["c7"] <= TH["cap7"] and r["c30"] <= TH["cap30"] and not r["hot"]
                r["moving"] = r["a20"] or r["cfirst"]
                r["nsig"] = sum([r["under"], r["a20"], r["cvol"], r["brk"]])
                r["score"] = (max(-r["z30"], 0) * 10 + min(max((r["vx"] or 1) - 1, 0) * 25, 25) + (12 if s["rotc"] else 5 if s["q"] in ("imp", "lead") else 0)
                              + (5 if r["cfirst"] else 0))
            live = [r for r in rows.values() if "sec" in r]

            def pick3(cands, per_sec=TH["top_per_sec"]):
                out, per = [], {}
                for r in sorted(cands, key=lambda r: -r["mc"]):
                    if per.get(r["sec"], 0) < per_sec and len(out) < 3:
                        out.append(r)
                        per[r["sec"]] = per.get(r["sec"], 0) + 1
                return out
            top = pick3([r for r in live if S[r["sec"]]["rotc"] and r["hard"] and r["cool"] and r["moving"]])
            for r in top:
                row = rec("top", r, T["top"])
                if row:
                    top_dates.append((grid[i], row))
                    BYS.setdefault(S[r["sec"]]["k"], []).append(row)
                    if alt is not None:
                        ALT["25 이하" if alt <= 25 else "25~50" if alt <= 50 else "50~75" if alt < 75 else "75 이상"].append(row)
            lag = [r for r in sorted(live, key=lambda r: -r["mc"]) if r["hard"] and r["c7"] <= TH["cap7"] and r["c30"] <= TH["cap30"]
                   and any(S[k]["top"] and z30 <= TH["z30"] and z7 <= TH["z7"] for k, (z30, z7) in r["zs"].items() if k in S)][:3]
            for r in lag:
                rec("lag30", r, T["lag30"])
            tids = {r["id"] for r in top}
            for r in sorted([r for r in live if r["id"] not in tids and (S[r["sec"]]["rotc"] or S[r["sec"]]["q"] in ("imp", "lead"))
                             and r["mc"] >= TH["pick_mcap"] and r["nsig"] >= 2 and not r["hot"]], key=lambda r: -r["score"])[:TH["early_max"]]:
                rec("early", r, T["early"])
            for r in sorted([r for r in live if r["id"] not in tids and r["mc"] < TH["pick_mcap"] and r["nsig"] >= 2], key=lambda r: -r["score"])[:TH["small_max"]]:
                rec("small", r, T["small"])
            for r in live:
                s = S[r["sec"]]
                if (s["x30"] >= TH["pull_sec30"] and r["c30"] >= TH["pull_c30"] and r["srank"] <= math.ceil(r["sn"] / 2) and r["ma20"]
                        and r["px"] < r["ma20"] and TH["pull_hi_min"] <= r["hi30"] <= TH["pull_hi_max"]):
                    lv = sorted([r[f"ma{n}"] for n in (60, 100, 200) if r[f"ma{n}"] and r[f"ma{n}"] <= r["px"]], reverse=True)
                    if lv and pct(r["px"], lv[0]) <= TH["ma_near"]:
                        rec("pull", r, T["pull"])
                if r["rc"]:
                    rec("reclaim_turn" if (r["ma60"] and r["px"] > r["ma60"]) else "reclaim_bounce", r,
                        T["reclaim_turn" if (r["ma60"] and r["px"] > r["ma60"]) else "reclaim_bounce"])
                if r["tp"]:
                    rec("tp", r, T["tp"])
                if r["fall"]:
                    rec("fall", r, T["fall"])
                if r["hot"]:
                    rec("rsi_hot", r, T["rsi_hot"])
                if r["dip"]:
                    rec("rsi_dip", r, T["rsi_dip"])
            for s in S.values():
                if s["top"]:
                    lead = max([r for r in s["ms"] if "sec" in r and r["sec"] == s["k"]] or [None], key=lambda r: r["c30"] if r else 0)
                    if lead:
                        rec("lead", lead, T["lead"])
            # 실험 (Top 3 변형)
            base = [r for r in live if r["hard"] and r["cool"]]
            for r in pick3([r for r in base if S[r["sec"]]["rotc"] and S[r["sec"]]["q"] == "imp" and r["moving"]]):
                rec("imp_only", r, X["imp_only"])
            for r in pick3([r for r in base if S[r["sec"]]["rotc"]]):
                rec("no_move", r, X["no_move"])
            for r in pick3([r for r in base if S[r["sec"]]["rotc0"] and r["moving"]]):
                rec("no_conf", r, X["no_conf"])
            for r in pick3([r for r in base if S[r["sec"]]["q"] == "lag" and S[r["sec"]]["ok"]]):
                rec("lag_sec", r, X["lag_sec"])
            for r in pick3([r for r in live if S[r["sec"]]["rotc"] and r["hard"] and r["cool"] and r["moving"]], per_sec=1):
                rec("per1", r, X["per1"])
        except Exception as e:   # 하루 계산이 실패해도 나머지 날은 계속
            skipped.append(f"{grid[i]} {type(e).__name__}: {str(e)[:80]}")
    if not T["top"] and not T["early"]:
        return None
    mid = len(grid) // 2
    halves = {f"앞 기간 (~{grid[mid]})": summ([r for d, r in top_dates if d <= grid[mid]]),
              f"뒤 기간 ({grid[mid]}~)": summ([r for d, r in top_dates if d > grid[mid]])}
    return {"v": m.VERSION, "ts": m.NOW_TS, "skipped": len(skipped), "skip_first": skipped[0] if skipped else None, "start": grid[start], "end": grid[-8], "coins": len(coin_secs),
            "lists": {k: summ(v) for k, v in T.items() if summ(v)}, "exp": {k: summ(v) for k, v in X.items() if summ(v)},
            "quad": {k: summ(v) for k, v in Q.items() if summ(v)}, "bench": "코인: 같은 날 추적 코인 전체의 7일 뒤 수익률 중간값 / 섹터: 섹터 지수 vs 시장 지수",
            "alt": {k: summ(v) for k, v in ALT.items() if summ(v)}, "halves": {k: v for k, v in halves.items() if v},
            "by_sector": {k: summ(v) for k, v in sorted(BYS.items(), key=lambda kv: -len(kv[1])) if summ(v)}}


def main():
    t0 = time.time()
    notes = []
    cache = m.load(os.path.join(m.CACHE_DIR, "cache.json"), {})
    hist_store = m.load(HIST_PATH, {"meta": {}, "h": {}})
    markets = cache.get("markets") or {}
    sec_ids = cache.get("sec_ids") or {}
    if m.MOCK:
        markets, sec_ids = m.mock_markets(), m.mock_sector_ids()
    else:
        if not markets:
            print("가격 데이터가 캐시에 없어 새로 받습니다")
            markets = m.fetch_markets()
        if not sec_ids:
            print("섹터 구성이 캐시에 없어 새로 받습니다")
            ids, _ = m.resolve_ids(m.fetch_catlist())
            for s in m.SECTORS:
                if s["key"] in ids:
                    try:
                        sec_ids[s["key"]] = m.fetch_category_ids(ids[s["key"]])
                    except Exception as e:
                        notes.append(f"섹터 {s['name']}: {e}")
    members = {s["key"]: list(s.get("ids") or sec_ids.get(s["key"], [])) for s in m.SECTORS}
    pool = {i for ids in members.values() for i in ids if i in markets and i != "bitcoin" and not m.excluded(markets[i])
            and markets[i]["mc"] >= TH["minor_mcap"]}
    targets = ["bitcoin"] + sorted(pool, key=lambda i: -markets[i]["mc"])[:MAX_COINS]
    print(f"대상 코인 {len(targets)}개")
    fetched = skipped = failed = 0
    for n, cid in enumerate(targets, 1):
        if m.NOW_TS - hist_store["meta"].get(cid, 0) < REFETCH_S and cid in hist_store["h"] and hist_store.get("v") == 3:
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
    hist_store["v"] = 3     # 3.0부터 날짜 기준이 바뀌어 2.0 때 받은 기록은 다시 받음
    m.save(HIST_PATH, hist_store)
    hist = {cid: h for cid, h in hist_store["h"].items() if cid in pool or cid == "bitcoin"}
    try:
        bt = backtest(members, hist)
    except Exception:
        import traceback
        traceback.print_exc()
        print("백테스트 계산 오류. 위 로그를 캡처해 주세요. 받은 과거 데이터는 보관되어 다시 실행하면 빠릅니다.")
        raise
    if bt:
        bt["notes"] = notes
        m.save(os.path.join(m.DATA_DIR, "backtest.json"), bt)
    print(f"완료: 새로 받음 {fetched}, 건너뜀 {skipped}, 실패 {failed}, {time.time() - t0:.0f}초")
    if bt and bt.get("skipped"):
        print(f"  계산하지 못한 날 {bt['skipped']}일 · 첫 오류: {bt['skip_first']}")
    if bt:
        for grp in ("quad", "lists", "exp"):
            print(f" [{grp}] (7일 뒤 시장 지수 대비)")
            for k, x in (bt.get(grp) or {}).items():
                print(f"  {k}: n={x['n7']} 승률 {x['win7']:.0f}% 중간값 {x['med7']:+.2f}%p 평균 {x['avg7']:+.2f}%p")
    for x in notes:
        print(" -", x)


if __name__ == "__main__":
    main()
