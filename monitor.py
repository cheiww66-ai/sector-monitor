#!/usr/bin/env python3
"""섹터 모니터 v2.0 — Team All Street · Made by Tyler
(개발 당시 v3.1 = 모니터 1.0. 버전 규칙: 코인을 고르는 규칙이 바뀌면 큰 업데이트 x.0, 화면·표시만 바뀌면 작은 업데이트 x.1)

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

# ═════════════════════════ 버전 ═════════════════════════
VERSION = "2.0"
RELEASED = "2026-09-23"
TEAM, AUTHOR = "Team All Street", "Tyler"
SUBTITLE = "Project Charon for Team All Street"
VERSION_RULE = "큰 업데이트(x.0)는 코인을 고르는 규칙이 바뀐 것, 작은 업데이트(x.1)는 화면·표시만 바뀐 것입니다. 실전 성적은 큰 버전별로 따로 집계합니다."
CHANGELOG = [
    ("2.0", "2026-09-23", "큰 업데이트", [
        "강조 대상 시총 하한 $300M. $70M~300M은 '소형(참고)'으로 따로 보여주고 성적도 따로 기록",
        "상장 기준을 Bitget·OKX·Binance·업비트로 변경 (소형은 2곳 이상). DEX에서만 거래되는 코인과 Hyperliquid 전용 코인 제외",
        "새 목록 '상승 초입 후보(실험)': 섹터 동조, 거래량 증가 추세, 하락 추세 돌파, 사용량 증가, 숏 스퀴즈 준비, 업비트 관심 중 2개 이상. 성적 따로 기록",
        "CoinMarketCap 교차 확인 추가 (가격·거래량 불일치 표시)",
        "코인마다 조건 통과·미통과 칩, 7일 미니 차트, 체인·컨트랙트 주소, 상장 거래소 표시",
        "섹터 지도(원형 그래프): 초입·개선·주의·과열을 색으로 구분, 누르면 해당 코인으로 이동",
        "화면 폭에 따라 자동 배치: 휴대폰은 한 줄, PC는 두 칸 (오른쪽에 지도·비교 차트 고정)",
        "백테스트에 조건별 성적, 반대 전략 비교, 앞·뒤 기간 검증, 소형·실험 목록 성적 추가. 합격 조건에 중앙값 추가",
        "실전 성적표를 큰 버전별로 따로 집계",
        "Bybit·Binance 선물 데이터 수집 중단 (GitHub 서버 IP 차단). 선물 데이터는 Hyperliquid·Bitget·OKX",
        "버전·변경 이력·제작 표기, Project Charon for Team All Street 부제",
    ]),
    ("1.0", "2026-09-22", "첫 버전", [
        "24개 섹터 자금흐름 판정, 지금 볼 것·관심 목록, 비교 차트, 실전 성적표, 1년 백테스트, 텔레그램 알림 (개발 당시 v3.1)",
    ]),
]


def major(v):
    return str(v or "1.0").split(".")[0]


# ═════════════════════════ 설정 ═════════════════════════
KST = dt.timezone(dt.timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, "cache")
SITE_DIR = os.path.join(ROOT, "site")
MOCK = os.environ.get("MOCK") == "1"
NOW_TS = int(os.environ.get("NOW_TS") or time.time())  # 테스트용 시간 조작
CG_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()
CMC_KEY = os.environ.get("CMC_API_KEY", "").strip()
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
    "minor_mcap": 70e6, "pick_mcap": 300e6, "small_min_venues": 2, "min_volume": 2e6, "turnover_min": 0.02, "turnover_max": 0.5,
    "float_min": 0.5, "ath_dd_min": -95.0,
    # 후보
    "lag_min": 5.0,         # 섹터 중앙값보다 30일 수익률이 이만큼(%p) 이상 낮아야 '지연'
    "vol_surge": 1.5,       # 오늘 거래량 / 직전 평균 거래량
    "coin_funding_max": 40.0,
    "red_max": 3, "yellow_max": 10, "top_n": 10,
    "verify_min_samples": 20,
    # 실험 신호 (상승 초입 후보)
    "sync_corr": 0.6,        # 섹터 7일 흐름과의 상관계수
    "vol_trend": 1.3,        # 최근 3일 거래량 / 그 전 평균
    "break_days": 30,        # 이 기간 최고가 돌파
    "break_dd": -50.0,       # 고점 대비 이만큼 이상 빠져 있던 코인만
    "fee_up": 1.3,           # 최근 7일 수수료 / 30일 평균 페이스
    "squeeze_oi": 5.0,       # 코인 OI 24시간 증가율(%)
    "upbit_surge": 2.0,      # 업비트 원화 거래대금 / 그 전 평균
    "exp_min_hits": 2, "exp_max": 10,
    "xcheck_px": 3.0, "xcheck_vol": 3.0,   # CMC 교차확인: 가격 차이(%), 거래량 배수
}
LIST_VENUES = {"Bitget": "bitget", "OKX": "okex", "Binance": "binance", "Upbit": "upbit"}   # 상장 확인 거래소 (CoinGecko 거래소 id)
USER_VENUES = list(LIST_VENUES)
EXCHANGES = ["Hyperliquid", "Bitget", "OKX"]   # 선물 데이터(OI·펀딩) 출처. 거래처가 아니라 데이터용. Bybit·Binance 선물은 GitHub 서버(미국) IP 차단
STABLE_SYMS = {"usdt", "usdc", "dai", "usde", "fdusd", "pyusd", "usds", "tusd", "usdd", "frax", "usd1",
               "rlusd", "susde", "gho", "lusd", "crvusd", "usdx", "eurc", "usdg", "bfusd"}
EXCLUDE_WORDS = ("wrapped", "staked", "bridged", "liquid staking", "restaked", "wormhole", "binance-peg", "tether", " usd")
CAT_REFRESH_S = 4 * 3600 - 600
DAY_REFRESH_S = 24 * 3600 - 600


# ═════════════════════════ 공통 ═════════════════════════
def get_json(url, method="GET", body=None, headers=None, retries=3):
    h = {"User-Agent": "sector-monitor/2.0", "Accept": "application/json"}
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


def f_usd_plain(v):
    if not v:
        return "—"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            return f"${v / div:,.1f}{unit}".replace(".0", "")
    return f"${v:,.0f}"


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


PLAT_KO = {"ethereum": "이더리움", "binance-smart-chain": "BNB체인", "solana": "솔라나", "base": "베이스",
           "arbitrum-one": "아비트럼", "sui": "수이", "avalanche": "아발란체", "the-open-network": "톤",
           "tron": "트론", "aptos": "앱토스", "hyperevm": "하이퍼EVM", "hyperliquid": "하이퍼리퀴드",
           "polygon-pos": "폴리곤", "optimistic-ethereum": "옵티미즘", "sonic": "소닉", "near-protocol": "니어"}
SEC_PLAT = {"ETH": "ethereum", "SOL": "solana", "BNB": "binance-smart-chain", "BASE": "base", "ARB": "arbitrum-one",
            "SUI": "sui", "AVAX": "avalanche", "TON": "the-open-network", "TRX": "tron", "APT": "aptos", "HYPE": "hyperevm"}


def fetch_platforms(ids):
    """코인별 체인·컨트랙트 주소. 체인 위 토큰이 아닌 메인넷 코인은 빈 dict"""
    out = {}
    for r in cg("/coins/list?include_platform=true"):
        if r.get("id") in ids:
            out[r["id"]] = {k: v for k, v in (r.get("platforms") or {}).items() if k and v}
    return out


def fetch_listing(ex_id, max_pages=25):
    """거래소에 상장된 코인(CoinGecko id) 목록과 심볼->id 매핑. 같은 심볼의 가짜 토큰과 섞이지 않도록 id로 확인"""
    ids, sym = set(), {}
    for page in range(1, max_pages + 1):
        rows = cg(f"/exchanges/{ex_id}/tickers?page={page}").get("tickers") or []
        for t in rows:
            if t.get("is_stale") or t.get("is_anomaly") or not t.get("coin_id"):
                continue
            ids.add(t["coin_id"])
            if t.get("target") == "KRW":
                sym[(t.get("base") or "").upper()] = t["coin_id"]
        if len(rows) < 100:
            break
    return {"ids": sorted(ids), "krw": sym}


def fetch_upbit_krw(krw_map):
    """업비트 원화 마켓 24시간 거래대금(원) -> CoinGecko id"""
    markets = [m["market"] for m in get_json("https://api.upbit.com/v1/market/all?isDetails=false") if m["market"].startswith("KRW-")]
    out = {}
    for i in range(0, len(markets), 100):
        for t in get_json("https://api.upbit.com/v1/ticker?markets=" + ",".join(markets[i:i + 100])):
            cid = krw_map.get(t["market"].split("-", 1)[1])
            if cid:
                out[cid] = fl(t.get("acc_trade_price_24h"))
        time.sleep(0.3)
    return out


def fetch_cmc():
    """CoinMarketCap 상위 1500개 (교차 확인용). 심볼 -> [(가격, 24h 거래량, 시총)]"""
    d = get_json("https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?limit=1500&convert=USD",
                 headers={"X-CMC_PRO_API_KEY": CMC_KEY})
    out = {}
    for r in d.get("data", []):
        q = (r.get("quote") or {}).get("USD") or {}
        out.setdefault((r.get("symbol") or "").upper(), []).append([q.get("price"), q.get("volume_24h"), q.get("market_cap")])
    return out


def xcheck(c, cmc):
    """CoinGecko 값과 CMC 값 비교. None=확인 불가, (ok, 설명)"""
    rows = [r for r in cmc.get(c["sym"], []) if r[0] and c["px"] and abs(r[0] / c["px"] - 1) < 0.15]
    if not rows:
        return None
    r = min(rows, key=lambda r: abs((r[2] or 0) - c["mc"]))
    dpx = abs(r[0] / c["px"] - 1) * 100
    vr = (r[1] / c["vol"]) if r[1] and c["vol"] else None
    bad = []
    if dpx > TH["xcheck_px"]:
        bad.append(f"가격 {dpx:.1f}% 차이")
    if vr is not None and not (1 / TH["xcheck_vol"] <= vr <= TH["xcheck_vol"]):
        bad.append(f"거래량 {vr:.1f}배 차이")
    return (not bad, " · ".join(bad) or "CMC와 일치")


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
    out, out7 = {}, {}
    for p in d.get("protocols", []):
        t30, t7 = fl(p.get("total30d")), fl(p.get("total7d"))
        g = (gid.get(str(p.get("defillamaId"))) or gid.get((p.get("slug") or "").lower())
             or gid.get((p.get("name") or "").lower()))
        if g and t30 and t30 > 0:
            out[g] = out.get(g, 0) + t30
            out7[g] = out7.get(g, 0) + (t7 or 0)
    return out, out7


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


FETCHERS = {k: v for k, v in {"Hyperliquid": fetch_hyperliquid, "Bitget": fetch_bitget, "OKX": fetch_okx,
                              "Bybit": fetch_bybit, "Binance": fetch_binance}.items() if k in EXCHANGES}


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
        d = {}
        for sym, px in pxmap.items():
            if base_rnd.random() < 0.6:
                d[sym] = {"oi": rnd.uniform(1e6, 3e8), "fund_h": rnd.uniform(-0.00002, 0.00006),
                          "px24": rnd.uniform(-5, 5), "px": px, "raw": sym + "USDT" if ex != "OKX" else sym + "-USDT-SWAP"}
        derivs[ex] = d
        dstat[ex] = "ok"
    return btc, glob, cats, chain, fees, derivs, dstat


def mock_extras(ids, seed):
    rnd, base = random.Random(seed), random.Random(11)
    listing = {v: {"ids": sorted(i for i in ids if base.random() < p), "krw": {}} for v, p in
               (("Bitget", .7), ("OKX", .6), ("Binance", .5), ("Upbit", .35))}
    listing["Upbit"]["krw"] = {i.upper(): i for i in listing["Upbit"]["ids"]}
    upbit = {i: rnd.uniform(1e9, 5e10) * (3 if rnd.random() < .1 else 1) for i in listing["Upbit"]["ids"]}
    return listing, upbit


def mock_platforms(ids):
    rnd = random.Random(3)
    keys = list(PLAT_KO)[:8]
    out = {}
    for i in sorted(ids):
        if rnd.random() < 0.2:
            out[i] = {}
        else:
            out[i] = {rnd.choice(keys): "0x" + "".join(rnd.choice("0123456789abcdef") for _ in range(40))}
    return out


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
    if user_venue_check:
        n = len(a.get("listed") or [])
        if n == 0:
            fails.append("상장 거래소 없음")
        elif a["mc"] < TH["pick_mcap"] and n < TH["small_min_venues"]:
            fails.append("소형인데 상장 1곳뿐")
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
            qual.append((a, "중형" if a["mc"] >= TH["pick_mcap"] else "소형"))
    res = {"s": s, "qual": qual, "n_pool": len(pool)}
    if len(qual) < 3:
        res.update(label="데이터 부족", strong=False, early=[], late=[], e=0, l=0, avail=0)
        return res
    q = [a for a, _ in qual]
    med7, med30 = med([a["c7"] for a in q]), med([a["c30"] for a in q])
    paths = [[v / a["spark"][0] - 1 for v in a["spark"]] for a in q if a["spark"] and len(a["spark"]) >= 20 and a["spark"][0]]
    L = min((len(p) for p in paths), default=0)
    res["path"] = [statistics.median(p[k] for p in paths) for k in range(L)] if len(paths) >= 3 else None
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


def corr(x, y):
    n = min(len(x), len(y))
    if n < 10:
        return None
    x, y = x[-n:], y[-n:]
    dx = [x[i] - x[i - 1] for i in range(1, n)]
    dy = [y[i] - y[i - 1] for i in range(1, n)]
    try:
        return statistics.correlation(dx, dy)
    except (statistics.StatisticsError, ZeroDivisionError):
        return None


def exp_signals(a, sec):
    """실험 신호: 상승 초입 코인의 공통점 (NEAR·ZEC·MET 사례에서 뽑은 가설). ok=None은 데이터 없음"""
    t = TH
    path = sec.get("path")
    cp = [v / a["spark"][0] - 1 for v in a["spark"]] if a["spark"] and a["spark"][0] else None
    cr = corr(cp, path) if cp and path else None
    sig = [
        {"k": "섹터 동조", "ok": None if cr is None else cr >= t["sync_corr"], "v": "" if cr is None else f"{cr:.2f}",
         "tip": f"최근 7일 가격 흐름이 섹터 전체 흐름과 같이 움직임 (상관계수 {t['sync_corr']} 이상)"},
        {"k": "거래량 증가 추세", "ok": None if a.get("vtrend") is None else a["vtrend"] >= t["vol_trend"],
         "v": "" if a.get("vtrend") is None else f"{a['vtrend']:.1f}배", "tip": f"최근 3일 평균 거래량이 그 전 평균의 {t['vol_trend']}배 이상"},
        {"k": "하락 추세 돌파", "ok": a.get("brk"), "v": "" if a.get("brk") is None else ("돌파" if a["brk"] else ""),
         "tip": f"고점 대비 {t['break_dd']:.0f}% 이상 빠져 있던 코인이 최근 {t['break_days']}일 최고가를 넘음"},
        {"k": "사용량 증가", "ok": None if a.get("fee_up") is None else a["fee_up"] >= t["fee_up"],
         "v": "" if a.get("fee_up") is None else f"수수료 {a['fee_up']:.1f}배", "tip": "최근 7일 프로토콜 수수료가 30일 평균 페이스보다 높음 (디파이 코인만)"},
        {"k": "숏 스퀴즈 준비", "ok": None if a["fund_apr"] is None or a.get("oi24c") is None else
            (a["fund_apr"] <= 0 and a["ma7"] is not None and a["px"] > a["ma7"] and a["oi24c"] >= t["squeeze_oi"]),
         "v": "" if a["fund_apr"] is None else f"펀딩 {a['fund_apr']:.0f}%",
         "tip": f"펀딩 0 이하(숏 우세)인데 가격은 평균가 위, OI 24시간 {t['squeeze_oi']:.0f}% 이상 증가"},
        {"k": "업비트 관심", "ok": None if a.get("upx") is None else a["upx"] >= t["upbit_surge"],
         "v": "" if a.get("upx") is None else f"{a['upx']:.1f}배", "tip": f"업비트 원화 거래대금이 평소의 {t['upbit_surge']}배 이상"},
    ]
    return sig, sum(1 for x in sig if x["ok"]), sum(1 for x in sig if x["ok"] is not None)


def evaluate_candidate(a, tier, sec):
    lag = sec["med30"] - a["c30"]
    above = a["ma7"] is not None and a["px"] > a["ma7"]
    vol_ok = None if a["vr"] is None else a["vr"] >= TH["vol_surge"]
    fund_ok = a["fund_apr"] is None or a["fund_apr"] < TH["coin_funding_max"]
    pf_cheap = bool(a["pf"] and sec.get("pf_med") and a["pf"] < sec["pf_med"])
    big = a["mc"] >= TH["pick_mcap"]
    rule = None
    if sec["strong"] and lag >= TH["lag_min"] and fund_ok:
        if above and vol_ok:
            rule = "red"
        elif above or vol_ok:
            rule = "yellow"
    grade = rule if big else None
    small_grade = rule if not big else None
    if sec["label"] in ("초입 정황", "개선 중"):
        sv = sec["label"]
    else:
        sv = "" if sec["rs30"] is None else f"BTC 대비 {sec['rs30']:+.0f}%p"
    conds = [
        {"k": "강한 섹터", "ok": sec["strong"], "v": sv, "key": False,
         "tip": "섹터에 돈이 들어오는 신호가 있거나, BTC보다 7일·30일 모두 강하고 과열 경고가 아님"},
        {"k": "덜 오름", "ok": lag >= TH["lag_min"], "v": f"{lag:.0f}%p", "key": True,
         "tip": f"섹터 중앙값보다 30일 수익률이 {TH['lag_min']:.0f}%p 이상 낮음"},
        {"k": "평균가 위", "ok": above, "v": "", "key": True, "tip": "현재가가 최근 7일 평균 가격보다 높음"},
        {"k": "거래량", "ok": vol_ok, "v": "쌓는 중" if a["vr"] is None else f"{a['vr']:.1f}배", "key": True,
         "tip": f"오늘 거래량이 최근 평균의 {TH['vol_surge']}배 이상"},
        {"k": "펀딩 정상", "ok": fund_ok, "v": "선물 없음" if a["fund_apr"] is None else f"연 {a['fund_apr']:.0f}%", "key": False,
         "tip": f"선물 펀딩비 연환산 {TH['coin_funding_max']:.0f}% 미만 (롱 쏠림 아님)"},
        {"k": "시총", "ok": big, "v": f_usd_plain(a["mc"]), "key": False,
         "tip": f"강조 대상은 시총 {f_usd_plain(TH['pick_mcap'])} 이상"},
        {"k": "기본 기준", "ok": True, "v": "", "key": False,
         "tip": "거래량·회전율·유통량·고점 대비 하락폭·상장(Bitget·OKX·Binance·업비트 중 1곳, 소형은 2곳)을 모두 통과"},
    ]
    if a.get("xc") is not None:
        conds.append({"k": "교차 확인", "ok": a["xc"][0], "v": "" if a["xc"][0] else a["xc"][1], "key": False,
                      "tip": "CoinGecko와 CoinMarketCap의 가격·거래량이 일치하는지"})
    esig, ehits, eavail = exp_signals(a, sec)
    exp = bool(sec["strong"] and ehits >= TH["exp_min_hits"])

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
    return {"a": a, "tier": tier, "sec": sec, "grade": grade, "small_grade": small_grade, "conds": conds,
            "esig": esig, "ehits": ehits, "eavail": eavail, "exp": exp,
            "score": score, "lag": lag,
            "above": above, "vol_ok": vol_ok, "pf_cheap": pf_cheap, "why": why, "risk": risk[:2]}


# ═════════════════════════ 기록·성적표·알림 ═════════════════════════
def update_log(log, picks, coins, sectors_by_key, now_ts):
    new_red = []
    for grade in ("red", "yellow", "small", "exp"):
        # 같은 코인·같은 등급은 7일에 한 번만 기록 (표본 중복·알림 반복 방지)
        seen = {e["id"] for e in log if e["g"] == grade and now_ts - e["ts"] < 7 * 86400 and major(e.get("v")) == major(VERSION)}
        for p in picks[grade]:
            a = p["a"]
            if a["id"] in seen:
                continue
            log.append({"ts": now_ts, "v": VERSION, "id": a["id"], "sym": a["sym"], "sec": p["sec"]["s"]["key"], "g": grade,
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
    return log[-6000:], new_red


def scoreboard(log):
    """현재 큰 버전의 기록만 집계. 이전 버전 기록은 개수만 따로 표시"""
    cur = [e for e in log if major(e.get("v")) == major(VERSION)]
    out = {"old": len(log) - len(cur)}
    log = cur
    for g in ("red", "yellow", "small", "exp"):
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
        lines.append(f"🔴 {a['sym']} ({p['sec']['s']['name']}) · {chain_text(a, p['sec']['s']['key'])}\n왜: " + " / ".join(p["why"][1:3]) +
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
    ("메이저 / 중형 / 소형", "메이저: 섹터 시총 상위 5위 안 + 시총 $1B 이상 + 선물이 여러 거래소에 상장. 중형: 시총 $300M 이상이면서 기본 기준을 통과. 소형: 시총 $70M~300M이면서 기본 기준 통과 + 상장 거래소 2곳 이상. 소형은 강조·알림에서 빼고 성적만 따로 기록합니다."),
    ("DEX 토큰 주의", "DEX(탈중앙 거래소)에는 누구나 같은 이름의 토큰을 만들 수 있습니다. 이 모니터는 Bitget·OKX·Binance·업비트 상장 코인만 보여주지만, 앱에서 검색할 때는 상장 거래소의 현물·선물 탭에서 찾고 체인·컨트랙트 주소 앞뒤 글자가 같은지 확인하세요."),
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


def chain_pick(a, sec_key=None):
    pl = a.get("plats")
    if pl is None:
        return None
    if not pl:
        return ("메인넷 코인", "")
    pref = SEC_PLAT.get(sec_key)
    k = pref if pref in pl else next(iter(pl))
    return (PLAT_KO.get(k, k), pl[k], len(pl) - 1)


def short_addr(addr):
    return addr if len(addr) <= 14 else addr[:6] + "…" + addr[-5:]


def chain_text(a, sec_key=None):
    c = chain_pick(a, sec_key)
    if not c:
        return "체인 정보 없음"
    return c[0] if not c[1] else f"{c[0]} {short_addr(c[1])}"


def chain_html(a, sec_key=None):
    c = chain_pick(a, sec_key)
    if not c:
        return '<span class="na">체인 정보 없음</span>'
    if not c[1]:
        return f'<span title="토큰이 아니라 자체 블록체인의 기본 코인">{c[0]}</span>'
    more = f' <span class="na">외 {c[2]}개 체인</span>' if c[2] else ""
    return (f'{esc(c[0])} <code title="{esc(c[1])}">{esc(short_addr(c[1]))}</code>'
            f'<button class="copy" data-copy="{esc(c[1])}" aria-label="컨트랙트 주소 복사">복사</button>{more}')


VENUE_KO = {"Bitget": "Bitget", "OKX": "OKX", "Binance": "Binance", "Upbit": "업비트"}


def venue_html(a):
    ls = a.get("listed") or []
    return " ".join(f'<span class="{"up" if v in ls else "na"}">{"✓" if v in ls else "✕"} {VENUE_KO[v]}</span>' for v in USER_VENUES)


def spark_svg(sp, w=76, h=22):
    if not sp or len(sp) < 2:
        return ""
    lo, hi = min(sp), max(sp)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i / (len(sp) - 1) * w:.1f},{h - 2 - (v - lo) / rng * (h - 4):.1f}" for i, v in enumerate(sp))
    cls = "sp-up" if sp[-1] >= sp[0] else "sp-dn"
    return f'<svg class="spark {cls}" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true"><polyline points="{pts}"/></svg>'


def chip(c):
    ok = c["ok"]
    cls = "ok" if ok else "na" if ok is None else "bad"
    mark = "✓" if ok else "–" if ok is None else "✕"
    val = f' <em>{esc(c["v"])}</em>' if c.get("v") else ""
    return f'<span class="chip {cls}" title="{esc(c.get("tip", ""))}">{mark} {esc(c["k"])}{val}</span>'


def chips(p, compact=False):
    cs = p["conds"]
    if not compact:
        return '<div class="chips">' + "".join(chip(c) for c in cs) + "</div>"
    keys = [c for c in cs if c["key"]]
    rest = [c for c in cs if not c["key"]]
    out = "".join(chip(c) for c in keys) + "".join(chip(c) for c in rest if not c["ok"])
    good = [c for c in rest if c["ok"]]
    if good:
        out += f'<span class="chip ok" title="{esc(", ".join(c["k"] for c in good))} 통과">✓ 기본 {len(good)}개</span>'
    return '<div class="chips">' + out + "</div>"


def act_html(a, spark_ids):
    spark_ids.add(a["id"])
    return (f'<a href="{esc(a["link"][1])}" target="_blank" rel="noopener">차트</a>'
            f'<button class="cmp" data-id="{esc(a["id"])}" aria-pressed="false">비교</button>')


def coin_row(p, spark_ids, extra=""):
    a = p["a"]
    return (f'<tr><td><b>{esc(a["sym"])}</b><small>{esc(a["name"][:18])}</small></td><td><span class="tier">{p["tier"]}</span></td>'
            f'<td>{f_pct(a["c7"])}</td><td>{f_pct(a["c30"])}</td>{extra}<td class="act">{act_html(a, spark_ids)}</td></tr>')


def focus_card(p, spark_ids):
    a = p["a"]
    sk = p["sec"]["s"]["key"]
    dist = pct(a["low7"], a["px"]) if a["low7"] and a["px"] else None
    chk = "".join(f"<li>{esc(c)}</li>" for c in CHECKLIST)
    return f"""
<article class="card focus" data-coin="{esc(a["id"])}">
 <div class="card-h"><span class="c-icon" aria-hidden="true">◆</span><b class="sym">{esc(a["sym"])}</b><span class="c-name">{esc(a["name"])}</span>{spark_svg(a["spark"])}<span class="px">{f_px(a["px"])}</span></div>
 <p class="meta">{tag(p["sec"]["s"])}<span class="tier">{p["tier"]} · 시총 {f_usd_plain(a["mc"])}</span> 7일 {f_pct(a["c7"])} · 30일 {f_pct(a["c30"])}</p>
 <p class="meta">{chain_html(a, sk)}<span class="sep">·</span><span class="nw">상장 {venue_html(a)}</span></p>
 {chips(p)}
 <p class="line"><span class="k">위험</span>{esc(" · ".join(p["risk"]))}</p>
 <p class="line"><span class="k">무효</span>7일 저점 <b>{f_px(a["low7"])}</b> 이탈 또는 섹터 '과열 경고' 시 제외. 현재가에서 {f_pct(dist)}</p>
 <div class="c-actions"><a class="btn" href="{esc(a["link"][1])}" target="_blank" rel="noopener">{esc(a["link"][0])}에서 차트</a>
 <button class="cmp btn ghost" data-id="{esc(a["id"])}" aria-pressed="false">비교 차트에 추가</button></div>
 <details class="inner"><summary>자세히 · 차트 체크리스트</summary>
  <table class="kv"><tr><td>유통량 비율</td><td>{"—" if a["float"] is None else f'{a["float"] * 100:.0f}%'}</td></tr>
  <tr><td>고점 대비</td><td>{f_pct(a["dd"], 0)}</td></tr>
  <tr><td>하루 거래량 / 회전율</td><td>{f_usd_plain(a["vol"])} / {"—" if a["turn"] is None else f'{a["turn"] * 100:.0f}%'}</td></tr></table>
  <ul class="check">{chk}</ul></details>
</article>"""


def exp_chips(p):
    out = "".join(chip(x) for x in p["esig"] if x["ok"]) + "".join(
        chip({**x, "ok": None, "v": ""}) for x in p["esig"] if x["ok"] is False)
    return f'<div class="chips"><span class="chip hits">신호 {p["ehits"]}/{p["eavail"]}</span>{out}</div>'


def row_item(p, spark_ids, mode="lag"):
    a = p["a"]
    return f"""<li class="row" data-coin="{esc(a["id"])}">{spark_svg(a["spark"])}<div class="row-h"><b class="sym">{esc(a["sym"])}</b><span class="c-name">{esc(a["name"][:20])}</span>{tag(p["sec"]["s"])}
<span class="nums-s">7일 {f_pct(a["c7"])} · 30일 {f_pct(a["c30"])}</span></div>
{exp_chips(p) if mode == "exp" else chips(p, True)}<div class="row-f"><p class="meta sm"><span class="tier">{p["tier"]} · {f_usd_plain(a["mc"])}</span><span class="sep">·</span>{chain_html(a, p["sec"]["s"]["key"])}<span class="sep">·</span><span class="nw">상장 {venue_html(a)}</span></p><span class="act">{act_html(a, spark_ids)}</span></div></li>"""


def row_list(items, spark_ids, first=5, more_label="나머지", mode="lag"):
    if not items:
        return ""
    head = "".join(row_item(p, spark_ids, mode) for p in items[:first])
    tail = items[first:]
    extra = "" if not tail else (f'<details class="inner"><summary>{more_label} {len(tail)}개 더 보기</summary>'
                                 f'<ul class="rows">{"".join(row_item(p, spark_ids, mode) for p in tail)}</ul></details>')
    return f'<ul class="rows">{head}</ul>{extra}'


def bt_verdict(bt):
    if not bt:
        return "아직 없음 (Actions → backfill 실행)", "na"
    if major(bt.get("v")) != major(VERSION):
        return f"옛 규칙(v{bt.get('v', '1.0')}) 결과. backfill을 다시 실행하세요", "warn-text"
    s = bt["summary"]["red"]
    if (s["n7"] or 0) < 30:
        return f"표본 부족 ({s['n7']}개)", "warn-text"
    if s["win7"] >= 55 and (s["avg7"] or 0) > 0 and (s.get("med7") or 0) > 0:
        return f"통과: 7일 뒤 섹터보다 좋았던 비율 {s['win7']:.0f}% ({s['n7']}개)", "up"
    return f"미달: 7일 뒤 섹터보다 좋았던 비율 {s['win7']:.0f}% ({s['n7']}개)", "down"


def pc(v):
    return '<span class="na">—</span>' if v is None else f"{v:.0f}%"


def bt_row(name, s, note=""):
    return (f'<tr><td>{name}{f"<small>{note}</small>" if note else ""}</td><td>{s["n7"]}</td><td>{pc(s["win7"])}</td>'
            f'<td>{f_pct(s["avg7"], 1, True)}</td><td>{f_pct(s.get("med7"), 1, True)}</td><td>{pc(s["win30"])}</td></tr>')


BT_HEAD = '<tr><th>구분</th><th>표본</th><th>7일 승률</th><th>7일 평균</th><th>7일 중앙값</th><th>30일 승률</th></tr>'
VARIANT_NAMES = [("base", "기준선", "강한 섹터의 모든 코인"), ("lag", "덜 오름만", ""), ("lag_above", "덜 오름 + 평균가 위", ""),
                 ("lag_vol", "덜 오름 + 거래량", ""), ("both", "덜 오름 + 둘 다", "= 지금 볼 것 규칙"),
                 ("lead", "반대 전략", "섹터보다 더 오른 코인 + 평균가 위")]


def bt_section(bt):
    if not bt:
        return ('<p class="na">아직 실행하지 않았습니다. Actions 탭 → backfill → Run workflow를 한 번 실행하면 '
                '과거 1년 데이터로 이 규칙의 성적을 계산합니다.</p>')
    sm = bt["summary"]
    old = major(bt.get("v")) != major(VERSION)
    warn = f'<p class="warn-text">이 결과는 v{esc(bt.get("v", "1.0"))} 규칙으로 계산됐습니다. backfill을 다시 실행해야 현재 규칙의 성적이 나옵니다.</p>' if old else ""
    parts = [f'<p class="meta">과거 {esc(bt["start"])} ~ {esc(bt["end"])} · 코인 {bt["coins"]}개 · 계산일 '
             f'{dt.datetime.fromtimestamp(bt["ts"], KST):%Y-%m-%d}</p>{warn}',
             f'<div class="tbl"><table class="list">{BT_HEAD}{bt_row("지금 볼 것", sm["red"])}{bt_row("관심 목록", sm["yellow"])}'
             + (bt_row("소형 (참고)", sm["small"]) if "small" in sm else "")
             + (bt_row("상승 초입 (실험)", sm["exp"], "과거 데이터로 가능한 신호 3개만") if "exp" in sm else "") + '</table></div>',
             '<p class="na sm">무작위로 골라도 7일 승률은 약 50%입니다. 승률 55% 이상, 평균·중앙값 모두 플러스여야 통과입니다.</p>']
    if bt.get("halves"):
        h = bt["halves"]
        parts.append(f'<details class="inner"><summary>기간 나눠 검증 (지금 볼 것)</summary><div class="tbl"><table class="list">{BT_HEAD}'
                     + "".join(bt_row(k, v) for k, v in h.items()) + '</table></div>'
                     '<p class="na sm">앞 기간에서만 좋고 뒤 기간에서 무너지면 우연히 맞은 규칙일 가능성이 큽니다.</p></details>')
    if bt.get("variants"):
        v = bt["variants"]
        parts.append(f'<details class="inner"><summary>조건별 성적 · 반대 전략 비교</summary><div class="tbl"><table class="list">{BT_HEAD}'
                     + "".join(bt_row(n, v[k], note) for k, n, note in VARIANT_NAMES if k in v) + '</table></div>'
                     '<p class="na sm">조건을 하나씩 더할 때 승률이 오르면 그 조건이 도움, 내려가면 방해입니다. 개수 제한 없이 계산해 위 표와 표본 수가 다릅니다.</p></details>')
    secs = "".join(f'<tr><td>{esc(k)}</td><td>{s["n7"]}</td><td>{pc(s["win7"])}</td><td>{f_pct(s["avg7"], 1, True)}</td></tr>'
                   for k, s in bt["by_sector"].items())
    recent = "".join(
        f'<tr><td>{esc(t["date"][5:])}</td><td><b>{esc(t["sym"])}</b></td><td>{esc(t["sec"])}</td><td>{f_pct(t["r7"])}</td>'
        f'<td>{f_pct(t["x7"], 1, True)}</td><td>{"이탈" if t["stop"] else ""}</td></tr>' for t in reversed(bt["recent"][-15:]))
    parts.append(f'<details class="inner"><summary>섹터별 성적</summary><div class="tbl"><table class="list"><tr><th>섹터</th><th>표본</th><th>승률</th><th>평균</th></tr>{secs}</table></div></details>')
    parts.append(f'<details class="inner"><summary>최근 과거 강조 사례</summary><div class="tbl"><table class="list"><tr><th>날짜</th><th>코인</th><th>섹터</th><th>7일</th><th>섹터 대비</th><th>무효가</th></tr>{recent}</table></div></details>')
    parts.append('<details class="inner"><summary>백테스트의 한계</summary><ul>'
                 '<li>지금 카테고리에 남은 코인만으로 과거를 돌렸습니다(사라진 코인 제외). 실제보다 결과가 좋게 나올 수 있습니다.</li>'
                 "<li>과거의 선물·스테이블코인 데이터가 없어 '강한 섹터'를 가격(BTC 대비 7일·30일)으로만 판정했습니다.</li>"
                 '<li>수수료·슬리피지는 빼지 않았습니다. 결과를 보고 기준을 반복해서 바꾸면 과거에만 맞는 규칙이 됩니다.</li></ul></details>')
    return "".join(parts)


def rules_html():
    t = TH
    items = [
        ("강조 대상", f"시총 {f_usd_plain(t['pick_mcap'])} 이상 (메이저·중형). {f_usd_plain(t['minor_mcap'])}~{f_usd_plain(t['pick_mcap'])}은 소형(참고)으로 따로 표시하고 성적도 따로 기록"),
        ("강한 섹터", "돈이 들어오는 신호(초입 정황·개선 중)가 있거나, 섹터 중앙값이 BTC보다 7일·30일 모두 강함. 과열 경고 섹터는 제외"),
        ("덜 오름", f"섹터 중앙값보다 30일 수익률이 {t['lag_min']:.0f}%p 이상 낮음"),
        ("평균가 위", "현재가가 최근 7일 평균 가격보다 높음"),
        ("거래량", f"오늘 거래량이 최근 평균의 {t['vol_surge']}배 이상"),
        ("펀딩 정상", f"선물 펀딩비 연환산 {t['coin_funding_max']:.0f}% 미만"),
        ("기본 기준", f"하루 거래량 {f_usd_plain(t['min_volume'])} 이상, 회전율 {t['turnover_min'] * 100:.0f}~{t['turnover_max'] * 100:.0f}%, "
                  f"유통량 {t['float_min'] * 100:.0f}% 이상, 고점 대비 {t['ath_dd_min']:.0f}% 이내, Bitget·OKX·Binance·업비트 중 1곳 이상 상장 (소형은 2곳 이상). DEX에서만 거래되는 코인은 제외"),
        ("지금 볼 것", "위 조건을 모두 통과"),
        ("관심 목록", "평균가 위·거래량 중 하나만 통과하고 나머지는 모두 통과"),
        ("상승 초입 (실험)", f"강한 섹터 안에서 실험 신호 6개 중 {t['exp_min_hits']}개 이상. 신호 개수가 많은 순. 규칙이 아니라 검증 중인 가설이며 성적을 따로 기록"),
        ("섹터 동조", f"최근 7일 가격 흐름과 섹터 흐름의 상관계수 {t['sync_corr']} 이상"),
        ("거래량 증가 추세", f"최근 3일 평균 거래량이 그 전 평균의 {t['vol_trend']}배 이상"),
        ("하락 추세 돌파", f"고점 대비 {t['break_dd']:.0f}% 이상 빠져 있던 코인이 최근 {t['break_days']}일 최고가를 넘음"),
        ("사용량 증가", f"최근 7일 수수료가 30일 평균 페이스의 {t['fee_up']}배 이상 (디파이 코인만)"),
        ("숏 스퀴즈 준비", f"펀딩 0 이하 + 가격이 7일 평균 위 + OI 24시간 {t['squeeze_oi']:.0f}% 이상 증가"),
        ("업비트 관심", f"업비트 원화 거래대금이 평소의 {t['upbit_surge']}배 이상"),
        ("교차 확인", f"CoinGecko와 CoinMarketCap 가격 차이 {t['xcheck_px']:.0f}% 이내, 거래량 차이 {t['xcheck_vol']:.0f}배 이내"),
    ]
    return '<dl class="gloss">' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in items) + "</dl>"


def changelog_html():
    out = []
    for v, d, kind, items in CHANGELOG:
        lis = "".join(f"<li>{esc(x)}</li>" for x in items)
        out.append(f'<div class="cl"><p><b>v{v}</b> <span class="na">{d} · {kind}</span></p><ul>{lis}</ul></div>')
    return "".join(out)


def render(ctx):
    now, btc, glob, sectors, picks, board, dstat, errors, meta = (
        ctx["now"], ctx["btc"], ctx["glob"], ctx["sectors"], ctx["picks"], ctx["board"], ctx["dstat"], ctx["errors"], ctx["meta"])
    spark_ids = set()
    bt = ctx.get("bt")

    # 상단 상태
    ex_pills = "".join(f'<span class="pill {"ok" if dstat.get(ex) == "ok" else "bad"}">{"✓" if dstat.get(ex) == "ok" else "✕"} {ex}</span>' for ex in EXCHANGES)
    red_b, yel_b = board["red"], board["yellow"]
    if red_b["n"] < TH["verify_min_samples"]:
        live = f'실전 <span class="warn-text">검증 전</span> ({red_b["n"]}/{TH["verify_min_samples"]}개)'
    else:
        live = f'실전 {red_b["rate"]:.0f}% ({red_b["wins"]}/{red_b["n"]}개)'
    bt_say, bt_cls = bt_verdict(bt)
    props = f"""
<dl class="props">
 <div><dt>갱신</dt><dd>{now:%m-%d %H:%M} KST <span class="na">· 섹터 {meta["cat_age"]}</span></dd></div>
 <div><dt>선물 데이터</dt><dd>{ex_pills}</dd></div>
 <div><dt>도구 성적</dt><dd>{live} <span class="na">·</span> 백테스트 <span class="{bt_cls}">{bt_say}</span></dd></div>
</dl>"""
    errs = "" if not errors else (f'<details class="inner warnbox"><summary>받지 못한 데이터 {len(errors)}건</summary><ul>'
                                  + "".join(f"<li>{esc(e)}</li>" for e in errors[:15]) + "</ul></details>")

    # BTC
    c7 = btc.get("c7")
    if c7 is None:
        btc_say, btc_cls = "BTC 데이터를 받지 못했습니다. 아래 판정은 참고만 하세요.", "warn"
    elif c7 <= -8:
        btc_say, btc_cls = "BTC가 1주일 새 크게 빠졌습니다. 아래 신호 대부분이 믿기 어렵습니다.", "warn"
    elif c7 <= -3:
        btc_say, btc_cls = "BTC 약세. 새로 들어가는 건 보수적으로.", "warn"
    else:
        btc_say, btc_cls = "BTC 흐름 정상.", "info"
    dom = "—" if glob.get("btc_dom") is None else f'{glob["btc_dom"]:.1f}%'
    btc_block = (f'<div class="callout {btc_cls} slim"><b>BTC</b> {f_px(btc.get("px"))} <span class="nums-s">7일 {f_pct(c7)} · 30일 '
                 f'{f_pct(btc.get("c30"))} · 도미넌스 {dom}</span><span class="say">{btc_say}</span></div>')

    # 지금 볼 것 / 관심 / 소형
    if picks["red"]:
        focus = "".join(focus_card(p, spark_ids) for p in picks["red"])
    else:
        focus = f'<div class="callout empty slim">{esc(meta["empty_reason"])}</div>'
    watch = row_list(picks["yellow"], spark_ids) or '<p class="na">관심 목록 조건을 통과한 코인이 없습니다.</p>'
    exp = picks.get("exp") or []
    exp_html = row_list(exp, spark_ids, first=5, mode="exp") or '<p class="na">강한 섹터에서 실험 신호 2개 이상을 동시에 보인 코인이 없습니다.</p>'
    small = picks.get("small") or []
    small_html = "" if not small else (
        f'<details class="fold"><summary>소형 코인 (참고) <span class="na">{len(small)}개 · 시총 {f_usd_plain(TH["minor_mcap"])}~{f_usd_plain(TH["pick_mcap"])}, 기록·알림 제외</span></summary>'
        f'{row_list(small, spark_ids, first=len(small))}</details>')

    # 섹터
    sec_html = []
    for sec in sorted(sectors, key=lambda x: (x["label"] == "데이터 부족", -(x.get("rs30") or -999))):
        s = sec["s"]
        head = (f'<summary><span class="s-name">{esc(s["name"])}</span><span class="kind">{s["kind"]}</span>'
                f'<span class="label {LABEL_CLS[sec["label"]]}">{sec["label"]}</span>'
                f'<span class="s-rs" title="BTC 대비 30일">{f_pct(sec.get("rs30"), 0, True)}</span></summary>')
        if sec["label"] == "데이터 부족":
            sec_html.append(f'<details class="sector" data-sec="{s["key"]}">{head}<p class="na">{LABEL_SAY["데이터 부족"]} (후보 {sec["n_pool"]}개 중)</p></details>')
            continue
        gain = sorted(sec["qual"], key=lambda t: -t[0]["c7"])[: TH["top_n"]]
        gain_rows = "".join(coin_row({"a": a, "tier": t}, spark_ids) for a, t in gain)
        cands = sorted([c for c in sec["cands"] if c["lag"] >= TH["lag_min"]], key=lambda c: -c["score"])[: TH["top_n"]]
        cand_rows = "".join(coin_row(c, spark_ids, f'<td>{c["lag"]:.0f}%p</td><td>{"●" if c["above"] else "○"}</td>'
                                     f'<td>{"—" if c["vol_ok"] is None else ("●" if c["vol_ok"] else "○")}</td>') for c in cands) \
            or '<tr><td colspan="8" class="na">섹터 평균보다 크게 덜 오른 코인이 없음</td></tr>'
        strong_note = "강한 섹터라 후보를 강조 대상에 포함합니다." if sec["strong"] else "강한 섹터가 아니라 후보를 강조하지 않습니다."
        sig = "".join(f'<li class="{"hit" if c["ok"] else "na" if c["ok"] is None else "miss"}"><span>{"●" if c["ok"] else "—" if c["ok"] is None else "○"}</span><div><b>{esc(c["label"])}</b><small>{esc(c["why"])}</small></div></li>' for c in sec["early"])
        sig_l = "".join(f'<li class="{"warnhit" if c["ok"] else "na" if c["ok"] is None else "miss"}"><span>{"●" if c["ok"] else "—" if c["ok"] is None else "○"}</span><div><b>{esc(c["label"])}</b><small>{esc(c["why"])}</small></div></li>' for c in sec["late"])
        chain_kv = "" if s["kind"] != "체인" else (
            f'<tr><td>스테이블코인 7일</td><td>{f_pct(sec.get("stable7"))}</td></tr>'
            f'<tr><td>DEX 거래량 주간</td><td>{f_pct(sec.get("dex"))}</td></tr>'
            f'<tr><td>TVL 7일 (가격 착시 포함)</td><td>{f_pct(sec.get("tvl7"))}</td></tr>')
        sec_html.append(f"""
<details class="sector" data-sec="{s["key"]}">{head}
 <p class="meta">{LABEL_SAY[sec["label"]]}. {strong_note}</p>
 <details class="inner" open><summary>덜 오른 후보</summary>
 <div class="tbl"><table class="list"><tr><th>코인</th><th>등급</th><th>7일</th><th>30일</th><th>덜 오름</th><th>평균가 위</th><th>거래량</th><th></th></tr>{cand_rows}</table></div></details>
 <details class="inner"><summary>지금 오르는 코인</summary>
 <div class="tbl"><table class="list"><tr><th>코인</th><th>등급</th><th>7일</th><th>30일</th><th></th></tr>{gain_rows}</table></div></details>
 <details class="inner"><summary>섹터 판정 근거 · 돈 유입 {sec["e"]}/{sec["avail"]} · 과열 {sec["l"]}/3</summary>
  <ul class="sig">{sig}</ul><p class="c-sub">과열 신호</p><ul class="sig">{sig_l}</ul>
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
    old_note = f'<p class="na sm">이전 큰 버전의 기록 {board["old"]}개는 규칙이 달라 집계에서 뺐습니다.</p>' if board.get("old") else ""
    board_html = f"""<h4>실전 기록 (v{major(VERSION)}.x 규칙)</h4><div class="tbl"><table class="list"><tr><th>구분</th><th>누적</th><th>7일 경과</th><th>승률</th><th>평균 초과</th></tr>
{brow("지금 볼 것", red_b)}{brow("관심 목록", yel_b)}{brow("소형 (참고)", board["small"])}{brow("상승 초입 (실험)", board["exp"])}</table></div>{old_note}
<h4>백테스트</h4>{bt_section(bt)}"""

    gloss = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in GLOSSARY)

    sparks = {i: {"s": ctx["coins"][i]["sym"], "p": [round(x, 10) for x in ctx["coins"][i]["spark"]]}
              for i in spark_ids if i in ctx["coins"] and ctx["coins"][i]["spark"]}
    init = [p["a"]["id"] for p in picks["red"]][:3]
    nodes, links, seen = [], [], set()
    for sec in sectors:
        if sec["label"] == "데이터 부족":
            continue
        nodes.append({"id": "s:" + sec["s"]["key"], "n": sec["s"]["name"], "t": "s", "st": sec["label"],
                      "r": sec.get("rs30")})
    secset = {n["id"] for n in nodes}
    risky = {"주의", "과열 경고"}
    for grp, items in (("red", picks["red"]), ("exp", exp), ("yellow", picks["yellow"]), ("small", small)):
        for p in items:
            a, sid = p["a"], "s:" + p["sec"]["s"]["key"]
            if sid not in secset:
                continue
            if a["id"] not in seen:
                seen.add(a["id"])
                warn = p["sec"]["label"] in risky or (a["fund_apr"] or 0) >= 20 or (a.get("xc") and not a["xc"][0])
                nodes.append({"id": a["id"], "n": a["sym"], "t": "c", "g": grp, "w": bool(warn), "mc": a["mc"]})
            links.append([sid, a["id"]])
    payload = json.dumps({"sp": sparks, "btc": btc.get("spark") or [], "init": init, "map": {"n": nodes, "l": links}},
                         separators=(",", ":"), ensure_ascii=False)
    nr, ny = len(picks["red"]), len(picks["yellow"])

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="theme-color" content="#1e1e1e">
<title>섹터 모니터 · {TEAM}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{CSS}</style></head><body><main class="note">
<div class="top"><h1>섹터 모니터</h1><span class="ver">v{VERSION}</span><span class="sub">{SUBTITLE}</span></div>
<nav class="jump"><a href="#now">지금 볼 것 <b>{nr}</b></a><a href="#exp">상승 초입 <b>{len(exp)}</b></a><a href="#watch">관심 <b>{ny}</b></a><a href="#sectors">섹터</a><a href="#score">성적표</a><a href="#rules">기준</a></nav>
{props}
{errs}
{btc_block}
<div class="layout">
<aside class="side">
 <section class="panel"><div class="panel-h"><b>섹터 지도</b><span class="na sm">누르면 해당 코인으로 이동 · 끌어서 움직이기</span></div>
  <div id="map" role="img" aria-label="섹터와 코인 상태 지도"></div>
  <div class="legend"><span><i class="d g"></i>초입·상승 신호</span><span><i class="d b"></i>개선 중</span><span><i class="d p"></i>지금 볼 것</span><span><i class="d a"></i>주의</span><span><i class="d r"></i>과열</span><span><i class="d n"></i>중립</span></div></section>
 <details class="fold panel"{" open" if init else ""}><summary>비교 차트 <span class="na">최근 7일 · 점선은 BTC</span></summary>
 <div class="chart-wrap"><svg id="chart" viewBox="0 0 640 240" role="img" aria-label="7일 수익률 비교 차트"></svg><div id="legend"></div></div></details>
</aside>
<div class="main">
<h2 id="now">지금 볼 것<small>모든 조건 통과 · 최대 {TH["red_max"]}개</small></h2>
{focus}
<h2 id="exp">상승 초입 후보<span class="exp-badge">실험</span><small>강한 섹터 + 신호 {TH["exp_min_hits"]}개 이상 · 신호 많은 순</small></h2>
{exp_html}
<h2 id="watch">관심 목록<small>핵심 조건 1개 미달 · 최대 {TH["yellow_max"]}개</small></h2>
{watch}
{small_html}
<h2 id="sectors">섹터<small>오른쪽 숫자 = BTC 대비 30일 · 강한 순서</small></h2>
{"".join(sec_html[:8])}
{"" if len(sec_html) <= 8 else f'<details class="fold"><summary>나머지 섹터 {len(sec_html) - 8}개</summary>{"".join(sec_html[8:])}</details>'}
<h2 id="score">도구 성적표</h2>
<details class="fold"><summary>실전 기록 · 백테스트 펼치기</summary>{board_html}</details>
<h2 id="rules">기준 · 용어</h2>
<details class="fold"><summary>조건 기준 펼치기</summary>{rules_html()}</details>
<details class="fold"><summary>용어 풀이 펼치기</summary><dl class="gloss">{gloss}</dl></details>
</div>
</div>
<footer>
 <p class="brand"><b>{TEAM}</b><span class="na">·</span>Made by {AUTHOR}</p>
 <p class="na sm">{SUBTITLE}</p>
 <p>섹터 모니터 v{VERSION} · {RELEASED} 업데이트</p>
 <details class="inner"><summary>변경 이력</summary><p class="na sm">{esc(VERSION_RULE)}</p>{changelog_html()}</details>
 <p class="na sm">데이터: CoinGecko, DefiLlama, 각 거래소 공개 API. Data provided by CoinGecko. 모든 강조는 확률을 높이는 정황일 뿐 예측이 아닙니다.</p>
</footer>
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>const D={payload};{JS}</script></body></html>"""


CSS = r"""
:root{--bg:#1e1e1e;--bg2:#262626;--bg3:#2e2e2e;--line:#363636;--text:#dcddde;--muted:#a3a3a3;--faint:#747474;
--accent:#a88bfa;--accent-bg:rgba(168,139,250,.10);--accent-line:rgba(168,139,250,.45);
--up:#5cc99a;--up-bg:rgba(92,201,154,.10);--down:#e5776e;--down-bg:rgba(229,119,110,.10);--amber:#e3b25c;--amber-bg:rgba(227,178,92,.10);--info:#6ea8e0;--info-bg:rgba(110,168,224,.09)}
@media (prefers-color-scheme:light){:root{--bg:#ffffff;--bg2:#f6f6f6;--bg3:#efefef;--line:#e2e2e2;--text:#222;--muted:#5c5c5c;--faint:#8a8a8a;
--accent:#7652e8;--accent-bg:rgba(118,82,232,.07);--accent-line:rgba(118,82,232,.4);--up:#17895a;--up-bg:rgba(23,137,90,.08);--down:#c9463c;--down-bg:rgba(201,70,60,.07);--amber:#a8730f;--amber-bg:rgba(168,115,15,.08);--info:#2e6db0;--info-bg:rgba(46,109,176,.07)}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;scroll-padding-top:12px}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 "Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
.note{max-width:760px;margin:0 auto;padding:28px 18px 56px}
.top{display:flex;align-items:baseline;gap:10px}
h1{font-size:1.7rem;font-weight:700;letter-spacing:-.02em;margin:0}
.top{flex-wrap:wrap}.ver{font-size:.78rem;color:var(--accent);background:var(--accent-bg);padding:1px 8px;border-radius:999px}
.sub{font-size:.78rem;color:var(--faint);letter-spacing:.01em}
.exp-badge{font-size:.72rem;font-weight:600;color:var(--up);background:var(--up-bg);padding:1px 7px;border-radius:4px}
.chip.hits{color:var(--text);background:var(--bg3);font-weight:600}
svg.spark{flex:none;vertical-align:middle}svg.spark polyline{fill:none;stroke-width:1.5;stroke-linejoin:round}
.sp-up polyline{stroke:var(--up)}.sp-dn polyline{stroke:var(--down)}
.card-h svg.spark{margin-left:auto}.card-h svg.spark+.px{margin-left:0}
li.row>svg.spark{float:right;margin:3px 0 0 10px}
[data-coin].flash{animation:flash 1.4s ease}
@keyframes flash{0%,40%{background:var(--accent-bg)}100%{background:transparent}}
/* 레이아웃 */
.layout{display:flex;flex-direction:column}
.side{order:-1}
.panel{background:var(--bg2);border-radius:8px;padding:10px 12px;margin:12px 0 4px}
details.panel{border-bottom:0}details.panel>summary{padding:4px 0}
.panel-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
#map{width:100%;height:300px}
#map text{font-size:10px;fill:var(--muted);pointer-events:none}#map text.sl{font-size:11px;fill:var(--text);font-weight:600}
#map line{stroke:var(--line);stroke-width:1}#map circle{cursor:pointer;stroke:var(--bg2);stroke-width:1.5}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:.74rem;color:var(--muted);margin-top:4px}
.legend i.d{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle}
.d.g{background:var(--up)}.d.b{background:var(--info)}.d.p{background:var(--accent)}.d.a{background:var(--amber)}.d.r{background:var(--down)}.d.n{background:var(--faint)}
@media (min-width:1100px){
 .note{max-width:1320px;padding:32px 28px 60px}
 .layout{display:grid;grid-template-columns:minmax(0,1fr) 440px;gap:28px;align-items:start}
 .side{order:0;grid-column:2;grid-row:1;position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}
 .main{grid-column:1;grid-row:1}
 #map{height:440px}
}
h2{font-size:1.2rem;font-weight:650;letter-spacing:-.01em;margin:30px 0 8px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h2 small{font-size:.78rem;font-weight:400;color:var(--faint)}
h4{font-size:.9rem;font-weight:600;margin:14px 0 6px;color:var(--muted)}
p{margin:.35em 0}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.na{color:var(--faint)}.up{color:var(--up)}.down{color:var(--down)}.warn-text{color:var(--amber);font-weight:600}
.nw{white-space:nowrap}.sm{font-size:.8rem}.sep{color:var(--faint);margin:0 6px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem;background:var(--bg3);padding:0 5px;border-radius:4px}
/* 바로가기 */
.jump{display:flex;gap:6px;overflow-x:auto;margin:12px 0 10px;padding-bottom:2px;-webkit-overflow-scrolling:touch}
.jump a{flex:none;font-size:.82rem;color:var(--muted);background:var(--bg2);padding:4px 11px;border-radius:999px}
.jump a b{color:var(--accent);font-weight:600;margin-left:2px}.jump a:hover{text-decoration:none;color:var(--text)}
/* 상태 */
.props{margin:0 0 10px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:4px 0}
.props div{display:grid;grid-template-columns:84px 1fr;gap:10px;padding:3px 0;font-size:.85rem}
.props dt{color:var(--muted)}.props dd{margin:0}
.pill{display:inline-block;font-size:.76rem;padding:0 8px;border-radius:999px;margin:0 4px 2px 0;background:var(--bg3)}
.pill.ok{color:var(--up)}.pill.bad{color:var(--faint);text-decoration:line-through}
/* 콜아웃 */
.callout{border-radius:6px;padding:12px 14px;margin:10px 0;background:var(--bg2)}
.callout.slim{padding:9px 14px;font-size:.88rem}
.callout.info{background:var(--info-bg)}.callout.info b{color:var(--info)}
.callout.warn{background:var(--amber-bg)}.callout.warn b{color:var(--amber)}
.callout.empty{color:var(--muted)}
.callout .say{display:block;color:var(--muted);font-size:.82rem}
.nums-s{color:var(--muted);font-size:.84rem;font-variant-numeric:tabular-nums;white-space:nowrap}
.warnbox>summary{color:var(--amber)!important}.warnbox ul{margin:4px 0;padding-left:1.2em;font-size:.84rem;color:var(--muted)}
/* 카드 */
.card{border-radius:8px;padding:12px 14px;margin:10px 0;background:var(--bg2)}
.card.focus{background:var(--accent-bg);box-shadow:inset 3px 0 0 var(--accent)}
.card-h{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.card-h .sym{color:var(--accent);font-size:1.2rem}.c-icon{color:var(--accent);font-size:.85rem}
.c-name{color:var(--muted);font-size:.85rem}.px{margin-left:auto;font-weight:600;font-variant-numeric:tabular-nums}
.meta{font-size:.82rem;color:var(--muted);margin:3px 0}.card .meta .tier{margin-right:8px}
.line{font-size:.85rem;margin:4px 0}.line .k{display:inline-block;min-width:34px;color:var(--faint);font-size:.78rem;margin-right:6px}
.tag{display:inline-block;font-size:.76rem;color:var(--accent);background:var(--accent-bg);padding:0 7px;border-radius:999px;margin-right:6px;white-space:nowrap}
.tier{font-size:.76rem;color:var(--muted)}
/* 조건 칩 */
.chips{display:flex;flex-wrap:wrap;gap:4px;margin:7px 0}
.chip{font-size:.76rem;padding:1px 8px;border-radius:5px;white-space:nowrap;cursor:help}
.chip em{font-style:normal;opacity:.85;font-variant-numeric:tabular-nums}
.chip.ok{color:var(--up);background:var(--up-bg)}.chip.bad{color:var(--down);background:var(--down-bg)}.chip.na{color:var(--faint);background:var(--bg3)}
.copy{font:inherit;font-size:.72rem;margin-left:4px;padding:0 6px;border-radius:4px;border:1px solid var(--line);background:none;color:var(--muted);cursor:pointer}
/* 목록 행 */
ul.rows{list-style:none;margin:0;padding:0}
li.row{padding:9px 0;border-bottom:1px solid var(--line)}
.row-h{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}.row-h .sym{font-size:.98rem}
.row-f{display:flex;align-items:flex-end;gap:10px}.row-f .meta{flex:1}.row-f .act{font-size:.82rem;white-space:nowrap}
li.row .chips{margin:5px 0 3px}li.row .meta{margin:0}
.act a{margin-right:10px}
.c-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.btn{display:inline-block;font:inherit;font-size:.84rem;padding:6px 13px;border-radius:6px;background:var(--accent);color:#fff;border:0;cursor:pointer}
.btn:hover{text-decoration:none;filter:brightness(1.08)}
.btn.ghost{background:transparent;color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent-line)}
.btn.ghost[aria-pressed=true]{background:var(--accent-bg)}
/* 접기 */
details>summary{cursor:pointer;list-style:none}details>summary::-webkit-details-marker{display:none}
details.sector,details.fold{border-bottom:1px solid var(--line)}
details.sector>summary,details.fold>summary{display:flex;align-items:center;gap:10px;padding:10px 0;flex-wrap:wrap}
details.fold>summary{font-size:.9rem}
details.sector>summary::before,details.inner>summary::before,details.fold>summary::before{content:"";width:0;height:0;border-left:5px solid var(--faint);border-top:4px solid transparent;border-bottom:4px solid transparent;transition:transform .15s}
details[open]>summary::before{transform:rotate(90deg)}
details.sector[open],details.fold[open]{padding-bottom:12px}
.s-name{font-weight:650;font-size:1rem}.kind{font-size:.72rem;color:var(--faint)}
.s-rs{margin-left:auto;font-size:.82rem;color:var(--muted);font-variant-numeric:tabular-nums}
.label{font-size:.75rem;font-weight:600;padding:1px 8px;border-radius:4px}
.l-early{color:var(--accent);background:var(--accent-bg)}.l-improve{color:var(--info);background:var(--info-bg)}
.l-neutral{color:var(--faint);background:var(--bg3)}.l-caution{color:var(--amber);background:var(--amber-bg)}.l-hot{color:var(--down);background:var(--down-bg)}
details.inner{margin:8px 0}details.inner>summary{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:.84rem}
/* 표 */
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.84rem;font-variant-numeric:tabular-nums}
th{color:var(--faint);font-weight:500;text-align:left;font-size:.75rem;padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
td small{display:block;color:var(--faint);font-size:.72rem}
td.act{text-align:right}
.cmp:not(.btn){font:inherit;font-size:.8rem;background:none;border:0;color:var(--muted);cursor:pointer;padding:0}
.cmp[aria-pressed=true]:not(.btn){color:var(--accent);font-weight:600}
table.kv td:first-child{color:var(--muted);white-space:normal}
ul.sig,ul.check{list-style:none;padding:0;margin:4px 0 8px}
ul.sig li{display:flex;gap:10px;padding:3px 0;font-size:.88rem}ul.sig li>span{width:12px;flex:none}
ul.sig small{display:block;color:var(--faint)}
ul.sig li.hit>span{color:var(--up)}ul.sig li.warnhit>span{color:var(--down)}ul.sig li.miss>span,ul.sig li.na>span{color:var(--faint)}
ul.check li{font-size:.86rem}ul.check li::before{content:"☐ ";color:var(--muted)}
.c-sub{font-size:.78rem;color:var(--muted);margin:10px 0 2px;font-weight:600}
/* 차트 */
.chart-wrap{background:var(--bg2);border-radius:6px;padding:8px}
#chart{width:100%;height:auto;display:block}
#legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.8rem;padding:6px 4px 0}
#legend button{font:inherit;background:none;border:0;color:var(--text);cursor:pointer;padding:0}
.gloss dt{font-weight:600;margin-top:10px;font-size:.9rem}.gloss dd{margin:2px 0 0;color:var(--muted);font-size:.86rem}
/* 푸터 */
footer{margin-top:36px;padding-top:14px;border-top:1px solid var(--line);font-size:.82rem;color:var(--muted)}
footer .brand{font-size:.92rem;color:var(--text);display:flex;gap:8px;align-items:baseline}
.cl{margin:8px 0}.cl ul{margin:2px 0;padding-left:1.2em}.cl li{margin:1px 0}
@media (max-width:560px){.note{padding:18px 12px 48px}h1{font-size:1.45rem}.props div{grid-template-columns:76px 1fr}svg.spark{width:56px}#map{height:340px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}html{scroll-behavior:auto}}
"""

JS = r"""
const COLORS=['#a88bfa','#5cc99a','#e3b25c','#e5776e','#6ea8e0','#c8b45a'];
const sel=new Set(D.init.filter(i=>D.sp[i]));
function norm(p){return p.map(v=>(v/p[0]-1)*100)}
function draw(){
  const svg=document.getElementById('chart'),W=640,H=240,L=44,R=10,T=12,B=26;
  const series=[...sel].slice(0,6).map((id,k)=>({id,name:D.sp[id].s,v:norm(D.sp[id].p),c:COLORS[k]}));
  const btc=D.btc.length?norm(D.btc):null;
  const all=series.flatMap(s=>s.v).concat(btc||[]);
  if(!all.length){svg.innerHTML='<text x="320" y="120" text-anchor="middle" fill="currentColor" opacity=".5" font-size="14">목록의 비교 버튼으로 코인을 추가하세요</text>';document.getElementById('legend').innerHTML='';return}
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
function copyText(t){if(navigator.clipboard&&window.isSecureContext)return navigator.clipboard.writeText(t);
  const a=document.createElement('textarea');a.value=t;a.style.position='absolute';a.style.left='-9999px';document.body.appendChild(a);a.select();
  try{document.execCommand('copy')}finally{a.remove()}return Promise.resolve()}
document.addEventListener('click',e=>{
  const c=e.target.closest('.copy');
  if(c){copyText(c.dataset.copy).then(()=>{const o=c.textContent;c.textContent='복사됨';setTimeout(()=>c.textContent=o,1200)});return}
  const b=e.target.closest('.cmp');
  if(b){const id=b.dataset.id;if(!D.sp[id])return;if(sel.has(id))sel.delete(id);else{if(sel.size>=6){alert('비교는 최대 6개까지');return}sel.add(id)}
    const f=document.getElementById('chart').closest('details');if(f&&sel.size)f.open=true;draw();return}
  const r=e.target.closest('[data-rm]');if(r){sel.delete(r.dataset.rm);draw()}
});
draw();
function goto(sel){const el=document.querySelector(sel);if(!el)return;
  const d=el.closest('details:not([open])');if(d)d.open=true;if(el.tagName==='DETAILS')el.open=true;
  el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash')}
function drawMap(){
  const box=document.getElementById('map');if(!box)return;box.innerHTML='';
  if(!window.d3){box.innerHTML='<p class="na sm">지도 라이브러리를 불러오지 못했습니다.</p>';return}
  const cs=getComputedStyle(document.documentElement),v=n=>cs.getPropertyValue(n).trim();
  const SC={'초입 정황':v('--up'),'개선 중':v('--info'),'중립':v('--faint'),'주의':v('--amber'),'과열 경고':v('--down')};
  const CC={red:v('--accent'),exp:v('--up'),yellow:v('--info'),small:v('--muted')};
  const W=box.clientWidth,H=box.clientHeight;
  const nodes=D.map.n.map(d=>({...d})),links=D.map.l.map(([s,t])=>({source:s,target:t}));
  const has=new Set(links.map(l=>l.source));
  nodes.forEach(d=>{d.rad=d.t==='s'?(d.st==='중립'&&!has.has(d.id)?5:9):3+Math.max(0,Math.min(6,Math.log10((d.mc||5e7)/5e7)*2.2));
    d.lab=d.t!=='s'||d.st!=='중립'||has.has(d.id)});
  const svg=d3.select(box).append('svg').attr('viewBox',[0,0,W,H]).attr('width',W).attr('height',H);
  const g=svg.append('g');
  svg.call(d3.zoom().scaleExtent([.5,3]).on('zoom',e=>g.attr('transform',e.transform)));
  const link=g.append('g').selectAll('line').data(links).join('line');
  const node=g.append('g').selectAll('circle').data(nodes).join('circle').attr('r',d=>d.rad)
    .attr('fill',d=>d.t==='s'?(SC[d.st]||v('--faint')):(d.w?v('--amber'):CC[d.g]))
    .on('click',(e,d)=>goto(d.t==='s'?`details[data-sec="${d.id.slice(2)}"]`:`[data-coin="${d.id}"]`));
  node.append('title').text(d=>d.t==='s'?`${d.n} · ${d.st}`:`${d.n}${d.w?' · 주의 필요':''}`);
  const label=g.append('g').selectAll('text').data(nodes).join('text').attr('class',d=>d.t==='s'?'sl':'')
    .attr('text-anchor','middle').text(d=>d.lab?d.n:'');
  const sim=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(d=>d.id).distance(32).strength(.7))
    .force('charge',d3.forceManyBody().strength(d=>d.t==='s'?-120:-30)).force('center',d3.forceCenter(W/2,H/2))
    .force('collide',d3.forceCollide(d=>d.rad+(d.t==='s'?(d.lab?18:8):7))).force('x',d3.forceX(W/2).strength(.04)).force('y',d3.forceY(H/2).strength(.06));
  node.call(d3.drag().on('start',(e,d)=>{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y})
    .on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y}).on('end',(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null}));
  const PX=Math.min(44,W*.1);
  sim.on('tick',()=>{nodes.forEach(d=>{d.x=Math.max(PX,Math.min(W-PX,d.x));d.y=Math.max(14,Math.min(H-20,d.y))});
    link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
    node.attr('cx',d=>d.x).attr('cy',d=>d.y);label.attr('x',d=>d.x).attr('y',d=>d.y+d.rad+11)});
}
drawMap();let rt;window.addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(drawMap,300)});
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
    state.setdefault("coin_oi", [])
    phist = load(os.path.join(DATA_DIR, "price.json"), {})
    uhist = load(os.path.join(DATA_DIR, "upbit.json"), {})

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
                cache["fees"], cache["fees7"] = fees_new
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
    user_check = bool(cache.get("listing")) or MOCK or any(dstat.get(v) == "ok" for v in ("Bitget", "OKX"))
    if not user_check:
        errors.append("상장 거래소 정보를 받지 못해 '상장' 기준을 건너뜀")

    # 거래량 기록 (섹터 데이터가 새로 온 경우만, 하루 1칸)
    all_rows = {}
    for rows in cats.values():
        for c in rows:
            all_rows.setdefault(c["id"], c)
    if cat_fresh:
        for i, c in all_rows.items():
            if c["mc"] >= TH["minor_mcap"]:
                h = [x for x in dvol.get(i, []) if x[0] != today] + [[today, c["vol"]]]
                dvol[i] = h[-8:]
        dvol = {i: h for i, h in dvol.items() if i in all_rows}
    coins = {i: analyze_coin(c, derivs, dvol, fees, today) for i, c in all_rows.items() if not excluded(c)}
    # 체인·컨트랙트 주소 (하루 1번, 새 코인이 생기면 다음 날 반영)
    want_ids = {i for i, c in coins.items() if c["mc"] >= TH["minor_mcap"]}
    if MOCK:
        cache["plat"] = mock_platforms(want_ids)
    elif NOW_TS - cache.get("plat_ts", 0) >= DAY_REFRESH_S or not cache.get("plat"):
        pl = safe("체인 정보", lambda: fetch_platforms(want_ids), None)
        if pl:
            cache["plat"], cache["plat_ts"] = pl, NOW_TS
    plat = cache.get("plat") or {}
    # 상장 거래소 (하루 1번) · 업비트 거래대금 · CMC 교차확인 (섹터 데이터와 같은 4시간 주기)
    if MOCK:
        cache["listing"], upb_now = mock_extras(want_ids, NOW_TS // 3600)
        _r = random.Random(NOW_TS // 86400)
        cache["fees7"] = {k: v / 30 * 7 * _r.uniform(0.6, 1.8) for k, v in fees.items()}
        cache["cmc"] = {c["sym"]: [[c["px"] * (1.06 if hash(i) % 13 == 0 else 1.0), c["vol"], c["mc"]]] for i, c in coins.items()}
    else:
        upb_now = None
        if NOW_TS - cache.get("list_ts", 0) >= DAY_REFRESH_S or not cache.get("listing"):
            new = {}
            for v, ex in LIST_VENUES.items():
                r = safe(f"{v} 상장 목록", lambda e=ex: fetch_listing(e), None)
                if r:
                    new[v] = r
            if new:
                old = cache.get("listing", {})
                old.update(new)
                cache["listing"], cache["list_ts"] = old, NOW_TS
        if cat_fresh:
            krw = (cache.get("listing", {}).get("Upbit") or {}).get("krw") or {}
            if krw:
                upb_now = safe("업비트 거래대금", lambda: fetch_upbit_krw(krw), None)
            if CMC_KEY:
                cm = safe("CoinMarketCap", fetch_cmc, None)
                if cm:
                    cache["cmc"] = cm
        if not CMC_KEY:
            errors.append("CoinMarketCap 키(CMC_API_KEY)가 없어 교차 확인을 건너뜀")
    listing = {v: set(d.get("ids", [])) for v, d in (cache.get("listing") or {}).items()}
    cmc = cache.get("cmc") or {}
    if cat_fresh:
        for i, c in coins.items():   # 가격 이력 (하루 1칸, 최대 61일)
            if c["mc"] >= TH["minor_mcap"] and c["px"]:
                h = [x for x in phist.get(i, []) if x[0] != today] + [[today, c["px"]]]
                phist[i] = h[-61:]
        phist = {i: h for i, h in phist.items() if i in all_rows}
        if upb_now:
            for i, v in upb_now.items():
                if v:
                    h = [x for x in uhist.get(i, []) if x[0] != today] + [[today, v]]
                    uhist[i] = h[-8:]
    # 코인별 OI 24시간 변화
    snap = {i: c["oi"] for i, c in coins.items() if c["oi"]}
    prev_oi = min(state["coin_oi"], key=lambda h: abs(h["ts"] - (NOW_TS - 86400)), default=None)
    if prev_oi and abs(prev_oi["ts"] - (NOW_TS - 86400)) > 3 * 3600:
        prev_oi = None
    state["coin_oi"] = [h for h in state["coin_oi"] if NOW_TS - h["ts"] <= 30 * 3600] + [{"ts": NOW_TS, "oi": snap}]
    fees7 = cache.get("fees7", {})
    for i, c in coins.items():
        c["plats"] = plat.get(i)
        c["listed"] = sorted({v for v, ids in listing.items() if i in ids} | {v for v in ("Bitget", "OKX") if v in c["venues"]},
                             key=USER_VENUES.index)
        vh = [v for _, v in dvol.get(i, [])]
        c["vtrend"] = statistics.mean(vh[-3:]) / statistics.mean(vh[:-3]) if len(vh) >= 6 and statistics.mean(vh[:-3]) > 0 else None
        ph = [p for d, p in phist.get(i, []) if d != today][-TH["break_days"]:]
        c["brk"] = None if len(ph) < TH["break_days"] - 5 or c["dd"] is None or not c["px"] else \
            (c["dd"] <= TH["break_dd"] and c["px"] > max(ph))
        f30, f7 = fees.get(i), fees7.get(i)
        c["fee_up"] = f7 / (f30 / 30 * 7) if f30 and f7 is not None and i in fees7 else None
        c["oi24c"] = pct(c["oi"], prev_oi["oi"].get(i)) if prev_oi and c["oi"] and prev_oi["oi"].get(i) else None
        uh = uhist.get(i, [])
        up = [v for d, v in uh if d != today]
        cur = next((v for d, v in uh if d == today), None)
        c["upx"] = cur / statistics.mean(up) if cur and len(up) >= 4 and statistics.mean(up) > 0 else None
        c["xc"] = xcheck(c, cmc) if cmc else None

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
    # 소형 코인(참고): 시총만 미달이고 나머지 규칙은 통과
    sbest = {}
    for sec in sectors:
        for c in sec["cands"]:
            if c["small_grade"] and (c["a"]["id"] not in sbest or c["score"] > sbest[c["a"]["id"]]["score"]):
                sbest[c["a"]["id"]] = c
    small = sorted(sbest.values(), key=lambda c: (c["small_grade"] != "red", -c["score"]))[:10]
    ebest = {}
    for sec in sectors:
        for c in sec["cands"]:
            k = (c["ehits"], c["score"])
            if c["exp"] and (c["a"]["id"] not in ebest or k > (ebest[c["a"]["id"]]["ehits"], ebest[c["a"]["id"]]["score"])):
                ebest[c["a"]["id"]] = c
    exp = sorted(ebest.values(), key=lambda c: (-c["ehits"], -(c["a"]["c7"] or 0)))[: TH["exp_max"]]
    picks = {"red": red, "yellow": yellow, "small": small, "exp": exp}

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
        empty = f"강한 섹터는 있지만 시총 {f_usd_plain(TH['pick_mcap'])} 이상에서 모든 조건을 통과한 코인이 없습니다. 관심 목록을 참고하세요."
    age_m = max(0, NOW_TS - cache["cat_ts"]) // 60 if cache.get("cat_ts") else None
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
    save(os.path.join(DATA_DIR, "price.json"), phist)
    save(os.path.join(DATA_DIR, "upbit.json"), uhist)
    save(os.path.join(CACHE_DIR, "cache.json"), cache)
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"완료 v{VERSION} {now:%Y-%m-%d %H:%M} | 지금 볼 것 {len(red)} | 관심 {len(yellow)} | 소형 {len(small)} | 실험 {len(exp)} | 섹터 {len(sectors)} | 거래소 {dstat}")
    for e in errors:
        print(" -", e)


if __name__ == "__main__":
    main()
