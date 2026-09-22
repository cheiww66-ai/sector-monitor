#!/usr/bin/env python3
"""CHARON 섹터 모니터 v3.1

목표: 강한 섹터 안에서 '덜 올랐지만 망가지지 않았고, 움직이기 시작한' 코인을 강조한다.
- 1시간마다 실행. 데이터마다 갱신 주기를 달리해 무료 한도 안에서 운영.
    BTC·선물(OI·펀딩)      : 1시간
    섹터별 코인(CoinGecko) : 4시간
    체인·수수료(DefiLlama) : 1일
- 결과 페이지: site/index.html (GitHub Pages로 배포)
- 기록(성적표 등): data/*.json (저장소에 커밋)
- 다시 받을 수 있는 큰 데이터: cache/*.json (GitHub 캐시에 보관)
외부 라이브러리 없음.
"""
import datetime as dt
import html
import json
import os
import random
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

# ═════════════════════════ 설정 ═════════════════════════
KST = dt.timezone(dt.timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, "cache")
SITE_DIR = os.path.join(ROOT, "site")
MOCK = os.environ.get("MOCK") == "1"
NOW_TS = int(os.environ.get("NOW_TS") or time.time())  # 테스트용 시간 조작
CG_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
PAGE_URL = os.environ.get("PAGE_URL", "").strip()

# 섹터: CoinGecko 카테고리 ID가 바뀌면 names로 자동 재탐색
SECTORS = [
    # 체인 생태계
    {"key": "ETH", "name": "이더리움", "kind": "체인", "cg": "ethereum-ecosystem", "names": ["Ethereum Ecosystem"], "llama": "Ethereum", "dex": "ethereum"},
    {"key": "SOL", "name": "솔라나", "kind": "체인", "cg": "solana-ecosystem", "names": ["Solana Ecosystem"], "llama": "Solana", "dex": "solana"},
    {"key": "BNB", "name": "BNB체인", "kind": "체인", "cg": "binance-smart-chain", "names": ["BNB Chain Ecosystem", "Binance Smart Chain Ecosystem"], "llama": "BSC", "dex": "bsc"},
    {"key": "BASE", "name": "베이스", "kind": "체인", "cg": "base-ecosystem", "names": ["Base Ecosystem"], "llama": "Base", "dex": "base"},
    {"key": "ARB", "name": "아비트럼", "kind": "체인", "cg": "arbitrum-ecosystem", "names": ["Arbitrum Ecosystem"], "llama": "Arbitrum", "dex": "arbitrum"},
    {"key": "SUI", "name": "수이", "kind": "체인", "cg": "sui-ecosystem", "names": ["Sui Ecosystem"], "llama": "Sui", "dex": "sui"},
    {"key": "AVAX", "name": "아발란체", "kind": "체인", "cg": "avalanche-ecosystem", "names": ["Avalanche Ecosystem"], "llama": "Avalanche", "dex": "avalanche"},
    {"key": "TON", "name": "톤", "kind": "체인", "cg": "ton-ecosystem", "names": ["TON Ecosystem", "The Open Network Ecosystem", "Toncoin Ecosystem"], "llama": "TON", "dex": "ton"},
    {"key": "TRX", "name": "트론", "kind": "체인", "cg": "tron-ecosystem", "names": ["Tron Ecosystem", "TRON Ecosystem"], "llama": "Tron", "dex": "tron"},
    {"key": "APT", "name": "앱토스", "kind": "체인", "cg": "aptos-ecosystem", "names": ["Aptos Ecosystem"], "llama": "Aptos", "dex": "aptos"},
    {"key": "HYPE", "name": "하이퍼리퀴드", "kind": "체인", "cg": "hyperliquid-ecosystem", "names": ["Hyperliquid Ecosystem", "HyperEVM Ecosystem"], "llama": "Hyperliquid L1", "dex": "hyperliquid-l1"},
    {"key": "BTCE", "name": "비트코인 생태계", "kind": "체인", "cg": "bitcoin-ecosystem", "names": ["Bitcoin Ecosystem"], "llama": None, "dex": None},
    # 내러티브
    {"key": "MEME", "name": "밈", "kind": "내러티브", "cg": "meme-token", "names": ["Meme"]},
    {"key": "AI", "name": "AI", "kind": "내러티브", "cg": "artificial-intelligence", "names": ["Artificial Intelligence (AI)", "Artificial Intelligence"]},
    {"key": "AGENT", "name": "AI 에이전트", "kind": "내러티브", "cg": "ai-agents", "names": ["AI Agents"]},
    {"key": "RWA", "name": "실물자산", "kind": "내러티브", "cg": "real-world-assets-rwa", "names": ["Real World Assets (RWA)"]},
    {"key": "DEPIN", "name": "DePIN", "kind": "내러티브", "cg": "depin", "names": ["DePIN"]},
    {"key": "DEFI", "name": "디파이", "kind": "내러티브", "cg": "decentralized-finance-defi", "names": ["Decentralized Finance (DeFi)"]},
    {"key": "PERP", "name": "선물 DEX", "kind": "내러티브", "cg": "perpetuals", "names": ["Perpetuals"]},
    {"key": "L2", "name": "레이어2", "kind": "내러티브", "cg": "layer-2", "names": ["Layer 2 (L2)"]},
    {"key": "GAME", "name": "게임", "kind": "내러티브", "cg": "gaming", "names": ["Gaming (GameFi)", "Gaming"]},
    {"key": "PRIV", "name": "프라이버시", "kind": "내러티브", "cg": "privacy-coins", "names": ["Privacy Coins"]},
    {"key": "RESTAKE", "name": "리스테이킹", "kind": "내러티브", "cg": "restaking", "names": ["Restaking"]},
    {"key": "PRED", "name": "예측시장", "kind": "내러티브", "cg": "prediction-markets", "names": ["Prediction Markets"]},
]

TH = {  # 판정 기준 (숫자만 바꾸면 기준이 바뀜)
    # 섹터 신호
    "funding_hot_apr": 40.0, "funding_neutral_apr": 15.0,
    "stable_in_pct": 1.0, "stable_out_pct": -1.0, "dex_up_pct": 10.0,
    "breadth_strong": 60.0, "oi_jump_pct": 10.0, "price_flat_pct": 2.0,
    # 등급
    "major_rank": 5, "major_mcap": 1e9, "major_venues": 2,
    "minor_mcap": 50e6, "min_volume": 2e6, "turnover_min": 0.02, "turnover_max": 0.5,
    "float_min": 0.5, "ath_dd_min": -95.0,
    # 후보
    "lag_min": 5.0,         # 섹터 중앙값보다 30일 수익률이 이만큼(%p) 이상 낮아야 '지연'
    "vol_surge": 1.5,       # 오늘 거래량 / 직전 평균 거래량
    "coin_funding_max": 40.0,
    "red_max": 3, "yellow_max": 10, "top_n": 10,
    "verify_min_samples": 20,
}
USER_VENUES = ["Bitget", "OKX", "Hyperliquid"]   # 실제로 거래하는 곳
EXCHANGES = ["Hyperliquid", "Bitget", "OKX", "Bybit", "Binance"]
STABLE_SYMS = {"usdt", "usdc", "dai", "usde", "fdusd", "pyusd", "usds", "tusd", "usdd", "frax", "usd1",
               "rlusd", "susde", "gho", "lusd", "crvusd", "usdx", "eurc", "usdg", "bfusd"}
EXCLUDE_WORDS = ("wrapped", "staked", "bridged", "liquid staking", "restaked", "wormhole", "binance-peg", "tether", " usd")
CAT_REFRESH_S = 4 * 3600 - 600
DAY_REFRESH_S = 24 * 3600 - 600


# ═════════════════════════ 공통 ═════════════════════════
def get_json(url, method="GET", body=None, headers=None, retries=3):
    h = {"User-Agent": "charon-monitor/3.0", "Accept": "application/json"}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404, 451):
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


def downsample(xs, n=42):
    xs = [x for x in (xs or []) if x is not None]
    if len(xs) <= n:
        return xs
    step = (len(xs) - 1) / (n - 1)
    return [xs[round(i * step)] for i in range(n)]


# ═════════════════════════ 수집: CoinGecko ═════════════════════════
NOTES = []
_KEY = {"ok": bool(CG_KEY)}


def cg(path):
    url = "https://api.coingecko.com/api/v3" + path
    try:
        res = get_json(url, headers={"x-cg-demo-api-key": CG_KEY} if _KEY["ok"] else {})
    except urllib.error.HTTPError as e:
        if e.code != 401 or not _KEY["ok"]:
            raise
        _KEY["ok"] = False   # 키가 거부됨 -> 이번 실행은 키 없이
        NOTES.append("CoinGecko 키가 거부되어 키 없이 받았습니다(속도 제한이 더 엄격함). Settings → Secrets의 COINGECKO_API_KEY 값을 확인하세요.")
        time.sleep(8)
        res = get_json(url)
    time.sleep(2.5 if _KEY["ok"] else 8)
    return res


def fetch_btc():
    r = cg("/coins/markets?vs_currency=usd&ids=bitcoin&sparkline=true&price_change_percentage=24h,7d,30d")[0]
    return {"px": r.get("current_price"), "c24": r.get("price_change_percentage_24h_in_currency"),
            "c7": r.get("price_change_percentage_7d_in_currency"),
            "c30": r.get("price_change_percentage_30d_in_currency"),
            "spark": downsample((r.get("sparkline_in_7d") or {}).get("price"))}


def fetch_global():
    g = cg("/global")["data"]
    return {"btc_dom": g["market_cap_percentage"].get("btc")}


def fetch_catlist():
    return {r["category_id"]: r["name"] for r in cg("/coins/categories/list")}


def resolve_ids(catlist):
    out, missing = {}, []
    lower = {v.lower(): k for k, v in catlist.items()}
    for s in SECTORS:
        cid = s["cg"] if s["cg"] in catlist else next((lower[n.lower()] for n in s["names"] if n.lower() in lower), None)
        if cid:
            out[s["key"]] = cid
        else:
            missing.append(s["name"])
    return out, missing


def fetch_category(cid):
    rows = cg(f"/coins/markets?vs_currency=usd&category={cid}&order=market_cap_desc&per_page=250&page=1"
              "&sparkline=true&price_change_percentage=1h,24h,7d,30d")
    out = []
    for r in rows:
        out.append({"id": r["id"], "sym": (r.get("symbol") or "").upper(), "name": r.get("name") or "",
                    "px": r.get("current_price"), "mc": r.get("market_cap") or 0, "fdv": r.get("fully_diluted_valuation"),
                    "vol": r.get("total_volume") or 0, "dd": r.get("ath_change_percentage"),
                    "c1h": r.get("price_change_percentage_1h_in_currency"),
                    "c24": r.get("price_change_percentage_24h_in_currency"),
                    "c7": r.get("price_change_percentage_7d_in_currency"),
                    "c30": r.get("price_change_percentage_30d_in_currency"),
                    "spark": downsample((r.get("sparkline_in_7d") or {}).get("price"))})
    return out


# ═════════════════════════ 수집: DefiLlama ═════════════════════════
def fetch_stable(chain):
    rows = get_json(f"https://stablecoins.llama.fi/stablecoincharts/{urllib.parse.quote(chain)}")
    vals = [v for v in (r.get("totalCirculatingUSD", {}).get("peggedUSD") for r in rows) if v]
    return pct(vals[-1], vals[-8])


def fetch_tvl(chain):
    vals = [r["tvl"] for r in get_json(f"https://api.llama.fi/v2/historicalChainTvl/{urllib.parse.quote(chain)}")]
    return pct(vals[-1], vals[-8])


def fetch_dex(chain):
    d = get_json(f"https://api.llama.fi/overview/dexs/{chain}?excludeTotalDataChartBreakdown=true")
    s = [v for _, v in d.get("totalDataChart", [])]
    return pct(sum(s[-7:]), sum(s[-14:-7])) if len(s) >= 15 else None


def fetch_fees():
    """코인(CoinGecko id) -> 최근 30일 수수료 합계"""
    gid = {}
    for p in get_json("https://api.llama.fi/protocols"):
        g = p.get("gecko_id")
        if g:
            for k in (str(p.get("id")), (p.get("slug") or "").lower(), (p.get("name") or "").lower()):
                gid[k] = g
    d = get_json("https://api.llama.fi/overview/fees?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true")
    out = {}
    for p in d.get("protocols", []):
        t30 = fl(p.get("total30d"))
        g = (gid.get(str(p.get("defillamaId"))) or gid.get((p.get("slug") or "").lower())
             or gid.get((p.get("name") or "").lower()))
        if g and t30 and t30 > 0:
            out[g] = out.get(g, 0) + t30
    return out


# ═════════════════════════ 수집: 선물 거래소 ═════════════════════════
def norm(sym):
    """1000PEPEUSDT, SHIB1000USDT, PEPE-USDT-SWAP -> PEPE"""
    s = sym.upper()
    for suf in ("-USDT-SWAP", "USDT"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    else:
        return None
    s = re.sub(r"^10{3,}", "", s)
    return re.sub(r"10{3,}$", "", s)


def add(acc, base, oi, fund_h, px24, px, raw):
    if not base or not oi or oi <= 0:
        return
    r = acc.setdefault(base, {"oi": 0.0, "fw": 0.0, "fn": 0.0, "pw": 0.0, "pn": 0.0, "main": 0.0, "px": None, "raw": None})
    r["oi"] += oi
    if fund_h is not None:
        r["fw"] += fund_h * oi
        r["fn"] += oi
    if px24 is not None:
        r["pw"] += px24 * oi
        r["pn"] += oi
    if oi > r["main"]:
        r["main"], r["px"], r["raw"] = oi, px, raw


def finalize(acc):
    return {b: {"oi": r["oi"], "fund_h": r["fw"] / r["fn"] if r["fn"] else None,
                "px24": r["pw"] / r["pn"] if r["pn"] else None, "px": r["px"], "raw": r["raw"]}
            for b, r in acc.items()}


def fetch_hyperliquid(wanted):
    meta, ctxs = get_json("https://api.hyperliquid.xyz/info", method="POST", body={"type": "metaAndAssetCtxs"})
    acc = {}
    for a, c in zip(meta["universe"], ctxs):
        name = a["name"]
        base = name[1:] if name.startswith("k") and name[1:].isupper() else name.upper()
        px, oi = fl(c.get("markPx")), fl(c.get("openInterest"))
        if px and oi:
            add(acc, base, oi * px, fl(c.get("funding")), pct(px, fl(c.get("prevDayPx"))), px, name)
    return finalize(acc)


def fetch_bitget(wanted):
    acc = {}
    for r in get_json("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES")["data"]:
        sym = r["symbol"]
        px = fl(r.get("markPrice")) or fl(r.get("lastPr"))
        oi, fund, p24 = fl(r.get("holdingAmount")), fl(r.get("fundingRate")), fl(r.get("change24h"))
        ivh = fl(r.get("fundingRateInterval")) or 8
        if px and oi:
            add(acc, norm(sym), oi * px, fund / ivh if fund is not None else None,
                p24 * 100 if p24 is not None else None, px, sym)
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
        t = tick.get(iid, {})
        last = fl(t.get("last"))
        oi = fl(r.get("oiUsd")) or (fl(r.get("oiCcy")) or 0) * (last or 0)
        try:
            fr = get_json(f"{b}/api/v5/public/funding-rate?instId={iid}")["data"][0]
            fund, ft, nft = fl(fr.get("fundingRate")), fl(fr.get("fundingTime")), fl(fr.get("nextFundingTime"))
            ivh = (nft - ft) / 3.6e6 if ft is not None and nft is not None and nft > ft else 8
            fund_h = fund / ivh if fund is not None else None
        except Exception:
            fund_h = None
        add(acc, base, oi, fund_h, pct(last, fl(t.get("open24h"))), last, iid)
        time.sleep(0.12)
    return finalize(acc)


def fetch_bybit(wanted):
    b = "https://api.bybit.com"
    rows = get_json(b + "/v5/market/tickers?category=linear")["result"]["list"]
    try:
        inst = get_json(b + "/v5/market/instruments-info?category=linear&limit=1000")["result"]["list"]
        iv = {i["symbol"]: fl(i.get("fundingInterval")) / 60 for i in inst if fl(i.get("fundingInterval"))}
    except Exception:
        iv = {}
    acc = {}
    for r in rows:
        sym = r["symbol"]
        fund, p24 = fl(r.get("fundingRate")), fl(r.get("price24hPcnt"))
        ivh = fl(r.get("fundingIntervalHour")) or iv.get(sym) or 8
        add(acc, norm(sym), fl(r.get("openInterestValue")), fund / ivh if fund is not None else None,
            p24 * 100 if p24 is not None else None, fl(r.get("markPrice")), sym)
    return finalize(acc)


def fetch_binance(wanted):
    b = "https://fapi.binance.com"
    prem = get_json(b + "/fapi/v1/premiumIndex")
    try:
        iv = {r["symbol"]: fl(r.get("fundingIntervalHours")) for r in get_json(b + "/fapi/v1/fundingInfo")}
    except Exception:
        iv = {}
    chg = {r["symbol"]: fl(r.get("priceChangePercent")) for r in get_json(b + "/fapi/v1/ticker/24hr")}
    acc = {}
    for r in prem:
        sym = r["symbol"]
        base = norm(sym)
        if base not in wanted:
            continue
        oi = fl(get_json(f"{b}/fapi/v1/openInterest?symbol={sym}").get("openInterest"))
        px, fund = fl(r.get("markPrice")), fl(r.get("lastFundingRate"))
        if px and oi:
            add(acc, base, oi * px, fund / (iv.get(sym) or 8) if fund is not None else None, chg.get(sym), px, sym)
    return finalize(acc)


FETCHERS = {"Hyperliquid": fetch_hyperliquid, "Bitget": fetch_bitget, "OKX": fetch_okx,
            "Bybit": fetch_bybit, "Binance": fetch_binance}


def px_match(ex_px, cg_px):
    """같은 심볼의 다른 코인을 걸러내기 위해 가격이 맞는지 확인 (1000배 단위 계약 포함)"""
    if not ex_px or not cg_px:
        return False
    r = ex_px / cg_px
    return any(abs(r / k - 1) < 0.08 for k in (1, 1e3, 1e4, 1e6))


def tv_link(venues, coin_id):
    for ex, fmt in (("Bitget", lambda r: f"BITGET:{r}.P"),
                    ("OKX", lambda r: "OKX:" + r.replace("-SWAP", "").replace("-", "") + ".P"),
                    ("Bybit", lambda r: f"BYBIT:{r}.P"),
                    ("Binance", lambda r: f"BINANCE:{r}.P")):
        v = venues.get(ex)
        if v and v.get("raw"):
            return ("TradingView", "https://www.tradingview.com/chart/?symbol=" + urllib.parse.quote(fmt(v["raw"])))
    return ("CoinGecko 차트", f"https://www.coingecko.com/en/coins/{coin_id}")


# ═════════════════════════ 모의 데이터 (테스트용) ═════════════════════════
def mock_world(seed):
    rnd = random.Random(seed)
    btc_spark = [100000 * (1 + 0.002 * i + rnd.uniform(-0.01, 0.01)) for i in range(42)]
    btc = {"px": btc_spark[-1], "c24": rnd.uniform(-3, 3), "c7": rnd.uniform(-6, 8), "c30": rnd.uniform(-10, 15),
           "spark": btc_spark}
    glob = {"btc_dom": rnd.uniform(55, 62)}
    base_rnd = random.Random(7)  # 코인 구성은 실행마다 동일
    universe = []
    for i in range(160):
        mc = 10 ** base_rnd.uniform(7.3, 10.5)
        universe.append({"id": f"coin-{i}", "sym": f"C{i}", "name": f"Coin {i}", "mc0": mc})
    cats = {}
    for s in SECTORS:
        members = base_rnd.sample(universe, 45)
        drift = rnd.uniform(-15, 25)
        rows = []
        for u in members:
            c30 = drift + rnd.uniform(-25, 25)
            c7 = c30 / 3 + rnd.uniform(-8, 8)
            px = u["mc0"] / 1e8 * (1 + c30 / 100)
            spark = [px * (1 - c7 / 100 * (1 - k / 41)) * (1 + rnd.uniform(-0.02, 0.02)) for k in range(42)]
            mc = u["mc0"] * (1 + c30 / 100)
            rows.append({"id": u["id"], "sym": u["sym"], "name": u["name"], "px": px, "mc": mc,
                         "fdv": mc / rnd.uniform(0.3, 1.0), "vol": mc * rnd.uniform(0.01, 0.4),
                         "dd": rnd.uniform(-97, -5), "c1h": rnd.uniform(-2, 2), "c24": rnd.uniform(-6, 6),
                         "c7": c7, "c30": c30, "spark": spark})
        cats[s["key"]] = sorted(rows, key=lambda r: -r["mc"])
    chain = {s["key"]: {"stable7": rnd.uniform(-3, 3), "tvl7": rnd.uniform(-8, 8), "dex": rnd.uniform(-25, 30)}
             for s in SECTORS if s.get("llama")}
    fees = {u["id"]: u["mc0"] * rnd.uniform(0.001, 0.02) for u in universe[:60]}
    derivs, dstat = {}, {}
    pxmap = {}
    for rows in cats.values():
        for r in rows:
            pxmap[r["sym"]] = r["px"]
    for ex in EXCHANGES:
        if ex == "Binance":
            dstat[ex] = "HTTPError 451 (모의)"
            continue
        d = {}
        for sym, px in pxmap.items():
            if base_rnd.random() < 0.6:
                d[sym] = {"oi": rnd.uniform(1e6, 3e8), "fund_h": rnd.uniform(-0.00002, 0.00006),
                          "px24": rnd.uniform(-5, 5), "px": px, "raw": sym + "USDT" if ex != "OKX" else sym + "-USDT-SWAP"}
        derivs[ex] = d
        dstat[ex] = "ok"
    return btc, glob, cats, chain, fees, derivs, dstat


# ═════════════════════════ 분석 ═════════════════════════
def excluded(c):
    name = " " + c["name"].lower()
    return (c["sym"].lower() in STABLE_SYMS or any(w in name for w in EXCLUDE_WORDS)
            or (c["px"] and 0.97 <= c["px"] <= 1.03) or not c["px"] or c["c30"] is None or c["c7"] is None)


def analyze_coin(c, derivs, dvol, fees, today):
    venues = {ex: d[c["sym"]] for ex, d in derivs.items() if c["sym"] in d and px_match(d[c["sym"]]["px"], c["px"])}
    oi = sum(v["oi"] for v in venues.values())
    fr = [(v["fund_h"], v["oi"]) for v in venues.values() if v["fund_h"] is not None]
    fund_apr = sum(f * w for f, w in fr) / sum(w for _, w in fr) * 24 * 365 * 100 if fr else None
    sp = c["spark"]
    prev = [v for d, v in dvol.get(c["id"], []) if d != today]
    vr = c["vol"] / statistics.mean(prev) if len(prev) >= 5 and statistics.mean(prev) > 0 else None
    fee30 = fees.get(c["id"])
    return {**c, "venues": venues, "oi": oi, "fund_apr": fund_apr,
            "turn": c["vol"] / c["mc"] if c["mc"] else None,
            "float": c["mc"] / c["fdv"] if c.get("fdv") else None,
            "ma7": statistics.mean(sp) if sp else None, "low7": min(sp) if sp else None,
            "vr": vr, "pf": c["mc"] / (fee30 * 365 / 30) if fee30 else None,
            "link": tv_link(venues, c["id"])}


def reliability(a, user_venue_check):
    fails = []
    if a["mc"] < TH["minor_mcap"]:
        fails.append("시총 작음")
    if a["vol"] < TH["min_volume"]:
        fails.append("거래량 부족")
    if a["turn"] is not None and not (TH["turnover_min"] <= a["turn"] <= TH["turnover_max"]):
        fails.append("회전율 이상")
    if a["float"] is not None and a["float"] < TH["float_min"]:
        fails.append("유통량 적음")
    if a["dd"] is not None and a["dd"] < TH["ath_dd_min"]:
        fails.append("고점 대비 붕괴")
    if user_venue_check and not any(v in a["venues"] for v in USER_VENUES):
        fails.append("내 거래소 미상장")
    return fails


def sector_signals(stable7, dex, oi24, fund_apr, px24, breadth, med7, rs7):
    def chk(label, cond, why):
        return {"label": label, "ok": cond, "why": why}
    early = [
        chk("BTC보다 강함 (7일)", None if rs7 is None else rs7 > 0, "섹터를 파는 사람이 줄고 돈이 옮겨오는 중. BTC가 급락할 때 '덜 빠진 것'이면 가짜 신호"),
        chk("스테이블코인 유입 (7일)", None if stable7 is None else stable7 >= TH["stable_in_pct"], "체인 위에 쓸 수 있는 달러가 늘었다는 뜻. 거래소 지갑 이동이 섞일 수 있음"),
        chk("DEX 거래 증가 (주간)", None if dex is None else dex >= TH["dex_up_pct"], "들어온 달러가 실제로 쓰이는 중. 봇 거래로 부풀려질 수 있음"),
        chk("현물이 끌고 가는 상승", None if oi24 is None or fund_apr is None else (oi24 > 0 and abs(fund_apr) <= TH["funding_neutral_apr"]), "선물 포지션은 늘지만 롱 쏠림이 없음. 청산 연쇄 위험이 낮은 상승"),
        chk("섹터 전체로 확산", None if breadth is None else breadth >= TH["breadth_strong"], "대장만이 아니라 여러 코인이 함께 오름. 테마에 돈이 붙었다는 뜻"),
    ]
    late = [
        chk("롱 쏠림 과열", None if fund_apr is None else fund_apr >= TH["funding_hot_apr"], "살 사람이 거의 다 샀다는 뜻. 작은 하락이 연쇄 청산으로 번질 수 있음"),
        chk("레버리지만 늘고 가격 정체", None if oi24 is None or px24 is None else (oi24 >= TH["oi_jump_pct"] and abs(px24) < TH["price_flat_pct"]), "누군가 받아주며 팔고 있을 가능성"),
        chk("달러는 빠지는데 가격 유지", None if stable7 is None or med7 is None else (stable7 <= TH["stable_out_pct"] and med7 > 0), "가격을 받치던 돈이 빠지는 중"),
    ]
    e = sum(1 for c in early if c["ok"])
    l = sum(1 for c in late if c["ok"])
    avail = sum(1 for c in early if c["ok"] is not None)
    need = max(2, -(-avail * 3 // 5))  # 확인 가능한 신호의 60% 이상 (최소 2개)
    if l >= 2:
        label = "과열 경고"
    elif e >= need and l == 0:
        label = "초입 정황"
    elif l == 1:
        label = "주의"
    elif e >= 2:
        label = "개선 중"
    else:
        label = "중립"
    return early, late, e, l, avail, label


def analyze_sector(s, rows, coins, btc, chain, oi_prev, user_check, n_ok):
    pool = [coins[r["id"]] for r in rows if r["id"] in coins]
    pool.sort(key=lambda a: -a["mc"])
    qual = []
    for rank, a in enumerate(pool, 1):
        venues_needed = min(TH["major_venues"], max(n_ok, 1))
        if rank <= TH["major_rank"] and a["mc"] >= TH["major_mcap"] and len(a["venues"]) >= venues_needed:
            qual.append((a, "메이저"))
        elif not reliability(a, user_check):
            qual.append((a, "신뢰 마이너"))
    res = {"s": s, "qual": qual, "n_pool": len(pool)}
    if len(qual) < 3:
        res.update(label="데이터 부족", strong=False, early=[], late=[], e=0, l=0, avail=0)
        return res
    q = [a for a, _ in qual]
    med7, med30 = med([a["c7"] for a in q]), med([a["c30"] for a in q])
    rs7 = med7 - btc["c7"] if med7 is not None and btc.get("c7") is not None else None
    rs30 = med30 - btc["c30"] if med30 is not None and btc.get("c30") is not None else None
    breadth = sum(1 for a in q if a["c7"] > 0) / len(q) * 100
    by_ex, fw, fn, pw, pn = {}, 0.0, 0.0, 0.0, 0.0
    for a in q:
        for ex, v in a["venues"].items():
            by_ex[ex] = by_ex.get(ex, 0) + v["oi"]
            if v["fund_h"] is not None:
                fw, fn = fw + v["fund_h"] * v["oi"], fn + v["oi"]
            if v["px24"] is not None:
                pw, pn = pw + v["px24"] * v["oi"], pn + v["oi"]
    fund_apr = fw / fn * 24 * 365 * 100 if fn else None
    px24 = pw / pn if pn else None
    common = [ex for ex in by_ex if oi_prev.get(ex)]
    oi24 = pct(sum(by_ex[e] for e in common), sum(oi_prev[e] for e in common)) if common else None
    ch = chain.get(s["key"], {})
    early, late, e, l, avail, label = sector_signals(ch.get("stable7"), ch.get("dex"), oi24, fund_apr, px24, breadth, med7, rs7)
    strong = label != "과열 경고" and (label in ("초입 정황", "개선 중") or ((rs7 or 0) > 0 and (rs30 or 0) > 0))
    pfs = [a["pf"] for a in q if a["pf"]]
    res.update(med7=med7, med30=med30, rs7=rs7, rs30=rs30, breadth=breadth, oi=sum(by_ex.values()) or None,
               oi24=oi24, oi_by_ex=by_ex, fund_apr=fund_apr, px24=px24, early=early, late=late, e=e, l=l,
               avail=avail, label=label, strong=strong, pf_med=med(pfs) if len(pfs) >= 3 else None,
               stable7=ch.get("stable7"), dex=ch.get("dex"), tvl7=ch.get("tvl7"))
    return res


def evaluate_candidate(a, tier, sec):
    lag = sec["med30"] - a["c30"]
    above = a["ma7"] is not None and a["px"] > a["ma7"]
    vol_ok = None if a["vr"] is None else a["vr"] >= TH["vol_surge"]
    fund_ok = a["fund_apr"] is None or a["fund_apr"] < TH["coin_funding_max"]
    pf_cheap = bool(a["pf"] and sec.get("pf_med") and a["pf"] < sec["pf_med"])
    grade = None
    if sec["strong"] and lag >= TH["lag_min"] and fund_ok:
        if above and vol_ok:
            grade = "red"
        elif above or vol_ok:
            grade = "yellow"
    vr_bonus = (min(a["vr"], 3) - 1) * 10 if a["vr"] and a["vr"] > 1 else 0
    score = min(lag, 40) + vr_bonus + max(min(sec["rs30"] or 0, 20), 0) + (10 if pf_cheap else 0)
    s = sec["s"]
    why = []
    if sec["label"] in ("초입 정황", "개선 중"):
        why.append(f"{s['name']} 섹터로 돈이 들어오는 신호가 있음")
    elif sec["rs30"] is not None:
        why.append(f"{s['name']} 섹터가 30일간 BTC보다 {sec['rs30']:+.0f}%p " + ("강함" if sec["rs30"] > 0 else "약함"))
    why.append(f"섹터 평균보다 30일간 {lag:.0f}%p 덜 올랐음")
    if vol_ok:
        why.append(f"오늘 거래량이 평소의 {a['vr']:.1f}배")
    if above:
        why.append("7일 평균 가격 위로 올라섬")
    if pf_cheap:
        why.append("벌어들이는 수수료에 비해 시총이 섹터 평균보다 낮음")
    risk = []
    if a["float"] is not None and a["float"] < 0.7:
        risk.append(f"유통량이 전체의 {a['float'] * 100:.0f}%. 남은 물량이 풀리면 매도 압력")
    if a["fund_apr"] is not None and a["fund_apr"] > 20:
        risk.append(f"선물 롱 쏠림 (펀딩 연 {a['fund_apr']:.0f}%)")
    if a["mc"] < 150e6:
        risk.append("시총이 작아 가격이 크게 흔들릴 수 있음")
    if a["turn"] is not None and a["turn"] > 0.3:
        risk.append("거래가 과열됨. 급등락 주의")
    if a["dd"] is not None and a["dd"] < -85:
        risk.append(f"고점 대비 {a['dd']:.0f}%. 오래 약세였던 코인")
    if sec["label"] == "주의":
        risk.append("섹터에 과열 신호가 1개 있음")
    if vol_ok is None:
        risk.append("거래량 비교 데이터가 아직 쌓이는 중")
    if not risk:
        risk.append("눈에 띄는 위험은 없음. 레버리지는 여전히 주의")
    return {"a": a, "tier": tier, "sec": sec, "grade": grade, "score": score, "lag": lag,
            "above": above, "vol_ok": vol_ok, "pf_cheap": pf_cheap, "why": why, "risk": risk[:2]}


# ═════════════════════════ 기록·성적표·알림 ═════════════════════════
def update_log(log, picks, coins, sectors_by_key, now_ts):
    new_red = []
    for grade in ("red", "yellow"):
        # 같은 코인·같은 등급은 7일에 한 번만 기록 (표본 중복·알림 반복 방지)
        seen = {e["id"] for e in log if e["g"] == grade and now_ts - e["ts"] < 7 * 86400}
        for p in picks[grade]:
            a = p["a"]
            if a["id"] in seen:
                continue
            log.append({"ts": now_ts, "id": a["id"], "sym": a["sym"], "sec": p["sec"]["s"]["key"], "g": grade,
                        "px": a["px"], "low7": a["low7"], "r7": None, "x7": None, "r30": None, "x30": None, "inv": None})
            if grade == "red":
                new_red.append(p)
    for e in log:
        a = coins.get(e["id"])
        sec = sectors_by_key.get(e["sec"])
        if not a or not a["px"]:
            continue
        age = now_ts - e["ts"]
        if e["inv"] is None and e.get("low7") and a["px"] < e["low7"]:
            e["inv"] = now_ts
        if e["r7"] is None and age >= 7 * 86400:
            e["r7"] = pct(a["px"], e["px"])
            if sec and sec.get("med7") is not None and e["r7"] is not None:
                e["x7"] = e["r7"] - sec["med7"]
        if e["r30"] is None and age >= 30 * 86400:
            e["r30"] = pct(a["px"], e["px"])
            if sec and sec.get("med30") is not None and e["r30"] is not None:
                e["x30"] = e["r30"] - sec["med30"]
    return log[-3000:], new_red


def scoreboard(log):
    out = {}
    for g in ("red", "yellow"):
        done = [e for e in log if e["g"] == g and e["x7"] is not None]
        wins = sum(1 for e in done if e["x7"] > 0)
        out[g] = {"n": len(done), "wins": wins, "rate": wins / len(done) * 100 if done else None,
                  "avg": statistics.mean(e["x7"] for e in done) if done else None,
                  "total": sum(1 for e in log if e["g"] == g)}
    return out


def telegram(picks):
    if not (TG_TOKEN and TG_CHAT) or not picks:
        return None
    lines = []
    for p in picks:
        a = p["a"]
        lines.append(f"🔴 {a['sym']} ({p['sec']['s']['name']})\n왜: " + " / ".join(p["why"][1:3]) +
                     f"\n위험: {p['risk'][0]}\n무효: 7일 저점 {f_px(a['low7'])} 이탈 시\n차트: {a['link'][1]}")
    if PAGE_URL:
        lines.append(f"전체 보기: {PAGE_URL}")
    try:
        get_json(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", method="POST",
                 body={"chat_id": TG_CHAT, "text": "\n\n".join(lines), "disable_web_page_preview": True}, retries=2)
        return None
    except Exception as e:
        return f"텔레그램 전송 실패: {type(e).__name__}"


# ═════════════════════════ 렌더링 ═════════════════════════
def esc(x):
    return html.escape(str(x))


def f_pct(v, d=1, pp=False):
    if v is None:
        return '<span class="na">—</span>'
    cls = "up" if v > 0 else "down" if v < 0 else ""
    return f'<span class="{cls}">{v:+.{d}f}{"%p" if pp else "%"}</span>'


def f_usd(v):
    if not v:
        return '<span class="na">—</span>'
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            return f"${v / div:,.1f}{unit}"
    return f"${v:,.0f}"


def f_px(v):
    if not v:
        return "—"
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:,.2f}"
    return f"${v:.4g}"


LABEL_CLS = {"초입 정황": "l-early", "개선 중": "l-improve", "중립": "l-neutral", "주의": "l-caution",
             "과열 경고": "l-hot", "데이터 부족": "l-neutral"}
LABEL_SAY = {
    "초입 정황": "돈이 들어오기 시작한 정황이 여러 개. 가장 눈여겨볼 상태",
    "개선 중": "좋아지는 신호가 일부 있음",
    "중립": "뚜렷한 방향 없음",
    "주의": "과열 신호가 1개 있음. 새로 들어가기엔 조심",
    "과열 경고": "과열 신호가 2개 이상. 이 섹터에서는 새로 들어가지 않는 편이 안전",
    "데이터 부족": "기준을 통과한 코인이 3개 미만",
}
GLOSSARY = [
    ("섹터 중앙값", "섹터 안 코인들의 수익률을 줄 세웠을 때 가운데 값. 대장 코인 하나에 휘둘리지 않는 '섹터 평균'."),
    ("메이저 / 신뢰 마이너", "메이저: 섹터 시총 상위 5위 안 + 시총 1조 원대 이상 + 선물이 여러 거래소에 상장. 신뢰 마이너: 시총 약 700억 원 이상이면서 거래량·유통량·거래소 상장 기준을 통과한 코인. 둘 다 아니면 화면에 나오지 않습니다."),
    ("7일 평균 가격", "최근 7일 가격의 평균. 현재가가 이 위로 올라섰다는 건 단기 흐름이 위로 돌아섰을 가능성."),
    ("거래량 배수", "오늘 거래량 ÷ 최근 며칠 평균 거래량. 1.5배 이상이면 평소보다 관심이 몰린 것."),
    ("유통량 비율", "지금 시장에 풀린 물량 ÷ 전체 발행 예정 물량. 낮을수록 앞으로 풀릴 물량(매도 압력)이 많음."),
    ("펀딩비", "선물에서 롱과 숏이 서로 주고받는 비용. 연 40% 이상이면 롱이 한쪽으로 크게 쏠린 상태."),
    ("OI (미결제약정)", "아직 정리되지 않은 선물 포지션의 총액. 늘면 레버리지 돈이 새로 들어오는 중."),
    ("스테이블코인 유입", "체인 위의 달러(USDT·USDC) 총량 변화. 늘면 그 체인에서 쓸 수 있는 실탄이 늘어난 것."),
    ("수수료 대비 시총", "1년치 수수료 수입 대비 시총. 주식의 PER과 비슷. 같은 섹터 안에서 낮을수록 상대적으로 싸다."),
]
CHECKLIST = ["일봉에서 고점과 저점이 높아지는 구조로 바뀌었는가", "무효 가격(7일 저점)과 현재가 거리가 감당할 만한가",
             "상승하는 봉에 거래량이 함께 붙었는가"]


def tag(s):
    return f'<span class="tag">#{esc(s["name"].replace(" ", "_"))}</span>'


def coin_row(p, spark_ids, extra=""):
    a = p["a"]
    spark_ids.add(a["id"])
    return (f'<tr><td><b>{esc(a["sym"])}</b><small>{esc(a["name"][:18])}</small></td><td><span class="tier">{p["tier"]}</span></td>'
            f'<td>{f_pct(a["c7"])}</td><td>{f_pct(a["c30"])}</td>{extra}'
            f'<td class="act"><a href="{esc(a["link"][1])}" target="_blank" rel="noopener">차트</a>'
            f'<button class="cmp" data-id="{esc(a["id"])}" aria-pressed="false">비교</button></td></tr>')


def focus_callout(p, spark_ids):
    a = p["a"]
    spark_ids.add(a["id"])
    why = "".join(f"<li>{esc(w)}</li>" for w in p["why"])
    risk = "".join(f"<li>{esc(r)}</li>" for r in p["risk"])
    chk = "".join(f"<li>{esc(c)}</li>" for c in CHECKLIST)
    return f"""
<div class="callout focus">
  <div class="c-title"><span class="c-icon" aria-hidden="true">◆</span><b>{esc(a["sym"])}</b><span class="c-name">{esc(a["name"])}</span></div>
  <div class="tags">{tag(p["sec"]["s"])}<span class="tag muted">#{p["tier"].replace(" ", "_")}</span></div>
  <p class="c-sub">왜 봐야 하나</p><ul>{why}</ul>
  <p class="c-sub">위험</p><ul>{risk}</ul>
  <p class="c-sub">무효 조건</p><p>7일 저점 <b>{f_px(a["low7"])}</b> 아래로 내려가거나 섹터가 '과열 경고'로 바뀌면 목록에서 빠집니다. 현재가 {f_px(a["px"])}</p>
  <details class="inner"><summary>차트에서 확인할 것</summary><ul class="check">{chk}</ul></details>
  <div class="c-actions"><a class="btn" href="{esc(a["link"][1])}" target="_blank" rel="noopener">{esc(a["link"][0])}에서 차트 열기</a>
  <button class="cmp btn ghost" data-id="{esc(a["id"])}" aria-pressed="false">비교 차트에 추가</button></div>
  <details class="inner"><summary>숫자로 보기</summary><table class="kv">
   <tr><td>30일 / 7일</td><td>{f_pct(a["c30"])} / {f_pct(a["c7"])}</td></tr>
   <tr><td>섹터보다 덜 오른 폭 (30일)</td><td>{p["lag"]:.1f}%p</td></tr>
   <tr><td>거래량 배수</td><td>{"—" if a["vr"] is None else f'{a["vr"]:.2f}배'}</td></tr>
   <tr><td>시총 / 유통량 비율</td><td>{f_usd(a["mc"])} / {"—" if a["float"] is None else f'{a["float"] * 100:.0f}%'}</td></tr>
   <tr><td>펀딩 연환산</td><td>{f_pct(a["fund_apr"])}</td></tr>
   <tr><td>상장 선물 거래소</td><td>{esc(", ".join(a["venues"]) or "없음")}</td></tr>
  </table></details>
</div>"""


def bt_verdict(bt):
    if not bt:
        return "아직 없음 (Actions → backfill 실행)", "na"
    s = bt["summary"]["red"]
    if (s["n7"] or 0) < 30:
        return f"표본 부족 ({s['n7']}개)", "warn-text"
    if s["win7"] >= 55 and (s["avg7"] or 0) > 0:
        return f"통과: 7일 뒤 섹터보다 좋았던 비율 {s['win7']:.0f}% ({s['n7']}개)", "up"
    return f"미달: 7일 뒤 섹터보다 좋았던 비율 {s['win7']:.0f}% ({s['n7']}개). 기준 조정 필요", "down"


def bt_section(bt):
    if not bt:
        return ('<h4>백테스트</h4><p class="na">아직 실행하지 않았습니다. Actions 탭 → backfill → Run workflow를 한 번 실행하면 '
                '과거 1년 데이터로 이 규칙의 성적을 계산합니다.</p>')

    def row(name, s):
        def pc(v):
            return '<span class="na">—</span>' if v is None else f"{v:.0f}%"
        return (f'<tr><td>{name}</td><td>{s["n7"]}</td><td>{pc(s["win7"])}</td><td>{f_pct(s["avg7"], 1, True)}</td>'
                f'<td>{pc(s["win30"])}</td><td>{f_pct(s["avg30"], 1, True)}</td><td>{pc(s["stop"])}</td></tr>')
    sm = bt["summary"]

    def pc0(v):
        return "—" if v is None else f"{v:.0f}%"
    secs = "".join(
        f'<tr><td>{esc(k)}</td><td>{v["n7"]}</td><td>{pc0(v["win7"])}</td><td>{f_pct(v["avg7"], 1, True)}</td></tr>'
        for k, v in bt["by_sector"].items())
    recent = "".join(
        f'<tr><td>{esc(t["date"][5:])}</td><td><b>{esc(t["sym"])}</b></td><td>{esc(t["sec"])}</td><td>{f_pct(t["r7"])}</td>'
        f'<td>{f_pct(t["x7"], 1, True)}</td><td>{"이탈" if t["stop"] else ""}</td></tr>' for t in reversed(bt["recent"][-15:]))
    return f"""<h4>백테스트 (과거 {esc(bt["start"])} ~ {esc(bt["end"])}, 코인 {bt["coins"]}개)</h4>
<div class="tbl"><table class="list"><tr><th>구분</th><th>표본</th><th>7일 뒤 섹터보다 좋았던 비율</th><th>7일 평균 초과</th><th>30일 비율</th><th>30일 평균 초과</th><th>무효가 이탈</th></tr>
{row("지금 볼 것", sm["red"])}{row("관심 목록", sm["yellow"])}</table></div>
<p class="na">섹터 안에서 무작위로 골랐다면 '섹터보다 좋았던 비율'은 약 50%가 기준입니다. 55% 이상이면서 평균 초과가 플러스여야 의미가 있습니다.</p>
<details class="inner"><summary>백테스트의 한계</summary><ul>
<li>지금 카테고리에 남은 코인만으로 과거를 돌렸습니다(사라진 코인 제외). 실제보다 결과가 좋게 나올 수 있습니다.</li>
<li>과거의 선물·스테이블코인 데이터가 없어 '강한 섹터'를 가격(BTC 대비 7일·30일)으로만 판정했습니다.</li>
<li>수수료·슬리피지는 빼지 않았습니다. 이 결과를 보고 기준을 반복해서 바꾸면 과거에만 맞는 규칙이 됩니다.</li></ul></details>
<details class="inner"><summary>섹터별 성적</summary><div class="tbl"><table class="list"><tr><th>섹터</th><th>표본</th><th>섹터보다 좋았던 비율</th><th>평균 초과</th></tr>{secs}</table></div></details>
<details class="inner"><summary>최근 과거 강조 사례</summary><div class="tbl"><table class="list"><tr><th>날짜</th><th>코인</th><th>섹터</th><th>7일 수익</th><th>섹터 대비</th><th>무효가</th></tr>{recent}</table></div></details>"""


def render(ctx):
    now, btc, glob, sectors, picks, board, dstat, errors, meta = (
        ctx["now"], ctx["btc"], ctx["glob"], ctx["sectors"], ctx["picks"], ctx["board"], ctx["dstat"], ctx["errors"], ctx["meta"])
    spark_ids = set()

    # 속성
    ex_pills = "".join(f'<span class="pill {"ok" if dstat.get(ex) == "ok" else "bad"}">{"✓" if dstat.get(ex) == "ok" else "✕"} {ex}</span>' for ex in EXCHANGES)
    red_b, yel_b = board["red"], board["yellow"]
    bt = ctx.get("bt")
    if red_b["n"] < TH["verify_min_samples"]:
        verdict = f'실전 <span class="warn-text">검증 전</span> ({red_b["n"]}/{TH["verify_min_samples"]}개)'
    else:
        verdict = f'실전 {red_b["n"]}개 중 {red_b["wins"]}개가 섹터보다 좋았음 ({red_b["rate"]:.0f}%)'
    bt_say, bt_cls = bt_verdict(bt)
    verdict += f'<br>백테스트 <span class="{bt_cls}">{bt_say}</span>'
    props = f"""
<dl class="props">
 <div><dt>갱신</dt><dd>{now:%Y-%m-%d %H:%M} KST</dd></div>
 <div><dt>섹터 데이터</dt><dd>{meta["cat_age"]} (4시간마다)</dd></div>
 <div><dt>선물 데이터</dt><dd>{ex_pills}</dd></div>
 <div><dt>관찰 기간</dt><dd>{meta["obs"]}</dd></div>
 <div><dt>도구 성적</dt><dd>{verdict}</dd></div>
</dl>"""

    # BTC 필터
    c7 = btc.get("c7")
    if c7 is None:
        btc_say = "BTC 데이터를 받지 못했습니다. 아래 판정은 참고만 하세요."
    elif c7 <= -8:
        btc_say = "BTC가 1주일 새 크게 빠졌습니다. 이럴 땐 아래 신호 대부분이 믿기 어렵습니다."
    elif c7 <= -3:
        btc_say = "BTC가 약세입니다. 새로 들어가는 건 보수적으로."
    else:
        btc_say = "BTC 흐름은 정상 범위입니다."
    btc_block = f"""
<div class="callout info"><div class="c-title"><span class="c-icon" aria-hidden="true">◇</span><b>먼저 BTC</b></div>
<p>{btc_say}</p>
<p class="nums">{f_px(btc.get("px"))} <span>7일 {f_pct(c7)}</span> <span>30일 {f_pct(btc.get("c30"))}</span> <span>도미넌스 {"—" if glob.get("btc_dom") is None else f'{glob["btc_dom"]:.1f}%'}</span></p></div>"""

    # 지금 볼 것
    if picks["red"]:
        focus = "".join(focus_callout(p, spark_ids) for p in picks["red"])
    else:
        why_empty = meta["empty_reason"]
        focus = f'<div class="callout empty"><div class="c-title"><b>지금은 없음</b></div><p>{esc(why_empty)}</p></div>'

    # 관심 목록
    if picks["yellow"]:
        rows = "".join(
            coin_row(p, spark_ids, f'<td>{tag(p["sec"]["s"])}</td><td class="why">{esc(p["why"][1])}</td>') for p in picks["yellow"])
        watch = f'<div class="tbl"><table class="list"><tr><th>코인</th><th>등급</th><th>7일</th><th>30일</th><th>섹터</th><th>이유</th><th></th></tr>{rows}</table></div>'
    else:
        watch = '<p class="na">관심 목록 조건을 통과한 코인이 없습니다.</p>'

    # 섹터
    sec_html = []
    for sec in sorted(sectors, key=lambda x: (x["label"] == "데이터 부족", -(x.get("rs30") or -999))):
        s = sec["s"]
        head = (f'<summary><span class="s-name">{esc(s["name"])}</span><span class="kind">{s["kind"]}</span>'
                f'<span class="label {LABEL_CLS[sec["label"]]}">{sec["label"]}</span>'
                f'<span class="s-rs">BTC 대비 30일 {f_pct(sec.get("rs30"), 0, True)}</span></summary>')
        if sec["label"] == "데이터 부족":
            sec_html.append(f'<details class="sector">{head}<p class="na">{LABEL_SAY["데이터 부족"]} (후보 {sec["n_pool"]}개 중)</p></details>')
            continue
        gain = sorted(sec["qual"], key=lambda t: -t[0]["c7"])[: TH["top_n"]]
        gain_rows = "".join(coin_row({"a": a, "tier": t}, spark_ids) for a, t in gain)
        cands = sorted([c for c in sec["cands"] if c["lag"] >= TH["lag_min"]], key=lambda c: -c["score"])[: TH["top_n"]]
        cand_rows = "".join(coin_row(c, spark_ids, f'<td>{c["lag"]:.0f}%p</td><td>{"●" if c["above"] else "○"}</td>'
                                     f'<td>{"—" if c["vol_ok"] is None else ("●" if c["vol_ok"] else "○")}</td>') for c in cands) \
            or '<tr><td colspan="8" class="na">섹터 평균보다 크게 덜 오른 신뢰 코인이 없음</td></tr>'
        strong_note = "강한 섹터라 후보를 강조 대상에 포함합니다." if sec["strong"] else "강한 섹터가 아니라 아래 후보는 강조하지 않습니다."
        sig = "".join(f'<li class="{"hit" if c["ok"] else "na" if c["ok"] is None else "miss"}"><span>{"●" if c["ok"] else "—" if c["ok"] is None else "○"}</span><div><b>{esc(c["label"])}</b><small>{esc(c["why"])}</small></div></li>' for c in sec["early"])
        sig_l = "".join(f'<li class="{"warnhit" if c["ok"] else "na" if c["ok"] is None else "miss"}"><span>{"●" if c["ok"] else "—" if c["ok"] is None else "○"}</span><div><b>{esc(c["label"])}</b><small>{esc(c["why"])}</small></div></li>' for c in sec["late"])
        chain_kv = "" if s["kind"] != "체인" else (
            f'<tr><td>스테이블코인 7일</td><td>{f_pct(sec.get("stable7"))}</td></tr>'
            f'<tr><td>DEX 거래량 주간</td><td>{f_pct(sec.get("dex"))}</td></tr>'
            f'<tr><td>TVL 7일 (가격 착시 포함)</td><td>{f_pct(sec.get("tvl7"))}</td></tr>')
        sec_html.append(f"""
<details class="sector">{head}
 <p>{LABEL_SAY[sec["label"]]}. {strong_note}</p>
 <h4>지금 오르는 코인</h4>
 <div class="tbl"><table class="list"><tr><th>코인</th><th>등급</th><th>7일</th><th>30일</th><th></th></tr>{gain_rows}</table></div>
 <h4>덜 오른 후보</h4>
 <div class="tbl"><table class="list"><tr><th>코인</th><th>등급</th><th>7일</th><th>30일</th><th>덜 오른 폭</th><th>평균가 위</th><th>거래량 급증</th><th></th></tr>{cand_rows}</table></div>
 <details class="inner"><summary>섹터 판정 근거</summary>
  <p class="c-sub">돈이 들어오는 신호 ({sec["e"]}/{sec["avail"]} 확인 가능)</p><ul class="sig">{sig}</ul>
  <p class="c-sub">과열 신호 ({sec["l"]}/3)</p><ul class="sig">{sig_l}</ul>
  <table class="kv"><tr><td>섹터 중앙값 7일 / 30일</td><td>{f_pct(sec["med7"])} / {f_pct(sec["med30"])}</td></tr>
  <tr><td>7일 상승 코인 비율</td><td>{sec["breadth"]:.0f}%</td></tr>
  <tr><td>선물 OI / 24시간 변화</td><td>{f_usd(sec["oi"])} / {f_pct(sec["oi24"])}</td></tr>
  <tr><td>펀딩 연환산</td><td>{f_pct(sec["fund_apr"])}</td></tr>{chain_kv}</table>
 </details>
</details>""")

    # 성적표
    def brow(name, b):
        rate = "—" if b["rate"] is None else f'{b["rate"]:.0f}%'
        avg = f_pct(b["avg"], 1, True) if b["avg"] is not None else '<span class="na">—</span>'
        return f'<tr><td>{name}</td><td>{b["total"]}</td><td>{b["n"]}</td><td>{rate}</td><td>{avg}</td></tr>'
    board_html = f"""<h4>실전 기록</h4><div class="tbl"><table class="list"><tr><th>구분</th><th>누적</th><th>7일 경과</th><th>섹터보다 좋았던 비율</th><th>평균 초과 수익</th></tr>
{brow("지금 볼 것", red_b)}{brow("관심 목록", yel_b)}</table></div>
{bt_section(bt)}"""

    gloss = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in GLOSSARY)
    errs = "" if not errors else '<div class="callout warn"><div class="c-title"><b>받지 못한 데이터</b></div><ul>' + "".join(f"<li>{esc(e)}</li>" for e in errors[:15]) + "</ul></div>"

    sparks = {i: {"s": ctx["coins"][i]["sym"], "p": [round(x, 10) for x in ctx["coins"][i]["spark"]]}
              for i in spark_ids if i in ctx["coins"] and ctx["coins"][i]["spark"]}
    init = [p["a"]["id"] for p in picks["red"]][:3]
    payload = json.dumps({"sp": sparks, "btc": btc.get("spark") or [], "init": init}, separators=(",", ":"))

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="theme-color" content="#1e1e1e">
<title>섹터 모니터</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{CSS}</style></head><body><main class="note">
<h1>섹터 모니터</h1>
{props}
{errs}
{btc_block}
<h2>지금 볼 것</h2>
<p class="lead">모든 조건을 통과한 코인. 최대 {TH["red_max"]}개만 보여줍니다. 차트에서 한 번 더 확인하기 전에는 진입 근거가 아닙니다.</p>
{focus}
<h2>관심 목록</h2>
<p class="lead">조건을 대부분 통과한 코인. 최대 {TH["yellow_max"]}개.</p>
{watch}
<h2>비교 차트</h2>
<p class="lead">최근 7일 수익률을 같은 출발점에서 겹쳐 봅니다. 목록의 '비교' 버튼으로 추가하세요. 점선은 BTC.</p>
<div class="chart-wrap"><svg id="chart" viewBox="0 0 640 280" role="img" aria-label="7일 수익률 비교 차트"></svg><div id="legend"></div></div>
<h2>섹터</h2>
<p class="lead">BTC보다 강한 순서. 눌러서 펼치세요.</p>
{"".join(sec_html)}
<h2>도구 성적표</h2>
{board_html}
<h2>용어</h2>
<details class="sector"><summary><span class="s-name">용어 풀이 펼치기</span></summary><dl class="gloss">{gloss}</dl></details>
<footer>데이터: CoinGecko, DefiLlama, 각 거래소 공개 API. Data provided by CoinGecko. 모든 강조는 확률을 높이는 정황일 뿐 예측이 아닙니다.</footer>
</main>
<script>const D={payload};{JS}</script></body></html>"""


CSS = r"""
:root{--bg:#1e1e1e;--bg2:#262626;--bg3:#2e2e2e;--line:#363636;--text:#dcddde;--muted:#a3a3a3;--faint:#747474;
--accent:#a88bfa;--accent-bg:rgba(168,139,250,.10);--accent-line:rgba(168,139,250,.45);
--up:#5cc99a;--down:#e5776e;--amber:#e3b25c;--amber-bg:rgba(227,178,92,.10);--info:#6ea8e0;--info-bg:rgba(110,168,224,.09)}
@media (prefers-color-scheme:light){:root{--bg:#ffffff;--bg2:#f6f6f6;--bg3:#efefef;--line:#e2e2e2;--text:#222;--muted:#5c5c5c;--faint:#8a8a8a;
--accent:#7652e8;--accent-bg:rgba(118,82,232,.07);--accent-line:rgba(118,82,232,.4);--up:#17895a;--down:#c9463c;--amber:#a8730f;--amber-bg:rgba(168,115,15,.08);--info:#2e6db0;--info-bg:rgba(46,109,176,.07)}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 "Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
.note{max-width:760px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:2rem;font-weight:700;letter-spacing:-.02em;margin:0 0 18px}
h2{font-size:1.35rem;font-weight:650;letter-spacing:-.01em;margin:44px 0 6px}
h4{font-size:.95rem;font-weight:600;margin:20px 0 6px;color:var(--muted)}
p{margin:.4em 0}
.lead{color:var(--muted);font-size:.92rem;margin-bottom:14px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.na{color:var(--faint)}.up{color:var(--up)}.down{color:var(--down)}.warn-text{color:var(--amber);font-weight:600}
/* 옵시디언 속성 */
.props{margin:0 0 28px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:8px 0}
.props div{display:grid;grid-template-columns:110px 1fr;gap:12px;padding:5px 0;font-size:.9rem}
.props dt{color:var(--muted)}.props dd{margin:0}
.pill{display:inline-block;font-size:.78rem;padding:1px 8px;border-radius:999px;margin:0 4px 4px 0;background:var(--bg3)}
.pill.ok{color:var(--up)}.pill.bad{color:var(--faint);text-decoration:line-through}
/* 콜아웃 */
.callout{border-radius:6px;padding:14px 16px;margin:12px 0;background:var(--bg2)}
.callout ul{margin:.2em 0 .6em;padding-left:1.2em}.callout li{margin:.15em 0}
.c-title{display:flex;align-items:baseline;gap:8px;font-size:1.02rem}
.c-icon{font-size:.9rem}.c-name{color:var(--muted);font-size:.88rem}
.c-sub{font-size:.8rem;color:var(--muted);margin:12px 0 2px;font-weight:600}
.callout.focus{background:var(--accent-bg);box-shadow:inset 3px 0 0 var(--accent)}
.callout.focus .c-title{color:var(--accent);font-size:1.25rem}
.callout.info{background:var(--info-bg)}.callout.info .c-title{color:var(--info)}
.callout.warn{background:var(--amber-bg)}.callout.warn .c-title{color:var(--amber)}
.callout.empty{background:var(--bg2);color:var(--muted)}
.nums{font-variant-numeric:tabular-nums;font-weight:600}.nums>span{font-weight:400;color:var(--muted);margin-left:12px;white-space:nowrap;display:inline-block}
.tags{margin:6px 0 2px}
.tag{display:inline-block;font-size:.8rem;color:var(--accent);background:var(--accent-bg);padding:0 8px;border-radius:999px;margin-right:4px;white-space:nowrap}
.tag.muted{color:var(--muted);background:var(--bg3)}
.c-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.btn{display:inline-block;font:inherit;font-size:.88rem;padding:7px 14px;border-radius:6px;background:var(--accent);color:#fff;border:0;cursor:pointer}
.btn:hover{text-decoration:none;filter:brightness(1.08)}
.btn.ghost{background:transparent;color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent-line)}
.btn.ghost[aria-pressed=true]{background:var(--accent-bg)}
/* 접는 헤딩 (옵시디언 fold) */
details>summary{cursor:pointer;list-style:none}details>summary::-webkit-details-marker{display:none}
details.sector{border-bottom:1px solid var(--line)}
details.sector>summary{display:flex;align-items:center;gap:10px;padding:12px 0;flex-wrap:wrap}
details.sector>summary::before,details.inner>summary::before{content:"";width:0;height:0;border-left:5px solid var(--faint);border-top:4px solid transparent;border-bottom:4px solid transparent;transition:transform .15s}
details[open]>summary::before{transform:rotate(90deg)}
details.sector[open]{padding-bottom:16px}
.s-name{font-weight:650;font-size:1.05rem}.kind{font-size:.75rem;color:var(--faint)}
.s-rs{margin-left:auto;font-size:.85rem;color:var(--muted);font-variant-numeric:tabular-nums}
.label{font-size:.78rem;font-weight:600;padding:1px 8px;border-radius:4px}
.l-early{color:var(--accent);background:var(--accent-bg)}.l-improve{color:var(--info);background:var(--info-bg)}
.l-neutral{color:var(--faint);background:var(--bg3)}.l-caution{color:var(--amber);background:var(--amber-bg)}.l-hot{color:var(--down);background:rgba(229,119,110,.12)}
details.inner{margin:10px 0}details.inner>summary{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:.88rem}
/* 표 */
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.88rem;font-variant-numeric:tabular-nums}
th{color:var(--faint);font-weight:500;text-align:left;font-size:.78rem;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
td small{display:block;color:var(--faint);font-size:.75rem}
td.why{white-space:normal;min-width:160px;color:var(--muted)}
.tier{font-size:.75rem;color:var(--muted)}
td.act{text-align:right}td.act a{margin-right:10px}
.cmp:not(.btn){font:inherit;font-size:.8rem;background:none;border:0;color:var(--muted);cursor:pointer;padding:0}
.cmp[aria-pressed=true]:not(.btn){color:var(--accent);font-weight:600}
table.kv td:first-child{color:var(--muted);white-space:normal}
ul.sig,ul.check{list-style:none;padding:0;margin:4px 0 10px}
ul.sig li{display:flex;gap:10px;padding:4px 0}ul.sig li>span{width:12px;flex:none}
ul.sig small{display:block;color:var(--faint)}
ul.sig li.hit>span{color:var(--up)}ul.sig li.warnhit>span{color:var(--down)}ul.sig li.miss>span,ul.sig li.na>span{color:var(--faint)}
ul.check li::before{content:"☐ ";color:var(--muted)}
/* 차트 */
.chart-wrap{background:var(--bg2);border-radius:6px;padding:10px}
#chart{width:100%;height:auto;display:block}
#legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.82rem;padding:6px 4px 0}
#legend button{font:inherit;background:none;border:0;color:var(--text);cursor:pointer;padding:0}
.gloss dt{font-weight:600;margin-top:12px}.gloss dd{margin:2px 0 0;color:var(--muted)}
footer{margin-top:48px;color:var(--faint);font-size:.8rem}
@media (max-width:560px){.note{padding:24px 14px 60px}h1{font-size:1.6rem}.props div{grid-template-columns:88px 1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = r"""
const COLORS=['#a88bfa','#5cc99a','#e3b25c','#e5776e','#6ea8e0','#c8b45a'];
const sel=new Set(D.init.filter(i=>D.sp[i]));
function norm(p){return p.map(v=>(v/p[0]-1)*100)}
function draw(){
  const svg=document.getElementById('chart'),W=640,H=280,L=44,R=10,T=12,B=26;
  const series=[...sel].slice(0,6).map((id,k)=>({id,name:D.sp[id].s,v:norm(D.sp[id].p),c:COLORS[k]}));
  const btc=D.btc.length?norm(D.btc):null;
  const all=series.flatMap(s=>s.v).concat(btc||[]);
  if(!all.length){svg.innerHTML='<text x="320" y="140" text-anchor="middle" fill="currentColor" opacity=".5" font-size="14">비교할 코인을 추가하세요</text>';document.getElementById('legend').innerHTML='';return}
  let lo=Math.min(0,...all),hi=Math.max(0,...all);const pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;
  const y=v=>T+(hi-v)/(hi-lo)*(H-T-B),x=(i,n)=>L+i/(n-1)*(W-L-R);
  const path=v=>v.map((p,i)=>(i?'L':'M')+x(i,v.length).toFixed(1)+' '+y(p).toFixed(1)).join('');
  let g='';const step=Math.pow(10,Math.floor(Math.log10((hi-lo)/4)));const st=[1,2,5,10].map(m=>m*step).find(s=>(hi-lo)/s<=6);
  for(let v=Math.ceil(lo/st)*st;v<=hi;v+=st){g+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="currentColor" opacity="${Math.abs(v)<1e-9?.35:.1}"/><text x="${L-6}" y="${y(v)+4}" text-anchor="end" font-size="11" fill="currentColor" opacity=".55">${v>0?'+':''}${+v.toFixed(1)}%</text>`}
  g+=`<text x="${L}" y="${H-6}" font-size="11" fill="currentColor" opacity=".55">7일 전</text><text x="${W-R}" y="${H-6}" text-anchor="end" font-size="11" fill="currentColor" opacity=".55">지금</text>`;
  if(btc)g+=`<path d="${path(btc)}" fill="none" stroke="currentColor" stroke-opacity=".45" stroke-width="1.5" stroke-dasharray="4 4"/>`;
  series.forEach(s=>{g+=`<path d="${path(s.v)}" fill="none" stroke="${s.c}" stroke-width="2.2" stroke-linejoin="round"/>`});
  svg.innerHTML=g;
  document.getElementById('legend').innerHTML=series.map(s=>{const last=s.v[s.v.length-1];return `<button data-rm="${s.id}" title="눌러서 빼기"><span style="color:${s.c}">●</span> ${s.name} ${last>0?'+':''}${last.toFixed(1)}% ✕</button>`}).join('')+(btc?`<span style="opacity:.6">┄ BTC ${(btc[btc.length-1]>0?'+':'')+btc[btc.length-1].toFixed(1)}%</span>`:'');
  document.querySelectorAll('.cmp').forEach(b=>b.setAttribute('aria-pressed',sel.has(b.dataset.id)));
}
document.addEventListener('click',e=>{
  const b=e.target.closest('.cmp');
  if(b){const id=b.dataset.id;if(!D.sp[id])return;if(sel.has(id))sel.delete(id);else{if(sel.size>=6){alert('비교는 최대 6개까지');return}sel.add(id)}draw();return}
  const r=e.target.closest('[data-rm]');if(r){sel.delete(r.dataset.rm);draw()}
});
draw();
"""


# ═════════════════════════ 실행 ═════════════════════════
def main():
    now = dt.datetime.fromtimestamp(NOW_TS, KST)
    today = now.strftime("%Y-%m-%d")
    errors = []

    state = load(os.path.join(DATA_DIR, "state.json"), {})
    log = load(os.path.join(DATA_DIR, "log.json"), [])
    dvol = load(os.path.join(DATA_DIR, "volume.json"), {})
    cache = load(os.path.join(CACHE_DIR, "cache.json"), {})
    state.setdefault("started", NOW_TS)
    state.setdefault("oi_hist", [])

    def safe(label, fn, default):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__} {str(e)[:100]}")
            return default

    cat_fresh = False
    if MOCK:
        btc, glob, cats, chain, fees, derivs, dstat = mock_world(NOW_TS // 3600)
        if NOW_TS - cache.get("cat_ts", 0) >= CAT_REFRESH_S:
            cache["cats"], cache["cat_ts"], cat_fresh = cats, NOW_TS, True
        cats = cache["cats"]
    else:
        btc = safe("BTC 가격", fetch_btc, {})
        glob = safe("도미넌스", fetch_global, {})
        # 카테고리 ID 확인 (하루 1번)
        if NOW_TS - cache.get("catlist_ts", 0) >= DAY_REFRESH_S or not cache.get("ids"):
            cl = safe("카테고리 목록", fetch_catlist, None)
            if cl:
                ids, missing = resolve_ids(cl)
                cache["ids"], cache["catlist_ts"], cache["missing"] = ids, NOW_TS, missing
        ids = cache.get("ids") or {s["key"]: s["cg"] for s in SECTORS}
        if cache.get("missing"):
            errors.append("CoinGecko에서 찾지 못한 섹터: " + ", ".join(cache["missing"]))
        # 섹터별 코인 (4시간마다)
        if NOW_TS - cache.get("cat_ts", 0) >= CAT_REFRESH_S or not cache.get("cats"):
            new = {}
            for s in SECTORS:
                if s["key"] in ids:
                    rows = safe(f"섹터 {s['name']}", lambda c=ids[s["key"]]: fetch_category(c), None)
                    if rows:
                        new[s["key"]] = rows
            if new:
                old = cache.get("cats", {})
                old.update(new)
                cache["cats"], cache["cat_ts"], cat_fresh = old, NOW_TS, True
        cats = cache.get("cats", {})
        # 체인·수수료 (하루 1번)
        if NOW_TS - cache.get("day_ts", 0) >= DAY_REFRESH_S:
            chain = {}
            for s in SECTORS:
                if s.get("llama"):
                    chain[s["key"]] = {"stable7": safe(f"스테이블 {s['name']}", lambda c=s["llama"]: fetch_stable(c), None),
                                       "tvl7": safe(f"TVL {s['name']}", lambda c=s["llama"]: fetch_tvl(c), None),
                                       "dex": safe(f"DEX {s['name']}", lambda c=s["dex"]: fetch_dex(c), None)}
            fees_new = safe("수수료", fetch_fees, None)
            cache["chain"], cache["day_ts"] = chain, NOW_TS
            if fees_new:
                cache["fees"] = fees_new
        chain, fees = cache.get("chain", {}), cache.get("fees", {})
        # 선물 (매시간)
        wanted = {c["sym"] for rows in cats.values() for c in rows if c["mc"] >= TH["minor_mcap"]}
        derivs, dstat = {}, {}
        for ex, fn in FETCHERS.items():
            res = safe(f"{ex} 선물", lambda f=fn: f(wanted), None)
            if res:
                derivs[ex], dstat[ex] = res, "ok"
            else:
                dstat[ex] = "fail"

    n_ok = sum(1 for v in dstat.values() if v == "ok")
    user_check = any(dstat.get(v) == "ok" for v in USER_VENUES)
    if not user_check:
        errors.append("내 거래소(Bitget·OKX·Hyperliquid) 선물 데이터를 모두 받지 못해 '내 거래소 상장' 기준을 건너뜀")

    # 거래량 기록 (섹터 데이터가 새로 온 경우만, 하루 1칸)
    all_rows = {}
    for rows in cats.values():
        for c in rows:
            all_rows.setdefault(c["id"], c)
    coins = {i: analyze_coin(c, derivs, dvol, fees, today) for i, c in all_rows.items() if not excluded(c)}
    if cat_fresh:
        for i, c in all_rows.items():
            if c["mc"] >= TH["minor_mcap"]:
                h = [x for x in dvol.get(i, []) if x[0] != today] + [[today, c["vol"]]]
                dvol[i] = h[-8:]
        dvol = {i: h for i, h in dvol.items() if i in all_rows}

    # 섹터 분석
    oi_prev_snap = min(state["oi_hist"], key=lambda h: abs(h["ts"] - (NOW_TS - 86400)), default=None)
    if oi_prev_snap and abs(oi_prev_snap["ts"] - (NOW_TS - 86400)) > 3 * 3600:
        oi_prev_snap = None
    sectors = []
    for s in SECTORS:
        if s["key"] not in cats:
            continue
        prev = (oi_prev_snap or {}).get("sec", {}).get(s["key"], {})
        sectors.append(analyze_sector(s, cats[s["key"]], coins, btc, chain, prev, user_check, n_ok))
    for sec in sectors:
        sec["cands"] = [evaluate_candidate(a, t, sec) for a, t in sec["qual"]] if sec["label"] != "데이터 부족" else []

    # 전체 강조 선정 (한 코인은 가장 점수 높은 섹터로 한 번만)
    best = {}
    for sec in sectors:
        for c in sec["cands"]:
            if c["grade"] and (c["a"]["id"] not in best or c["score"] > best[c["a"]["id"]]["score"]):
                best[c["a"]["id"]] = c
    ranked = sorted(best.values(), key=lambda c: -c["score"])
    red = [c for c in ranked if c["grade"] == "red"][: TH["red_max"]]
    red_ids = {c["a"]["id"] for c in red}
    yellow = [c for c in ranked if c["a"]["id"] not in red_ids][: TH["yellow_max"]]
    picks = {"red": red, "yellow": yellow}

    # 기록
    sectors_by_key = {sec["s"]["key"]: sec for sec in sectors}
    log, new_red = update_log(log, picks, coins, sectors_by_key, NOW_TS)
    state["oi_hist"] = [h for h in state["oi_hist"] if NOW_TS - h["ts"] <= 30 * 3600] + [
        {"ts": NOW_TS, "sec": {sec["s"]["key"]: sec.get("oi_by_ex", {}) for sec in sectors}}]
    tg_err = telegram(new_red)
    if tg_err:
        errors.append(tg_err)

    # 빈 상태 안내
    days = (NOW_TS - state["started"]) / 86400
    vol_ready = any(len(h) >= 6 for h in dvol.values())
    if not any(s["strong"] for s in sectors):
        empty = "지금은 돈이 들어오는 섹터가 없습니다. 억지로 찾지 않는 것이 정상입니다."
    elif not vol_ready:
        empty = f"거래량 비교 데이터를 모으는 중입니다. 약 {max(1, 6 - int(days))}일 뒤부터 강조가 나옵니다. 그동안 관심 목록을 참고하세요."
    else:
        empty = "강한 섹터는 있지만 모든 조건을 통과한 코인이 없습니다. 관심 목록을 참고하세요."
    age_m = (NOW_TS - cache["cat_ts"]) // 60 if cache.get("cat_ts") else None
    cat_age = "없음" if age_m is None else (f"{age_m}분 전" if age_m < 60 else f"{age_m // 60}시간 전")
    meta = {"obs": f"실전 {int(days) + 1}일째 (백테스트 확인 후 1~2주 점검 권장)", "cat_age": cat_age, "empty_reason": empty}
    errors = NOTES + errors

    board = scoreboard(log)
    page = render({"now": now, "btc": btc, "glob": glob, "sectors": sectors, "picks": picks, "board": board,
                   "dstat": dstat, "errors": errors, "meta": meta, "coins": coins,
                   "bt": load(os.path.join(DATA_DIR, "backtest.json"), None)})

    save(os.path.join(DATA_DIR, "state.json"), state)
    save(os.path.join(DATA_DIR, "log.json"), log)
    save(os.path.join(DATA_DIR, "volume.json"), dvol)
    save(os.path.join(CACHE_DIR, "cache.json"), cache)
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"완료 {now:%Y-%m-%d %H:%M} | 지금 볼 것 {len(red)} | 관심 {len(yellow)} | 섹터 {len(sectors)} | 거래소 {dstat}")
    for e in errors:
        print(" -", e)


if __name__ == "__main__":
    main()
