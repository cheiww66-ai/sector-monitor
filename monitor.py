#!/usr/bin/env python3
"""섹터 모니터 v3.0 — Project Charon for Team All Street · Made by Tyler

2시간마다 GitHub Actions에서 실행:
1. CoinGecko: 시총 상위 1000개 가격(매 실행), 섹터 구성(하루 1번), 전체 시총·도미넌스(매 실행)
2. 거래소 일봉(Bitget → OKX → CoinGecko 순): 20·60·100·200일선을 트레이딩뷰와 같은 방식으로 계산
3. 선물(Hyperliquid·Bitget·OKX): 펀딩·OI → 숏 스퀴즈 / 업비트·빗썸: 거래대금·상장 후보
4. 목록: Top 3 · 초입 후보 · 소형 도전 · 눌림목 · 20일선 재돌파 · 상장 후보 · 숏 스퀴즈
5. 시장: 알트 사이클 8단계(팀 리더 조언), 알트시즌 지수, 체급별 흐름, 시장 폭
"""
import datetime as dt
import html
import json
import math
import os
import random
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "3.0"
RELEASED = "2026-09-24"
CREDIT = "Made by Tyler"
SUBTITLE = "Project Charon for Team All Street"
VERSION_RULE = "큰 업데이트(x.0)는 코인을 고르는 규칙이 바뀐 것, 작은 업데이트(x.1)는 화면·표시만 바뀐 것입니다. 실전 성적은 큰 버전별로 따로 집계합니다."
CHANGELOG = [
    ("3.0", "2026-09-24", "큰 업데이트", [
        "탭 화면(순위·초입 후보·소형 도전·눌림목·상장·섹터·시장·성적표·데이터 점검), 항상 다크 모드, 2시간마다 갱신",
        "덜 오름 기준을 섹터 안 표준점수(중앙값·MAD)로 변경. Top 3는 시총 순, 한 번 들어오면 느슨한 기준까지 유지",
        "평균가 위·거래량 급증을 필수 조건에서 제외 (2.0 백테스트에서 성적을 낮춤). 7일 +15%·30일 +40% 상한",
        "이평선을 거래소 일봉(마감 봉 + 현재가, 트레이딩뷰 방식)으로 계산. 20·60·100·200일선",
        "눌림목(이미 오른 코인의 조정), 20일선 재돌파(반등·전환), 숏 스퀴즈 순위, 상장 후보(업비트 BTC·USDT 마켓만·빗썸만)",
        "팀 리더 조언 반영: 알트 사이클 8단계, 익절 구간·꺾임 주의 배지, 시장 폭, 알트시즌 지수(자체 계산)",
        "체급(메이저·대형·중형·마이너)별 흐름, 섹터·체급·상승장 대장 코인, 로빈후드 관찰 섹터",
        "상위 20개 거래소 중 상장 수, 업비트 투자유의 표시",
        "2.0의 날짜 섞임 버그 수정 (일봉 기준 UTC 0시로 통일)",
        "DefiLlama 섹터 신호·CMC 코인별 칩·섹터 지도·비교 차트·컨트랙트 주소 제거",
    ]),
    ("2.0", "2026-09-23", "큰 업데이트", [
        "시총 하한 $300M, 소형(참고)·상승 초입(실험) 목록, CMC 교차 확인, 조건 칩, 섹터 지도, 백테스트 세부표",
    ]),
    ("1.0", "2026-09-22", "첫 버전", [
        "24개 섹터 자금흐름 판정, 지금 볼 것·관심 목록, 비교 차트, 실전 성적표, 1년 백테스트, 텔레그램 알림 (개발 당시 v3.1)",
    ]),
]


def major(v):
    return str(v or "1.0").split(".")[0]


# ═════════════════════════ 설정 ═════════════════════════
KST = dt.timezone(dt.timedelta(hours=9))
UTC = dt.timezone.utc
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, "cache")
SITE_DIR = os.path.join(ROOT, "site")
MOCK = os.environ.get("MOCK") == "1"
NOW_TS = int(os.environ.get("NOW_TS") or time.time())
CG_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()
CMC_KEY = os.environ.get("CMC_API_KEY", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TG_INVITE = os.environ.get("TELEGRAM_INVITE_URL", "").strip()   # 알림방 입장 버튼 (없으면 버튼 숨김)
PAGE_URL = os.environ.get("PAGE_URL", "").strip()

SECTORS = [
    # 체인 생태계
    {"key": "ETH", "name": "이더리움", "cg": "ethereum-ecosystem", "names": ["Ethereum Ecosystem"]},
    {"key": "SOL", "name": "솔라나", "cg": "solana-ecosystem", "names": ["Solana Ecosystem"]},
    {"key": "BNB", "name": "BNB체인", "cg": "binance-smart-chain", "names": ["BNB Chain Ecosystem", "Binance Smart Chain Ecosystem"]},
    {"key": "BASE", "name": "베이스", "cg": "base-ecosystem", "names": ["Base Ecosystem"]},
    {"key": "ARB", "name": "아비트럼", "cg": "arbitrum-ecosystem", "names": ["Arbitrum Ecosystem"]},
    {"key": "SUI", "name": "수이", "cg": "sui-ecosystem", "names": ["Sui Ecosystem"]},
    {"key": "AVAX", "name": "아발란체", "cg": "avalanche-ecosystem", "names": ["Avalanche Ecosystem"]},
    {"key": "TON", "name": "톤", "cg": "ton-ecosystem", "names": ["TON Ecosystem", "The Open Network Ecosystem", "Toncoin Ecosystem"]},
    {"key": "TRX", "name": "트론", "cg": "tron-ecosystem", "names": ["Tron Ecosystem", "TRON Ecosystem"]},
    {"key": "APT", "name": "앱토스", "cg": "aptos-ecosystem", "names": ["Aptos Ecosystem"]},
    {"key": "HYPE", "name": "하이퍼리퀴드", "cg": "hyperliquid-ecosystem", "names": ["Hyperliquid Ecosystem", "HyperEVM Ecosystem"]},
    {"key": "BTCE", "name": "비트코인 생태계", "cg": "bitcoin-ecosystem", "names": ["Bitcoin Ecosystem"]},
    # 내러티브
    {"key": "MEME", "name": "밈", "cg": "meme-token", "names": ["Meme"]},
    {"key": "AI", "name": "AI", "cg": "artificial-intelligence", "names": ["Artificial Intelligence (AI)", "Artificial Intelligence"]},
    {"key": "AGENT", "name": "AI 에이전트", "cg": "ai-agents", "names": ["AI Agents"]},
    {"key": "RWA", "name": "실물자산", "cg": "real-world-assets-rwa", "names": ["Real World Assets (RWA)"]},
    {"key": "DEPIN", "name": "DePIN", "cg": "depin", "names": ["DePIN"]},
    {"key": "DEFI", "name": "디파이", "cg": "decentralized-finance-defi", "names": ["Decentralized Finance (DeFi)"]},
    {"key": "PERP", "name": "선물 DEX", "cg": "perpetuals", "names": ["Perpetuals"]},
    {"key": "L2", "name": "레이어2", "cg": "layer-2", "names": ["Layer 2 (L2)"]},
    {"key": "GAME", "name": "게임", "cg": "gaming", "names": ["Gaming (GameFi)", "Gaming"]},
    {"key": "PRIV", "name": "프라이버시", "cg": "privacy-coins", "names": ["Privacy Coins"]},
    {"key": "RESTAKE", "name": "리스테이킹", "cg": "restaking", "names": ["Restaking"]},
    {"key": "PRED", "name": "예측시장", "cg": "prediction-markets", "names": ["Prediction Markets"]},
    # 직접 정한 목록 (CoinGecko 카테고리는 브리지 사본이 섞여 있어 사용하지 않음)
    {"key": "ROBIN", "name": "로빈후드", "ids": ["cash-cat", "artificial-inu-3", "morpho", "lighter", "uniswap", "dydx-chain"],
     "native": ["cash-cat", "artificial-inu-3"], "watch": True},
]
# watch=True: 순위·대장만 보여주고 추천을 뽑는 섹터에서는 제외 (코인 수가 적고 한두 코인에 쏠림). 바꾸려면 False

TH = {  # 판정 기준 (숫자만 바꾸면 기준이 바뀜)
    # 섹터
    "sec_min": 8, "top_sec": 5, "breadth_min": 55.0,
    # 기본 거르기
    "minor_mcap": 70e6, "pick_mcap": 300e6, "min_volume": 1e6, "pick_volume": 5e6, "funding_hot": 40.0,
    # 덜 오름 (섹터 안 표준점수)
    "z30": -0.5, "z30_keep": -0.25, "z7": 0.5, "cap30": 40.0, "cap7": 15.0,
    # 신호
    "vol_x": 1.3, "upbit_x": 2.0, "sq_oi": 5.0, "sq_short": 55.0,
    "early_max": 10, "small_max": 8, "list_max": 10,
    # 눌림목
    "pull_sec30": 5.0, "pull_c30": 10.0, "pull_hi_max": -8.0, "pull_hi_min": -30.0, "ma_near": 5.0, "near_max": 12,
    # 20일선 재돌파
    "reclaim_days": 5, "reclaim_vol": 1.5,
    # 익절 경보 (팀 리더 조언)
    "tp_run": 100.0, "tp_near": -10.0, "wave_dd": -25.0, "brk_run": 80.0, "brk_off": -20.0,
}
LIST_VENUES = {"Bitget": "bitget", "OKX": "okex", "Binance": "binance", "Upbit": "upbit"}   # 상장 필터 거래소 (CoinGecko id)
VENUE_CODE = {"Upbit": "U", "Bitget": "G", "OKX": "O", "Binance": "B"}
EXCHANGES = ["Hyperliquid", "Bitget", "OKX"]   # 선물 데이터 출처 (Bybit·Binance 선물은 GitHub 서버 IP 차단)
TIERS = [("메이저", "$10B+", 10e9, 1e30), ("대형", "$1~10B", 1e9, 10e9), ("중형", "$300M~1B", 300e6, 1e9), ("마이너", "$70~300M", 70e6, 300e6)]
STABLE_SYMS = {"usdt", "usdc", "dai", "usde", "fdusd", "pyusd", "usds", "tusd", "usdd", "frax", "usd1",
               "rlusd", "susde", "gho", "lusd", "crvusd", "usdx", "eurc", "usdg", "bfusd", "jpyc", "xaut", "paxg"}
EXCLUDE_WORDS = ("wrapped", "staked", "bridged", "liquid staking", "restaked", "wormhole", "binance-peg", "tether", " usd", "tokenized")
DAY_S = 86400
MARKET_PAGES = 4          # 시총 상위 250 × 4 = 1000개
CANDLE_DAYS = 210
TICKER_BUDGET = 48        # 하루에 새로 확인할 '상위 20개 거래소 상장 수' 코인 수
CG_CANDLE_BUDGET = 40     # 거래소 일봉이 없는 코인에 CoinGecko 일봉을 받는 하루 한도


# ═════════════════════════ 공통 ═════════════════════════
def get_json(url, method="GET", body=None, headers=None, retries=3, timeout=60):
    h = {"User-Agent": "Mozilla/5.0 (sector-monitor/3.0)", "Accept": "application/json"}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404, 451):
                raise
            if e.code == 429 and i < retries - 1:
                time.sleep(30 * (i + 1))
                continue
            if i == retries - 1:
                raise
            time.sleep(5)
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(5)


def fl(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def pct(new, old):
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def rnd6(x):
    return None if x is None else float(f"{x:.6g}")


def utc_day(ts):
    return dt.datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


NOTES = []
_KEY = {"ok": bool(CG_KEY)}
CALLS = {"cg": 0}


def cg(path):
    url = "https://api.coingecko.com/api/v3" + path
    CALLS["cg"] += 1
    try:
        res = get_json(url, headers={"x-cg-demo-api-key": CG_KEY} if _KEY["ok"] else {})
    except urllib.error.HTTPError as e:
        if e.code != 401 or not _KEY["ok"]:
            raise
        _KEY["ok"] = False
        NOTES.append("CoinGecko 키가 거부되어 키 없이 받았습니다. Settings → Secrets의 COINGECKO_API_KEY 값을 확인하세요.")
        time.sleep(8)
        res = get_json(url)
    time.sleep(2.2 if _KEY["ok"] else 8)
    return res


# ═════════════════════════ 수집: CoinGecko ═════════════════════════
def market_row(r):
    return {"id": r["id"], "sym": (r.get("symbol") or "").upper(), "name": r.get("name") or "",
            "px": r.get("current_price"), "mc": r.get("market_cap") or 0, "fdv": r.get("fully_diluted_valuation"),
            "vol": r.get("total_volume") or 0, "dd": r.get("ath_change_percentage"),
            "c1": r.get("price_change_percentage_24h_in_currency"),
            "c7": r.get("price_change_percentage_7d_in_currency"),
            "c30": r.get("price_change_percentage_30d_in_currency"),
            "c200": r.get("price_change_percentage_200d_in_currency")}


def fetch_markets():
    out = {}
    for page in range(1, MARKET_PAGES + 1):
        for r in cg(f"/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page={page}"
                    "&price_change_percentage=24h,7d,30d,200d"):
            out[r["id"]] = market_row(r)
    return out


def fetch_markets_ids(ids):
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 200):
        for r in cg("/coins/markets?vs_currency=usd&per_page=250&price_change_percentage=24h,7d,30d,200d&ids="
                    + ",".join(ids[i:i + 200])):
            out[r["id"]] = market_row(r)
    return out


def fetch_global():
    g = cg("/global")["data"]
    p = g.get("market_cap_percentage") or {}
    return {"total": (g.get("total_market_cap") or {}).get("usd"), "btc": p.get("btc"), "eth": p.get("eth")}


def fetch_catlist():
    return {r["category_id"]: r["name"] for r in cg("/coins/categories/list")}


def resolve_ids(catlist):
    out, missing = {}, []
    lower = {v.lower(): k for k, v in catlist.items()}
    for s in SECTORS:
        if "cg" not in s:
            continue
        cid = s["cg"] if s["cg"] in catlist else next((lower[n.lower()] for n in s["names"] if n.lower() in lower), None)
        if cid:
            out[s["key"]] = cid
        else:
            missing.append(s["name"])
    return out, missing


def fetch_category_ids(cid):
    rows = cg(f"/coins/markets?vs_currency=usd&category={cid}&order=market_cap_desc&per_page=250&page=1")
    return [r["id"] for r in rows if (r.get("market_cap") or 0) >= TH["minor_mcap"]]


def fetch_listing(ex_id, max_pages=25):
    """거래소에 상장된 코인(CoinGecko id). 같은 심볼의 가짜 토큰과 섞이지 않도록 id로 확인"""
    ids, krw = set(), {}
    for page in range(1, max_pages + 1):
        rows = cg(f"/exchanges/{ex_id}/tickers?page={page}").get("tickers") or []
        for t in rows:
            if t.get("is_stale") or t.get("is_anomaly") or not t.get("coin_id"):
                continue
            ids.add(t["coin_id"])
            if t.get("target") == "KRW":
                krw[(t.get("base") or "").upper()] = t["coin_id"]
        if len(rows) < 100:
            break
    return {"ids": sorted(ids), "krw": krw}


def fetch_top_exchanges(n=20):
    rows = cg("/exchanges?per_page=60&page=1")
    rows = sorted(rows, key=lambda r: -(r.get("trade_volume_24h_btc") or 0))[:n]
    return [{"id": r["id"], "name": r.get("name") or r["id"]} for r in rows]


def fetch_coin_exchanges(cid):
    rows = cg(f"/coins/{cid}/tickers?page=1&order=volume_desc").get("tickers") or []
    return sorted({(t.get("market") or {}).get("identifier") for t in rows if not t.get("is_stale")} - {None})


def fetch_cg_candles(cid):
    """거래소 일봉이 없는 코인용. CoinGecko 0시(UTC) 가격 = 전날 종가 → 날짜를 하루 당김"""
    d = cg(f"/coins/{cid}/market_chart?vs_currency=usd&days={CANDLE_DAYS + 5}&interval=daily")
    today = utc_day(NOW_TS)
    byday = {}
    for ts, v in d.get("prices", []):
        day = utc_day(ts / 1000 - DAY_S)
        if day < today:
            byday[day] = v
    vol = {}
    for ts, v in d.get("total_volumes", []):
        day = utc_day(ts / 1000 - DAY_S)
        if day < today:
            vol[day] = v
    days = sorted(byday)[-CANDLE_DAYS:]
    return {"src": "CoinGecko 평균가", "tv": None, "d": days, "c": [rnd6(byday[x]) for x in days],
            "h": [rnd6(byday[x]) for x in days], "v": [rnd6(vol.get(x)) for x in days]}


def fetch_cmc():
    d = get_json("https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?limit=1500&convert=USD",
                 headers={"X-CMC_PRO_API_KEY": CMC_KEY})
    out = {}
    for r in d.get("data", []):
        q = (r.get("quote") or {}).get("USD") or {}
        out.setdefault((r.get("symbol") or "").upper(), []).append([q.get("price"), q.get("volume_24h"), q.get("market_cap")])
    return out


def cmc_summary(coins, cmc):
    ok = bad = 0
    worst = []
    for c in coins.values():
        rows = [r for r in cmc.get(c["sym"], []) if r[0] and c["px"] and abs(r[0] / c["px"] - 1) < 0.15]
        if not rows:
            continue
        r = min(rows, key=lambda r: abs((r[2] or 0) - c["mc"]))
        d = abs(r[0] / c["px"] - 1) * 100
        if d > 3:
            bad += 1
            worst.append((d, c["sym"]))
        else:
            ok += 1
    return {"ok": ok, "bad": bad, "worst": [f"{s} {d:.1f}%" for d, s in sorted(worst, reverse=True)[:5]]}


# ═════════════════════════ 수집: 거래소 일봉 ═════════════════════════
def _closed(rows):
    """[ms, close, high, quote_vol] 중 오늘(UTC) 진행 중인 봉 제외"""
    today = utc_day(NOW_TS)
    rows = sorted((r for r in rows if utc_day(r[0] / 1000) < today), key=lambda r: r[0])
    return rows[-CANDLE_DAYS:]


def candles_bitget(sym):
    d = get_json(f"https://api.bitget.com/api/v2/spot/market/candles?symbol={sym}USDT&granularity=1day&limit={CANDLE_DAYS + 5}",
                 retries=2, timeout=20)
    rows = [[int(r[0]), fl(r[4]), fl(r[2]), fl(r[6]) if len(r) > 6 else None] for r in d.get("data") or []]
    return _closed(rows), f"BITGET:{sym}USDT"


def candles_okx(sym):
    rows, after = [], ""
    for _ in range(3):
        d = get_json(f"https://www.okx.com/api/v5/market/history-candles?instId={sym}-USDT&bar=1Dutc&limit=100{after}",
                     retries=2, timeout=20)
        part = d.get("data") or []
        if not part:
            break
        rows += [[int(r[0]), fl(r[4]), fl(r[2]), fl(r[7]) if len(r) > 7 else None] for r in part]
        after = f"&after={part[-1][0]}"
        time.sleep(0.12)
    return _closed(rows), f"OKX:{sym}USDT"


def pack_candles(rows, tv, src):
    return {"src": src, "tv": tv, "d": [utc_day(r[0] / 1000) for r in rows], "c": [rnd6(r[1]) for r in rows],
            "h": [rnd6(r[2]) for r in rows], "v": [rnd6(r[3]) for r in rows]}


def fetch_candles(c):
    """차트 버튼과 같은 거래소·페어의 일봉. 가격이 CoinGecko와 15% 넘게 다르면 다른 코인으로 보고 버림"""
    sym = re.sub(r"[^A-Z0-9]", "", c["sym"])
    for fn, name in ((candles_bitget, "Bitget"), (candles_okx, "OKX")):
        try:
            rows, tv = fn(sym)
        except Exception:
            continue
        if len(rows) >= 25 and rows[-1][1] and c["px"] and abs(rows[-1][1] / c["px"] - 1) < 0.15:
            return pack_candles(rows, tv, name)
    return None


# ═════════════════════════ 수집: 선물 거래소 ═════════════════════════
def norm(sym):
    s = sym.upper()
    for suf in ("-USDT-SWAP", "USDT"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    else:
        return None
    s = re.sub(r"^10{3,}", "", s)
    return re.sub(r"10{3,}$", "", s)


def add(acc, base, oi, fund_h, px, raw):
    if not base or not oi or oi <= 0:
        return
    r = acc.setdefault(base, {"oi": 0.0, "fw": 0.0, "fn": 0.0, "main": 0.0, "px": None, "raw": None})
    r["oi"] += oi
    if fund_h is not None:
        r["fw"] += fund_h * oi
        r["fn"] += oi
    if oi > r["main"]:
        r["main"], r["px"], r["raw"] = oi, px, raw


def finalize(acc):
    return {b: {"oi": r["oi"], "fund_h": r["fw"] / r["fn"] if r["fn"] else None, "px": r["px"], "raw": r["raw"]}
            for b, r in acc.items()}


def fetch_hyperliquid(wanted):
    meta, ctxs = get_json("https://api.hyperliquid.xyz/info", method="POST", body={"type": "metaAndAssetCtxs"})
    acc = {}
    for a, c in zip(meta["universe"], ctxs):
        name = a["name"]
        base = name[1:] if name.startswith("k") and name[1:].isupper() else name.upper()
        px, oi = fl(c.get("markPx")), fl(c.get("openInterest"))
        if px and oi:
            add(acc, base, oi * px, fl(c.get("funding")), px, name)
    return finalize(acc)


def fetch_bitget(wanted):
    acc = {}
    for r in get_json("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES")["data"]:
        sym = r["symbol"]
        px = fl(r.get("markPrice")) or fl(r.get("lastPr"))
        oi, fund = fl(r.get("holdingAmount")), fl(r.get("fundingRate"))
        ivh = fl(r.get("fundingRateInterval")) or 8
        if px and oi:
            add(acc, norm(sym), oi * px, fund / ivh if fund is not None else None, px, sym)
    return finalize(acc)


def fetch_okx(wanted):
    b = "https://www.okx.com"
    tick = {t["instId"]: t for t in get_json(b + "/api/v5/market/tickers?instType=SWAP")["data"]}
    acc = {}
    for r in get_json(b + "/api/v5/public/open-interest?instType=SWAP")["data"]:
        iid = r["instId"]
        base = norm(iid)
        if base not in wanted or not iid.endswith("-USDT-SWAP"):
            continue
        last = fl(tick.get(iid, {}).get("last"))
        oi = fl(r.get("oiUsd")) or (fl(r.get("oiCcy")) or 0) * (last or 0)
        try:
            fr = get_json(f"{b}/api/v5/public/funding-rate?instId={iid}", retries=1, timeout=15)["data"][0]
            fund, ft, nft = fl(fr.get("fundingRate")), fl(fr.get("fundingTime")), fl(fr.get("nextFundingTime"))
            ivh = (nft - ft) / 3.6e6 if ft is not None and nft is not None and nft > ft else 8
            fund_h = fund / ivh if fund is not None else None
        except Exception:
            fund_h = None
        add(acc, base, oi, fund_h, last, iid)
        time.sleep(0.12)
    return finalize(acc)


FETCHERS = {"Hyperliquid": fetch_hyperliquid, "Bitget": fetch_bitget, "OKX": fetch_okx}


def px_match(ex_px, cg_px):
    if not ex_px or not cg_px:
        return False
    r = ex_px / cg_px
    return any(abs(r / k - 1) < 0.08 for k in (1, 1e3, 1e4, 1e6))


def fetch_short_ratio(sym):
    """Bitget 선물 계정 기준 숏 비율(%)"""
    d = get_json(f"https://api.bitget.com/api/v2/mix/market/account-long-short?symbol={sym}USDT&period=1h",
                 retries=1, timeout=15).get("data") or []
    if not d:
        return None
    last = d[-1] if isinstance(d, list) else d
    s = fl(last.get("shortAccountRatio"))
    if s is None and fl(last.get("longAccountRatio")) is not None:
        s = 1 - fl(last["longAccountRatio"])
    return None if s is None else (s * 100 if s <= 1 else s)


# ═════════════════════════ 수집: 국내 거래소 ═════════════════════════
def fetch_upbit_markets():
    """업비트 마켓 목록: 심볼별 마켓(KRW/BTC/USDT)과 투자유의 여부"""
    out = {}
    for m in get_json("https://api.upbit.com/v1/market/all?isDetails=true"):
        q, base = m["market"].split("-", 1)
        r = out.setdefault(base.upper(), {"mk": [], "warn": False})
        r["mk"].append(q)
        ev = m.get("market_event") or {}
        if m.get("market_warning") == "CAUTION" or ev.get("warning"):
            r["warn"] = True
    return out


def fetch_upbit_krw(krw_map):
    markets = [m["market"] for m in get_json("https://api.upbit.com/v1/market/all?isDetails=false") if m["market"].startswith("KRW-")]
    out = {}
    for i in range(0, len(markets), 100):
        for t in get_json("https://api.upbit.com/v1/ticker?markets=" + ",".join(markets[i:i + 100])):
            cid = krw_map.get(t["market"].split("-", 1)[1])
            if cid:
                out[cid] = fl(t.get("acc_trade_price_24h"))
        time.sleep(0.3)
    return out


def fetch_bithumb():
    d = get_json("https://api.bithumb.com/public/ticker/ALL_KRW").get("data") or {}
    return sorted(k.upper() for k in d if k != "date")


def fetch_upbit_notices():
    d = get_json("https://api-manager.upbit.com/api/v1/announcements?os=web&page=1&per_page=20&category=trade", retries=1, timeout=20)
    out = []
    for n in ((d.get("data") or {}).get("notices") or []):
        t = n.get("title") or ""
        if "거래지원" in t and ("신규" in t or "추가" in t):
            out.append({"d": (n.get("listed_at") or n.get("first_listed_at") or "")[:10], "ex": "업비트", "t": t,
                        "u": f"https://upbit.com/service_center/notice?id={n.get('id')}"})
    return out[:10]


def fetch_binance_notices():
    d = get_json("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=48&pageNo=1&pageSize=15",
                 retries=1, timeout=20)
    out = []
    for cat in ((d.get("data") or {}).get("catalogs") or []):
        for a in cat.get("articles") or []:
            t = a.get("title") or ""
            if "Will List" in t or "Will Add" in t:
                ts = a.get("releaseDate")
                out.append({"d": utc_day(ts / 1000) if ts else "", "ex": "바이낸스", "t": t,
                            "u": f"https://www.binance.com/en/support/announcement/{a.get('code', '')}"})
    return out[:10]


# ═════════════════════════ 모의 데이터 (MOCK=1 테스트용) ═════════════════════════
_MW = {}


def mock_universe():
    if _MW:
        return _MW
    today = dt.datetime.fromtimestamp(NOW_TS, UTC).date()
    days = [(today - dt.timedelta(days=CANDLE_DAYS + 10 - i)).isoformat() for i in range(CANDLE_DAYS + 10)]
    names = ["bitcoin", "ethereum", "tether", "solana", "binancecoin"] + [f"coin-{i:03d}" for i in range(360)] + \
            ["cash-cat", "artificial-inu-3", "morpho", "lighter", "uniswap", "dydx-chain"]
    coins = {}
    for n, cid in enumerate(names):
        r = random.Random(cid)
        if cid == "tether":
            ps = [1.0] * len(days)
            mc = 150e9
        else:
            p = {"bitcoin": 60000, "ethereum": 2500}.get(cid, r.uniform(0.01, 80))
            drift = r.uniform(-0.002, 0.006)
            ps = []
            for i in range(len(days)):
                boost = 0.02 if (n % 17 == 0 and i > len(days) - 40) else 0
                p *= 1 + drift + boost + r.gauss(0, 0.035 if cid != "bitcoin" else 0.02)
                ps.append(p)
            mc = {"bitcoin": 1.9e12, "ethereum": 3.2e11}.get(cid, math.exp(r.uniform(math.log(4e7), math.log(3e10))))
        sym = {"bitcoin": "BTC", "ethereum": "ETH", "tether": "USDT", "solana": "SOL", "binancecoin": "BNB",
               "cash-cat": "CASHCAT", "artificial-inu-3": "AI", "morpho": "MORPHO", "lighter": "LIT",
               "uniswap": "UNI", "dydx-chain": "DYDX"}.get(cid, "C" + cid[-3:])
        vols = [mc * r.uniform(0.02, 0.15) * (1.8 if i > len(days) - 3 and n % 5 == 0 else 1) for i in range(len(days))]
        coins[cid] = {"sym": sym, "name": cid.replace("-", " ").title() if cid != "tether" else "Tether",
                      "p": ps, "v": vols, "mc0": mc / ps[-1] if ps[-1] else 0}
    _MW.update({"days": days, "coins": coins})
    return _MW


def mock_markets():
    w = mock_universe()
    out = {}
    for cid, c in w["coins"].items():
        p = c["p"]
        px = p[-1] * (1 + random.Random(cid + str(NOW_TS // 7200)).uniform(-0.01, 0.01))
        mc = c["mc0"] * px
        out[cid] = {"id": cid, "sym": c["sym"], "name": c["name"], "px": px, "mc": mc, "fdv": mc * random.Random(cid).uniform(1, 2.2),
                    "vol": c["v"][-1], "dd": pct(px, max(p)), "c1": pct(px, p[-2]), "c7": pct(px, p[-8]),
                    "c30": pct(px, p[-31]), "c200": pct(px, p[-201])}
    return out


def mock_sector_ids():
    w = mock_universe()
    keys = [s["key"] for s in SECTORS if "cg" in s]
    out = {k: [] for k in keys}
    for i, cid in enumerate(w["coins"]):
        if cid in ("tether",):
            continue
        r = random.Random(cid + "s")
        for k in r.sample(keys, r.choice([1, 1, 2, 3])):
            out[k].append(cid)
    return out


def mock_global():
    w = mock_markets()
    tot = sum(c["mc"] for c in w.values()) * 1.25
    r = random.Random(NOW_TS // 7200)
    return {"total": tot, "btc": w["bitcoin"]["mc"] / tot * 100 * r.uniform(0.98, 1.02), "eth": w["ethereum"]["mc"] / tot * 100}


def mock_derivs(markets):
    out = {"Hyperliquid": {}, "Bitget": {}, "OKX": {}}
    for cid, c in markets.items():
        r = random.Random(cid + "d" + str(NOW_TS // 7200))
        if r.random() < 0.6:
            ex = r.choice(list(out))
            out[ex][c["sym"]] = {"oi": c["mc"] * r.uniform(0.01, 0.08), "fund_h": r.uniform(-0.00003, 0.00005),
                                 "px": c["px"], "raw": c["sym"] + "USDT"}
    return out


def mock_listing(markets):
    out = {}
    for v in LIST_VENUES:
        ids = [cid for cid in markets if random.Random(cid + v).random() < (0.8 if v != "Upbit" else 0.45)]
        out[v] = {"ids": ids, "krw": {markets[i]["sym"]: i for i in ids} if v == "Upbit" else {}}
    return out


def mock_upbit_markets(markets):
    out = {}
    for cid, c in markets.items():
        r = random.Random(cid + "u")
        x = r.random()
        if x < 0.45:
            out[c["sym"]] = {"mk": ["KRW", "BTC", "USDT"], "warn": r.random() < 0.05}
        elif x < 0.52:
            out[c["sym"]] = {"mk": ["BTC", "USDT"], "warn": False}
    return out


def mock_candles(cid):
    w = mock_universe()
    c = w["coins"][cid]
    n = CANDLE_DAYS
    return {"src": "Bitget", "tv": f"BITGET:{c['sym']}USDT", "d": w["days"][-n:], "c": [rnd6(x) for x in c["p"][-n:]],
            "h": [rnd6(x * 1.02) for x in c["p"][-n:]], "v": [rnd6(x) for x in c["v"][-n:]]}


# ═════════════════════════ 판정: 코인 ═════════════════════════
def excluded(c):
    name = " " + (c.get("name") or "").lower()
    return (c["sym"].lower() in STABLE_SYMS or any(w in name for w in EXCLUDE_WORDS)
            or not c.get("px") or (0.97 <= c["px"] <= 1.03 and abs(c.get("c30") or 0) < 3)
            or c.get("c30") is None or c.get("c7") is None)


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def coin_metrics(c, cd):
    """거래소 일봉(마감 봉) + 현재가 = 트레이딩뷰 일봉 이평과 같은 방식"""
    out = {"src": None, "tv": None, "c3": None, "c180": None, "ma20": None, "ma60": None, "ma100": None, "ma200": None,
           "hi30": None, "brk": False, "slope": None, "hl": False, "rc": 0, "vx": None, "vd": None, "run": None, "offpk": None,
           "tp": None, "spark": [], "ma20line": [], "wk": [None] * 4, "r90": None}
    if not cd or len(cd.get("c") or []) < 25 or not c.get("px"):
        return out
    cl = [x for x in cd["c"] if x]
    px = c["px"]
    s = cl + [px]
    out.update(src=cd.get("src"), tv=cd.get("tv"))
    out["c3"] = pct(px, cl[-3]) if len(cl) >= 3 else None
    out["c180"] = pct(px, cl[-180]) if len(cl) >= 180 else None
    out["r90"] = pct(px, cl[-90]) if len(cl) >= 90 else None
    for n in (20, 60, 100, 200):
        out[f"ma{n}"] = sma(s, n)
    hs = [x for x in (cd.get("h") or [])[-30:] if x]
    out["hi30"] = pct(px, max(hs + [px])) if hs else pct(px, max(cl[-30:] + [px]))
    out["brk"] = len(cl) >= 30 and px > max(cl[-30:])
    ma20s = [sum(s[i - 20:i]) / 20 for i in range(max(20, len(s) - 14), len(s) + 1)]
    out["ma20line"] = [rnd6(x) for x in ma20s]
    out["slope"] = pct(ma20s[-1], ma20s[-6]) if len(ma20s) >= 6 else None
    out["spark"] = [rnd6(x) for x in s[-31:]]
    lows = s[-20:]
    out["hl"] = len(lows) == 20 and min(lows[-10:]) > min(lows[:10])
    below = 0
    for k in range(2, 16):   # 어제까지 20일선 아래 연속 일수
        i = len(s) - k
        if i < 20:
            break
        if s[i] < sum(s[i - 19:i + 1]) / 20:
            below += 1
        else:
            break
    out["rc"] = below if (out["ma20"] and px > out["ma20"] and below >= TH["reclaim_days"]) else 0
    v = [x for x in (cd.get("v") or []) if x]
    if len(v) >= 23 and statistics.mean(v[-23:-3]) > 0:
        out["vx"] = statistics.mean(v[-3:]) / statistics.mean(v[-23:-3])
        out["vd"] = v[-1] / statistics.mean(v[-21:-1])
    # 팀 리더 조언: 익절 구간·2차 파동·꺾임
    w90 = s[-90:]
    lo, hi = min(w90), max(w90)
    out["run"], out["offpk"] = pct(px, lo), pct(px, hi)
    body = s[-180:-5] if len(s) > 60 else []
    tp = None
    if body:
        i1 = max(range(len(body)), key=lambda i: body[i])
        p1 = body[i1]
        trough = min(s[-180:][i1:])
        if pct(trough, p1) <= TH["wave_dd"] and px >= p1 * 0.9 and px >= trough * 1.25:
            tp = ["2차 파동 고점 근접", f"첫 고점에서 {pct(trough, p1):.0f}% 조정 후 재상승, " +
                  (f"첫 고점을 {pct(px, p1):+.0f}% 넘어섬" if px > p1 else f"첫 고점까지 {pct(px, p1):.0f}%")]
    if not tp and out["run"] >= TH["tp_run"] and out["offpk"] >= TH["tp_near"]:
        tp = ["급등 누적", f"90일 저점 대비 {out['run']:+.0f}%, 고점 근처"]
    if not tp and out["run"] >= TH["brk_run"] and out["offpk"] <= TH["brk_off"]:
        tp = ["꺾임 주의", f"90일 저점 대비 {out['run']:+.0f}% 올랐다가 고점 대비 {out['offpk']:.0f}%"]
    out["tp"] = tp
    out["wk"] = [pct(s[-b], s[-a]) if len(s) > a else None for a, b in ((29, 22), (22, 15), (15, 8), (8, 1))]
    return out


def rz(x, xs):
    m = statistics.median(xs)
    mad = statistics.median([abs(v - m) for v in xs]) or 1e-9
    return (x - m) / (1.4826 * mad)


def build_world(markets, sec_ids, candles, derivs, listing, upx, oi_prev, short, ex20, upb_mk, bithumb, prev_state):
    """모든 목록·지표 계산. 결과는 페이지(D)와 기록에 그대로 쓰임"""
    # 추적 코인: 섹터 소속 + 시총 $70M 이상
    member = {}
    for s in SECTORS:
        for cid in (s.get("ids") or sec_ids.get(s["key"], [])):
            if cid in markets and cid != "bitcoin":
                member.setdefault(cid, []).append(s["key"])
    coins = {}
    for cid, secs in member.items():
        c = dict(markets[cid])
        if excluded(c) or c["mc"] < TH["minor_mcap"]:
            continue
        c.update(coin_metrics(c, candles.get(cid)))
        c["secs"] = secs
        coins[cid] = c
    mk7 = med(c["c7"] for c in coins.values())
    mk30 = med(c["c30"] for c in coins.values())
    mk3 = med(c["c3"] for c in coins.values() if c["c3"] is not None) or 0
    # 섹터
    secs = {}
    for s in SECTORS:
        ms = [coins[i] for i, c in coins.items() if s["key"] in c["secs"]]
        if len(ms) < 3:
            continue
        c7 = [c["c7"] for c in ms]
        x = {"k": s["key"], "n": s["name"], "m3": med(c["c3"] for c in ms if c["c3"] is not None) or 0, "m7": med(c7),
             "m30": med(c["c30"] for c in ms), "br": sum(1 for v in c7 if v > 0) / len(c7) * 100, "ids": [c["id"] for c in ms],
             "mc": sum(c["mc"] for c in ms), "watch": bool(s.get("watch")), "native": s.get("native") or [],
             "thin": len(ms) < TH["sec_min"]}
        x["x7"], x["x30"] = x["m7"] - mk7, x["m30"] - mk30
        x["score"] = x["x7"] * 2 + x["x30"] * .5 + (x["br"] - 50) * .3
        lead = [c for c in ms if (c["vol"] or 0) >= TH["pick_volume"]]
        if lead:
            L = max(lead, key=lambda c: c["c30"])
            x["lead"] = {"id": L["id"], "s": L["sym"], "c30": L["c30"], "c7": L["c7"]}
        secs[s["key"]] = x
    order = sorted(secs.values(), key=lambda s: -s["score"])
    for i, s in enumerate(order):
        s["rank"], s["top"] = i + 1, False
    for s in [s for s in order if not s["watch"] and not s["thin"] and s["x7"] > 0 and s["x30"] > 0 and s["br"] >= TH["breadth_min"]][:TH["top_sec"]]:
        s["top"] = True
    # 코인별 섹터 안 순위·표준점수 (대표 섹터: 상위 섹터이면서 덜 오른 곳 > 상위 섹터 > 점수)
    for k, s in secs.items():
        ms = [coins[i] for i in s["ids"]]
        c30s, c7s = [c["c30"] for c in ms], [c["c7"] for c in ms]
        byret = sorted(ms, key=lambda c: -c["c30"])
        bymc = sorted(ms, key=lambda c: -c["mc"])
        for c in ms:
            z30, z7 = rz(c["c30"], c30s), rz(c["c7"], c7s)
            pri = (s["top"] and z30 <= TH["z30"], s["top"], s["score"])
            if "sec" not in c or pri > c["_pri"]:
                c.update(sec=k, _pri=pri, z30=z30, z7=z7, srank=byret.index(c) + 1, sn=len(ms), mrank=bymc.index(c) + 1)
    coins = {i: c for i, c in coins.items() if "sec" in c}
    # 코인 판정
    for cid, c in coins.items():
        s = secs[c["sec"]]
        venues = {ex: d[c["sym"]] for ex, d in derivs.items() if c["sym"] in d and px_match(d[c["sym"]]["px"], c["px"])}
        oi = sum(v["oi"] for v in venues.values())
        fr = [(v["fund_h"], v["oi"]) for v in venues.values() if v["fund_h"] is not None]
        c["fund"] = round(sum(f * w for f, w in fr) / sum(w for _, w in fr) * 24 * 365 * 100) if fr else None
        c["oi"] = pct(oi, oi_prev.get(cid)) if oi and oi_prev.get(cid) else None
        c["oi_usd"] = oi or None
        c["sh"] = short.get(cid)
        c["upx"] = upx.get(cid)
        c["L"] = "".join(VENUE_CODE[v] for v in VENUE_CODE if cid in listing.get(v, set()) or (v in ("Bitget", "OKX") and v in venues))
        c["ex20"] = ex20.get(cid)
        um = upb_mk.get(c["sym"]) or {}
        c["uwarn"] = bool(um.get("warn")) and "U" in c["L"]
        c["float"] = c["mc"] / c["fdv"] if c.get("fdv") else None
        c["fatal"] = c["vol"] < TH["min_volume"] or not c["L"]
        c["under"] = c["z30"] <= TH["z30"] and c["z7"] <= TH["z7"] and c["c30"] <= TH["cap30"] and c["c7"] <= TH["cap7"]
        c["a20"] = bool(c["ma20"] and c["px"] > c["ma20"])
        c["cvol"] = c["vx"] is not None and c["vx"] >= TH["vol_x"]
        c["cfirst"] = c["c3"] is not None and c["c3"] > s["m3"]
        sq = [["숏 우세", c["fund"] is not None and c["fund"] <= 0, "펀딩 —" if c["fund"] is None else f"펀딩 {c['fund']}%"],
              ["숏 쌓임", c["oi"] is not None and c["oi"] >= TH["sq_oi"], "OI —" if c["oi"] is None else f"OI {c['oi']:+.1f}%"],
              ["숏 계정 많음", c["sh"] is not None and c["sh"] >= TH["sq_short"], "숏 —" if c["sh"] is None else f"숏 {c['sh']:.0f}%"],
              ["가격 버팀", c["c7"] >= 0, f"7일 {c['c7']:+.1f}%"]]
        c["sq"], c["sqn"] = sq, sum(1 for q in sq if q[1])
        c["squeeze"] = c["sqn"] >= 3 and c["fund"] is not None
        w = []
        if c["uwarn"]:
            w.append("업비트 투자유의")
        if len(c["L"]) < 2:
            w.append("상장 1곳")
        if c["float"] is not None and c["float"] < 0.5:
            w.append(f"유통 {c['float'] * 100:.0f}%")
        if c["mc"] < TH["pick_mcap"]:
            w.append("소형")
        if c["vol"] < TH["pick_volume"]:
            w.append("거래량 적음")
        if c["fund"] is not None and c["fund"] >= TH["funding_hot"]:
            w.append("롱 과열")
        if c["c7"] > TH["cap7"]:
            w.append(f"7일 급등 {c['c7']:+.0f}%")
        if c["c30"] > TH["cap30"]:
            w.append(f"30일 +{c['c30']:.0f}%")
        if c["ma20"] and not c["a20"]:
            w.append("20일선 아래")
        c["warns"] = w
        c["hard"] = (c["mc"] >= TH["pick_mcap"] and c["vol"] >= TH["pick_volume"] and len(c["L"]) >= 2
                     and (c["fund"] is None or c["fund"] < TH["funding_hot"]) and not c["uwarn"])
        sig = [["덜 오름", c["under"]], ["20일선 위", c["a20"]], ["거래량 증가", c["cvol"]], ["추세 돌파", c["brk"]],
               ["스퀴즈 준비", c["squeeze"]], ["업비트 관심", (c["upx"] or 0) >= TH["upbit_x"]]]
        c["sig"], c["nsig"] = sig, sum(1 for q in sig if q[1])
        c["score"] = round(max(-c["z30"], 0) * 15 + min(max((c["vx"] or 1) - 1, 0) * 25, 25) + max(s["score"], 0) * .5
                           + (5 if c["cfirst"] else 0) + (6 if c["squeeze"] else 0) - len(w) * 3, 1)
        # 눌림목: 강하게 오른 섹터의 선두권이 20일선 아래로 조정
        conds = [("섹터 30일 강함", s["x30"] >= TH["pull_sec30"]), ("코인 30일 +10% 이상", c["c30"] >= TH["pull_c30"]),
                 ("섹터 안 상위 절반", c["srank"] <= math.ceil(c["sn"] / 2)), ("20일선 아래", bool(c["ma20"] and c["px"] < c["ma20"])),
                 (f"고점 대비 {TH['pull_hi_max']:.0f}~{TH['pull_hi_min']:.0f}%", c["hi30"] is not None and TH["pull_hi_min"] <= c["hi30"] <= TH["pull_hi_max"])]
        miss = [a for a, b in conds if not b]
        c["pull"] = c["pullmiss"] = None
        if not miss and c["ma20"]:
            lv = [(n, c[f"ma{n}"]) for n in (60, 100, 200) if c[f"ma{n}"]]
            below = sorted([x for x in lv if x[1] <= c["px"]], key=lambda x: -x[1])
            above = sorted([x for x in lv if x[1] > c["px"]], key=lambda x: x[1])
            if below and pct(c["px"], below[0][1]) <= TH["ma_near"]:
                st, txt, sup = "hold", f"{below[0][0]}일선 지지 테스트 (+{pct(c['px'], below[0][1]):.1f}%)", below[0][0]
            elif above and (not below or above[0][0] < below[0][0]):
                st = "lost"
                txt = f"{above[0][0]}일선 이탈" + (f" · 다음 {below[0][0]}일선까지 −{(1 - below[0][1] / c['px']) * 100:.0f}%" if below else "")
                sup = below[0][0] if below else None
            else:
                st, sup = "wait", below[0][0] if below else None
                txt = f"{below[0][0]}일선까지 −{(1 - below[0][1] / c['px']) * 100:.0f}% 남음" if below else "받쳐줄 이평선 없음"
            q = [["이평 정배열", bool(c["ma60"] and c["ma100"] and c["ma200"] and c["ma60"] > c["ma100"] > c["ma200"])],
                 ["조정 중 거래량 감소", c["vx"] is not None and c["vx"] < 1], ["펀딩 식음", c["fund"] is None or c["fund"] < 10]]
            c["pull"] = {"st": st, "txt": txt, "sup": sup, "q": q, "qn": sum(1 for a in q if a[1])}
        elif 1 <= len(miss) <= 2 and c["c30"] >= TH["pull_c30"] and "20일선 아래" not in miss:
            c["pullmiss"] = miss
        c["reclaim"] = None
        if c["rc"]:
            turn = bool(c["ma60"] and c["px"] > c["ma60"])
            q = [["재돌파 거래량 증가", c["vd"] is not None and c["vd"] >= TH["reclaim_vol"]],
                 ["20일선 기울기 평탄·상승", c["slope"] is not None and c["slope"] >= -0.5], ["저점 상승", c["hl"]]]
            c["reclaim"] = {"st": "turn" if turn else "bounce", "q": q, "qn": sum(1 for a in q if a[1])}
        # 상장 후보: 업비트 원화·바이낸스에 없음
        why = []
        if "U" not in c["L"] and "B" not in c["L"]:
            if um.get("mk") and "KRW" not in um["mk"]:
                why.append("업비트 " + "·".join(um["mk"]) + " 마켓만")
            if c["sym"] in bithumb:
                why.append("빗썸 원화 상장")
            if not why and "G" in c["L"] and "O" in c["L"]:
                why.append("Bitget·OKX 상장")
        c["listwhy"] = why
    live = {i: c for i, c in coins.items() if not c["fatal"]}
    # Top 3 (시총 순, 유지 규칙)
    prev_top = set(prev_state.get("top") or [])
    for c in live.values():
        s = secs[c["sec"]]
        c["kept"] = (c["id"] in prev_top and not (s["top"] and c["under"]) and s["rank"] <= TH["top_sec"] + 2 and not s["watch"]
                     and c["z30"] <= TH["z30_keep"] and c["c7"] <= TH["cap7"] and c["c30"] <= TH["cap30"] and c["hard"])
    top = sorted([c for c in live.values() if (secs[c["sec"]]["top"] and c["under"] and c["hard"]) or c["kept"]], key=lambda c: -c["mc"])[:3]
    for i, c in enumerate(top):
        c["topRank"] = i + 1
    top_ids = [c["id"] for c in top]
    early = sorted([c for c in live.values() if c["id"] not in top_ids and secs[c["sec"]]["top"] and c["mc"] >= TH["pick_mcap"] and c["nsig"] >= 2],
                   key=lambda c: -c["score"])[:TH["early_max"]]
    small = sorted([c for c in live.values() if c["id"] not in top_ids and c["mc"] < TH["pick_mcap"] and c["nsig"] >= 2],
                   key=lambda c: -c["score"])[:TH["small_max"]]
    listc = sorted([c for c in live.values() if c["listwhy"] and c["vol"] >= TH["pick_volume"]], key=lambda c: -c["vol"])[:TH["list_max"]]
    # 변화 사유
    pf = prev_state.get("flags") or {}
    changes = []
    for c in top:
        if c["id"] not in prev_top:
            p = pf.get(c["id"])
            if p:
                why = [f"{k} 충족" for k, now in (("상위 섹터", secs[c["sec"]]["top"]), ("덜 오름", c["under"]), ("안전 조건", c["hard"])) if now and not p.get(k)]
            else:
                why = ["새로 추적 시작"]
            changes.append({"t": "in", "s": c["sym"], "id": c["id"], "why": why or ["다른 코인이 빠지면서 시총 순위로 진입"]})
    for cid in prev_top - set(top_ids):
        c = coins.get(cid)
        if not c:
            changes.append({"t": "out", "s": (pf.get(cid) or {}).get("sym", cid), "id": cid, "why": ["추적 대상에서 빠짐 (시총·거래량)"]})
            continue
        s = secs[c["sec"]]
        if not s["top"]:
            why = ["상위 섹터 탈락"]
        elif c["c7"] > TH["cap7"]:
            why = [f"7일 +{c['c7']:.0f}% 급등으로 상한 초과"]
        elif c["z30"] > TH["z30_keep"]:
            why = ["30일 수익률이 섹터 중간 수준까지 따라잡음"]
        elif not c["hard"]:
            why = ["안전 조건 탈락"]
        else:
            why = ["다른 코인에 밀림 (3개 제한)"]
        changes.append({"t": "out", "s": c["sym"], "id": cid, "why": why})
    flags = {c["id"]: {"sym": c["sym"], "상위 섹터": secs[c["sec"]]["top"], "덜 오름": c["under"], "안전 조건": c["hard"]} for c in live.values()}
    return {"coins": coins, "secs": secs, "mk": {"m3": mk3, "m7": mk7, "m30": mk30, "n": len(coins)}, "top": top, "early": early,
            "small": small, "listc": listc, "changes": changes, "state": {"top": top_ids, "flags": flags}}


# ═════════════════════════ 판정: 시장 ═════════════════════════
def market_view(W, markets, candles, glob_hist, btc_cd):
    coins = W["coins"]
    # BTC
    b = markets.get("bitcoin") or {}
    btc = {"px": b.get("px"), "c7": b.get("c7"), "c30": b.get("c30"), "dd": b.get("dd"), "up": None, "slopeUp": None}
    if btc_cd and len(btc_cd.get("c") or []) >= 55 and b.get("px"):
        s = btc_cd["c"] + [b["px"]]
        ma50, ma50p = sma(s, 50), sma(s[:-5], 50)
        btc.update(up=b["px"] > ma50, slopeUp=ma50 > ma50p, ma50=ma50)
    # 도미넌스·알트/BTC (전체 시총 기록)
    g = glob_hist[-1] if glob_hist else {}

    def ago(days):
        tgt = NOW_TS - days * DAY_S
        h = min(glob_hist, key=lambda r: abs(r["ts"] - tgt), default=None)
        return h if h and abs(h["ts"] - tgt) <= 1.5 * DAY_S else None
    btc.update(dom=g.get("btc"), dom7=None, alt30=None, altd=None)
    h7 = ago(7)
    if h7 and g.get("btc") is not None:
        btc["dom7"] = g["btc"] - h7["btc"]

    def t3b(r):
        return r["total"] * (1 - (r["btc"] + r["eth"]) / 100) / (r["total"] * r["btc"] / 100) if r and r.get("total") and r.get("btc") else None
    for d in (30, 7):
        h = ago(d)
        if h and t3b(h) and t3b(g):
            btc["alt30"], btc["altd"] = pct(t3b(g), t3b(h)), d
            break
    # 자체 알트시즌 지수: 시총 상위 50개 알트 중 최근 90일 BTC보다 더 오른 비율
    alts = sorted([c for c in markets.values() if c["id"] != "bitcoin" and not excluded(c)], key=lambda c: -c["mc"])[:50]
    b90 = pct(b.get("px"), btc_cd["c"][-90]) if btc_cd and len(btc_cd.get("c") or []) >= 90 else None
    got = [(coins[c["id"]]["r90"] if c["id"] in coins else None) for c in alts]
    got = [x for x in got if x is not None]
    if b90 is not None and len(got) >= 25:
        btc["alt"], btc["altn"], btc["altbase"] = round(sum(1 for x in got if x > b90) / len(got) * 100), len(got), "90일"
    else:
        r30 = [c["c30"] for c in alts if c.get("c30") is not None]
        btc["alt"] = round(sum(1 for x in r30 if x > (b.get("c30") or 0)) / len(r30) * 100) if r30 else None
        btc["altn"], btc["altbase"] = len(r30), "30일 (90일 기록 쌓는 중)"
    # 체급 (시총 상위 1000개 기준)
    uni = [c for c in markets.values() if not excluded(c) and c["mc"] >= TH["minor_mcap"] and c["id"] != "bitcoin"]
    tiers = []
    for nm, rg, lo, hi in TIERS:
        cs = [c for c in uni if lo <= c["mc"] < hi]
        if not cs:
            continue
        ld = [c for c in cs if c["vol"] >= TH["pick_volume"] and c.get("c30") is not None]
        L = max(ld, key=lambda c: c["c30"]) if ld else None
        wk = []
        for j in range(4):
            r = [coins[c["id"]]["wk"][j] for c in cs if c["id"] in coins and coins[c["id"]]["wk"][j] is not None]
            wk.append(med(r))
        tiers.append({"n": nm, "rg": rg, "cnt": len(cs), "m7": med(c["c7"] for c in cs), "m30": med(c["c30"] for c in cs),
                      "up": sum(1 for c in cs if (c["c7"] or 0) > 0) / len(cs) * 100, "wk": wk,
                      "lead": {"id": L["id"], "s": L["sym"], "c30": L["c30"]} if L else None})
    # 대장
    big = [c for c in coins.values() if c["vol"] >= 20e6]
    lead = {"ret": None, "vol": None, "top5": []}
    if big:
        r1 = max(big, key=lambda c: c["c30"])
        lead["ret"] = {"id": r1["id"], "s": r1["sym"], "c30": r1["c30"], "vol": r1["vol"]}
        run = [c for c in big if c["c30"] >= 20]
        if run:
            r2 = max(run, key=lambda c: c["vol"])
            lead["vol"] = {"id": r2["id"], "s": r2["sym"], "c30": r2["c30"], "vol": r2["vol"]}
        lead["top5"] = [{"id": c["id"], "s": c["sym"], "c30": c["c30"]} for c in sorted(big, key=lambda c: -c["c30"])[:5]]
    # 시장 폭 (팀 리더 조언: 초기엔 알트가 다 같이 오름)
    cs = list(coins.values())
    n = len(cs) or 1
    wr = [c for c in cs if c["run"] is not None]
    nw = len(wr) or 1
    cyc = {"n": len(cs), "b30": sum(1 for c in cs if c["c30"] > 0) / n * 100, "b7": sum(1 for c in cs if c["c7"] > 0) / n * 100,
           "b7p": None, "big": sum(1 for c in wr if c["run"] >= 50) / nw * 100, "hot": sum(1 for c in wr if c["run"] >= 100) / nw * 100,
           "tp": sum(1 for c in cs if c["tp"] and c["tp"][0] != "꺾임 주의") / n * 100,
           "brk": sum(1 for c in cs if c["tp"] and c["tp"][0] == "꺾임 주의") / n * 100}
    prev7 = [pct(cd["c"][-8], cd["c"][-15]) for cid, cd in candles.items() if cid in coins and len(cd.get("c") or []) >= 15]
    prev7 = [x for x in prev7 if x is not None]
    cyc["b7p"] = sum(1 for x in prev7 if x > 0) / len(prev7) * 100 if prev7 else cyc["b7"]
    # 섹터 순환: 섹터끼리 7일 수익률 차이 (지금 vs 최근 30일 평소)
    def disp_at(k):
        m = []
        for s in W["secs"].values():
            r = [pct(candles[i]["c"][-1 - k], candles[i]["c"][-8 - k]) for i in s["ids"] if i in candles and len(candles[i]["c"]) > 8 + k]
            r = [x for x in r if x is not None]
            if len(r) >= 3:
                m.append(statistics.median(r))
        return statistics.pstdev(m) if len(m) >= 5 else None
    now_d = statistics.pstdev([s["m7"] for s in W["secs"].values()]) if len(W["secs"]) >= 5 else None
    hist_d = [x for x in (disp_at(k) for k in range(0, 30)) if x is not None]
    disp = {"now": now_d, "norm": med(hist_d) if hist_d else None}
    return {"btc": btc, "tiers": tiers, "lead": lead, "cyc": cyc, "disp": disp}


# ═════════════════════════ 실전 기록 ═════════════════════════
LOG_LISTS = [("top", "Top 3"), ("early", "초입 후보"), ("small", "소형 도전"), ("pull", "눌림목 (지지 중)"), ("reclaim", "20일선 재돌파")]


def update_log(log, W):
    coins, secs = W["coins"], W["secs"]
    picks = {"top": W["top"], "early": W["early"], "small": W["small"],
             "pull": [c for c in coins.values() if c.get("pull") and c["pull"]["st"] == "hold" and not c["fatal"]],
             "reclaim": [c for c in coins.values() if c.get("reclaim") and not c["fatal"]]}
    new_top = []
    for g, _ in LOG_LISTS:
        seen = {e["id"] for e in log if e["g"] == g and NOW_TS - e["ts"] < 7 * DAY_S and major(e.get("v")) == major(VERSION)}
        for c in picks[g]:
            if c["id"] in seen:
                continue
            log.append({"ts": NOW_TS, "v": VERSION, "id": c["id"], "sym": c["sym"], "sec": c["sec"], "g": g, "px": c["px"],
                        "stop": rnd6(c["ma20"]), "r7": None, "x7": None, "r30": None, "x30": None, "inv": None})
            if g == "top":
                new_top.append(c)
    for e in log:
        c, s = coins.get(e["id"]), secs.get(e.get("sec"))
        if not c or not c.get("px"):
            continue
        age = NOW_TS - e["ts"]
        if e.get("inv") is None and e.get("stop") and c["px"] < e["stop"] * 0.97:
            e["inv"] = NOW_TS
        if e.get("r7") is None and age >= 7 * DAY_S:
            e["r7"] = pct(c["px"], e["px"])
            if s and e["r7"] is not None:
                e["x7"] = e["r7"] - s["m7"]
        if e.get("r30") is None and age >= 30 * DAY_S:
            e["r30"] = pct(c["px"], e["px"])
            if s and e["r30"] is not None:
                e["x30"] = e["r30"] - s["m30"]
    return log[-8000:], new_top


def scoreboard(log):
    cur = [e for e in log if major(e.get("v")) == major(VERSION)]
    out = {"old": len(log) - len(cur), "lists": []}
    for g, name in LOG_LISTS:
        done = [e for e in cur if e["g"] == g and e.get("x7") is not None]
        out["lists"].append({"g": g, "n": name, "total": sum(1 for e in cur if e["g"] == g), "n7": len(done),
                             "win7": sum(1 for e in done if e["x7"] > 0) / len(done) * 100 if done else None,
                             "med7": med(e["x7"] for e in done), "avg7": statistics.mean(e["x7"] for e in done) if done else None})
    return out


def telegram(new_top):
    if not (TG_TOKEN and TG_CHAT) or not new_top:
        return None
    lines = []
    for c in new_top:
        lines.append(f"🟣 Top 3 진입: {c['sym']} ({c['sec']})\n7일 {c['c7']:+.1f}% · 30일 {c['c30']:+.1f}%\n"
                     f"무효: 20일선 {c['ma20']:.6g} 아래 마감 시" if c.get("ma20") else f"🟣 Top 3 진입: {c['sym']}")
    if PAGE_URL:
        lines.append(f"전체 보기: {PAGE_URL}")
    try:
        get_json(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", method="POST",
                 body={"chat_id": TG_CHAT, "text": "\n\n".join(lines), "disable_web_page_preview": True}, retries=2)
        return None
    except Exception as e:
        return f"텔레그램 전송 실패: {type(e).__name__}"


# ═════════════════════════ 페이지 ═════════════════════════
COIN_KEYS = ["id", "sym", "name", "sec", "secs", "px", "mc", "vol", "c1", "c3", "c7", "c30", "c180", "ma20", "ma60", "ma100", "ma200",
             "hi30", "brk", "slope", "hl", "rc", "vx", "spark", "ma20line", "z30", "z7", "srank", "sn", "mrank", "L", "fund", "oi", "sh",
             "upx", "ex20", "uwarn", "under", "a20", "cvol", "cfirst", "sq", "sqn", "squeeze", "warns", "fatal", "hard", "sig", "nsig",
             "score", "pull", "pullmiss", "reclaim", "kept", "run", "offpk", "tp", "tv", "src", "listwhy", "topRank"]


def slim(c):
    out = {}
    for k in COIN_KEYS:
        v = c.get(k)
        if isinstance(v, float):
            v = rnd6(v)
        out["s" if k == "sym" else k] = v
    return out


def render(D):
    data = json.dumps(D, ensure_ascii=False, separators=(",", ":"), default=lambda o: None).replace("</", "<\\/")
    sections = "".join(f'<section role="tabpanel" id="p-{k}"{"" if k == "home" else " hidden"}></section>'
                       for k in ["home", "early", "small", "pull", "list", "sec", "mkt", "bt", "chk"])
    invite = (f'<a class="tg" href="{html.escape(TG_INVITE)}" target="_blank" rel="noopener">텔레그램 알림방 입장</a>' if TG_INVITE else "")
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="color-scheme" content="dark">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>섹터 모니터 v{VERSION}</title><style>{CSS}</style></head><body>
<div class="wrap">
 <div class="head"><h1>섹터 모니터</h1><span class="ver">v{VERSION}</span>{invite}
  <div class="search" role="search"><input id="q" type="search" placeholder="코인 검색 (심볼·이름)" aria-label="코인 검색" autocomplete="off"><div class="sres" id="sres" role="listbox"></div></div></div>
 <p class="regime" id="regime"></p>
 <div class="bar"><div class="tabs" role="tablist" id="tabs"></div><div class="filt" id="filt"></div></div>
 {sections}
 <footer id="foot"></footer></div>
<dialog id="dlg" aria-label="코인 상세"><div class="dl" id="dlb"></div></dialog>
<script>const D={data};
{JS}</script></body></html>"""


# ═════════════════════════ 실행 ═════════════════════════
def main():
    t0 = time.time()
    now = dt.datetime.fromtimestamp(NOW_TS, KST)
    today = now.strftime("%Y-%m-%d")
    yday_utc = utc_day(NOW_TS - DAY_S)
    errors, src = [], {}

    state = load(os.path.join(DATA_DIR, "state.json"), {})
    if "flags" not in state and "top" not in state:   # 2.0 state → 3.0
        state = {"started": state.get("started", NOW_TS)}
    state.setdefault("started", NOW_TS)
    state.setdefault("coin_oi", [])
    log = load(os.path.join(DATA_DIR, "log.json"), [])
    cache = load(os.path.join(CACHE_DIR, "cache.json"), {})
    candles = load(os.path.join(CACHE_DIR, "candles.json"), {})   # 용량이 커서 git 대신 Actions 캐시에 보관
    glob_hist = load(os.path.join(DATA_DIR, "global.json"), [])
    uhist = load(os.path.join(DATA_DIR, "upbit.json"), {})

    def safe(label, fn, default, key=None):
        try:
            r = fn()
            if key:
                src[key] = ["ok", ""]
            return r
        except Exception as e:
            msg = f"{type(e).__name__} {str(e)[:90]}"
            errors.append(f"{label}: {msg}")
            if key:
                src[key] = ["fail", msg]
            return default

    def daily(key):
        return NOW_TS - cache.get(key, 0) >= DAY_S - 1800

    # 1) 가격 (매 실행)
    markets = mock_markets() if MOCK else safe("시총 상위 1000개", fetch_markets, None, "CoinGecko 가격")
    if markets:
        cache["markets"], cache["mk_ts"] = markets, NOW_TS
    else:
        markets = cache.get("markets") or {}
        errors.append("가격을 받지 못해 지난 값으로 표시합니다")
    if not markets:   # 처음 실행인데 가격을 못 받음 → 안내 페이지만 만들고 종료 (다음 실행에서 재시도)
        os.makedirs(SITE_DIR, exist_ok=True)
        with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write('<!doctype html><meta charset="utf-8"><meta name="color-scheme" content="dark"><body style="background:#1e1e1e;color:#ddd;font-family:sans-serif;padding:24px">'
                    f'<h1>섹터 모니터 v{VERSION}</h1><p>가격 데이터를 받지 못했습니다. 다음 실행(2시간 뒤)에 다시 시도합니다.</p><ul>'
                    + "".join(f"<li>{html.escape(e)}</li>" for e in NOTES + errors) + "</ul>")
        print("가격 데이터 없음:", NOTES + errors)
        return
    # 2) 섹터 구성 (하루 1번)
    if MOCK:
        cache["sec_ids"] = mock_sector_ids()
    elif daily("sec_ts") or not cache.get("sec_ids"):
        cl = safe("카테고리 목록", fetch_catlist, None)
        if cl:
            ids, missing = resolve_ids(cl)
            new = {}
            for s in SECTORS:
                if s["key"] in ids:
                    r = safe(f"섹터 {s['name']}", lambda c=ids[s["key"]]: fetch_category_ids(c), None)
                    if r is not None:
                        new[s["key"]] = r
            if new:
                old = cache.get("sec_ids") or {}
                old.update(new)
                cache["sec_ids"], cache["sec_ts"], cache["missing"] = old, NOW_TS, missing
                src["CoinGecko 섹터"] = ["ok", f"{len(new)}개 섹터"]
    sec_ids = cache.get("sec_ids") or {}
    if cache.get("missing"):
        errors.append("CoinGecko에서 찾지 못한 섹터: " + ", ".join(cache["missing"]))
    want = {i for s in SECTORS for i in (s.get("ids") or sec_ids.get(s["key"], []))}
    extra = sorted(want - set(markets))
    if extra and not MOCK:
        more = safe("상위 1000위 밖 섹터 코인", lambda: fetch_markets_ids(extra), {})
        markets.update(more)
    # 3) 전체 시총·도미넌스 (매 실행, 60일 보관)
    g = mock_global() if MOCK else safe("전체 시총", fetch_global, None, "CoinGecko 도미넌스")
    if g and g.get("total"):
        glob_hist = [r for r in glob_hist if NOW_TS - r["ts"] <= 62 * DAY_S] + [{"ts": NOW_TS, **g}]
    # 4) 선물 (매 실행)
    tracked = {i for i in want if i in markets and i != "bitcoin" and not excluded(markets[i]) and markets[i]["mc"] >= TH["minor_mcap"]}
    derivs = {}
    if MOCK:
        derivs = mock_derivs(markets)
    else:
        wanted = {markets[i]["sym"] for i in tracked}
        for ex, fn in FETCHERS.items():
            r = safe(f"{ex} 선물", lambda f=fn: f(wanted), None, f"{ex} 선물")
            if r:
                derivs[ex] = r
    # 5) 상장 거래소 (하루 1번)
    if MOCK:
        cache["listing"] = mock_listing(markets)
    elif daily("list_ts") or not cache.get("listing"):
        new = {}
        for v, ex in LIST_VENUES.items():
            r = safe(f"{v} 상장 목록", lambda e=ex: fetch_listing(e), None, f"{v} 상장 목록")
            if r:
                new[v] = r
        if new:
            old = cache.get("listing") or {}
            old.update(new)
            cache["listing"], cache["list_ts"] = old, NOW_TS
    listing = {v: set(d.get("ids", [])) for v, d in (cache.get("listing") or {}).items()}
    # 6) 업비트 마켓·빗썸·상장 공지 (하루 1번)
    if MOCK:
        cache["upb_mk"], cache["bithumb"] = mock_upbit_markets(markets), []
        cache["news"] = [{"d": today, "ex": "업비트", "t": "[거래] 모의 코인(MOCK) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)", "u": "https://upbit.com"}]
    elif daily("kr_ts") or not cache.get("upb_mk"):
        um = safe("업비트 마켓", fetch_upbit_markets, None, "업비트 마켓")
        if um:
            cache["upb_mk"] = um
        bt = safe("빗썸 상장 목록", fetch_bithumb, None, "빗썸")
        if bt:
            cache["bithumb"] = bt
        news = safe("업비트 공지", fetch_upbit_notices, [], "업비트 공지") + safe("바이낸스 공지", fetch_binance_notices, [], "바이낸스 공지")
        if news:
            cache["news"] = sorted(news, key=lambda n: n["d"], reverse=True)[:12]
        if um:
            cache["kr_ts"] = NOW_TS   # 실패하면 다음 실행에서 다시 시도
    # 7) 업비트 원화 거래대금 (매 실행, 하루 1칸)
    krw = ((cache.get("listing") or {}).get("Upbit") or {}).get("krw") or {}
    upb_now = {} if MOCK else (safe("업비트 거래대금", lambda: fetch_upbit_krw(krw), {}, "업비트 거래대금") if krw else {})
    if MOCK:
        upb_now = {i: markets[i]["vol"] * 1300 * random.Random(i + today).uniform(0.02, 0.3) for i in listing.get("Upbit", [])}
    for i, v in upb_now.items():
        if v:
            uhist[i] = ([x for x in uhist.get(i, []) if x[0] != today] + [[today, v]])[-8:]
    upx = {}
    for i, h in uhist.items():
        prev = [v for d, v in h if d != today]
        cur = next((v for d, v in h if d == today), None)
        if cur and len(prev) >= 4 and statistics.mean(prev) > 0:
            upx[i] = cur / statistics.mean(prev)
    # 8) 거래소 일봉 (하루 1번, 마감된 봉만)
    need = [i for i in sorted(tracked | ({"bitcoin"} & set(markets)), key=lambda i: -markets[i]["mc"]) if (candles.get(i) or {}).get("d", [""])[-1:] != [yday_utc]]
    got = fails = cg_used = 0
    cg_err = None
    for i in need:
        if time.time() - t0 > 11 * 60:
            errors.append(f"시간 제한으로 일봉 {len(need) - got - fails}개는 다음 실행에서 받습니다")
            break
        if MOCK:
            cd = mock_candles(i)
        else:
            cd = fetch_candles(markets[i])
            if not cd and cg_used < CG_CANDLE_BUDGET:
                cg_used += 1
                try:
                    cd = fetch_cg_candles(i)
                except Exception as e:
                    cd, cg_err = None, f"{type(e).__name__} {str(e)[:60]}"
        if cd:
            candles[i], got = cd, got + 1
        else:
            fails += 1
    candles = {i: v for i, v in candles.items() if i in tracked or i == "bitcoin"}
    if need:
        src["거래소 일봉"] = ["ok" if got else "fail", f"새로 받음 {got} · 실패 {fails} · CoinGecko 대체 {cg_used}"]
        if fails:
            errors.append(f"일봉을 받지 못한 코인 {fails}개 (Bitget·OKX 미상장이고 CoinGecko 대체 한도 초과 또는 실패{': ' + cg_err if cg_err else ''})")
    # 9) 코인별 OI 24시간 전
    snap = {}
    for i in tracked:
        c = markets[i]
        oi = sum(d[c["sym"]]["oi"] for d in derivs.values() if c["sym"] in d and px_match(d[c["sym"]]["px"], c["px"]))
        if oi:
            snap[i] = oi
    prev = min(state["coin_oi"], key=lambda h: abs(h["ts"] - (NOW_TS - DAY_S)), default=None)
    oi_prev = prev["oi"] if prev and abs(prev["ts"] - (NOW_TS - DAY_S)) <= 3 * 3600 else {}
    state["coin_oi"] = [h for h in state["coin_oi"] if NOW_TS - h["ts"] <= 30 * 3600] + [{"ts": NOW_TS, "oi": snap}]
    # 10) 상위 20개 거래소 중 상장 수 (하루 예산 안에서, 코인당 7일마다 갱신)
    ex20c = cache.get("ex20") or {}
    if MOCK:
        top20 = [f"ex{i}" for i in range(20)]
        for i in tracked:
            ex20c[i] = [NOW_TS, [f"ex{k}" for k in range(20) if random.Random(i + str(k)).random() < 0.55]]
    else:
        if daily("top20_ts") or not cache.get("top20"):
            t20 = safe("거래소 순위", fetch_top_exchanges, None, "거래소 순위")
            if t20:
                cache["top20"], cache["top20_ts"] = t20, NOW_TS
        top20 = [x["id"] for x in cache.get("top20") or []]
        order = [i for i in (state.get("shown") or []) if i in tracked] + sorted(tracked, key=lambda i: -markets[i]["mc"])
        todo = [i for i in dict.fromkeys(order) if NOW_TS - (ex20c.get(i) or [0])[0] > 7 * DAY_S][:TICKER_BUDGET // 12 + 1]
        for i in todo:
            r = safe(f"{markets[i]['sym']} 거래소 목록", lambda c=i: fetch_coin_exchanges(c), None)
            if r is not None:
                ex20c[i] = [NOW_TS, r]
    cache["ex20"] = {i: v for i, v in ex20c.items() if i in tracked}
    ex20 = {i: len(set(v[1]) & set(top20)) for i, v in cache["ex20"].items()} if top20 else {}

    # 11) 판정 (숏 계정 비율은 후보만 추가로 받고 다시 계산)
    args = dict(markets=markets, sec_ids=sec_ids, candles=candles, derivs=derivs, listing=listing, upx=upx, oi_prev=oi_prev,
                ex20=ex20, upb_mk=cache.get("upb_mk") or {}, bithumb=set(cache.get("bithumb") or []), prev_state=state)
    W = build_world(short={}, **args)
    sq_c = sorted([c for c in W["coins"].values() if c["fund"] is not None and c["sqn"] >= 2], key=lambda c: -c["sqn"])[:30]
    short, sfail = {}, 0
    for c in sq_c:
        if MOCK:
            short[c["id"]] = random.Random(c["id"] + "sh").uniform(40, 65)
            continue
        try:
            r = fetch_short_ratio(re.sub(r"[^A-Z0-9]", "", c["sym"]))
            if r is not None:
                short[c["id"]], sfail = r, 0
        except Exception as e:
            sfail += 1
            if sfail >= 3 and not short:   # 연속 실패면 이번 실행은 건너뜀 (오류 한 줄만)
                errors.append(f"Bitget 롱숏 비율: {type(e).__name__} {str(e)[:80]}")
                src["Bitget 롱숏 비율"] = ["fail", type(e).__name__]
                break
        time.sleep(0.1)
    if short:
        src["Bitget 롱숏 비율"] = ["ok", f"{len(short)}개"]
    if short:
        W = build_world(short=short, **args)
    M = market_view(W, markets, candles, glob_hist, candles.get("bitcoin"))

    # 12) CMC 교차 확인 (하루 1번 요약)
    if CMC_KEY and not MOCK and (daily("cmc_ts") or not cache.get("cmc_sum")):
        cm = safe("CoinMarketCap", fetch_cmc, None, "CoinMarketCap")
        if cm:
            cache["cmc_sum"], cache["cmc_ts"] = cmc_summary(W["coins"], cm), NOW_TS
    if not CMC_KEY and not MOCK:
        src["CoinMarketCap"] = ["skip", "CMC_API_KEY 없음"]

    # 13) 기록·알림
    log, new_top = update_log(log, W)
    tg = telegram(new_top)
    if tg:
        errors.append(tg)
    state.update(W["state"])
    shown = [c["id"] for c in W["top"] + W["early"] + W["small"] + W["listc"]]
    shown += [i for i, c in sorted(W["coins"].items(), key=lambda kv: -(kv[1]["c7"] or 0))[:15]]
    state["shown"] = list(dict.fromkeys(shown))[:80]

    D = {"v": VERSION, "asof": now.strftime("%Y-%m-%d %H:%M"), "cday": yday_utc, "th": TH,
         "coins": [slim(c) for c in W["coins"].values()], "secs": list(W["secs"].values()),
         "top": [c["id"] for c in W["top"]], "early": [c["id"] for c in W["early"]], "small": [c["id"] for c in W["small"]],
         "listc": [c["id"] for c in W["listc"]], "changes": W["changes"], "mk": W["mk"],
         "excluded": sum(1 for c in W["coins"].values() if c["fatal"]), **M,
         "board": scoreboard(log), "bt": load(os.path.join(DATA_DIR, "backtest.json"), None),
         "news": cache.get("news") or [], "cmc": cache.get("cmc_sum"), "top20": [x["name"] for x in cache.get("top20") or []],
         "src": src, "errors": NOTES + errors, "invite": TG_INVITE, "calls": CALLS["cg"],
         "changelog": CHANGELOG, "rule": VERSION_RULE, "credit": CREDIT, "subtitle": SUBTITLE, "released": RELEASED}
    for s in D["secs"]:
        s.pop("_pri", None)
    page = render(D)

    save(os.path.join(DATA_DIR, "state.json"), state)
    save(os.path.join(DATA_DIR, "log.json"), log)
    save(os.path.join(CACHE_DIR, "candles.json"), candles)
    save(os.path.join(DATA_DIR, "global.json"), glob_hist)
    save(os.path.join(DATA_DIR, "upbit.json"), uhist)
    save(os.path.join(CACHE_DIR, "cache.json"), cache)
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"완료 v{VERSION} {now:%Y-%m-%d %H:%M} | 추적 {len(W['coins'])} | Top {len(W['top'])} | 초입 {len(W['early'])} | "
          f"소형 {len(W['small'])} | 상장 후보 {len(W['listc'])} | 섹터 {len(W['secs'])} | CoinGecko 호출 {CALLS['cg']} | {time.time() - t0:.0f}초")
    for e in NOTES + errors:
        print(" -", e)


CSS = r"""
:root{--bg:#ffffff;--bg2:#f6f6f7;--bg3:#ececef;--line:#e0e0e4;--text:#1f1f22;--muted:#5b5b63;--faint:#8b8b93;
--accent:#7652e8;--accent-bg:rgba(118,82,232,.08);--accent-line:rgba(118,82,232,.45);
--up:#17895a;--down:#c9463c;--amber:#a8730f;--amber-bg:rgba(168,115,15,.09);--info:#2e6db0;--info-bg:rgba(46,109,176,.08)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1e1e1e;--bg2:#262626;--bg3:#303030;--line:#383838;--text:#dcddde;--muted:#a3a3a3;--faint:#767676;
--accent:#a88bfa;--accent-bg:rgba(168,139,250,.11);--accent-line:rgba(168,139,250,.5);
--up:#5cc99a;--down:#e5776e;--amber:#e3b25c;--amber-bg:rgba(227,178,92,.11);--info:#78b0e6;--info-bg:rgba(110,168,224,.11)}}
:root[data-theme="dark"]{--bg:#1e1e1e;--bg2:#262626;--bg3:#303030;--line:#383838;--text:#dcddde;--muted:#a3a3a3;--faint:#767676;
--accent:#a88bfa;--accent-bg:rgba(168,139,250,.11);--accent-line:rgba(168,139,250,.5);
--up:#5cc99a;--down:#e5776e;--amber:#e3b25c;--amber-bg:rgba(227,178,92,.11);--info:#78b0e6;--info-bg:rgba(110,168,224,.11)}
:root{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
html{scroll-padding-top:env(safe-area-inset-top,0px);-webkit-text-size-adjust:100%}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 "Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:18px 16px 60px}
a{color:var(--info)}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--down)}.na{color:var(--faint)}.sm{font-size:.8rem}
/* 머리 */
.head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.head h1{font-size:1.45rem;margin:0;letter-spacing:-.02em}
.ver{font-size:.75rem;color:var(--accent);background:var(--accent-bg);padding:1px 8px;border-radius:999px}
.mock{font-size:.75rem;color:var(--amber);background:var(--amber-bg);padding:2px 8px;border-radius:4px}
.search{margin-left:auto;position:relative;flex:1 1 200px;max-width:280px}
.search input{width:100%;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg2);color:var(--text);font:inherit;font-size:.9rem}
.sres{position:absolute;top:100%;left:0;right:0;z-index:30;background:var(--bg);border:1px solid var(--line);border-radius:8px;margin-top:4px;max-height:320px;overflow:auto;display:none}
.sres button{display:flex;width:100%;gap:8px;align-items:baseline;padding:8px 10px;border:0;background:none;text-align:left;cursor:pointer}
.sres button:hover,.sres button:focus{background:var(--bg2)}
/* 국면 한 줄 */
.regime{margin:14px 0 0;padding:10px 12px;border-left:3px solid var(--accent);background:var(--bg2);border-radius:0 8px 8px 0}
.regime b{font-weight:650}
.regime .sub{display:block;font-size:.8rem;color:var(--muted);margin-top:2px}
/* 탭 + 필터 (고정) */
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:20;background:var(--bg);margin:12px -16px 0;padding:0 16px;border-bottom:1px solid var(--line)}
.tabs{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs button{flex:none;border:0;background:none;padding:10px 11px 9px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;font-size:.92rem;white-space:nowrap}
.tabs button[aria-selected="true"]{color:var(--text);border-bottom-color:var(--accent);font-weight:600}
.tabs .c{font-size:.72rem;color:var(--faint);margin-left:3px}
.filt{display:flex;gap:6px 14px;align-items:center;flex-wrap:wrap;padding:7px 0 9px;font-size:.84rem;color:var(--muted)}
.filt label{display:inline-flex;align-items:center;gap:4px;cursor:pointer;color:var(--text)}
.filt input{accent-color:var(--accent);width:15px;height:15px;margin:0}
.filt .hid{margin-left:auto;color:var(--faint);font-size:.78rem}
section[role="tabpanel"]{padding-top:16px}
h2{font-size:1.1rem;margin:0 0 4px;letter-spacing:-.01em}
h3{font-size:.95rem;margin:20px 0 6px}
.lead{color:var(--muted);font-size:.86rem;margin:0 0 12px;max-width:68ch}
details.rule{font-size:.82rem;color:var(--muted);margin:0 0 12px}
details.rule summary{cursor:pointer;color:var(--info)}
details.rule ul{margin:6px 0 0;padding-left:18px}
/* 칩 */
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.chip{font-size:.74rem;padding:1px 7px;border-radius:4px;background:var(--bg3);color:var(--faint);white-space:nowrap}
.chip.ok{background:var(--info-bg);color:var(--info)}
.chip.warn{background:var(--amber-bg);color:var(--amber)}
.chip.hot{background:var(--accent-bg);color:var(--accent)}
.ex{font-size:.7rem;padding:0 5px;border:1px solid var(--line);border-radius:3px;color:var(--muted)}
.ex.off{opacity:.35;text-decoration:line-through}
.secchip{font-size:.76rem;color:var(--muted)}
/* 추천 카드 */
.picks{display:grid;gap:10px;grid-template-columns:1fr}
@media (min-width:760px){.picks{grid-template-columns:repeat(3,1fr)}}
.pick{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;border:1px solid var(--accent-line);border-radius:10px;padding:12px;cursor:pointer;background:var(--bg);text-align:left;width:100%}
.pick:hover{background:var(--accent-bg)}
.pick .t{display:flex;align-items:baseline;gap:6px}
.pick .rk{font-size:.75rem;color:var(--accent);font-weight:700}
.pick .sym{font-size:1.15rem;font-weight:700}
.pick .rt{display:flex;gap:10px;font-size:.84rem;margin-top:4px}
.pick .why{font-size:.82rem;color:var(--muted);margin:6px 0 0}
.pick .stop{font-size:.78rem;color:var(--faint);margin-top:6px}
.empty{padding:16px;border:1px dashed var(--line);border-radius:8px;color:var(--muted);font-size:.88rem}
/* 코인 표 */
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th{font-weight:500;color:var(--faint);font-size:.76rem;text-align:right;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th button{border:0;background:none;color:inherit;cursor:pointer;padding:0;font-size:inherit}
th button[aria-sort]{color:var(--text)}
td{padding:8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top;white-space:nowrap}
tr:last-child td{border-bottom:0}
tr.row{cursor:pointer}tr.row:hover td{background:var(--bg2)}
td .nm{font-weight:650}
td .chips{margin-top:3px;max-width:340px;white-space:normal}
.vbar{display:inline-block;width:44px;height:6px;background:var(--bg3);border-radius:3px;vertical-align:middle;margin-left:5px;overflow:hidden}
.vbar i{display:block;height:100%;background:var(--info)}
.tog{display:inline-flex;gap:6px;align-items:center;font-size:.84rem;margin:0 0 10px;cursor:pointer}
.tog input{accent-color:var(--accent)}
/* 이평 사다리 */
.ladder{position:relative;height:40px;margin:6px 0 2px;min-width:220px}
.ladder .ln{position:absolute;left:0;right:0;top:20px;height:1px;background:var(--line)}
.ladder .m{position:absolute;top:13px;width:1px;height:15px;background:var(--faint)}
.ladder .m span{position:absolute;top:-14px;left:50%;transform:translateX(-50%);font-size:.66rem;color:var(--faint);white-space:nowrap}
.ladder .m.sup{background:var(--info);width:2px}
.ladder .m.sup span{color:var(--info);font-weight:600}
.ladder .p{position:absolute;top:15px;width:11px;height:11px;margin-left:-5px;border-radius:50%;background:var(--text);border:2px solid var(--bg)}
.ladder .p span{position:absolute;top:13px;left:50%;transform:translateX(-50%);font-size:.66rem;white-space:nowrap;font-weight:600}
.pl{display:grid;gap:10px}
.pc{border:1px solid var(--line);border-radius:10px;padding:10px 12px;cursor:pointer;background:var(--bg);width:100%;text-align:left}
.pc:hover{background:var(--bg2)}
.pc .t{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.state{font-size:.78rem;font-weight:600;padding:1px 7px;border-radius:4px}
.state.hold{color:var(--info);background:var(--info-bg)}.state.lost{color:var(--down);background:var(--bg3)}.state.turn{color:var(--accent);background:var(--accent-bg)}.state.bounce{color:var(--amber);background:var(--amber-bg)}
/* 섹터 */
.sec{display:grid;grid-template-columns:28px 1fr;gap:0 8px;padding:9px 0;border-bottom:1px solid var(--line)}
.sec .n{color:var(--faint);font-size:.82rem;padding-top:2px;text-align:right}
.sec .h{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.sec .nm{font-weight:650}
.sbar{height:5px;background:var(--bg3);border-radius:3px;margin:5px 0 0;max-width:420px;overflow:hidden}
.sbar i{display:block;height:100%;background:var(--faint)}
.sec.top .sbar i{background:var(--accent)}
.tagtop{font-size:.72rem;color:var(--accent)}
/* 시장 */
.grid2{display:grid;gap:14px;grid-template-columns:1fr}
@media (min-width:760px){.grid2{grid-template-columns:1fr 1fr}}
.box{border:1px solid var(--line);border-radius:10px;padding:12px}
.box h3{margin:0 0 8px}
.kv{display:flex;justify-content:space-between;gap:10px;font-size:.88rem;padding:4px 0;border-bottom:1px dashed var(--line)}
.kv:last-child{border-bottom:0}
.gauge{position:relative;height:10px;border-radius:5px;background:linear-gradient(90deg,var(--bg3) 0 25%,var(--bg2) 25% 75%,var(--accent-bg) 75%);border:1px solid var(--line);margin:22px 0 6px}
.gauge i{position:absolute;top:-6px;width:3px;height:20px;background:var(--text);border-radius:2px}
.gauge span{position:absolute;top:-22px;transform:translateX(-50%);font-size:.78rem;font-weight:700}
.gl{display:flex;justify-content:space-between;font-size:.72rem;color:var(--faint)}
.tier{display:grid;grid-template-columns:62px 1fr 56px;gap:8px;align-items:center;font-size:.85rem;padding:4px 0}
.tier .b{height:8px;position:relative;background:var(--bg2);border-radius:2px}
.tier .b i{position:absolute;top:0;height:100%;border-radius:2px}
.tier .b::after{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--faint)}
/* 성적표 */
.score{padding:12px 0;border-bottom:1px solid var(--line)}
.score .h{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.score p{margin:4px 0 0;font-size:.88rem;max-width:70ch}
.flip{position:relative;height:8px;background:var(--bg3);border-radius:4px;margin:10px 0 2px;max-width:420px}
.flip i{position:absolute;left:0;top:0;height:100%;border-radius:4px;background:var(--info)}
.flip b{position:absolute;left:50%;top:-4px;bottom:-4px;width:2px;background:var(--text)}
.verdict{font-size:.76rem;font-weight:600;padding:1px 7px;border-radius:4px}
.v-ok{color:var(--up);background:var(--bg3)}.v-hold{color:var(--amber);background:var(--amber-bg)}.v-no{color:var(--down);background:var(--bg3)}
/* 상세 시트 */
dialog{border:0;padding:0;width:min(560px,100%);max-height:88vh;border-radius:14px;background:var(--bg);color:var(--text);box-shadow:0 10px 40px rgba(0,0,0,.35)}
dialog::backdrop{background:rgba(0,0,0,.45)}
@media (max-width:600px){dialog{margin:auto 0 0;border-radius:14px 14px 0 0;max-width:100%}}
.dl{padding:16px 16px calc(16px + env(safe-area-inset-bottom,0px));overflow:auto;max-height:88vh}
.dl .top{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.dl .top b{font-size:1.3rem}
.dl .x{margin-left:auto;border:0;background:var(--bg2);border-radius:6px;padding:4px 10px;cursor:pointer}
.dl h4{font-size:.82rem;color:var(--muted);font-weight:600;margin:14px 0 4px}
.dl .links{display:flex;gap:8px;margin-top:14px}
.dl .links a{flex:1;text-align:center;padding:9px;border-radius:8px;background:var(--bg2);text-decoration:none;font-size:.88rem}
.dl .links a.pri{background:var(--accent);color:#fff}
/* 하단 */
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);font-size:.8rem;color:var(--muted)}
footer table{font-size:.8rem}
footer td{white-space:normal}footer td:last-child{white-space:nowrap}
@media (prefers-reduced-motion:no-preference){.pick,.pc,tr.row td{transition:background .15s}}
.tg{display:inline-flex;align-items:center;gap:5px;font-size:.8rem;padding:4px 10px;border-radius:999px;background:var(--info-bg);color:var(--info);text-decoration:none}
.eg{font-size:.66rem;color:var(--amber);border:1px solid currentColor;border-radius:3px;padding:0 3px;margin-left:3px;vertical-align:1px;font-style:normal}
svg.spark{flex:none;vertical-align:middle;overflow:visible}
svg.spark .p{fill:none;stroke-width:1.6;stroke-linejoin:round}
svg.spark .m{fill:none;stroke:var(--faint);stroke-width:1;stroke-dasharray:2 2}
.sp-up .p{stroke:var(--up)}.sp-dn .p{stroke:var(--down)}
.pick .t svg.spark{margin-left:auto}
td.sp{width:96px}
/* 구간 색 사다리 */
.zl{position:relative;height:46px;margin:8px 0 2px;min-width:230px}
.zl .z{position:absolute;top:14px;height:14px;border-radius:2px;opacity:.9}
.z0{background:color-mix(in srgb,var(--up) 50%,transparent)}
.z1{background:color-mix(in srgb,var(--amber) 50%,transparent)}
.z2{background:color-mix(in srgb,var(--down) 45%,transparent)}
.zl .m{position:absolute;top:10px;width:2px;height:22px;background:var(--text)}
.zl .m span{position:absolute;top:-13px;left:50%;transform:translateX(-50%);font-size:.66rem;color:var(--muted);white-space:nowrap}
.zl .p{position:absolute;top:15px;width:12px;height:12px;margin-left:-6px;border-radius:50%;background:var(--accent);border:2px solid var(--bg)}
.zl .p span{position:absolute;top:13px;left:50%;transform:translateX(-50%);font-size:.66rem;white-space:nowrap;font-weight:700;color:var(--accent)}
.zleg{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:.72rem;color:var(--muted)}
.zleg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.tvb{display:inline-block;font-size:.72rem;padding:2px 7px;border-radius:4px;background:var(--bg3);color:var(--text);text-decoration:none;white-space:nowrap}
.tvb:hover{background:var(--accent-bg);color:var(--accent)}
.ctl{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 10px;font-size:.82rem;color:var(--muted)}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
.seg button{border:0;background:none;padding:4px 9px;cursor:pointer;font-size:.8rem;color:var(--muted)}
.seg button[aria-pressed="true"]{background:var(--accent-bg);color:var(--accent);font-weight:600}
details.sd>summary{list-style:none;cursor:pointer}
details.sd>summary::-webkit-details-marker{display:none}
details.sd[open] .sec{border-bottom:0}
.slist{margin:0 0 10px 36px;border-left:2px solid var(--line);padding-left:10px}
.slist .r{display:flex;align-items:center;gap:8px;padding:5px 0;font-size:.84rem;border-bottom:1px dashed var(--line)}
.slist .r:last-child{border-bottom:0}
.slist .r b{min-width:74px}
.slist .r .g{margin-left:auto;display:flex;gap:10px;align-items:center}
.chg{font-size:.85rem;padding:6px 0;border-bottom:1px dashed var(--line)}
.chg b{margin-right:6px}
.alert{border:1px solid var(--amber);background:var(--amber-bg);border-radius:8px;padding:10px 12px;font-size:.86rem;margin:0 0 14px}

.tiers{display:grid;gap:6px}
.tr{display:grid;grid-template-columns:120px auto 1fr auto;gap:10px;align-items:center;padding:6px 0;border-bottom:1px dashed var(--line)}
.tr:last-child{border-bottom:0}
.tn{display:flex;flex-direction:column;line-height:1.3}
.tw{display:flex;gap:3px}
.wk{display:inline-block;width:38px;text-align:center;font-size:.72rem;padding:4px 0;border-radius:4px;font-variant-numeric:tabular-nums}
.tv{display:flex;flex-direction:column;font-size:.8rem;line-height:1.35}
@media (max-width:600px){.tr{grid-template-columns:1fr auto}.tv,.tl{grid-column:span 2}.tv{flex-direction:row;gap:10px}}

.hb{position:relative;display:inline-block;height:10px;background:var(--bg3);border-radius:5px;overflow:hidden;width:100%}
.hb i{position:absolute;left:0;top:0;height:100%;border-radius:5px}
.hb b{position:absolute;top:0;bottom:0;width:2px;background:var(--text)}
.hg{display:grid;grid-template-columns:auto 1fr 44px;gap:6px 10px;align-items:center;font-size:.84rem}
.hv{text-align:right}
.bh{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}.bh h3{margin:0}
.tb{display:grid;grid-template-columns:96px 1fr 150px auto;gap:10px;align-items:center;padding:7px 0;border-bottom:1px dashed var(--line)}
.tb:last-of-type{border-bottom:0}
.tbars{display:grid;gap:3px}.br{display:grid;grid-template-columns:1fr 56px;gap:6px;align-items:center;font-size:.78rem}
.db{position:relative;display:block;height:9px}.db i{position:absolute;top:0;height:100%;border-radius:2px}
.db::after{content:"";position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--faint)}
.tvx{display:grid;grid-template-columns:auto 1fr 40px;gap:6px;align-items:center}
.gauge.cg{background:linear-gradient(90deg,var(--amber) 0%,color-mix(in srgb,var(--amber) 40%,var(--bg3)) 25%,var(--bg3) 25%,var(--bg3) 75%,color-mix(in srgb,var(--accent) 50%,var(--bg3)) 75%,var(--accent) 100%)}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:6px}
.tile{display:flex;flex-direction:column;gap:2px;padding:8px;border-radius:8px;border:1px solid var(--line)}
.tile b{font-size:1rem}.tile.ok b{color:var(--up)}.tile.no b{color:var(--down)}
.rot{display:grid;grid-template-columns:1fr 48px;gap:8px;align-items:center}
.bt{display:grid;grid-template-columns:150px 1fr 40px 60px 34px minmax(0,1.3fr);gap:8px;align-items:center;padding:6px 0;border-bottom:1px dashed var(--line);font-size:.84rem}
.btn{display:flex;flex-direction:column;gap:2px}.bt .flip{margin:0}
@media (max-width:640px){.tb{grid-template-columns:80px 1fr}.tvx{grid-column:span 2}.bt{grid-template-columns:110px 1fr 40px 56px}.bt>.sm,.bt>.na{display:none}.hg{grid-template-columns:110px 1fr 40px}}

.steps{display:grid;grid-template-columns:repeat(8,1fr);gap:4px;margin-top:4px}
.st{position:relative;display:flex;flex-direction:column;gap:2px;padding:8px 6px 10px;border-radius:8px;background:var(--bg2);overflow:hidden;font-size:.74rem;line-height:1.3}
.st .dot{width:20px;height:20px;border-radius:50%;background:var(--bg3);display:grid;place-items:center;font-size:.72rem;font-weight:700}
.st .sn{font-weight:600;color:var(--muted)}.st .sa{color:var(--faint);font-size:.68rem}
.st i{position:absolute;left:0;bottom:0;height:3px;background:var(--faint)}
.st.on{background:var(--accent-bg);outline:1px solid var(--accent-line)}.st.on .dot{background:var(--accent);color:#fff}.st.on .sn{color:var(--text)}.st.on i{background:var(--accent)}
.st.nx{outline:1px dashed var(--accent-line)}.st.nx i{background:var(--accent-line)}
@media (max-width:700px){.steps{grid-template-columns:repeat(4,1fr)}}
.tier{display:grid;grid-template-columns:62px 1fr 56px;gap:8px;align-items:center;font-size:.85rem;padding:5px 0}
:root,:root[data-theme]{color-scheme:dark;--bg:#1e1e1e;--bg2:#262626;--bg3:#303030;--line:#383838;--text:#dcddde;--muted:#a3a3a3;--faint:#767676;--accent:#a88bfa;--accent-bg:rgba(168,139,250,.11);--accent-line:rgba(168,139,250,.5);--up:#5cc99a;--down:#e5776e;--amber:#e3b25c;--amber-bg:rgba(227,178,92,.11);--info:#78b0e6;--info-bg:rgba(110,168,224,.11)}
.z0{background:color-mix(in srgb,var(--up) 55%,transparent)}.z1{background:color-mix(in srgb,var(--up) 28%,transparent)}
.z2{background:color-mix(in srgb,var(--amber) 45%,transparent)}.z3{background:color-mix(in srgb,var(--down) 30%,transparent)}.z4{background:color-mix(in srgb,var(--down) 55%,transparent)}
footer details.rule h4{margin:10px 0 2px}
"""

JS = r""""use strict";
const TH=D.th;
const EXS=[["U","업비트"],["G","Bitget"],["O","OKX"],["B","Binance"]];
const SX={};D.secs.forEach(s=>SX[s.k]=s);
const C=D.coins;const CM={};C.forEach(c=>CM[c.id]=c);
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const f1=(v,d=1)=>v==null?"—":(v>0?"+":"")+v.toFixed(d)+"%";
const cls=v=>v==null?"na":v>0?"up":v<0?"dn":"";
const usd=v=>v==null?"—":v>=1e9?"$"+(v/1e9).toFixed(1)+"B":v>=1e6?"$"+Math.round(v/1e6)+"M":"$"+Math.round(v).toLocaleString();
const px=v=>v==null?"—":v>=100?v.toLocaleString("en-US",{maximumFractionDigits:1}):v>=1?v.toFixed(3):v>=.01?v.toFixed(4):v.toPrecision(4);
const chip=(t,k="")=>`<span class="chip ${k}">${esc(t)}</span>`;
const big$=v=>v==null?"—":v>=1e9?"$"+(v/1e9).toFixed(1)+"B":"$"+Math.round(v/1e6)+"M";
const OK=v=>v===true;

/* 거래소 필터 */
let EXON={U:true,G:true,O:true,B:true};
try{const v=JSON.parse(localStorage.getItem("charon-ex")||"null");if(v)EXON=v;}catch(e){}
const shown=c=>[...(c.L||"")].some(k=>EXON[k]);
const exBadges=c=>EXS.map(([k,n])=>(c.L||"").includes(k)?`<span class="ex">${n}</span>`:"").join(" ");
function tv(c){
  if(c.tv)return "https://www.tradingview.com/chart/?symbol="+encodeURIComponent(c.tv);
  const L=c.L||"",k=L.includes("G")?"BITGET":L.includes("O")?"OKX":L.includes("B")?"BINANCE":L.includes("U")?"UPBIT":null;
  return k?`https://www.tradingview.com/chart/?symbol=${k}:${c.s}${k==="UPBIT"?"KRW":"USDT"}`:`https://www.coingecko.com/en/coins/${c.id}`;}
const tvBtn=c=>`<a class="tvb" href="${tv(c)}" target="_blank" rel="noopener">차트</a>`;

/* 목록 */
const live=C.filter(c=>!c.fatal);
const byIds=ids=>(ids||[]).map(id=>CM[id]).filter(Boolean);
const TOP=byIds(D.top);
const EARLY=byIds(D.early),SMALL=byIds(D.small),LISTC=byIds(D.listc);
const PULL=live.filter(c=>c.pull).sort((a,b)=>({hold:0,wait:1,lost:2}[a.pull.st]-{hold:0,wait:1,lost:2}[b.pull.st])||b.pull.qn-a.pull.qn);
const NEAR=live.filter(c=>c.pullmiss).sort((a,b)=>a.pullmiss.length-b.pullmiss.length||a.hi30-b.hi30).slice(0,TH.near_max);
const RECL=live.filter(c=>c.reclaim).sort((a,b)=>(b.reclaim.st==="turn")-(a.reclaim.st==="turn")||b.reclaim.qn-a.reclaim.qn||b.mc-a.mc).slice(0,10);

/* 그림 */
function spark(c,w=88,h=24){
  const p=c.spark,m=c.ma20line||[];if(!p||p.length<2)return "";
  const all=p.concat(m);const lo=Math.min(...all),hi=Math.max(...all),r=hi-lo||1;
  const X=(i,n)=>(i/(n-1)*w).toFixed(1),Y=v=>(h-(v-lo)/r*h).toFixed(1);
  const pl=p.map((v,i)=>X(i,p.length)+","+Y(v)).join(" ");
  const off=p.length-m.length;const ml=m.map((v,i)=>X(i+off,p.length)+","+Y(v)).join(" ");
  return `<svg class="spark ${p[p.length-1]>=p[0]?"sp-up":"sp-dn"}" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="최근 30일 가격, 점선은 20일선"><polyline class="m" points="${ml}"/><polyline class="p" points="${pl}"/></svg>`;
}
const LEG=`<div class="zleg"><span class="na">← 높은 가격 · 낮은 가격 →</span><span><i class="z0"></i>모든 이평 위</span><span><i class="z1"></i></span><span><i class="z2"></i></span><span><i class="z3"></i></span><span><i class="z4"></i>모든 이평 아래</span></div>`;
function ladder(c,leg=true){
  const lv=[["20",c.ma20],["60",c.ma60],["100",c.ma100],["200",c.ma200]].filter(x=>x[1]);
  if(!lv.length||!c.px)return `<p class="sm na">일봉 기록이 부족합니다</p>`;
  const vals=lv.map(x=>x[1]).concat(c.px);const lo=Math.min(...vals)*.96,hi=Math.max(...vals)*1.04;
  const pos=v=>(hi-v)/(hi-lo)*100;
  const cuts=lv.map(x=>x[1]).sort((a,b)=>b-a);const edges=[hi,...cuts,lo];let z="";
  const zc=i=>Math.round(i*4/cuts.length);
  for(let i=0;i<edges.length-1;i++){const a=pos(edges[i]),b=pos(edges[i+1]);z+=`<div class="z z${zc(i)}" style="left:${a}%;width:${b-a}%"></div>`;}
  return `<div class="zl" role="img" aria-label="현재가와 이동평균선 위치">${z}${lv.map(([n,v])=>`<div class="m" style="left:${pos(v)}%"><span>${n}</span></div>`).join("")}<div class="p" style="left:${pos(c.px)}%"><span>현재</span></div></div>${leg?LEG:""}`;
}
const secTxt=c=>`<span class="secchip">${esc(SX[c.sec].n)} · 수익률 ${c.srank}/${c.sn}위 · 시총 ${c.mrank}위</span>`;
const vtxt=c=>c.vx==null?"—":`${c.vx.toFixed(1)}배<span class="vbar" aria-hidden="true"><i style="width:${Math.min(c.vx/3,1)*100}%"></i></span>`;
function badges(c){let b="";if(c.tp)b+=chip(c.tp[0]==="꺾임 주의"?"꺾임 주의":"익절 구간","warn");if(c.squeeze)b+=chip("스퀴즈 준비","hot");if(c.kept)b+=chip("유지 중","ok");return b;}
const warns=c=>(c.warns||[]).map(w=>chip(w,"warn")).join("");
const sigTxt=c=>`<div class="sm" style="white-space:normal;color:var(--info)" title="${c.sig.filter(x=>x[1]).map(x=>x[0]).join(", ")}">신호 ${c.nsig} · ${c.sig.filter(x=>x[1]&&x[0]!=="스퀴즈 준비").map(x=>x[0]).slice(0,3).join(" · ")}</div>`;
function stopTxt(c){
  for(const n of [20,60,100,200]){const v=c["ma"+n];if(v&&c.px>v)return `${n}일선 ${px(v)} 아래 마감`;}
  return "모든 이평선 아래 · 최근 저점 이탈";}
const nEx=c=>c.ex20==null?`<span class="na">—</span>`:`<span class="num">${c.ex20}<span class="na">/20</span></span>`;

/* 사이클 (팀 리더 조언 8단계) */
const B=D.btc||{};
const BT={up:B.up==null?null:B.up&&B.slopeUp,domDown:B.dom7==null?null:B.dom7<0,alt:B.alt,dd:B.dd};
const STAGES=[["BTC 상승","BTC 관찰·보유"],["메이저 알트 상승","알트 진입"],["알트 순환매","대장·테마 추적"],["알트 급등","수익실현 준비"],["알트 고점","매도"],["알트 급락","무리한 재진입 X"],["조정 후 BTC","BTC 매수"],["다음 사이클 준비","다음 파동 탐색"]];
function stageScores(){
  const y=D.cyc,T=Object.fromEntries((D.tiers||[]).map(t=>[t.n,t.m7])),r=D.disp&&D.disp.norm?D.disp.now/D.disp.norm:null;
  const bigT=((T["메이저"]||0)+(T["대형"]||0))/2,smT=((T["중형"]||0)+(T["마이너"]||0))/2;
  const A=BT.alt,has=A!=null;
  const q=(t,v)=>[t+(v==null?" (데이터 없음)":""),OK(v)];
  return [
   [q("BTC 상승 추세",BT.up),q("도미넌스 상승",BT.domDown==null?null:!BT.domDown),q("알트시즌 25 이하",has?A<=25:null),q("메이저가 가장 강함",bigT>smT)],
   [q("BTC 상승 추세",BT.up),q("도미넌스 하락",BT.domDown),q("메이저·대형이 중소형보다 강함",bigT>smT),q("알트시즌 25~50",has?A>25&&A<=50:null)],
   [q("중형·마이너가 더 강함",smT>bigT),q("섹터 순환 1.5배 이상",r==null?null:r>=1.5),q("알트시즌 40~75",has?A>=40&&A<75:null),q("7일 오른 코인 50% 이상",y.b7>=50)],
   [q("알트시즌 75 이상",has?A>=75:null),q("2배↑ 코인 20% 이상",y.hot>=20),q("30일 오른 코인 70% 이상",y.b30>=70)],
   [q("익절 구간 15% 이상",y.tp>=15),q("7일 오른 코인 1주 새 감소",y.b7<y.b7p-10),q("알트시즌 60 이상",has?A>=60:null)],
   [q("7일 오른 코인 30% 미만",y.b7<30),q("꺾인 코인 15% 이상",y.brk>=15),q("BTC 하락 추세 또는 도미넌스 상승",BT.up==null?null:(!BT.up||BT.domDown===false))],
   [q("BTC 고점 대비 −20% 이하",BT.dd==null?null:BT.dd<=-20),q("알트시즌 25 이하",has?A<=25:null),q("7일 오른 코인 30~50%",y.b7>=30&&y.b7<=50)],
   [q("BTC 50일선 회복",BT.up),q("알트시즌 25 이하",has?A<=25:null),q("섹터 순환 1배 미만",r==null?null:r<1)]];
}
function stageNow(){const S=stageScores(),fr=S.map(c=>c.filter(x=>x[1]).length/c.length);const cur=fr.indexOf(Math.max(...fr));
  return {S,fr,cur,nxt:cur+1<8&&fr[cur+1]>=.5?cur+1:null};}

/* 탭 */
const TABS=[["home","순위"],["early","초입 후보",()=>TOP.filter(shown).length+EARLY.filter(shown).length],["small","소형 도전",()=>SMALL.filter(shown).length],
 ["pull","눌림목",()=>PULL.filter(shown).length+NEAR.filter(shown).length+RECL.filter(shown).length],["list","상장",()=>LISTC.filter(shown).length],["sec","섹터"],["mkt","시장"],["bt","성적표"],["chk","데이터 점검"]];
let cur="home";
function renderTabs(){document.getElementById("tabs").innerHTML=TABS.map(([k,n,f])=>`<button role="tab" id="t-${k}" aria-controls="p-${k}" aria-selected="${k===cur}" data-tab="${k}">${n}${f?`<span class="c">${f()}</span>`:""}</button>`).join("");}
function go(k){cur=k;for(const [t] of TABS)document.getElementById("p-"+t).hidden=t!==k;renderTabs();const b=document.querySelector(".bar");if(window.scrollY>b.offsetTop)window.scrollTo({top:b.offsetTop});}
document.getElementById("tabs").addEventListener("click",e=>{const b=e.target.closest("[data-tab]");if(b)go(b.dataset.tab);});
function renderFilt(){const all=new Set([...TOP,...EARLY,...SMALL,...PULL,...RECL,...NEAR,...LISTC]);const hid=[...all].filter(c=>!shown(c)).length;
  document.getElementById("filt").innerHTML=`<span>현물 상장</span>`+EXS.map(([k,n])=>`<label><input type="checkbox" data-ex="${k}" ${EXON[k]?"checked":""}>${n}</label>`).join("")+`<span class="hid">${hid?`필터로 ${hid}개 숨김`:"체크한 곳 중 1곳 이상 상장"}</span>`;}
document.getElementById("filt").addEventListener("change",e=>{const k=e.target.dataset.ex;if(!k)return;EXON[k]=e.target.checked;try{localStorage.setItem("charon-ex",JSON.stringify(EXON));}catch(err){}renderAll();});

function renderRegime(){
  const top=D.secs.filter(s=>s.top).sort((a,b)=>a.rank-b.rank).map(s=>s.n);const st=stageNow();
  document.getElementById("regime").innerHTML=`<b>사이클 ${st.cur+1}단계: ${STAGES[st.cur][0]}</b> · 할 일 ${STAGES[st.cur][1]} · 뜨는 섹터 ${top.slice(0,3).join(", ")||"없음"} · 대장 <b>${D.lead.vol?D.lead.vol.s:"—"}</b><span class="sub">${D.asof} 갱신 · 이평선은 ${D.cday} 마감 봉 + 현재가</span>`;
}

/* 순위 */
let rk="c7";
function renderHome(){
  const per={c1:"1일",c7:"7일",c30:"30일",c180:"180일",sq:"숏 스퀴즈"};
  const seg=`<div class="ctl"><span class="seg">${Object.entries(per).map(([k,t])=>`<button data-rk="${k}" aria-pressed="${rk===k}">${t}</button>`).join("")}</span><span class="sm na">${rk==="sq"?"숏이 몰린 코인 · 신호 2개 이상":"가장 많이 오른 코인 15개"}</span></div>`;
  if(rk==="sq")return renderSq(seg);
  const rows=live.filter(c=>shown(c)&&c[rk]!=null).sort((a,b)=>b[rk]-a[rk]).slice(0,15);
  document.getElementById("p-home").innerHTML=seg+(rows.length?`<div class="tbl"><table><thead><tr><th>#</th><th style="text-align:left">코인</th><th>30일 흐름</th><th>${per[rk]}</th><th>24h 거래량</th><th>거래량 변화</th><th>시총</th><th title="거래대금 상위 20개 거래소 중 상장된 곳">상장 거래소</th><th></th></tr></thead><tbody>
  ${rows.map((c,i)=>`<tr class="row" data-coin="${c.id}" tabindex="0"><td class="na">${i+1}</td><td style="text-align:left"><span class="nm">${esc(c.s)}</span> <span class="secchip">${esc(SX[c.sec].n)}</span><div class="chips">${c.tp?chip(c.tp[0]==="꺾임 주의"?"꺾임 주의":"익절 구간","warn"):""}${c.topRank?chip("추천","hot"):""}${c.uwarn?chip("업비트 유의","warn"):""}</div></td>
  <td class="sp">${spark(c)}</td><td class="num ${cls(c[rk])}"><b>${f1(c[rk])}</b></td><td class="num">${usd(c.vol)}</td><td class="num">${vtxt(c)}</td><td class="num">${usd(c.mc)}</td><td>${nEx(c)}</td><td>${tvBtn(c)}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty">${rk==="c180"?"180일 기록이 아직 부족합니다 (일봉 180개 필요)":"해당 코인 없음"}</div>`)+
  `<h3>대장</h3><div class="chips">${D.lead.vol?chip(`거래대금 대장 ${D.lead.vol.s} ${f1(D.lead.vol.c30,0)}`,"hot"):""}${D.lead.ret?chip(`상승률 대장 ${D.lead.ret.s} ${f1(D.lead.ret.c30,0)}`,"hot"):""}</div>
  ${D.changes.length?`<h3>추천 변화</h3><div class="chips">${D.changes.map(x=>`<span class="chip ${x.t==="in"?"ok":""}" title="${esc(x.why.join(", "))}">${x.t==="in"?"＋":"－"} ${esc(x.s)} · ${esc(x.why[0])}</span>`).join("")}</div>`:""}`;
}
function renderSq(seg){
  const sc=c=>c.sqn*10+Math.max(-(c.fund||0),0)*.5+Math.max(c.oi||0,0)+Math.max((c.sh||50)-50,0);
  const rows=live.filter(c=>shown(c)&&c.fund!=null&&c.sqn>=2).sort((a,b)=>sc(b)-sc(a)).slice(0,15);
  document.getElementById("p-home").innerHTML=seg+`<div class="tbl"><table><thead><tr><th>#</th><th style="text-align:left">코인</th><th>신호</th><th>펀딩 (연)</th><th>OI 24h</th><th>숏 계정</th><th>7일</th><th></th></tr></thead><tbody>
  ${rows.map((c,i)=>`<tr class="row" data-coin="${c.id}" tabindex="0"><td class="na">${i+1}</td><td style="text-align:left"><span class="nm">${esc(c.s)}</span> <span class="secchip">${esc(SX[c.sec].n)}</span></td>
  <td>${bar(c.sqn/4*100,c.sqn>=3?"var(--accent)":"var(--faint)")}<span class="sm">${c.sqn}/4</span></td><td class="num ${c.fund<=0?"up":""}">${c.fund}%</td><td class="num ${(c.oi||0)>=5?"up":""}">${f1(c.oi)}</td><td class="num">${c.sh==null?"—":c.sh.toFixed(0)+"%"}</td><td class="num ${cls(c.c7)}">${f1(c.c7)}</td><td>${tvBtn(c)}</td></tr>`).join("")||'<tr><td colspan="8" class="na">해당 코인 없음</td></tr>'}</tbody></table></div>
  <details class="rule"><summary>기준 보기</summary><ul><li>숏 우세: 펀딩 0 이하 · 숏 쌓임: OI 24시간 +${TH.sq_oi}% 이상 · 숏 계정 ${TH.sq_short}% 이상 (Bitget) · 가격 버팀: 7일 0% 이상</li><li>3개 이상이면 "스퀴즈 준비". 숏이 몰렸는데 가격이 안 빠지면 숏 청산이 가격을 밀어 올릴 수 있음</li></ul></details>`;
}
document.getElementById("p-home").addEventListener("click",e=>{const b=e.target.closest("[data-rk]");if(b){rk=b.dataset.rk;renderHome();}});

/* 초입 후보 */
function miniCard(c){
  const s=SX[c.sec];
  return `<button class="pick" data-coin="${c.id}"><div class="t"><span class="rk">${c.topRank}위</span><span class="sym">${esc(c.s)}</span>${spark(c)}</div>
  <div class="rt num"><span>7일 <b class="${cls(c.c7)}">${f1(c.c7)}</b></span><span>30일 <b class="${cls(c.c30)}">${f1(c.c30)}</b></span></div>
  <p class="why">${esc(s.n)} 섹터보다 30일 ${(c.c30-s.m30).toFixed(0)}%p 덜 오름</p>
  <div class="chips">${(c.warns||[]).slice(0,2).map(w=>chip(w,"warn")).join("")}${c.kept?chip("유지 중","ok"):""}</div>
  <div class="stop">무효: ${esc(stopTxt(c))}</div></button>`;
}
function condRows(c){
  const s=SX[c.sec];
  const g=[["섹터",[[`상위 섹터 (${s.rank}위)`,s.top]]],
   ["덜 오름",[[`30일 z ${c.z30.toFixed(2)} (기준 ${TH.z30} 이하)`,c.z30<=TH.z30],[`7일 z ${c.z7.toFixed(2)} (기준 ${TH.z7} 이하)`,c.z7<=TH.z7],[`30일 ${f1(c.c30)} (+${TH.cap30}% 이하)`,c.c30<=TH.cap30],[`7일 ${f1(c.c7)} (+${TH.cap7}% 이하)`,c.c7<=TH.cap7]]],
   ["움직임 (참고)",[[`20일선 위`,c.a20],[`거래량 ${c.vx==null?"—":c.vx.toFixed(1)+"배"}`,c.cvol],[`3일 섹터보다 강함`,c.cfirst]]],
   ["안전",[[`시총 ${usd(c.mc)}`,c.mc>=TH.pick_mcap],[`거래량 ${usd(c.vol)}`,c.vol>=TH.pick_volume],[`상장 ${(c.L||"").length}곳`,(c.L||"").length>=2],[`펀딩 ${c.fund==null?"—":c.fund+"%"}`,c.fund==null||c.fund<TH.funding_hot],[`업비트 유의 아님`,!c.uwarn]]]];
  return g.map(([h,rows])=>`<h4>${h}</h4><div class="chips">${rows.map(([t,ok])=>chip((ok?"✓ ":"✕ ")+t,ok?"ok":"")).join("")}</div>`).join("");
}
const sortSt={early:"score",small:"score"};
function coinTable(rows,key){
  const sk=sortSt[key];
  rows=[...rows].sort((a,b)=>sk==="score"?b.score-a.score:sk==="vx"?(b.vx||0)-(a.vx||0):sk==="c7"?a.c7-b.c7:a.c30-b.c30);
  const th=(k,t)=>`<th><button data-sort="${k}" data-list="${key}" ${sk===k?'aria-sort="descending"':""}>${t}${sk===k?" ▾":""}</button></th>`;
  return `<div class="tbl"><table><thead><tr><th>코인</th><th>30일 흐름</th><th>상장</th>${th("c7","7일")}${th("c30","30일")}${th("vx","거래량")}${th("score","점수")}<th></th></tr></thead><tbody>
  ${rows.map(c=>`<tr class="row" data-coin="${c.id}" tabindex="0"><td><span class="nm">${esc(c.s)}</span> ${secTxt(c)}${sigTxt(c)}<div class="chips">${badges(c)}${warns(c)}</div></td>
  <td class="sp">${spark(c)}</td><td>${nEx(c)}</td><td class="num ${cls(c.c7)}">${f1(c.c7)}</td><td class="num ${cls(c.c30)}">${f1(c.c30)}</td><td class="num">${vtxt(c)}</td><td class="num"><b>${c.score.toFixed(0)}</b></td><td>${tvBtn(c)}</td></tr>`).join("")||'<tr><td colspan="8" class="na">해당 코인 없음</td></tr>'}</tbody></table></div>`;
}
let sqOnly=false;
function renderEarly(){let r=EARLY.filter(shown);if(sqOnly)r=r.filter(c=>c.squeeze);const t=TOP.filter(shown);
  document.getElementById("p-early").innerHTML=`<h3 style="margin-top:0">Top 3 <span class="sm na">모든 조건 통과 · 시총 순</span></h3>
  ${t.length?`<div class="picks">${t.map(miniCard).join("")}</div>`:'<div class="empty">조건을 모두 통과한 코인이 없습니다. 억지로 찾지 않는 것이 정상입니다.</div>'}
  <h3>후보 <span class="sm na">상위 섹터 · 신호 2개 이상 · 시총 $300M+</span></h3>
  <details class="rule"><summary>기준 보기</summary><ul><li>Top 3: 상위 섹터 + 섹터 안 30일 z ${TH.z30} 이하 + 7일 z ${TH.z7} 이하 + 7일 +${TH.cap7}%·30일 +${TH.cap30}% 이하 + 안전 조건. 한 번 들어오면 z ${TH.z30_keep}까지 유지</li><li>후보 신호: 덜 오름 · 20일선 위 · 거래량 증가 · 추세 돌파 · 스퀴즈 준비 · 업비트 관심</li><li>항상 제외: 거래량 $1M 미만, 상장 거래소 없음 (지금 ${D.excluded}개)</li></ul></details>
  <label class="tog"><input type="checkbox" id="sqonly" ${sqOnly?"checked":""}>스퀴즈 준비만</label>${coinTable(r,"early")}`;}
function renderSmall(){
  const s=(D.bt&&D.bt.lists&&D.bt.lists.small)||null;
  document.getElementById("p-small").innerHTML=`<div class="alert">시총 $70M~300M · 신호 2개 이상 · 섹터 상위 여부 무관${s?` · 과거 1년 7일 승률 ${s.win7.toFixed(0)}%`:""} · 작은 비중 전제</div>${coinTable(SMALL.filter(shown),"small")}`;}
["p-early","p-small"].forEach(id=>{const el=document.getElementById(id);
  el.addEventListener("click",e=>{const b=e.target.closest("[data-sort]");if(b){sortSt[b.dataset.list]=b.dataset.sort;b.dataset.list==="early"?renderEarly():renderSmall();}});
  el.addEventListener("change",e=>{if(e.target.id==="sqonly"){sqOnly=e.target.checked;renderEarly();}});});

/* 눌림목 */
const ST={hold:["hold","지지 중"],lost:["lost","이탈"],wait:["bounce","조정 진행"],turn:["turn","전환 후보"],bounce:["bounce","반등"]};
function renderPull(){
  const p=PULL.filter(shown),n=NEAR.filter(shown),r=RECL.filter(shown);
  const card=(c,head,q)=>`<button class="pc" data-coin="${c.id}"><div class="t"><b>${esc(c.s)}</b>${head}${spark(c)}</div>${secTxt(c)} <span class="sm num">· 30일 <span class="${cls(c.c30)}">${f1(c.c30)}</span> · 30일 고점 대비 <span class="dn">${f1(c.hi30)}</span></span>${ladder(c,false)}<div class="chips">${q}${badges(c)} ${tvBtn(c)}</div></button>`;
  document.getElementById("p-pull").innerHTML=`<p class="lead">강하게 오른 섹터의 선두권 코인이 20일선 아래로 쉬는 중일 때, 60·100·200일선에서 받쳐지는지 봅니다. <b>실험 목록</b>: 2.0 백테스트에서 "더 오른 코인" 전략은 성적이 가장 나빴습니다.</p>
  ${LEG}<details class="rule"><summary>판정 기준</summary><ul><li>대상: 섹터 30일이 시장보다 +${TH.pull_sec30}%p 이상 · 코인 30일 +${TH.pull_c30}% 이상 · 섹터 안 수익률 상위 절반 · 20일선 아래 · 30일 고점 대비 ${TH.pull_hi_max}~${TH.pull_hi_min}%</li>
  <li>지지 중: 가장 가까운 아래 이평선(60·100·200) 위 0~${TH.ma_near}% · 이탈: 그 선 아래</li><li>품질: 이평 정배열, 조정 중 거래량 감소, 펀딩 식음</li></ul></details>
  <div class="pl">${p.map(c=>card(c,`<span class="state ${ST[c.pull.st][0]}">${ST[c.pull.st][1]}</span><span class="sm">${esc(c.pull.txt)}</span>`,c.pull.q.map(([t,ok])=>chip((ok?"✓ ":"✕ ")+t,ok?"ok":"")).join(""))).join("")||`<div class="empty">지금은 조건을 모두 채운 코인이 없습니다.</div>`}</div>
  ${n.length?`<h3>조건 1~2개 빠진 코인 (관찰)</h3><div class="pl">${n.map(c=>card(c,`<span class="state ${c.pullmiss.length===1?"bounce":"lost"}">${c.pullmiss.length}개 미달</span><span class="sm">빠진 조건: ${esc(c.pullmiss.join(", "))}</span>`,"")).join("")}</div>`:""}
  <h3>20일선 재돌파</h3><p class="lead">20일선 아래에 ${TH.reclaim_days}일 이상 있다가 올라온 코인. 60일선 아래면 반등, 위면 전환 후보.</p>
  <div class="pl">${r.map(c=>card(c,`<span class="state ${ST[c.reclaim.st][0]}">${ST[c.reclaim.st][1]}</span><span class="sm">20일선 아래 ${c.rc}일 → 재돌파</span>`,c.reclaim.q.map(([t,ok])=>chip((ok?"✓ ":"✕ ")+t,ok?"ok":"")).join(""))).join("")||'<div class="empty">재돌파 코인이 없습니다.</div>'}</div>`;
}

/* 상장 */
function renderList(){
  const L=LISTC.filter(shown);
  document.getElementById("p-list").innerHTML=`<h3 style="margin-top:0">최근 상장 공지</h3>
  ${D.news.length?`<div class="tbl"><table><tbody>${D.news.map(n=>`<tr><td style="text-align:left" class="na">${esc(n.d)}</td><td style="text-align:left">${esc(n.ex)}</td><td style="text-align:left;white-space:normal"><a href="${esc(n.u)}" target="_blank" rel="noopener">${esc(n.t)}</a></td></tr>`).join("")}</tbody></table></div>`:'<div class="empty">공지를 받지 못했습니다 (데이터 점검 탭 참고).</div>'}
  <h3>상장 후보 <span class="sm na">업비트 원화·바이낸스 미상장 · 거래량 $5M+</span></h3>
  <div class="tbl"><table><thead><tr><th>코인</th><th>30일 흐름</th><th style="text-align:left">근거</th><th>상장</th><th>7일</th><th>24h 거래량</th><th></th></tr></thead><tbody>
  ${L.map(c=>`<tr class="row" data-coin="${c.id}" tabindex="0"><td><span class="nm">${esc(c.s)}</span> <span class="secchip">${esc(SX[c.sec].n)}</span></td><td class="sp">${spark(c)}</td><td style="text-align:left">${c.listwhy.map(w=>chip(w,"ok")).join("")}</td><td>${nEx(c)}</td><td class="num ${cls(c.c7)}">${f1(c.c7)}</td><td class="num">${usd(c.vol)}</td><td>${tvBtn(c)}</td></tr>`).join("")||'<tr><td colspan="7" class="na">해당 코인 없음</td></tr>'}</tbody></table></div>`;
}

/* 섹터 */
let secSort="score",secDir=-1,coinOrd="lag";const OPEN=new Set();
document.getElementById("p-sec").addEventListener("toggle",e=>{const d=e.target;if(d.dataset&&d.dataset.k){d.open?OPEN.add(d.dataset.k):OPEN.delete(d.dataset.k);}},true);
function renderSec(){
  const key={score:s=>s.score,x7:s=>s.x7,x30:s=>s.x30,mc:s=>s.mc}[secSort];
  const rows=[...D.secs].sort((a,b)=>(key(a)-key(b))*secDir);
  const mx=Math.max(...D.secs.map(s=>Math.abs(s.score)),1);
  const seg=(cur,items,attr)=>`<span class="seg">${items.map(([k,t])=>`<button data-${attr}="${k}" aria-pressed="${cur===k}">${t}</button>`).join("")}</span>`;
  document.getElementById("p-sec").innerHTML=`<p class="sm na" style="margin:0 0 8px"><span class="tagtop">■ 보라</span> = 추천을 뽑는 상위 ${TH.top_sec}개 (7일·30일 시장 대비 + 오른 코인 비율 점수, 코인 ${TH.sec_min}개 이상) · 섹터를 누르면 코인 목록</p>
  <div class="ctl">정렬 ${seg(secSort,[["score","종합"],["x7","7일"],["x30","30일"],["mc","시총"]],"ss")}
  <span class="seg"><button data-sd="-1" aria-pressed="${secDir===-1}">높은 순</button><button data-sd="1" aria-pressed="${secDir===1}">낮은 순</button></span>
  코인 순서 ${seg(coinOrd,[["lag","덜 오른 순"],["now","지금 오르는 순"],["mc","시총 순"]],"co")}</div>
  ${rows.map(s=>{const cs=s.ids.map(i=>CM[i]).filter(Boolean);const nat=new Set(s.native||[]);
    const o={lag:(a,b)=>a.c30-b.c30,now:(a,b)=>(b.c3??-999)-(a.c3??-999),mc:(a,b)=>b.mc-a.mc}[coinOrd];
    return `<details class="sd" data-k="${s.k}" ${OPEN.has(s.k)?"open":""}><summary><div class="sec ${s.top?"top":""}"><span class="n">${s.rank}</span><div><div class="h"><span class="nm">${esc(s.n)}</span>${s.top?'<span class="tagtop">상위 섹터</span>':""}${s.watch?chip("관찰 섹터"):""}${s.thin&&!s.watch?chip("코인 수 부족"):""}<span class="sm num">7일 <span class="${cls(s.x7)}">${f1(s.x7)}p</span> · 30일 <span class="${cls(s.x30)}">${f1(s.x30,0)}p</span> · 상승 ${s.br.toFixed(0)}% · ${cs.length}개</span></div>
    <div class="sbar"><i style="width:${Math.max(s.score,0)/mx*100}%"></i></div>
    <div class="chips">${chip((s.x7>0?"✓ ":"✕ ")+`시장보다 7일 ${f1(s.x7)}p`,s.x7>0?"ok":"")}${chip((s.x30>0?"✓ ":"✕ ")+`30일 ${f1(s.x30,0)}p`,s.x30>0?"ok":"")}${chip((s.br>=TH.breadth_min?"✓ ":"✕ ")+`상승 비율 ${s.br.toFixed(0)}%`,s.br>=TH.breadth_min?"ok":"")}${s.lead?chip(`대장 ${s.lead.s} ${f1(s.lead.c30,0)}`,"hot"):""}${nat.size?chip(`혼합 섹터: 네이티브 ${nat.size}개 + 참여 프로젝트`,"warn"):""}</div></div></div></summary>
    <div class="slist">${[...cs].sort(o).map(c=>`<div class="r" data-coin="${c.id}"><b>${esc(c.s)}${s.lead&&s.lead.id===c.id?' <span class="chip hot">대장</span>':""}${nat.has(c.id)?' <span class="chip">네이티브</span>':""}</b>${spark(c,64,18)}<span class="g num"><span class="${cls(c.c3)}">3일 ${f1(c.c3)}</span><span class="${cls(c.c30)}">30일 ${f1(c.c30)}</span>${tvBtn(c)}</span></div>`).join("")}</div></details>`;}).join("")}`;
}
document.getElementById("p-sec").addEventListener("click",e=>{const b=e.target.closest("button[data-ss],button[data-sd],button[data-co]");if(!b)return;
  if(b.dataset.ss)secSort=b.dataset.ss;if(b.dataset.sd)secDir=+b.dataset.sd;if(b.dataset.co)coinOrd=b.dataset.co;renderSec();});

/* 시장 */
const bar=(v,col="var(--info)")=>`<span class="hb"><i style="width:${Math.max(0,Math.min(100,v))}%;background:${col}"></i></span>`;
function renderMkt(){
  const y=D.cyc,r=D.disp&&D.disp.norm?D.disp.now/D.disp.norm:null,T=D.tiers||[];
  const {S,fr,cur,nxt}=stageNow();
  const base=B.c7!=null?B.c7:D.mk.m7,baseN=B.c7!=null?"BTC 대비":"시장 전체 대비";
  const rel=T.map(t=>({...t,rel:t.m7-base}));const mx=Math.max(...rel.map(t=>Math.abs(t.rel)),1);
  const best=[...rel].sort((a,b)=>b.rel-a.rel)[0];
  const hist=[["7일간 오른 코인",y.b7,"var(--up)"],["30일간 오른 코인",y.b30,"var(--up)"],["90일 저점 대비 +50%↑",y.big,"var(--info)"],["90일 저점 대비 2배↑",y.hot,"var(--amber)"],["익절 구간",y.tp,"var(--amber)"],["급등 후 꺾임",y.brk,"var(--down)"]];
  const tiles=[["BTC 추세",BT.up==null?"—":BT.up?"상승 추세":"하락 추세",B.ma50?`50일선 ${B.px>B.ma50?"위":"아래"}`:"일봉 쌓는 중",BT.up],
    ["BTC 도미넌스",B.dom7==null?"—":`${B.dom7<0?"▼":"▲"} ${Math.abs(B.dom7).toFixed(1)}%p`,B.dom==null?"—":`${B.dom.toFixed(1)}% · 7일`,BT.domDown],
    ["알트/BTC (TOTAL3÷BTC)",B.alt30==null?"—":`${B.alt30>=0?"▲":"▼"} ${Math.abs(B.alt30).toFixed(1)}%`,B.altd?`${B.altd}일`:"기록 쌓는 중",B.alt30==null?null:B.alt30>0]];
  const alt=tiles.filter(t=>t[3]===true).length,known=tiles.filter(t=>t[3]!=null).length;
  document.getElementById("p-mkt").innerHTML=`
  <div class="box"><div class="bh"><h3>알트 사이클</h3><span class="state turn">${cur+1}. ${STAGES[cur][0]}${nxt!=null?` → ${nxt+1}. ${STAGES[nxt][0]} 전환 중`:""}</span></div>
   <div class="steps">${STAGES.map(([n,a],i)=>`<div class="st ${i===cur?"on":i===nxt?"nx":""}"><span class="dot">${i+1}</span><span class="sn">${n}</span><span class="sa">${a}</span><i style="width:${fr[i]*100}%"></i></div>`).join("")}</div>
   <div class="bh" style="margin:10px 0 4px"><b>지금 할 일: ${STAGES[cur][1]}</b></div>
   <div class="chips">${S[cur].map(([t,ok])=>chip((ok?"✓ ":"✕ ")+t,ok?"ok":"")).join("")}</div>
   ${nxt!=null?`<div class="chips" style="margin-top:4px"><span class="sm na">다음 단계 조건:</span>${S[nxt].map(([t,ok])=>chip((ok?"✓ ":"✕ ")+t,ok?"ok":"")).join("")}</div>`:""}
   <div style="margin-top:14px"><span class="sm na">알트시즌 지수 (상위 50개 알트 중 ${esc(B.altbase||"")} BTC보다 더 오른 비율)</span>${B.alt==null?'<p class="sm na">계산 불가</p>':`<div class="gauge cg"><i style="left:${B.alt}%"></i><span style="left:${B.alt}%">${B.alt}</span></div>`}<div class="gl"><span>BTC 시즌</span><span>중립</span><span>알트시즌</span></div></div>
   <details class="rule"><summary>단계 판정 방식</summary><ul><li>팀 리더가 말한 8단계 흐름을 단계마다 3~4개 조건으로 바꿨습니다. 막대 = 그 단계 조건을 채운 비율</li><li>가장 많이 채운 단계가 현재 단계, 다음 단계를 절반 이상 채우면 "전환 중"</li><li>기준값은 검증 전입니다</li></ul></details></div>
  <div class="grid2" style="margin-top:14px">
  <div class="box"><div class="bh"><h3>체급별 7일 수익률</h3><span class="sm na">${baseN}</span></div>
   ${rel.map(t=>{const w=Math.abs(t.rel)/mx*50;return `<div class="tier"><span>${t.n}<br><span class="na sm">${t.rg}</span></span><div class="b"><i style="${t.rel>=0?`left:50%;width:${w}%;background:var(--up)`:`right:50%;width:${w}%;background:var(--down)`}"></i></div><span class="num ${cls(t.rel)}">${f1(t.rel)}</span></div>`}).join("")}
   ${best?`<p class="sm" style="margin:8px 0 0">가장 강한 체급: <b>${best.n}</b>${best.lead?` · 대장 ${esc(best.lead.s)}`:""}. 메이저 → 대형 → 중형 → 마이너 순으로 번지면 알트 상승장이 넓어지는 신호.</p>`:""}</div>
  <div class="box"><div class="bh"><h3>BTC와 알트</h3><span class="state ${alt>=2?"hold":"lost"}">알트 유리 ${alt}/${known||3}</span></div>
   <div class="tiles">${tiles.map(([n,b,a,ok])=>`<div class="tile ${ok===true?"ok":ok===false?"no":""}"><span class="sm na">${n}</span><b>${b}</b><span class="sm">${a}</span></div>`).join("")}</div>
   <details class="rule"><summary>뜻 보기</summary><ul><li>BTC 추세: 일봉 50일선 위 + 50일선이 오르는 중이면 상승 추세</li><li>도미넌스 ▼: 돈이 BTC에서 알트로</li><li>알트/BTC ▲: BTC·ETH를 뺀 알트 시총이 BTC보다 빨리 커지는 중</li><li>도미넌스·알트/BTC는 3.0부터 기록을 쌓아 7일·30일 뒤부터 표시</li></ul></details>
   <div class="chips">${[["CRYPTOCAP:BTC.D","BTC.D"],["CRYPTOCAP:TOTAL3","TOTAL3"],["CRYPTOCAP:TOTAL3/CRYPTOCAP:BTC","TOTAL3÷BTC"],["CRYPTOCAP:OTHERS.D","OTHERS.D"]].map(([s,t])=>`<a class="tvb" href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(s)}" target="_blank" rel="noopener">${t}</a>`).join("")}</div></div></div>
  <div class="grid2" style="margin-top:14px">
  <div class="box"><div class="bh"><h3>시장 폭</h3><span class="sm na">추적 ${y.n}개</span></div>
   <div class="hg">${hist.map(([n,v,c])=>`<span class="hl">${n}</span>${bar(v,c)}<span class="hv num">${v.toFixed(0)}%</span>`).join("")}</div>
   <p class="sm na" style="margin:6px 0 0">7일간 오른 코인: 1주 전 ${y.b7p.toFixed(0)}% → 지금 ${y.b7.toFixed(0)}%</p></div>
  <div class="box"><div class="bh"><h3>섹터 순환</h3>${r==null?"":`<span class="state ${r>=2?"turn":"bounce"}">${r>=2?"순환장":"같이 움직임"}</span>`}</div>
   ${r==null?'<p class="sm na">계산 불가</p>':`<div class="rot"><span class="hb" style="position:relative"><i style="width:${Math.min(r/3,1)*100}%;background:var(--accent)"></i><b style="left:66.6%"></b></span><span class="num">${r.toFixed(1)}배</span></div>
   <div class="gl"><span>0</span><span>1배</span><span>2배 순환장</span><span>3배</span></div>`}
   <details class="rule"><summary>뜻 보기</summary><ul><li>섹터끼리 7일 수익률 차이가 최근 30일 평소의 몇 배인지</li><li>2배↑: 돈이 특정 섹터로 몰림 → 강한 섹터 고르기가 중요</li><li>평소 수준: 시장 전체가 같이 움직임 → BTC 방향이 중요</li></ul></details></div></div>`;
}

/* 성적표 */
const V={keep:["유지","v-ok"],watch:["지켜보기","v-hold"],drop:["빼기","v-no"],base:["기준","v-hold"],wait:["측정 중","v-hold"]};
function btRow(n,x,vd,why){
  const has=x&&x.n7;
  return `<div class="bt"><div class="btn"><b>${esc(n)}</b><span class="verdict ${V[vd][1]}">${V[vd][0]}</span></div>
   ${has?`<div class="flip"><i style="width:${x.win7}%"></i><b></b></div><span class="num">${x.win7.toFixed(0)}%</span><span class="num ${cls(x.med7)}">${f1(x.med7)}p</span><span class="num na">${x.n7}</span>`:`<div class="flip"></div><span class="na">—</span><span></span><span></span>`}<span class="sm">${why||""}</span></div>`;
}
function verdict(x){if(!x||!x.n7||x.n7<30)return "wait";if(x.win7>50&&x.med7>0&&x.avg7>0)return "keep";if(x.win7<45&&x.med7<0)return "drop";return "watch";}
function renderBt(){
  const b=D.bt,live3=D.board;
  const BL=b&&b.v&&b.v.startsWith("3")?b:null;
  const names={top:"Top 3",early:"초입 후보",small:"소형 도전",pull:"눌림목 (지지 중)",reclaim_turn:"20일선 재돌파: 전환",reclaim_bounce:"20일선 재돌파: 반등",lead:"반대 전략: 섹터 1등 코인",tp:"익절 경보가 뜬 코인"};
  const exps={z10:"덜 오름 z −1.0",score:"Top 3 점수 순",rs:"상대강도선 20일선 위",nocap:"상한 없음 (7일·30일)"};
  document.getElementById("p-bt").innerHTML=`<p class="sm na" style="margin:0 0 8px">막대 = 7일 뒤 같은 섹터 중간값보다 더 오른 비율 (가운데 선 50%) · 중간값 · 표본. 판정: 표본 30개 이상에서 승률·중간값·평균이 모두 좋으면 유지</p>
  <h3 style="margin-top:0">과거 1년 백테스트 ${BL?`<span class="sm na">${BL.start} ~ ${BL.end} · 코인 ${BL.coins}개</span>`:""}</h3>
  ${BL?Object.entries(names).filter(([k])=>BL.lists[k]).map(([k,n])=>btRow(n,BL.lists[k],k==="lead"?"base":k==="tp"?(BL.lists.tp.med7<0?"keep":"watch"):verdict(BL.lists[k]),k==="lead"?"비교 기준":k==="tp"?"중간값이 마이너스면 경보가 맞은 것":"")).join(""):'<div class="empty">3.0 백테스트가 아직 없습니다. Actions → backfill → Run workflow를 실행하세요.</div>'}
  ${BL&&BL.exp?`<details class="rule"><summary>실험 (Top 3 변형)</summary>${Object.entries(exps).filter(([k])=>BL.exp[k]).map(([k,n])=>btRow(n,BL.exp[k],verdict(BL.exp[k]),"")).join("")}
   ${BL.alt?`<h4>알트시즌 구간별 Top 3</h4>${Object.entries(BL.alt).map(([k,x])=>btRow("알트시즌 "+k,x,verdict(x),"")).join("")}`:""}
   ${BL.halves?`<h4>기간 나눠 보기 (Top 3)</h4>${Object.entries(BL.halves).map(([k,x])=>btRow(k,x,x&&x.win7>50?"keep":"watch","")).join("")}`:""}</details>`:""}
  <h3>실전 기록 (v${D.v}부터)</h3>
  ${live3.lists.map(x=>btRow(x.n,x.n7?{n7:x.n7,win7:x.win7,med7:x.med7,avg7:x.avg7}:null,x.n7>=30?verdict(x):"wait",`기록 ${x.total}개 · 7일 채점 ${x.n7}개`)).join("")}
  ${live3.old?`<p class="sm na">이전 버전 기록 ${live3.old}개는 따로 보관</p>`:""}
  <details class="rule"><summary>2.0에서 얻은 결론</summary><ul><li>덜 오름만 걸었을 때 가장 좋았음 (55%) → 3.0 핵심</li><li>평균가 위·거래량 급증을 더하면 나빠짐 → 필수에서 제외</li><li>상승 초입 실험 42%, 중간값 −1.3%p (이미 오른 코인을 7일 상승순으로 골랐음) → 신호 교체</li><li>섹터보다 더 오른 코인을 사는 전략이 가장 나빴음 (40%) → 눌림목은 실험 목록</li><li>트론 섹터 제외 후보, 솔라나·AI·디파이 지켜보기</li></ul></details>`;
}

/* 데이터 점검 */
function renderChk(){
  const SRC=[["CoinGecko","https://www.coingecko.com","가격·시총·거래량(2시간), 섹터 구성(하루), 도미넌스, 거래소 순위"],["Bitget","https://www.bitget.com","현물 일봉(이평선), 선물 OI·펀딩·롱숏 비율"],["OKX","https://www.okx.com","현물 일봉(대체), 선물 OI·펀딩"],["Hyperliquid","https://app.hyperliquid.xyz","선물 OI·펀딩"],["업비트","https://upbit.com","원화 거래대금, 마켓·투자유의, 상장 공지"],["빗썸","https://www.bithumb.com","원화 상장 목록"],["Binance","https://www.binance.com","상장 목록(CoinGecko 경유), 상장 공지"],["CoinMarketCap","https://coinmarketcap.com","가격 교차 확인(하루)"]];
  const st=D.src||{};
  const sttxt=Object.entries(st).map(([k,[s,m]])=>chip(`${s==="ok"?"✓":s==="skip"?"–":"✕"} ${k}${m?" · "+m:""}`,s==="ok"?"ok":s==="skip"?"":"warn")).join("");
  const chk=[...live].filter(c=>c.tv&&c.ma20).sort((a,b)=>b.mc-a.mc).slice(0,14);
  document.getElementById("p-chk").innerHTML=`<h3 style="margin-top:0">이번 실행 (${D.asof}) <span class="sm na">CoinGecko 호출 ${D.calls}회</span></h3><div class="chips">${sttxt||'<span class="sm na">새로 받은 항목 없음 (캐시 사용)</span>'}</div>
  ${D.errors.length?`<details class="rule" open><summary>받지 못한 데이터 ${D.errors.length}건</summary><ul>${D.errors.map(e=>`<li>${esc(e)}</li>`).join("")}</ul></details>`:""}
  ${D.cmc?`<p class="sm">CMC 교차 확인: ${D.cmc.ok}개 일치 · ${D.cmc.bad}개 3% 넘게 차이${D.cmc.worst.length?` (${esc(D.cmc.worst.join(", "))})`:""}</p>`:""}
  <h3>데이터 출처</h3><div class="tbl"><table><tbody>${SRC.map(([n,u,w])=>`<tr><td style="text-align:left"><a href="${u}" target="_blank" rel="noopener">${n}</a></td><td style="text-align:left;white-space:normal" class="sm">${w}</td></tr>`).join("")}</tbody></table></div>
  ${D.top20.length?`<p class="sm na">상장 수 기준 거래소 (거래대금 상위 20): ${esc(D.top20.join(", "))}</p>`:""}
  <h3>트레이딩뷰 대조</h3><p class="sm na">차트 버튼 → 일봉 → 이동평균(단순) 20·60·100·200. 이 사이트는 ${D.cday}까지 마감된 봉 + 현재가로 계산하므로 트레이딩뷰 현재 봉 값과 같아야 합니다 (갱신 시각 차이만큼 오차).</p>
  <div class="tbl"><table><thead><tr><th style="text-align:left">코인</th><th style="text-align:left">일봉 출처</th><th>현재가</th><th>20</th><th>60</th><th>100</th><th>200</th><th></th></tr></thead><tbody>
  ${chk.map(c=>`<tr><td style="text-align:left"><b>${esc(c.s)}</b></td><td style="text-align:left" class="sm">${esc(c.tv||c.src)}</td><td class="num">${px(c.px)}</td><td class="num">${px(c.ma20)}</td><td class="num">${px(c.ma60)}</td><td class="num">${px(c.ma100)}</td><td class="num">${px(c.ma200)}</td><td>${tvBtn(c)}</td></tr>`).join("")}</tbody></table></div>`;
}

/* 상세 */
const dlg=document.getElementById("dlg");
function openCoin(id){
  const c=CM[id];if(!c)return;const s=SX[c.sec];
  const where=c.topRank?`Top ${c.topRank}`:EARLY.includes(c)?"초입 후보":SMALL.includes(c)?"소형 도전":c.pull?"눌림목":c.reclaim?"20일선 재돌파":"목록 밖";
  document.getElementById("dlb").innerHTML=`<div class="top"><b>${esc(c.s)}</b><span class="na">${esc(c.name)}</span><span class="chip hot">${where}</span><button class="x" id="dlx">닫기</button></div>
  ${secTxt(c)}${c.secs.length>1?`<p class="sm na">다른 소속 섹터: ${c.secs.filter(k=>k!==c.sec&&SX[k]).map(k=>SX[k].n).join(", ")}</p>`:""}
  <div style="margin:8px 0">${spark(c,300,60)}</div>
  <div class="kv num"><span>현재가 · 시총</span><span>$${px(c.px)} · ${usd(c.mc)}</span></div>
  <div class="kv num"><span>1일 / 7일 / 30일 / 180일</span><span><span class="${cls(c.c1)}">${f1(c.c1)}</span> / <span class="${cls(c.c7)}">${f1(c.c7)}</span> / <span class="${cls(c.c30)}">${f1(c.c30)}</span> / <span class="${cls(c.c180)}">${f1(c.c180)}</span></span></div>
  <div class="kv num"><span>섹터 중간값 7일 / 30일</span><span>${f1(s.m7)} / ${f1(s.m30)}</span></div>
  <div class="kv num"><span>이평선 20 / 60 / 100 / 200</span><span>${px(c.ma20)} / ${px(c.ma60)} / ${px(c.ma100)} / ${px(c.ma200)}</span></div>
  <div class="kv num"><span>거래량</span><span>${usd(c.vol)} · 최근 3일 ${c.vx==null?"—":c.vx.toFixed(1)+"배"}</span></div>
  <div class="kv num"><span>상장 (상위 20개 거래소)</span><span>${c.ex20==null?"—":c.ex20+"곳"}</span></div>
  <div class="kv num"><span>구매 고려 점수</span><span><b>${c.score.toFixed(0)}</b></span></div>
  ${c.tp?`<div class="alert" style="margin-top:10px"><b>${esc(c.tp[0])}</b> · ${esc(c.tp[1])}</div>`:""}
  <h4>이평선 위치</h4>${ladder(c)}${condRows(c)}
  <h4>숏 스퀴즈 (${c.sqn}/4)</h4><div class="chips">${c.sq.map(([t,ok,v])=>chip(`${ok?"✓":"✕"} ${t} · ${v}`,ok?"ok":"")).join("")}</div>
  ${c.warns.length?`<h4>경고</h4><div class="chips">${warns(c)}</div>`:""}
  <h4>상장 거래소</h4><div class="chips">${EXS.map(([k,n])=>`<span class="ex ${(c.L||"").includes(k)?"":"off"}">${n}</span>`).join(" ")}</div>
  <p class="sm na" style="margin-top:10px">무효 기준: ${esc(stopTxt(c))} · 일봉 출처 ${esc(c.tv||c.src||"—")}</p>
  <div class="links"><a class="pri" href="${tv(c)}" target="_blank" rel="noopener">트레이딩뷰 차트</a><a href="https://www.coingecko.com/en/coins/${c.id}" target="_blank" rel="noopener">CoinGecko</a></div>`;
  dlg.showModal();document.getElementById("dlx").onclick=()=>dlg.close();
}
dlg.addEventListener("click",e=>{if(e.target===dlg)dlg.close();});
document.addEventListener("click",e=>{if(e.target.closest("a"))return;const b=e.target.closest("[data-coin]");if(b&&!e.target.closest("dialog"))openCoin(b.dataset.coin);});
document.addEventListener("keydown",e=>{if(e.key==="Enter"){const r=e.target.closest&&e.target.closest("tr[data-coin]");if(r)openCoin(r.dataset.coin);}});

/* 검색 */
const q=document.getElementById("q"),sres=document.getElementById("sres");
q.addEventListener("input",()=>{const v=q.value.trim().toLowerCase();if(!v){sres.style.display="none";return;}
  const hits=C.filter(c=>c.s.toLowerCase().includes(v)||(c.name||"").toLowerCase().includes(v)).sort((a,b)=>(b.s.toLowerCase()===v)-(a.s.toLowerCase()===v)||b.mc-a.mc).slice(0,8);
  sres.innerHTML=hits.map(c=>`<button data-coin="${c.id}"><b>${esc(c.s)}</b><span class="sm na">${esc(c.name)} · ${esc(SX[c.sec].n)} · 30일 ${f1(c.c30)}</span></button>`).join("")||`<div class="sm na" style="padding:8px 10px">"${esc(q.value)}" 없음. 추적 섹터 밖이거나 시총 $70M 미만입니다.</div>`;
  sres.style.display="block";});
document.addEventListener("click",e=>{if(!e.target.closest(".search"))sres.style.display="none";});

/* 하단 */
document.getElementById("foot").innerHTML=`<details class="rule"><summary>버전·변경 이력</summary><p class="sm">${esc(D.rule)}</p>${D.changelog.map(([v,d,k,items])=>`<h4>v${v} · ${d} · ${k}</h4><ul>${items.map(i=>`<li class="sm">${esc(i)}</li>`).join("")}</ul>`).join("")}</details>
<p>섹터 모니터 v${D.v} · ${esc(D.subtitle)} · ${esc(D.credit)}</p>`;

function renderAll(){renderRegime();renderTabs();renderFilt();renderHome();renderEarly();renderSmall();renderPull();renderList();renderSec();renderMkt();renderBt();renderChk();}
renderAll();
"""


if __name__ == "__main__":
    main()
