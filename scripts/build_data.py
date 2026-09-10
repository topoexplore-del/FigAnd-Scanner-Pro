"""
FIGAND SCANNER PRO — Build Data Pipeline v18.0
Dual data sources: Yahoo Finance (primary) + Finnhub (secondary).
Run: python scripts/build_data.py --out-dir data
"""
import argparse, json, os, time, warnings
import urllib.request
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")  # Free key from finnhub.io

def finnhub_quote(ticker):
    """Get real-time quote from Finnhub (free tier: 60 calls/min)."""
    if not FINNHUB_KEY:
        return None
    try:
        t = ticker.replace(".HK", "")  # Finnhub uses different format for HK
        url = f"https://finnhub.io/api/v1/quote?symbol={t}&token={FINNHUB_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "NexusScannerPro/8.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        if data and data.get("c", 0) > 0:
            return {"close": data["c"], "high": data["h"], "low": data["l"],
                    "open": data["o"], "prev_close": data["pc"], "change_pct": data.get("dp", 0)}
    except Exception:
        pass
    return None

def finnhub_metrics(ticker):
    """Get basic financials from Finnhub."""
    if not FINNHUB_KEY:
        return {}
    try:
        t = ticker.replace(".HK", "")
        url = f"https://finnhub.io/api/v1/stock/metric?symbol={t}&metric=all&token={FINNHUB_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "NexusScannerPro/8.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        m = data.get("metric", {})
        return {
            "pe_finnhub": m.get("peBasicExclExtraTTM"),
            "roe_finnhub": m.get("roeTTM"),
            "roa_finnhub": m.get("roaTTM"),
            "eps_growth_finnhub": m.get("epsGrowthTTMYoy"),
            "beta": m.get("beta"),
            "52w_high": m.get("52WeekHigh"),
            "52w_low": m.get("52WeekLow"),
            "dividend_yield": m.get("dividendYieldIndicatedAnnual"),
        }
    except Exception:
        return {}

# ── JSON SAFETY ──────────────────────────────────────────────────
# El módulo json de Python escribe NaN/Infinity literalmente, lo cual NO es
# JSON válido y rompe el dashboard en el navegador ("Unexpected token 'N'").
# Este sanitizador convierte cualquier valor no finito en null, recursivamente.
def json_safe(o):
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        o = o.item()
    if isinstance(o, float):
        return o if np.isfinite(o) else None
    return o

def dump_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json_safe(obj), f, ensure_ascii=False, allow_nan=False,
                  separators=(",", ":"))

# ── TICKER UNIVERSE ──────────────────────────────────────────────
GROUPS = {
    # ── US CORE ──
    "🎯 Watchlist Core": [
        "VRT","POWL","ETN","ANET","MPWR","PWR","CAT","FCX",
        "NVDA","PLTR","AVGO","AMD","LMT","NOC","CEG","SMCI",
        "GE","ROK","URI","DE", "SMHI","ALRS","RELY","FVR","CMDB","DAVE","CALY","CPIX","ANGO","XHR",
    "CLBK","FNWB","NODK","SNFCA","BSVN","HNVR","UHAL","UHAL-B","WBI",
    "TVIV","SUNC","SIND","OCAC-U","NHP","JAN","COAG","ARCI","TBI","FA",
    "GTY","TRNO","KRT","PECO","HONA","SPCX","FDXF","DWD","DFAC","CGDV","CBRS","ALAB","QXO","AIRR",
    "HBC2","CGXU","AWM","FENI","TRVC","SPMO","AHR","PTY","BSCS","BSCR",
    "CGIC","FPS","FEOE","ALS","CRWV","QYLD","BSCT","PFFA","SARO","SHC",
    "QDPL","NAD","FEGE","UTH","FT2","TLN","RWL","GTO","JPC","Q","P","EX9",
    "BSCU","BOTZ","FEY","NAVN","MG1","SUX","ONEQ","SAJA","MMT","NZF","LIF",
    "AGNT","INFL"
    ],
    "🤖 AI & Semiconductors": [
        "TSM","ASML","LRCX","KLAC","MU","ARM","ON",
        "QCOM","AMAT","MRVL","ADI","NXPI"
    ],
    # ── LATAM COMPLETO ──
    "🌎 LATAM": [
        "NU","MELI","VALE","PBR","SQM","BSBR","ABEV","ITUB",
        "GLOB","STNE","AMX","FMX","PAC","VIST","SUPV",
        "BAP","KOF","BMA","IFS","TGLS","YPF","BCH","BVN",
        "BSAC","EDN","BWMX","BBAR","DLO","CCU","TEO",
        "CX","AUNA","TV"
    ],
    # ── COLOMBIA ──
    "🇨🇴 Colombia": [
        "EC","CIB","AVAL","CNNE","CRGIY"
    ],
    # ── ESPAÑA ──
    "🇪🇸 España": [
        "SAN","TEF","BBVA","IBE","ITX","REP"
    ],
    # ── REINO UNIDO ──
    "🇬🇧 Reino Unido": [
        "SHEL","AZN","HSBC","BP","RIO","LSEG",
        "GSK","UL","DEO","BCS","NWG","VOD"
    ],
    # ── CHINA CONTINENTAL ──
    "🇨🇳 China Continental": [
        "BABA","PDD","JD","BIDU","NIO","LI",
        "XPEV","ZK","FUTU","TME","BILI","YMM"
    ],
    # ── HONG KONG ──
    "🇭🇰 Hong Kong": [
        "0700.HK","9988.HK","1299.HK","0005.HK","2318.HK",
        "0388.HK","0941.HK","1810.HK","9618.HK","3690.HK"
    ],
    # ── ÍNDICES MUNDIALES ──
    "📊 Índices Mundiales": [
        "SPY","QQQ","DIA","IWM",
        "EWZ","EWW","FXI","MCHI",
        "EWU","EWG","EWQ","EWJ","EWY",
        "EWA","EZA","EWT"
    ],
    # ── ETFs GLOBALES ──
    "💼 ETFs Globales": [
        "VTI","VXUS","VWO","VEA",
        "GLD","SLV","USO",
        "XLE","XLF","XLK","XLV","XLI",
        "SOXX","KWEB","ARKK",
        "TLT","HYG","LQD","VUG","IWF","VO","VGT","MGK","VOO","AGG","NOBL","VYM","IVV","VXUS","VEU","FBND","BNDX","HDV","PYLD","DFCF","XLB","VIG","MUB","IEF","GOVT","DYNF","SCHF","QQQM","AVDV","IALT","VTI","IEFA","XLK","SMH","VTIP","MBB","XLU","VYMI","JEPQ","PULS","VTWO","AIRR","FNDE","IJS","VOOG","ICLN","IJH","SCHD","DON","AVUV","DFAC","XLI","SHYG","DFAS","IGV","IQLT","SCHZ","CORO","DRAM","GGOV","BLCR","DFSD","JIRE","NYF","ANGL","VTES","HYD","PSI","QTUM","DIHP","QTEC","GPIQ","IFRA","BND","SCHX","SOXX","VCIT","SCHG","DFUS","SCHO","STIP","GLDM","IYW","IXUS","DVY","SCHE","GRID","DFAI","HEFA","ESGE","AVUS","VONV","EAGG","VCRB","PAAA","MGV","LMBS","BITO","XAR","CGMU","DUHP","VIS","ROBO","IBDV","IBDU","DBMF","IBTH","GSST","BALT","AOM","HYS","GPIX","FTSM","DVYE","VWO","VOE","JEPI","IWD","XLY","VT","ITA*","VXF","SDVY","ESGU","MDY","IWO","VSGX","GSLC","VGK","PFF","JPIE","VGLT","SCHH","PGX","IXN","VIGI","FDL","NLR","SPSB","IGIB","FLOT","IBDR","IDEV","JPEF","USRT","DFNM","DFEV","XJH","DIVO","SPHY","EFAV","PSK","CMDY","JCPB","JGRO","PMBS","AGGY","RECS","IDEF","KNG","AIPO","FWD","QLD","IBTI","IBTJ","IBTK","QQQI","NASA","FFLC","IBTL","IGPT","CDX","CGDG","TAFM","BUFF","ARTY","FLDR","VWOB","HDEF","JMOM","MINO","RAAX","SUSB","ICF","EMGF","VEA","SPYM","VTEB","BSV","VNQ","MINT","USHY","JPST","IEI","IUSB","CGGR","PAVE","DFAE","DFAT","SCHM","LQD","VGSH","XBI","IGSB","BOND","ESGV","EFG","SCHR","JBND","ACWX","ICSH","JAVA","PTL","GDXJ","CGMS","TBUX","SMMD","DIVI","SPYD","EEMV","BOTZ","IGRO","FREL","INTF","CWB","DFAL","SCHK","FHEQ","WQTM","LGOV","SSO","VPLS","FLHY","QLTA","NUKZ","BBAG","GFLW","DDTA","DDFA","XPH","AGZ","DDTZ","SDS",
        "AIQ","AVDE","AVGE","AVMV","BIV","BUFQ","CGCP","CGHM","CIBR","DCOR",
    "DFAR","DFAW","DFGP","DFGR","DFIC","DFIS","DFIV","DFLV","DFSI","DFSV",
    "DUSB","EMLC","ESGD","ESML","EWL","EWZ","FCOM","FDVV","FMDE","FNDX",
    "HACK","IBDW","IBDX","IYJ","JMST","JMUB","LMUB","LRGF","LVHI","MUNI",
    "NDQ","NEAR","PPA","RDVY","RSP","SCHP","SFLR","SPEM","SPIB","SPMB",
    "SPTL","SPY","SPYI","SPSM","SRLN","SUB","SYSB","TIP","UTES","VAW",
    "VCSH","VGIT","VLUE","VTEI","VTV","WCMI","XLP","XMMO","XOVR"
    ],
    # ── US MARKET (Top ~350 S&P 500 stocks) ──
    "🇺🇸 US Market": [
        # Tech
        "AAPL","MSFT","GOOGL","AMZN","META","TSLA","ORCL","CRM","ADBE","NOW",
        "PANW","CRWD","SNOW","NET","DDOG","INTU","CDNS","SNPS","FTNT","ZS",
        "WDAY","TEAM","HUBS","DOCU","VEEV","ANSS","CPAY","IT","KEYS","TYL",
        "EPAM","PAYC","MANH","MPWR","NXPI","MCHP","SWKS","QRVO","ZBRA","TER",
        "TRMB","GDDY","GEN","CTSH","WIT","ACN","IBM","CSCO","HPQ","HPE","DELL",
        "IMOS","FFIV","RDWR","CNXN","SCSC","NTCT","TRAX","IPCX","OKTA","TENB","QLYS","CYRX","VSTS",
          "KLAC","INTC","MU","MRVL","SNDK","TXN","APH","AVGO","LITE","WDC",
    "AMD","CIEN","AMKR","COHR","VRT","ARM","TSM","CGNX","IONQ","MTSI",
    "LRCX","ASX","JBL","ONTO","NOK","CVLT","QCOM","TWLO","ADI","NTAP",
    "CLS","TOST","MDB","LSCC","CRUS","CLSK","CIFR","PLXS","AUR","ZM",
    "SITM","ADP","MKSI","HIVE","SMCI","QBTS","UMC","AEVA",
        # Financials
        "JPM","V","MA","GS","MS","BLK","SCHW","AXP","C","BAC","WFC","USB",
        "PNC","TFC","COF","ICE","CME","SPGI","MCO","MSCI","FIS","FI","GPN",
        "AIG","MET","PRU","AFL","ALL","TRV","CB","AON","MMC","AJG","CINF","BRO",
        "TIGO","SMFG","NMR","NTRS","STT","VOYA","OPHC","SLF","PRI","SEIC","VIRT",
        "MFG","MUFG","HSBC","RY","BAP","UBS","SHG","KB","BPOP","FHI","GCMG","VCTR","IFS","PSO","QNST","RSI",
        "BNY","STT","IVZ","AMG","JXN","MFC","SLF","BMO","BNS","RY","TD","CM","ING","AEG","CFR","MTB","ZION","RF","FIBK","HWC","WTFC","BOH","CBU",
    "NBTB","BANR","NBHC","FBP","GNW","KRT","NREF","SEZL","PCB","SBFG","FFBC","CTBI","NEWT","PLBC","NTB","OPHC","NTRS","VCTR","GCMG","QNST",
    "NMR","UBS","MUFG","BRK/B","CFG","PNFP","NLY","EWBC","BEN","AIZ","MKL","AFRM","BGC",
    "RKT","ALLY","PIPR","HOOD","NDAQ","SAN","KEY","TROW","ERIE","COLB",
    "FCFS","MTG","BFH","CNS","CBOE","LYG","SNEX","UWMC","LPL",
        # Healthcare
        "UNH","LLY","JNJ","ABBV","MRK","PFE","TMO","ISRG","VRTX","REGN",
        "AMGN","GILD","MDT","SYK","BSX","EW","ZBH","BAX","BDX","HOLX","DXCM",
        "IDXX","MTD","A","WAT","IQV","CRL","TECH","ALGN","PODD","INCY",
        "RLAY","RVMD","DNTH","ACRS","TXG","SEPN","BLZE","TENX","FBRX","URGN",
        "PTGX","CRNX","MNPR","MIRM","IMVT","JAZZ","PSNL","DNLI","NKTX","PHVS","NRIX","PTCT","ICCC","SRRK","TGTX",
        "ABUS","NBIX","CORT","PRVA","ELV","VCEL","PNTG","WDFC","CHE","CVS","IART","GKOS","ACHC","PRVA","PGNY","ADPT","APGE","ELVN","PBYI",
    "ETON","MRVI","RLAY","RVMD","DNTH","ACRS","SEPN","BLZE","TENX","FBRX",
    "URGN","PTGX","CRNX","MNPR","MIRM","IMVT","JAZZ","PSNL","DNLI","NKTX",
    "PHVS","NRIX","PTCT","ICCC","SRRK","TGTX","ABUS","NBIX","CORT","VCEL",
    "PNTG","WDFC","CHE","MCK","BIIB","HIMS","ARGX","GSK","HRMY","DGX","NTRA","CAH","HALO",
    "TMDX","RARE","HQY",
        # Energy
        "XOM","CVX","COP","SLB","EOG","MPC","VLO","PSX","HES",
        "OXY","DVN","HAL","FANG","CTRA","APA","TRGP","WMB","OKE","KMI","POWW","DINO","PARR","PBA","GEV","ET","EPD","OVV","NOV","PBR","LNG","EQT","BKR","ENPH","SM",
    "WES","BE","AR","DTM","RUN","EOSE",
        # Defense & Aerospace
        "RTX","GD","BA","LHX","NOC","LMT","HII","TXT","HWM","TDG","AXON","HXL",
        # Industrials
        "HON","MMM","CMI","PH","ITW","TT","EMR","GE","ETN","ROK","AME",
        "DOV","FTV","XYL","NDSN","ROP","IEX","GWW","FAST","WSO","AOS",
        "IR","CARR","OTIS","JCI","GNRC","HUBB","RBC","SNA","WCC",
        "PENG","CVLG","EXPD","CSX","GTLS","BSET","WKC","SAH","PAG","UNP","UNF","EXPD","GTLS","BSET","SAH","PAG","RUSHA","CVLG","MATX","KFRC",
    "WKC","FA","GTY","TRNO","PDM","AAT","CUZ","HIW","STAG","IIPR","OTTR",
    "LQDT","WILC","SPB","XHR","DE","POWL","WM","LUV","ECHO","JBHT","ENS","DAL","VMI","EME","SWK",
    "MOG/A","MLI","QS","RRX","SPXC","FBIN","BMI","CHRW","OC","OII","AIR",
    "AAL","CR","APG","WTS","VRRM","NSP","FIX","OSK","XPO","R","SAIA",
        # Consumer Discretionary
        "COST","WMT","HD","LOW","NKE","SBUX","MCD","TJX","ROST","DG","DLTR",
        "BKNG","ABNB","MAR","HLT","RCL","CCL","LVS","WYNN","MGM",
        "F","GM","APTV","BWA","LEA","RL","TPR","GRMN","POOL","BBY","TSCO",
        "ORLY","AZO","AAP","KMX","LULU","DECK","ON","ULTA","EL","CPRI",
        "ARMK","JOYY","LTH","EAT","CUE","CAKE","CROX","ETSY","BJRI","CHEF","CROX","BBY","ABNB","BZH","RACD","CVNA","EXPE","TOL","QSR","PII","W","MHK","KTB","BOOT","DASH","M",
    "JD","VIPS","LEN/B",
        # Consumer Staples
        "PG","KO","PEP","PM","MO","STZ","BF-B","MNST","KDP","CLX",
        "CL","KMB","CHD","SJM","HSY","MKC","GIS","CAG","K","HRL","TSN","MDLZ","ATD","UL","FLO","SFM","PFGC","LW",
        # Real Estate
        "AMT","PLD","CCI","EQIX","PSA","SPG","O","DLR","VICI","WELL",
        "AVB","EQR","MAA","ESS","UDR","ARE","BXP","SLG","VNO","IIPR","VTR","HR","NXDT","HTO","PECO","BNL","FR","EPC","LAMR","COMP","CSGP","RYN","GLPI",
        # Utilities
        "NEE","DUK","SO","D","AEP","SRE","EXC","XEL","WEC","ES",
        "AEE","CMS","CNP","PNW","NI","EVRG","ATO","PEG","BNL","FR","PPL","ETR","CWEN","CEG","WTRG","UGI","VST","BIPC","BEPC",
        # Materials
        "LIN","APD","SHW","ECL","NUE","STLD","CF","MOS","ALB","FMC",
        "IFF","CE","PPG","VMC","MLM","NEM","FCX","AA","CPBI","KOP","ASH","GLW","SCCO","CRS","GPK","CBT","VALE","HL","NEU","SCL",
        # Communication Services
        "GOOG","DIS","NFLX","CMCSA","T","VZ","TMUS","CHTR","EA","TTWO",
        "MTCH","ZG","PINS","SNAP","ROKU","SPOT","WBD","PARA","LYV","DHX","JOYY","ANDG","MTCH","EA","JOYY","ANDG","DHX","ASTS","RDDT","LUMN","SE","TRI","FWONK","NTES"
    ],
}


# ── TECHNICAL MODEL (faithful Pine translation) ─────────────────
def compute_score(df):
    """Compute technical score 0-100. Anti-repaint: uses closed candles only."""
    c, h, v = df["Close"], df["High"], df["Volume"]
    ema50 = c.ewm(span=50, adjust=False).mean()
    ema200 = c.ewm(span=200, adjust=False).mean()
    # RSI
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    # ADX
    tr = pd.concat([h - df["Low"], (h - c.shift()).abs(), (df["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    up = h.diff(); dn = -df["Low"].diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0), index=df.index)
    ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0), index=df.index)
    pdi = 100 * pdm.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / atr.replace(0, np.nan)
    ndi = 100 * ndm.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    adx = dx.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    # Bollinger
    bb_basis = c.rolling(20).mean()
    bb_dev = c.rolling(20).std() * 2
    bb_w = (bb_basis + bb_dev - (bb_basis - bb_dev)) / bb_basis
    bb_w_low = bb_w.rolling(50).min()
    # Volume
    vol_ma = v.rolling(20).mean()
    rel_vol = v / vol_ma.replace(0, np.nan)
    # OBV
    obv = (np.sign(c.diff()) * v).cumsum()
    obv_sma = obv.rolling(10).mean()
    # Highest
    h20 = h.rolling(20).max()
    # Score components
    s_trend = ((ema50 > ema200) & (c > ema200)).astype(int) * 30
    s_mom = ((rsi > 50) & (rsi < 70)).astype(int) * 15
    s_adx = ((adx > 18) & (adx < 35)).astype(int) * 15
    s_comp = (bb_w < bb_w_low * 1.2).astype(int) * 15
    s_accum = ((obv > obv_sma) & (rel_vol > 1)).astype(int) * 15
    s_brk = (c > h20 * 0.97).astype(int) * 10
    score = s_trend + s_mom + s_adx + s_comp + s_accum + s_brk
    ext = (c - ema50) / ema50 * 100
    # AI probability (sigmoid)
    mz = (rsi - 50) / 10
    ts = (ema50 - ema200) / ema200.replace(0, np.nan)
    vr = bb_w / bb_w.rolling(50).mean().replace(0, np.nan)
    raw = mz * 0.8 + ts * 5 + (rel_vol - 1) * 1.2 + adx / 25
    ai = (100 / (1 + np.exp(-raw))) * (1 + (vr - 1) * 0.5)
    ai = ai.clip(5, 95)
    # ABC grade
    ema10 = c.ewm(span=10, adjust=False).mean()
    ema20 = c.ewm(span=20, adjust=False).mean()
    sma50 = c.rolling(50).mean()
    return {
        "score": score, "ai": ai, "rsi": rsi, "adx": adx,
        "ext": ext, "rel_vol": rel_vol, "ema50": ema50, "ema200": ema200,
        "ema10": ema10, "ema20": ema20, "sma50": sma50, "atr": atr,
    }


# ═══ SCREENER: PATRONES CHARTISTAS Y SEÑALES (estilo Finviz) ═════
# Detección por pivotes: un pivote alto/bajo es un máximo/mínimo local
# de ventana ±k. Sobre los pivotes se ajustan líneas de tendencia
# (regresión) y se clasifican las figuras clásicas del análisis técnico.

def find_pivots(hist, k=4, lookback=140):
    h = hist["High"].tail(lookback).reset_index(drop=True)
    l = hist["Low"].tail(lookback).reset_index(drop=True)
    ph, pl = [], []
    hv, lv = h.values, l.values
    for i in range(k, len(hv) - k):
        wh = hv[i - k:i + k + 1]
        wl = lv[i - k:i + k + 1]
        if hv[i] >= wh.max() - 1e-12 and int(wh.argmax()) == k:
            ph.append((i, float(hv[i])))
        if lv[i] <= wl.min() + 1e-12 and int(wl.argmin()) == k:
            pl.append((i, float(lv[i])))
    return ph, pl, len(hv)

def _slope_pct(points, ref_price):
    """Pendiente de la línea de tendencia en % del precio por barra."""
    if len(points) < 2 or ref_price <= 0:
        return None
    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    m = np.polyfit(xs, ys, 1)[0]
    return m / ref_price * 100

def detect_patterns(hist, lookback=140):
    """Patrones chartistas VIGENTES: [{name,tipo,icon,conf,obj,esc,lines}].
    v3 — Reglas de vigencia (evitan señalar figuras ya jugadas):
      · RECENCIA: el último pivote que define la figura debe estar a ≤15
        velas (≤20 en HCH y dobles) del presente. Un doble suelo cuyo 2º
        suelo quedó 40 velas atrás es historia, no una señal.
      · ALCANCE: el nivel de ruptura (cuello/resistencia) debe estar a ≤8%
        del precio actual; si no, la señal no es accionable hoy.
      · NO EXTENDIDO: si el precio ya superó el gatillo en >3%, el measured
        move está en curso o consumado y NO se señala (evita perseguir).
      · CONTENCIÓN: triángulos/canales/cuñas/rectángulos exigen que el
        precio siga DENTRO de la formación (±2-3%).
    El objetivo (obj) es la proyección clásica por measured move."""
    if len(hist) < 60:
        return []
    RECENT = 15          # velas máximas desde el último pivote (líneas de tendencia)
    RECENT_TOPS = 20     # ídem para dobles/triples/HCH (estructuras más lentas)
    REACH = 0.08         # el gatillo debe estar a ≤8% del precio
    EXT = 0.03           # extensión máxima permitida más allá del gatillo
    MAX_SPAN = 60        # separación máxima entre los dos techos/suelos

    ph, pl, nb = find_pivots(hist, k=4, lookback=lookback)
    c = hist["Close"].tail(lookback).reset_index(drop=True)
    n = len(c)
    close = float(c.iloc[-1])
    found = []

    def pct(p):
        return round((p / close - 1) * 100, 1)

    def add(name, tipo, conf, obj=None, esc=None, lines=None):
        icon = "🟢" if tipo == "bullish" else ("🔴" if tipo == "bearish" else "🟡")
        found.append({"name": name, "tipo": tipo, "icon": icon, "conf": int(conf),
                      "obj": round(obj, 2) if obj else None, "esc": esc,
                      "lines": [[int(a), round(b, 2), int(d), round(e, 2)] for a, b, d, e in (lines or [])]})

    def reach_ok(level):
        return abs(level / close - 1) <= REACH

    # ── Doble/Triple techo — vigente solo entre el 2º techo y la ruptura ──
    if len(ph) >= 2:
        (i1, v1), (i2, v2) = ph[-2], ph[-1]
        if 8 <= i2 - i1 <= MAX_SPAN and abs(v2 - v1) / max(v1, v2) <= 0.025 \
           and (n - 1 - i2) <= RECENT_TOPS:
            valley = float(c.iloc[i1:i2 + 1].min())
            top = (v1 + v2) / 2
            # vigencia: bajo los techos, pero SIN haber roto ya el cuello en exceso
            if valley <= top * 0.96 and close < top * 0.995 and close > valley * (1 - EXT) \
               and reach_ok(valley):
                obj = valley - (top - valley)
                esc = f"Bajista: si pierde el cuello ${valley:.2f}, proyección ≈ ${obj:.2f} ({pct(obj):+.1f}%)"
                lines = [(i1, v1, i2, v2), (max(0, i1 - 4), valley, min(n - 1, i2 + 6), valley)]
                triple = len(ph) >= 3 and abs(ph[-3][1] - v1) / v1 <= 0.03 and i2 - ph[-3][0] <= MAX_SPAN
                if triple:
                    lines[0] = (ph[-3][0], ph[-3][1], i2, v2)
                add("Triple techo" if triple else "Doble techo", "bearish", 75 if triple else 70, obj, esc, lines)
    # ── Doble/Triple suelo ──
    if len(pl) >= 2:
        (i1, v1), (i2, v2) = pl[-2], pl[-1]
        if 8 <= i2 - i1 <= MAX_SPAN and abs(v2 - v1) / max(v1, v2) <= 0.025 \
           and (n - 1 - i2) <= RECENT_TOPS:
            peak = float(c.iloc[i1:i2 + 1].max())
            bot = (v1 + v2) / 2
            if peak >= bot * 1.04 and close > bot * 1.005 and close < peak * (1 + EXT) \
               and reach_ok(peak):
                obj = peak + (peak - bot)
                esc = f"Alcista: si rompe el cuello ${peak:.2f}, proyección ≈ ${obj:.2f} ({pct(obj):+.1f}%)"
                lines = [(i1, v1, i2, v2), (max(0, i1 - 4), peak, min(n - 1, i2 + 6), peak)]
                triple = len(pl) >= 3 and abs(pl[-3][1] - v1) / v1 <= 0.03 and i2 - pl[-3][0] <= MAX_SPAN
                if triple:
                    lines[0] = (pl[-3][0], pl[-3][1], i2, v2)
                add("Triple suelo" if triple else "Doble suelo", "bullish", 75 if triple else 70, obj, esc, lines)

    # ── HCH y HCH invertido — cuello por los máximos/mínimos de REACCIÓN ──
    if len(ph) >= 3:
        (x1, s1), (x2, hd), (x3, s2) = ph[-3], ph[-2], ph[-1]
        if hd > s1 * 1.03 and hd > s2 * 1.03 and abs(s1 - s2) / max(s1, s2) <= 0.04 \
           and (n - 1 - x3) <= RECENT_TOPS and x3 - x1 <= MAX_SPAN * 1.5:
            r1 = float(c.iloc[x1:x2 + 1].min()); r2 = float(c.iloc[x2:x3 + 1].min())
            nl = (r1 + r2) / 2  # cuello = mínimos de reacción, NO el mínimo global
            if reach_ok(nl) and close > nl * (1 - EXT) and close < hd:
                obj = nl - (hd - nl)
                esc = f"Bajista: cabeza ${hd:.2f}; perder el cuello ${nl:.2f} proyecta ≈ ${obj:.2f} ({pct(obj):+.1f}%)"
                mid1, mid2 = (x1 + x2) // 2, (x2 + x3) // 2
                add("Hombro-Cabeza-Hombro", "bearish", 72, obj, esc,
                    [(x1, s1, x2, hd), (x2, hd, x3, s2), (mid1, r1, mid2, r2)])
    if len(pl) >= 3:
        (x1, s1), (x2, hd), (x3, s2) = pl[-3], pl[-2], pl[-1]
        if hd < s1 * 0.97 and hd < s2 * 0.97 and abs(s1 - s2) / max(s1, s2) <= 0.04 \
           and (n - 1 - x3) <= RECENT_TOPS and x3 - x1 <= MAX_SPAN * 1.5:
            r1 = float(c.iloc[x1:x2 + 1].max()); r2 = float(c.iloc[x2:x3 + 1].max())
            nl = (r1 + r2) / 2
            if reach_ok(nl) and close < nl * (1 + EXT) and close > hd:
                obj = nl + (nl - hd)
                esc = f"Alcista: romper el cuello ${nl:.2f} proyecta ≈ ${obj:.2f} ({pct(obj):+.1f}%)"
                mid1, mid2 = (x1 + x2) // 2, (x2 + x3) // 2
                add("HCH invertido", "bullish", 72, obj, esc,
                    [(x1, s1, x2, hd), (x2, hd, x3, s2), (mid1, r1, mid2, r2)])

    # ── Líneas de tendencia: exigen contención Y recencia ──
    rp = ph[-4:] if len(ph) >= 3 else []
    rl = pl[-4:] if len(pl) >= 3 else []
    sh = _slope_pct(rp, close)
    sl = _slope_pct(rl, close)
    trend60 = (close / float(c.iloc[max(0, n - 61)]) - 1) * 100

    def fitline(points):
        xs = np.array([p[0] for p in points], dtype=float)
        ys = np.array([p[1] for p in points], dtype=float)
        m, b = np.polyfit(xs, ys, 1)
        x1, x2 = int(xs.min()), min(n - 1, int(xs.max()) + 6)
        return (x1, m * x1 + b, x2, m * x2 + b), m, b

    if sh is not None and sl is not None and rp and rl:
        last_piv = max(rp[-1][0], rl[-1][0])
        if (n - 1 - last_piv) <= RECENT:
            FLAT, RISE = 0.06, 0.10
            h_flat, l_flat = abs(sh) < FLAT, abs(sl) < FLAT
            h_up, l_up = sh > RISE, sl > RISE
            h_dn, l_dn = sh < -RISE, sl < -RISE
            Lh, mh, bh = fitline(rp)
            Ll, ml, bl_ = fitline(rl)
            upper_now = mh * (n - 1) + bh
            lower_now = ml * (n - 1) + bl_
            inside = lower_now * 0.98 <= close <= upper_now * 1.02
            x0 = min(Lh[0], Ll[0])
            height = abs((mh * x0 + bh) - (ml * x0 + bl_))
            two = [Lh, Ll]
            if inside and h_flat and l_up and reach_ok(upper_now):
                obj = upper_now + height
                add("Triángulo ascendente", "bullish", 68, obj,
                    f"Alcista: romper la resistencia ${upper_now:.2f} proyecta ≈ ${obj:.2f} ({pct(obj):+.1f}%)", two)
            elif inside and l_flat and h_dn and reach_ok(lower_now):
                obj = lower_now - height
                add("Triángulo descendente", "bearish", 68, obj,
                    f"Bajista: perder el soporte ${lower_now:.2f} proyecta ≈ ${obj:.2f} ({pct(obj):+.1f}%)", two)
            elif inside and h_dn and l_up:
                add("Triángulo simétrico", "neutral", 60, None,
                    f"La ruptura define la dirección; movimiento esperado ≈ ±${height:.2f} ({height/close*100:.1f}%)", two)
            elif inside and h_up and l_up:
                if sl > sh * 1.5:
                    obj = close - height
                    add("Cuña ascendente", "bearish", 62, obj,
                        f"Bajista al romper abajo (${lower_now:.2f}): proyección ≈ ${obj:.2f} ({pct(obj):+.1f}%)", two)
                elif abs(sh - sl) <= max(0.05, 0.35 * abs(sh)):
                    obj = close + height
                    add("Canal alcista", "bullish", 65, obj,
                        f"Canal alcista vigente ({lower_now:.2f}–{upper_now:.2f}); continuar apunta ≈ ${obj:.2f} ({pct(obj):+.1f}%). Perder la base lo anula", two)
            elif inside and h_dn and l_dn:
                if abs(sh) > abs(sl) * 1.5:
                    obj = close + height
                    add("Cuña descendente", "bullish", 62, obj,
                        f"Alcista al romper arriba (${upper_now:.2f}): proyección ≈ ${obj:.2f} ({pct(obj):+.1f}%)", two)
                elif abs(sh - sl) <= max(0.05, 0.35 * abs(sh)):
                    obj = close - height
                    add("Canal bajista", "bearish", 65, obj,
                        f"Canal bajista vigente; continuar apunta ≈ ${obj:.2f} ({pct(obj):+.1f}%). Romper el techo lo anula", two)
            elif inside and h_flat and l_flat:
                hi = float(np.mean([p[1] for p in rp])); lo = float(np.mean([p[1] for p in rl]))
                width = (hi - lo) / close * 100
                if 3 <= width <= 15:
                    bull = trend60 > 0
                    obj = (hi + (hi - lo)) if bull else (lo - (hi - lo))
                    lvl = hi if bull else lo
                    add("Rectángulo " + ("alcista" if bull else "bajista"),
                        "bullish" if bull else "bearish", 58, obj,
                        (f"Alcista: romper ${lvl:.2f} proyecta ≈ ${obj:.2f}" if bull else
                         f"Bajista: perder ${lvl:.2f} proyecta ≈ ${obj:.2f}") + f" ({pct(obj):+.1f}%)", two)

    # ── S/R horizontal: nivel cercano (≤6%) y último toque reciente ──
    if len(ph) >= 3:
        last3 = ph[-3:]
        vals = [v for _, v in last3]
        lvl = float(np.mean(vals))
        if (max(vals) - min(vals)) / lvl <= 0.015 and abs(lvl / close - 1) <= 0.06 \
           and (n - 1 - last3[-1][0]) <= 20:
            add("Resistencia horizontal", "neutral", 66, None,
                f"Resistencia probada 3+ veces en ${lvl:.2f} (a {abs(lvl/close-1)*100:.1f}% del precio): romperla con volumen abre continuación",
                [(last3[0][0], lvl, min(n - 1, last3[-1][0] + 6), lvl)])
    if len(pl) >= 3:
        last3 = pl[-3:]
        vals = [v for _, v in last3]
        lvl = float(np.mean(vals))
        if (max(vals) - min(vals)) / lvl <= 0.015 and abs(lvl / close - 1) <= 0.06 \
           and (n - 1 - last3[-1][0]) <= 20:
            add("Soporte horizontal", "neutral", 66, None,
                f"Soporte probado 3+ veces en ${lvl:.2f}: perderlo con volumen abre caída",
                [(last3[0][0], lvl, min(n - 1, last3[-1][0] + 6), lvl)])

    # ── Banderas/banderines (recientes por construcción) ──
    for cons in range(6, 16):
        if n < cons + 20:
            break
        seg = c.iloc[-cons:]
        rng = (float(seg.max()) - float(seg.min())) / close * 100
        pole = (float(c.iloc[-cons - 1]) / float(c.iloc[-cons - 13]) - 1) * 100 if n >= cons + 14 else 0
        if rng <= 6:
            half = cons // 2
            r1 = float(seg.iloc[:half].max()) - float(seg.iloc[:half].min())
            r2 = float(seg.iloc[half:].max()) - float(seg.iloc[half:].min())
            shape = "Banderín" if r2 < r1 * 0.65 else "Bandera"
            x1, x2 = n - cons, n - 1
            box = [(x1, float(seg.max()), x2, float(seg.iloc[half:].max()) if shape == "Banderín" else float(seg.max())),
                   (x1, float(seg.min()), x2, float(seg.iloc[half:].min()) if shape == "Banderín" else float(seg.min()))]
            pole_abs = abs(pole) / 100 * close
            if pole >= 12:
                obj = close + pole_abs
                add(shape + " alcista", "bullish", 64, obj,
                    f"Continuación alcista: mástil de {pole:.0f}% proyectado ≈ ${obj:.2f} ({pct(obj):+.1f}%)",
                    box + [(max(0, x1 - 13), float(c.iloc[max(0, x1 - 13)]), x1, float(c.iloc[x1]))])
                break
            if pole <= -12:
                obj = close - pole_abs
                add(shape + " bajista", "bearish", 64, obj,
                    f"Continuación bajista: mástil de {pole:.0f}% proyectado ≈ ${obj:.2f} ({pct(obj):+.1f}%)",
                    box + [(max(0, x1 - 13), float(c.iloc[max(0, x1 - 13)]), x1, float(c.iloc[x1]))])
                break

    # ── Taza con asa: borde al alcance y sin extenderse ──
    if n >= 70:
        for span in (60, 80, 100):
            if n < span + 8:
                continue
            cup = c.iloc[-span - 8:-8]
            rim_l = float(cup.iloc[:8].max()); rim_r = float(cup.iloc[-8:].max())
            bot = float(cup.min()); bot_pos = int(cup.values.argmin()) / len(cup)
            depth = (min(rim_l, rim_r) - bot) / min(rim_l, rim_r) * 100
            handle = c.iloc[-8:]
            h_pull = (rim_r - float(handle.min())) / rim_r * 100
            if abs(rim_l - rim_r) / rim_r <= 0.05 and 10 <= depth <= 35 \
               and 0.25 <= bot_pos <= 0.75 and 0 < h_pull <= 8 \
               and rim_r * 0.94 <= close <= rim_r * (1 + EXT) and reach_ok(rim_r):
                obj = rim_r + (rim_r - bot)
                x1 = n - span - 8
                add("Taza con asa", "bullish", 66, obj,
                    f"Alcista: romper el borde ${rim_r:.2f} proyecta ≈ ${obj:.2f} ({pct(obj):+.1f}%)",
                    [(x1, rim_l, n - 1, rim_r)])
                break

    seen, out = set(), []
    for p in sorted(found, key=lambda x: -x["conf"]):
        if p["name"] not in seen:
            seen.add(p["name"]); out.append(p)
    return out[:3]

# ═══════════════════════════════════════════════════════════════════
# FIGAND ENGINE — variables del motor estadístico (módulo independiente)
# Réplica EXACTA en Python de las fórmulas que el dashboard ya usaba en JS
# (earlinessScore, earlinessLabel, mkCurrentState, fase de Game Theory,
# compositeGrade). No inventa indicadores: reutiliza la misma lógica para
# que el historial, el análisis y el scanner hablen el mismo idioma.
# ═══════════════════════════════════════════════════════════════════
def fg_earliness(rsi, d20, d5, ext):
    """Puntuación de precocidad 0-100 (idéntica a earlinessScore del dashboard)."""
    rsi = 50 if rsi is None else rsi
    d20 = 0 if d20 is None else d20
    d5 = 0 if d5 is None else d5
    ext = 0 if ext is None else ext
    e = 50
    if 40 <= rsi <= 55: e += 20
    elif 30 <= rsi < 40: e += 25
    elif 55 < rsi <= 65: e += 10
    elif 65 < rsi <= 72: e -= 5
    elif rsi > 72: e -= 20
    elif rsi < 30: e += 15
    if 0 <= d20 <= 8: e += 15
    elif 8 < d20 <= 15: e += 5
    elif 15 < d20 <= 25: e -= 10
    elif d20 > 25: e -= 25
    elif -8 <= d20 < 0: e += 10
    elif d20 < -8: e += 5
    if d5 > 0 and -5 <= d20 <= 5: e += 15
    elif d5 > 3 and d20 > 10: e -= 10
    if -2 <= ext <= 3: e += 10
    elif 3 < ext <= 8: e += 0
    elif ext > 8: e -= 15
    return max(0, min(100, round(e)))

def fg_earliness_label(e):
    if e >= 70: return "TEMPRANO"
    if e >= 55: return "FRESCO"
    if e >= 40: return "MADURO"
    if e >= 25: return "TARDIO"
    return "EXTENDIDO"

def fg_markov_state(score):
    """Estado Markov según el score (idéntico a mkCurrentState)."""
    s = score or 0
    if s >= 75: return 3, "STRONG"
    if s >= 55: return 2, "BULLISH"
    if s >= 35: return 1, "NEUTRAL"
    return 0, "BEARISH"

def fg_fase(state):
    """Fase de Game Theory derivada del estado del radar."""
    return {"ENTRY+": "Señal máxima", "ENTRY": "Señal activa", "ACCUM": "Acumulación"}.get(state, "Espera")

def fg_calidad(fund):
    if fund is None: return None
    if fund >= 80: return "EXCELENTE"
    if fund >= 65: return "BUENO"
    if fund >= 45: return "REGULAR"
    return "DÉBIL"

def fg_block(row):
    """Bloque FIGAND para un ticker: las variables del estudio estadístico."""
    e = fg_earliness(row.get("rsi"), row.get("20d"), row.get("5d"), row.get("ext"))
    mk_i, mk_n = fg_markov_state(row.get("score"))
    s20, s200 = row.get("sma20_rel"), row.get("sma200_rel")
    dif = round(s20 - s200, 2) if (s20 is not None and s200 is not None) else None
    return {
        "earliness": e,
        "earliness_lab": fg_earliness_label(e),
        "not_temprano": fg_earliness_label(e) != "TEMPRANO",
        "fase": fg_fase(row.get("state")),
        "markov": mk_i, "markov_lab": mk_n,
        "dif_ema": dif,
        "calidad": fg_calidad(row.get("fund")),
        "upside": row.get("upside"),
    }

def detect_signals(hist, rsi_v, rel_vol, close, hi52, lo52, sma50v, sma200v, daily):
    """Señales tipo Finviz (todas EOD, sin repaint)."""
    sig = []
    c = hist["Close"]
    try:
        if hi52 and close >= hi52 * 0.999: sig.append("new_high")
        elif hi52 and (close / hi52 - 1) * 100 >= -3: sig.append("near_high")
        if lo52 and close <= lo52 * 1.001: sig.append("new_low")
        elif lo52 and (close / lo52 - 1) * 100 <= 3: sig.append("near_low")
        if rsi_v is not None:
            if rsi_v >= 70: sig.append("overbought")
            if rsi_v <= 30: sig.append("oversold")
        if rel_vol is not None and rel_vol >= 2: sig.append("unusual_volume")
        if daily is not None:
            if daily >= 4: sig.append("gainer")
            if daily <= -4: sig.append("loser")
        if sma200v:
            sig.append("above_sma200" if close > sma200v else "below_sma200")
        if len(c) >= 212 and sma50v and sma200v:
            s50 = c.rolling(50).mean(); s200 = c.rolling(200).mean()
            d_now = float(s50.iloc[-1] - s200.iloc[-1])
            d_prev = float(s50.iloc[-11] - s200.iloc[-11])
            if d_now > 0 and d_prev <= 0: sig.append("golden_cross")
            if d_now < 0 and d_prev >= 0: sig.append("death_cross")
        if len(c) >= 22:
            if close > float(hist["High"].iloc[-21:-1].max()): sig.append("breakout_20d")
    except Exception:
        pass
    return sig

# ═══ MARKET REGIME (Faber 2007 — timing con SMA200) ══════════════
# Evidencia histórica: las señales LONG tienen win-rate y drawdown
# radicalmente distintos según el índice esté sobre/bajo su SMA200.
def compute_market_regime(spy_hist):
    """Clasifica el mercado en BULL / NEUTRAL / BEAR usando SPY."""
    c = spy_hist["Close"].dropna()          # Yahoo a veces entrega la última fila vacía
    if len(c) < 210:
        return None
    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    price = float(c.iloc[-1])
    s50 = float(sma50.iloc[-1]); s200 = float(sma200.iloc[-1])
    if not all(np.isfinite(x) for x in (price, s50, s200)) or s200 == 0:
        return None
    high52 = float(c.tail(252).max())
    drawdown = (price / high52 - 1) * 100 if high52 > 0 else 0.0
    vol20 = float(c.pct_change().tail(20).std() * np.sqrt(252) * 100)
    if not np.isfinite(vol20):
        vol20 = 0.0
    if price > s200 and s50 > s200 and drawdown > -10:
        regime, icon = "BULL", "🟢"
        advice = "Mercado alcista — señales LONG operan con criterios normales."
    elif price < s200 and s50 < s200:
        regime, icon = "BEAR", "🔴"
        advice = "Mercado bajista — alertas de compra suspendidas (preservar capital)."
    else:
        regime, icon = "NEUTRAL", "🟡"
        advice = "Mercado en transición — solo señales de máxima calidad (RS alto)."
    return {
        "regime": regime, "icon": icon, "advice": advice,
        "spy_price": round(price, 2), "spy_sma200": round(s200, 2),
        "spy_vs_sma200_pct": round((price / s200 - 1) * 100, 2),
        "drawdown_52w_pct": round(drawdown, 2),
        "realized_vol_20d": round(vol20, 1),
    }

def regime_series(spy_hist):
    """Serie histórica de régimen (para el backtest)."""
    c = spy_hist["Close"].dropna()
    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    bull = (c > sma200) & (sma50 > sma200)
    bear = (c < sma200) & (sma50 < sma200)
    out = pd.Series("NEUTRAL", index=c.index)
    out[bull] = "BULL"; out[bear] = "BEAR"
    return out

# ═══ BUFFETT QUALITY SCORE + MARGEN DE SEGURIDAD ═════════════════
# Inspirado en Buffett/Munger (foso competitivo, ROE sostenido, poca
# deuda, caja libre) y Graham (margen de seguridad vía valor intrínseco).
def buffett_quality(info, price):
    """Devuelve (score 0-100, verdict, checks, margin_of_safety_pct)."""
    def g(k):
        try:
            v = info.get(k)
            f = float(v)
            return f if np.isfinite(f) else None
        except Exception:
            return None
    roe = g("returnOnEquity"); roa = g("returnOnAssets")
    gm = g("grossMargins"); om = g("operatingMargins"); nm = g("profitMargins")
    de = g("debtToEquity")          # yfinance lo entrega en % (80 = 0.8x)
    cr = g("currentRatio")
    fcf = g("freeCashflow"); mcap = g("marketCap")
    pe = g("trailingPE"); rg = g("revenueGrowth")
    eps = g("trailingEps"); bvps = g("bookValue")
    checks = []
    def add(name, cond, weight):
        if cond is None:
            return
        checks.append({"name": name, "pass": bool(cond), "w": weight})
    add("ROE > 15% (rentabilidad del capital)", roe is not None and roe > 0.15, 15)
    add("ROA > 7% (eficiencia de activos)", roa is not None and roa > 0.07, 10)
    add("Margen bruto > 40% (foso/moat)", gm is not None and gm > 0.40, 15)
    add("Margen operativo > 15%", om is not None and om > 0.15, 10)
    add("Margen neto > 10%", nm is not None and nm > 0.10, 10)
    add("Deuda/Patrimonio < 0.8x", de is not None and de < 80, 15)
    add("Current ratio > 1.2 (liquidez)", cr is not None and cr > 1.2, 5)
    fcf_yield = (fcf / mcap * 100) if (fcf and mcap and mcap > 0) else None
    add("FCF yield > 4% (genera caja real)", fcf_yield is not None and fcf_yield > 4, 10)
    add("Earnings yield > 5% (P/E < 20)", pe is not None and 0 < pe < 20, 5)
    add("Crecimiento de ingresos > 5%", rg is not None and rg > 0.05, 5)
    evaluated = sum(ch["w"] for ch in checks)
    earned = sum(ch["w"] for ch in checks if ch["pass"])
    score = round(earned / evaluated * 100) if evaluated >= 40 else None
    if score is None:
        verdict, v_icon = "SIN DATOS", "⚪"
    elif score >= 75:
        verdict, v_icon = "MOAT", "🏰"
    elif score >= 55:
        verdict, v_icon = "QUALITY", "✅"
    elif score >= 35:
        verdict, v_icon = "PROMEDIO", "➖"
    else:
        verdict, v_icon = "DÉBIL", "⚠️"
    # Margen de seguridad: Número de Graham √(22.5 · EPS · BVPS).
    # Fallback: valoración por FCF (FCF/acción capitalizado al 8%).
    mos = None
    if price and price > 0:
        if eps and bvps and eps > 0 and bvps > 0:
            graham = float(np.sqrt(22.5 * eps * bvps))
            mos = round((graham / price - 1) * 100, 1)
        elif fcf and mcap and fcf > 0 and mcap > 0:
            fair = fcf / 0.08  # exigencia de retorno 8%
            mos = round((fair / mcap - 1) * 100, 1)
        if mos is not None:
            mos = max(-99.0, min(300.0, mos))
    return score, f"{v_icon} {verdict}", checks, mos

def abc_grade(ema10, ema20, sma50):
    if pd.isna(ema10) or pd.isna(ema20) or pd.isna(sma50): return None
    if ema10 > ema20 > sma50: return "A"
    if ema10 < ema20 < sma50: return "C"
    return "B"

# ═══ HESSIAN MATRIX COMPUTATION ══════════════════════════════════
# Applies Hessian Matrix (second-order partial derivatives) to detect
# curvature of price-volume surface → local minima (buy), maxima (sell), saddle (wait)
def compute_hessian(hist, window=20):
    """
    Compute 2D Hessian Matrix H = [[fxx, fxy], [fxy, fyy]] where:
    - f_xx = d²Price/dt² (price acceleration)
    - f_yy = d²Volume/dt² (volume acceleration)  
    - f_xy = cross-derivative (price-volume coupling)
    
    Returns DataFrame with Hessian metrics per bar.
    """
    c = hist["Close"].copy()
    v = hist["Volume"].copy()
    
    # Normalize: percentage changes for scale-invariance
    price_ret = c.pct_change().fillna(0) * 100  # Daily returns %
    vol_ret = v.pct_change().fillna(0) * 100     # Volume change %
    
    # First derivatives (velocity): rolling mean of changes
    dp = price_ret.rolling(window).mean()   # Price velocity
    dv = vol_ret.rolling(window).mean()     # Volume velocity
    
    # Second derivatives (acceleration): change of velocity
    fxx = dp.diff().rolling(window).mean()  # Price acceleration
    fyy = dv.diff().rolling(window).mean()  # Volume acceleration
    
    # Cross-derivative: rolling correlation of first-derivative changes,
    # scaled by curvature magnitude (cheap and numerically stable)
    dp_diff = price_ret.diff().fillna(0)
    dv_diff = vol_ret.diff().fillna(0)
    fxy = dp_diff.rolling(window).corr(dv_diff).fillna(0) * (fxx.abs() * fyy.abs()).apply(np.sqrt)
    
    # Determinant: D = fxx*fyy - fxy²
    det = fxx * fyy - fxy * fxy
    
    # Trace: tr(H) = fxx + fyy
    trace = fxx + fyy
    
    # Eigenvalues: λ = (tr ± √(tr²-4D)) / 2
    disc = trace * trace - 4 * det
    disc_safe = disc.clip(lower=0)
    lam1 = (trace + np.sqrt(disc_safe)) / 2
    lam2 = (trace - np.sqrt(disc_safe)) / 2
    
    # Curvature magnitude
    curvature = (fxx**2 + 2*fxy**2 + fyy**2).apply(np.sqrt)
    
    return {
        "fxx": fxx, "fyy": fyy, "fxy": fxy,
        "det": det, "trace": trace,
        "lam1": lam1, "lam2": lam2,
        "curvature": curvature,
    }

def classify_hessian(fxx, det):
    """Classify point using Second Derivative Test."""
    if pd.isna(fxx) or pd.isna(det):
        return "UNDEFINED", "⚪"
    if det > 0.001 and fxx > 0.001:
        return "LOCAL_MIN", "🟢"    # Convex → price at bottom → BUY
    elif det > 0.001 and fxx < -0.001:
        return "LOCAL_MAX", "🔴"    # Concave → price at top → AVOID
    elif det < -0.001:
        return "SADDLE", "🟡"       # Saddle point → unstable → WAIT
    else:
        return "FLAT", "⚪"         # Near zero → no curvature → NEUTRAL

def compute_state(score, ai, ext, fund_score=None):
    if score >= 75 and ai > 70 and ext < 12:
        if fund_score and fund_score >= 60: return "ENTRY+"
        return "ENTRY"
    if score >= 60 and ai > 60: return "ACCUM"
    return "WAIT"

# ── FUNDAMENTAL GRADES ───────────────────────────────────────────
def grade_pe(v):
    if v is None or np.isnan(v): return "N/A", None
    if v < 0: return "Loss", 0
    if v < 15: return "Cheap", 3
    if v < 25: return "Fair", 2
    if v < 40: return "Pricey", 1
    return "Overval", 0

def grade_roe(v):
    if v is None or np.isnan(v): return "N/A", None
    if v > 20: return "Excel", 3
    if v > 15: return "Good", 2
    if v > 10: return "Med", 1
    return "Weak", 0

def grade_roa(v):
    if v is None or np.isnan(v): return "N/A", None
    if v > 10: return "Excel", 3
    if v > 5: return "Good", 2
    if v > 3: return "Med", 1
    return "Weak", 0

def grade_eps(v):
    if v is None or np.isnan(v): return "N/A", None
    if v > 25: return "Strong", 3
    if v > 10: return "Solid", 2
    if v > 0: return "Mod", 1
    return "Decl", 0

def safe_float(info, key):
    try:
        v = info.get(key)
        if v is None or v == "N/A": return None
        f = float(v)
        return f if np.isfinite(f) else None
    except Exception: return None

def safe_pct(info, key):
    v = safe_float(info, key)
    if v is not None and abs(v) < 10: return round(v * 100, 2)
    return v

# ── PRICE PROJECTION ─────────────────────────────────────────────
def compute_projection(close, ema50, ema200, atr, rsi, score, ai, pe, sector_pe=20):
    """Quantitative price projection for LONG bias."""
    if close is None or np.isnan(close) or atr is None or np.isnan(atr):
        return None, None, None
    # Technical target: based on ATR extension and trend
    tech_upside = atr * 3  # 3 ATR upside target
    tech_target = close + tech_upside
    # Momentum adjustment
    if score >= 75 and ai > 70:
        tech_target *= 1.05  # Strong momentum bonus
    elif score < 40:
        tech_target *= 0.95  # Weak momentum penalty
    # Fundamental adjustment via P/E
    if pe and pe > 0 and sector_pe and sector_pe > 0:
        pe_ratio = sector_pe / pe
        if pe_ratio > 1.3:  # Undervalued
            tech_target *= 1.03
        elif pe_ratio < 0.6:  # Very overvalued
            tech_target *= 0.97
    # Confidence based on RSI + Score alignment
    if score >= 75 and 45 < rsi < 65:
        confidence = "High"
    elif score >= 60:
        confidence = "Med"
    else:
        confidence = "Low"
    pct_upside = ((tech_target / close) - 1) * 100
    return round(tech_target, 2), round(pct_upside, 1), confidence

# ═══ REAL BACKTESTING ENGINE ══════════════════════════════════════
# Uses historical prices + our SAME indicators to test signals in the past.
# No simulation — only real price movements.

HOLD_PERIODS = [
    {"label": "1 Semana", "days": 5,   "key": "1w"},
    {"label": "1 Mes",    "days": 21,  "key": "1m"},
    {"label": "3 Meses",  "days": 63,  "key": "3m"},
    {"label": "6 Meses",  "days": 126, "key": "6m"},
    {"label": "1 Año",    "days": 252, "key": "1y"},
]

def run_backtest_for_ticker(ticker, hist, ind, fund_data, is_etf=False, regimes=None):
    """
    Walk through historical data applying our 4-layer signal criteria.
    When signal triggers, measure REAL forward price change.
    
    Returns dict with results per holding period.
    """
    closes = hist["Close"]
    n = len(closes)
    
    # We need at least 252 bars of warmup + 252 bars of forward data
    # So we check signals from bar 200 onward, with step of 5 (weekly checks)
    start_bar = min(200, n - 60)  # Need at least some warmup
    if start_bar < 50:
        return None
    
    # Extract current fundamentals (proxy — yfinance doesn't provide historical fundamentals)
    pe = fund_data.get('pe')
    roe = fund_data.get('roe', 0) or 0
    roa = fund_data.get('roa', 0) or 0
    eps_g = fund_data.get('eps_g', 0) or 0
    fund_score = fund_data.get('fund')
    
    # Pre-compute grade scores for fundamentals (constant for the year)
    pe_gr_s = grade_pe(pe)[1] or 0
    roe_gr_s = grade_roe(roe)[1] or 0
    roa_gr_s = grade_roa(roa)[1] or 0
    eps_gr_s = grade_eps(eps_g)[1] or 0
    pts = [p for p in [pe_gr_s, roe_gr_s, roa_gr_s, eps_gr_s] if p is not None]
    composite = round(sum(pts) / (len(pts) * 3) * 100, 0) if pts else 0
    
    # Earnings quality check
    earnings_suspicious = (eps_gr_s >= 2 and roa_gr_s <= 0)
    # Debt risk check
    debt_high = (roe > 0 and roa > 0 and roe / max(roa, 0.01) > 3)
    
    # Results structure
    entry_trades = {p["key"]: [] for p in HOLD_PERIODS}  # Entry Zone trades (strict 4/4)
    tech_trades = {p["key"]: [] for p in HOLD_PERIODS}   # Technical signals (L1+L3 only)
    gt_trades = {p["key"]: {"nash": [], "bayesian": [], "sequential": []} for p in HOLD_PERIODS}
    hessian_trades = {p["key"]: [] for p in HOLD_PERIODS}  # Hessian local minimum signals
    regime_trades = {p["key"]: [] for p in HOLD_PERIODS}    # Tech signal + régimen BULL (filtro Faber)
    
    # Pre-compute Hessian for entire history
    try:
        hess = compute_hessian(hist, window=20)
    except Exception:
        hess = None
    
    # Walk through history (check every 5 bars = weekly)
    for i in range(start_bar, n, 5):
        sc = float(ind["score"].iloc[i]) if not pd.isna(ind["score"].iloc[i]) else 0
        ai_v = float(ind["ai"].iloc[i]) if not pd.isna(ind["ai"].iloc[i]) else 50
        rsi_v = float(ind["rsi"].iloc[i]) if not pd.isna(ind["rsi"].iloc[i]) else 50
        adx_v = float(ind["adx"].iloc[i]) if not pd.isna(ind["adx"].iloc[i]) else 15
        ext_v = float(ind["ext"].iloc[i]) if not pd.isna(ind["ext"].iloc[i]) else 0
        rv = float(ind["rel_vol"].iloc[i]) if not pd.isna(ind["rel_vol"].iloc[i]) else 1
        
        e10 = float(ind["ema10"].iloc[i]) if not pd.isna(ind["ema10"].iloc[i]) else None
        e20 = float(ind["ema20"].iloc[i]) if not pd.isna(ind["ema20"].iloc[i]) else None
        s50 = float(ind["sma50"].iloc[i]) if not pd.isna(ind["sma50"].iloc[i]) else None
        abc = abc_grade(e10, e20, s50)
        state = compute_state(sc, ai_v, ext_v, fund_score)
        
        close_price = float(closes.iloc[i])
        date_str = str(hist.index[i].date()) if hasattr(hist.index[i], 'date') else str(hist.index[i])[:10]
        bar_regime = "NEUTRAL"
        if regimes is not None:
            try:
                pos = regimes.index.get_indexer([hist.index[i]], method="ffill")[0]
                if pos >= 0:
                    bar_regime = str(regimes.iloc[pos])
            except Exception:
                pass
        
        # Momentum at this point
        d5 = ((closes.iloc[i] / closes.iloc[i-5]) - 1) * 100 if i >= 5 else 0
        d20 = ((closes.iloc[i] / closes.iloc[i-20]) - 1) * 100 if i >= 20 else 0
        
        # ═══ 4-LAYER VALIDATION (same criteria as check_alerts.py) ═══
        
        # Layer 1: Radar (slightly relaxed for historical — signals were valid at their time)
        if is_etf:
            l1 = sc >= 25 and d20 > -8
        else:
            l1 = (state in ('ENTRY+', 'ENTRY', 'ACCUM') and sc >= 50 and ai_v >= 55 
                  and abc in ('A', 'B') and rsi_v < 78)
        
        # Layer 2: Analysis (fundamentals — constant proxy, relaxed for history)
        if is_etf:
            l2 = sc >= 25 and d20 > -8
        else:
            l2 = (composite >= 45 and roe >= 5 and roa >= 2 
                  and not earnings_suspicious and not debt_high)
        
        # Layer 3: Entry Zones (momentum check, relaxed for history)
        if is_etf:
            l3 = d20 > -5 and d5 > -8
        else:
            l3 = d20 > -3 and d5 > -8
        
        # Layer 4: Game Theory (Bayesian probability)
        prior = 0.5
        lk_ai = ai_v / 100
        lk_vol = 1.3 if rv > 1.1 else 0.9
        lk_rsi = 1.2 if (40 < rsi_v < 70) else 0.7
        lk_fund = composite / 85 if composite > 0 else 0.5
        lk_mom = 1.2 if d20 > 3 else (1.0 if d20 > 0 else 0.7)
        lk_adx = 1.15 if adx_v > 20 else 0.85
        bayesian_prob = min(0.95, max(0.15, prior * lk_ai * lk_vol * lk_rsi * lk_fund * lk_mom * lk_adx * 3.5))
        
        if is_etf:
            l4 = bayesian_prob >= 0.45
        else:
            l4 = bayesian_prob >= 0.55
        
        all_pass = l1 and l2 and l3 and l4
        # Technical-only signal (L1 + L3 — these actually change historically)
        tech_pass = l1 and l3
        
        # ═══ MEASURE REAL FORWARD RETURNS ═══
        for period in HOLD_PERIODS:
            exit_bar = i + period["days"]
            if exit_bar >= n:
                continue  # Not enough future data
            
            exit_price = float(closes.iloc[exit_bar])
            real_pnl = ((exit_price / close_price) - 1) * 100
            real_pnl = round(real_pnl, 2)
            
            pnl_net = round(real_pnl - ROUND_TRIP_COST_PCT, 2)
            trade = {
                "date": date_str,
                "i": i,
                "entry": round(close_price, 2),
                "exit": round(exit_price, 2),
                "pnl": real_pnl,
                "pnl_net": pnl_net,
                "win": real_pnl > 0,
                "win_net": pnl_net > 0,
                "score": int(sc),
                "ai": round(ai_v, 1),
                "rsi": round(rsi_v, 1),
                "state": state,
                "prob": round(bayesian_prob * 100),
            }
            
            # Entry Zone backtest: only when ALL 4 layers pass
            if all_pass:
                entry_trades[period["key"]].append(trade)
            
            # Technical signal backtest: when L1 (Radar) + L3 (Momentum) pass
            if tech_pass:
                tech_trades[period["key"]].append(trade)

            # Filtro de régimen (Faber): misma señal técnica pero SOLO en BULL.
            # Comparar este bucket contra tech_signals muestra el valor del filtro.
            if tech_pass and bar_regime == "BULL":
                regime_trades[period["key"]].append(trade)
            
            # Hessian signal: D > 0 and fxx > 0 → local minimum → potential reversal up
            if hess is not None and i < len(hess["det"]):
                h_fxx_i = hess["fxx"].iloc[i] if not pd.isna(hess["fxx"].iloc[i]) else 0
                h_det_i = hess["det"].iloc[i] if not pd.isna(hess["det"].iloc[i]) else 0
                h_class_i, _ = classify_hessian(h_fxx_i, h_det_i)
                if h_class_i == "LOCAL_MIN" and d20 > -10:  # Local minimum + not in freefall
                    hessian_trades[period["key"]].append(trade)
            
            # Game Theory backtest: different per model
            # Nash: balanced (l1 or l2 combined with l3 and moderate l4)
            nash_pass = (l1 or l2) and l3 and bayesian_prob >= 0.45
            if nash_pass:
                gt_trades[period["key"]]["nash"].append(trade)
            
            # Bayesian: heavy AI weight (l2 + decent probability + ai >= 55)
            bay_pass = l2 and bayesian_prob >= 0.50 and ai_v >= 55 and d20 > -5
            if bay_pass:
                gt_trades[period["key"]]["bayesian"].append(trade)
            
            # Sequential: signal-based (state active + momentum)
            seq_pass = state in ('ENTRY+', 'ENTRY', 'ACCUM') and l3 and sc >= 45
            if seq_pass:
                gt_trades[period["key"]]["sequential"].append(trade)
    
    # ═══ COMPILE STATISTICS — nivel profesional ═══
    # Todas las métricas clave se calculan sobre el P&L NETO (tras costos).
    # Walk-forward: las primeras 60% de las barras son "in-sample" (IS) y el
    # 40% final "out-of-sample" (OOS). Si la estrategia solo gana en IS, está
    # sobreajustada — el número que importa es el OOS.
    wf_split = start_bar + int((n - start_bar) * 0.6)

    def calc_stats(trades_list, keep_trades=BACKTEST_KEEP_TRADES):
        empty = {"n": 0, "wins": 0, "win_rate": 0, "avg_pnl": 0, "avg_pnl_net": 0,
                 "total_pnl": 0, "max_win": 0, "max_loss": 0, "profit_factor": 0,
                 "expectancy_net": 0, "sharpe_trade": None, "max_dd": 0,
                 "wf": {"n_is": 0, "wr_is": None, "n_oos": 0, "wr_oos": None, "avg_net_oos": None},
                 "trades": []}
        if not trades_list:
            return empty
        tn = len(trades_list)
        wins = sum(1 for t in trades_list if t["win"])
        pnls = [t["pnl"] for t in trades_list]
        nets = [t.get("pnl_net", t["pnl"]) for t in trades_list]
        gross_win = sum(p for p in nets if p > 0)
        gross_loss = abs(sum(p for p in nets if p < 0))
        # Sharpe por operación (media/desv del P&L neto) — comparabilidad entre estrategias
        mu = sum(nets) / tn
        sd = (sum((x - mu) ** 2 for x in nets) / tn) ** 0.5 if tn > 1 else 0
        sharpe = round(mu / sd, 2) if sd > 0 else None
        # Máximo drawdown de la curva acumulada de P&L neto (aprox. aditiva en %)
        cum, peak, mdd = 0.0, 0.0, 0.0
        for x in nets:
            cum += x
            peak = max(peak, cum)
            mdd = min(mdd, cum - peak)
        # Walk-forward IS / OOS
        is_t = [t for t in trades_list if t.get("i", 0) < wf_split]
        oos_t = [t for t in trades_list if t.get("i", 0) >= wf_split]
        def wr(ts):
            return round(sum(1 for t in ts if t.get("win_net", t["win"])) / len(ts) * 100, 1) if ts else None
        oos_nets = [t.get("pnl_net", t["pnl"]) for t in oos_t]
        return {
            "n": tn,
            "wins": wins,
            "win_rate": round(wins / tn * 100, 1),
            "avg_pnl": round(sum(pnls) / tn, 2),
            "avg_pnl_net": round(mu, 2),
            "total_pnl": round(sum(nets), 2),
            "max_win": round(max(pnls), 2),
            "max_loss": round(min(pnls), 2),
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (99 if gross_win > 0 else 0),
            "expectancy_net": round(mu, 2),
            "sharpe_trade": sharpe,
            "max_dd": round(mdd, 2),
            "wf": {"n_is": len(is_t), "wr_is": wr(is_t),
                   "n_oos": len(oos_t), "wr_oos": wr(oos_t),
                   "avg_net_oos": round(sum(oos_nets) / len(oos_nets), 2) if oos_nets else None},
            # Solo se exportan trades donde la UI los muestra (keep_trades>0).
            # Con ~600 tickers × 5 estrategias × 5 horizontes × 20 trades, este
            # campo inflaba backtest.json a >120MB y GitHub rechaza >100MB.
            "trades": [{k: v for k, v in t.items() if k != "i"} for t in trades_list[-keep_trades:]] if keep_trades else [],  # 5 en vez de 20: el peso real del JSON
        }
    
    # Baseline: buy on EVERY sampled bar (no filter). If a strategy's
    # win-rate is not clearly above this base rate, the signal adds no edge.
    baseline = {p["key"]: [] for p in HOLD_PERIODS}
    for i in range(start_bar, n, 5):
        cp = float(closes.iloc[i])
        for period in HOLD_PERIODS:
            eb = i + period["days"]
            if eb >= n:
                continue
            pnl = round(((float(closes.iloc[eb]) / cp) - 1) * 100, 2)
            pnl_n = round(pnl - ROUND_TRIP_COST_PCT, 2)
            baseline[period["key"]].append({"pnl": pnl, "pnl_net": pnl_n, "win": pnl > 0,
                                            "win_net": pnl_n > 0, "i": i})

    result = {
        "ticker": ticker,
        "name": fund_data.get('name', ticker),
        "sector": fund_data.get('sector', 'N/A'),
        "is_etf": is_etf,
        "composite": composite,
        "data_bars": n,
        "entry_zones": {},
        "tech_signals": {},
        "regime_filtered": {},
        "hessian_signals": {},
        "game_theory": {},
        "baseline": {},
    }
    
    for p in HOLD_PERIODS:
        b = baseline[p["key"]]
        oos_b = [t for t in b if t["i"] >= wf_split]
        result["baseline"][p["key"]] = {
            "n": len(b),
            "win_rate": round(sum(1 for t in b if t["win"]) / len(b) * 100, 1) if b else 0,
            "avg_pnl": round(sum(t["pnl"] for t in b) / len(b), 2) if b else 0,
            "avg_pnl_net": round(sum(t["pnl_net"] for t in b) / len(b), 2) if b else 0,
            "wr_oos": round(sum(1 for t in oos_b if t["win_net"]) / len(oos_b) * 100, 1) if oos_b else None,
        }
        result["entry_zones"][p["key"]] = calc_stats(entry_trades[p["key"]])
        result["regime_filtered"][p["key"]] = calc_stats(regime_trades[p["key"]])
        result["tech_signals"][p["key"]] = calc_stats(tech_trades[p["key"]])
        result["hessian_signals"][p["key"]] = calc_stats(hessian_trades[p["key"]])
        result["game_theory"][p["key"]] = {
            "nash": calc_stats(gt_trades[p["key"]]["nash"]),
            "bayesian": calc_stats(gt_trades[p["key"]]["bayesian"]),
            "sequential": calc_stats(gt_trades[p["key"]]["sequential"]),
        }
    
    return result


def _spy_benchmark():
    """Retorno de comprar SPY y no hacer nada en la ventana del backtest.
    El listón que toda estrategia activa debe superar DESPUÉS de costos."""
    try:
        spy = fetch_history("SPY")
        c = spy["Close"].dropna()
        years = max(0.5, (c.index[-1] - c.index[0]).days / 365.25)
        total = (float(c.iloc[-1]) / float(c.iloc[0]) - 1) * 100
        cagr = ((float(c.iloc[-1]) / float(c.iloc[0])) ** (1 / years) - 1) * 100
        roll_max = c.cummax()
        mdd = float(((c / roll_max) - 1).min() * 100)
        return {"asset": "SPY buy & hold", "window_years": round(years, 1),
                "total_return_pct": round(total, 1), "cagr_pct": round(cagr, 1),
                "max_drawdown_pct": round(mdd, 1)}
    except Exception:
        return None

def run_full_backtest(groups_data, out_dir):
    """Run backtest for all tickers and save results."""
    print(f"\n{'='*55}")
    print(f"BACKTESTING — Using real historical prices")
    print(f"{'='*55}")
    
    ETF_SECTORS = {'Index', 'ETF', 'Commodity', 'Fixed Income', ''}
    all_results = []

    # Serie histórica de régimen (SPY) — se calcula una sola vez
    regimes = None
    spy_hist = fetch_history("SPY")
    if spy_hist is not None and len(spy_hist) >= 210:
        try:
            regimes = regime_series(spy_hist)
            counts = regimes.value_counts().to_dict()
            print(f"  Régimen histórico SPY: {counts}")
        except Exception as e:
            print(f"  ⚠️ Serie de régimen no disponible: {e}")
    
    all_tickers = set()
    for gn, rows in groups_data.items():
        for r in rows:
            all_tickers.add((r['ticker'], r.get('sector', 'N/A'), gn))
    
    for i, (ticker, sector, group) in enumerate(sorted(all_tickers)):
        print(f"  BT [{i+1}/{len(all_tickers)}] {ticker}...", end=" ")
        try:
            hist = fetch_history(ticker)
            if hist is None or len(hist) < 120:
                print("skip (not enough data)")
                continue
            
            ind = compute_score(hist)
            
            # Get fund data from snapshot
            fund_data = {}
            for gn, rows in groups_data.items():
                for r in rows:
                    if r['ticker'] == ticker:
                        fund_data = r
                        break
            
            is_etf = sector in ETF_SECTORS
            result = run_backtest_for_ticker(ticker, hist, ind, fund_data, is_etf, regimes=regimes)
            
            if result:
                result['group'] = group
                all_results.append(result)
                # Quick summary
                ez_1m = result['entry_zones'].get('1m', {})
                if ez_1m.get('n', 0) > 0:
                    print(f"EZ: {ez_1m['n']} trades, {ez_1m['win_rate']}% WR, avg {ez_1m['avg_pnl']}%")
                else:
                    print(f"no EZ signals (criteria too strict for history)")
            else:
                print("skip")
        except Exception as e:
            print(f"error: {e}")
        time.sleep(0.15)
    
    # Save
    bt_path = os.path.join(out_dir, "backtest.json")
    bt_data = {
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": "Real historical prices — Yahoo Finance 2-year data",
        "layers": "4-layer validation: Radar + Analysis + Entry Zones + Game Theory + Regime Filter (Faber SMA200)",
        "cost_model": f"P&L neto = bruto − {ROUND_TRIP_COST_PCT}% por operación (comisión + slippage, ida y vuelta). Configurable con BACKTEST_COST_PCT.",
        "walk_forward": "wf.wr_is = win-rate neto en el primer 60% del histórico (in-sample); wf.wr_oos = en el 40% final (out-of-sample). Si solo gana in-sample, la estrategia está sobreajustada.",
        "benchmark": _spy_benchmark(),
        "regime_note": "regime_filtered = misma señal técnica pero solo cuando SPY > SMA200 (mercado alcista). Compara su win-rate contra tech_signals y baseline para medir el edge real del filtro.",
        "note": "Fundamentals (P/E, ROE, ROA) use current values as proxy — historical fundamentals not available via free API",
        "total_tickers": len(all_results),
        "results": all_results,
    }
    dump_json(bt_data, bt_path)
    print(f"\nBacktest saved: {bt_path} — {len(all_results)} tickers tested")
    return bt_data


# ── MAIN BUILD ───────────────────────────────────────────────────
# Global caches: each ticker is downloaded ONCE (2y) and reused for
# both the snapshot (1y slice) and the backtest. Cuts API calls ~3x.
_HIST_CACHE = {}
_ROW_CACHE = {}

# Nº de trades de ejemplo exportados por estrategia/horizonte para la UI.
# Las ESTADÍSTICAS siempre se calculan sobre TODAS las operaciones; esto solo
# controla la lista visible. Cada +5 trades ≈ +10-12 MB en backtest.json con
# ~600 tickers (límite de GitHub: 100 MB). Configurable por entorno.
BACKTEST_KEEP_TRADES = int(os.environ.get("BACKTEST_KEEP_TRADES", "5"))

# Coste de ida y vuelta por operación (comisión + slippage), en %.
# 0.2% es conservador para acciones líquidas de EEUU. Configurable por entorno.
ROUND_TRIP_COST_PCT = float(os.environ.get("BACKTEST_COST_PCT", "0.2"))

def yf_symbol(t):
    """Normaliza al formato de Yahoo: BRK.B/BRK/B → BRK-B, quita '*' y espacios."""
    return t.strip().upper().replace(".", "-").replace("/", "-").rstrip("*")

def _now_et():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now()  # los workflows ya corren con TZ=America/New_York

def is_us_session_open(now_et):
    """True si la sesión regular de NYSE/Nasdaq está abierta (con margen).
    9:30–16:10 ET, lun-vie. Nota: para tickers de Asia la vela ya viene
    cerrada a las horas en que corren los workflows (15/18/21:30 UTC)."""
    if now_et.weekday() >= 5:
        return False
    mins = now_et.hour * 60 + now_et.minute
    return (9 * 60 + 30) <= mins < (16 * 60 + 10)

def fetch_history(ticker, retries=2):
    """Download 5y of daily candles with simple retry/backoff. Cached."""
    if ticker in _HIST_CACHE:
        return _HIST_CACHE[ticker]
    hist = None
    for attempt in range(retries + 1):
        try:
            hist = yf.Ticker(yf_symbol(ticker)).history(period="5y", auto_adjust=True)
            if hist is not None and len(hist) > 0:
                break
        except Exception as e:
            if attempt == retries:
                print(f"  ERROR {ticker}: {e}")
        time.sleep(1.5 * (attempt + 1))
    _HIST_CACHE[ticker] = hist
    return hist

def get_stock_data(ticker, spy_close=None):
    if ticker in _ROW_CACHE:
        return _ROW_CACHE[ticker]
    try:
        stock = yf.Ticker(yf_symbol(ticker))  # Yahoo usa guión: BRK-B, BF-B, HEI-A
        hist2y = fetch_history(ticker)
        if hist2y is None or len(hist2y) < 60:
            return None
        # Snapshot uses the last ~1y of the cached 2y history
        hist = hist2y.tail(260).copy()
        if hist is None or len(hist) < 60:
            return None
        # Anti-repaint inteligente: descartar la vela de hoy SOLO si la sesión
        # sigue abierta (vela incompleta). Tras el cierre (16:10 ET) la vela de
        # hoy es definitiva y descartarla retrasaba TODAS las señales un día.
        if hasattr(hist.index[-1], 'date') and hist.index[-1].date() == _now_et().date() \
           and is_us_session_open(_now_et()):
            hist = hist.iloc[:-1]
        if len(hist) < 60:
            return None
        ind = compute_score(hist)
        last = -1  # last closed candle
        close = float(hist["Close"].iloc[last])
        asof = str(hist.index[last].date()) if hasattr(hist.index[last], "date") else None
        sc = float(ind["score"].iloc[last])
        ai_p = float(ind["ai"].iloc[last])
        rsi_v = float(ind["rsi"].iloc[last]) if not pd.isna(ind["rsi"].iloc[last]) else None
        adx_v = float(ind["adx"].iloc[last]) if not pd.isna(ind["adx"].iloc[last]) else None
        ext_v = float(ind["ext"].iloc[last]) if not pd.isna(ind["ext"].iloc[last]) else None
        rv = float(ind["rel_vol"].iloc[last]) if not pd.isna(ind["rel_vol"].iloc[last]) else None
        abc = abc_grade(
            float(ind["ema10"].iloc[last]) if not pd.isna(ind["ema10"].iloc[last]) else None,
            float(ind["ema20"].iloc[last]) if not pd.isna(ind["ema20"].iloc[last]) else None,
            float(ind["sma50"].iloc[last]) if not pd.isna(ind["sma50"].iloc[last]) else None,
        )
        atr_v = float(ind["atr"].iloc[last]) if not pd.isna(ind["atr"].iloc[last]) else None
        # Performance
        daily = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100 if len(hist) >= 2 else None
        five_d = (hist["Close"].iloc[-1] / hist["Close"].iloc[-6] - 1) * 100 if len(hist) >= 6 else None
        twenty_d = (hist["Close"].iloc[-1] / hist["Close"].iloc[-21] - 1) * 100 if len(hist) >= 21 else None
        # Fundamentals
        pe, roe, roa, eps_g = None, None, None, None
        name, sector, mktcap = ticker, "N/A", None
        bq_score, bq_verdict, bq_mos = None, "⚪ SIN DATOS", None
        xf = {}
        try:
            info = stock.info
            pe = safe_float(info, "trailingPE")
            roe = safe_pct(info, "returnOnEquity")
            roa = safe_pct(info, "returnOnAssets")
            eps_g = safe_pct(info, "earningsQuarterlyGrowth")
            name = info.get("shortName", ticker)
            sector = info.get("sector", "N/A")
            if not sector or sector == "N/A":
                qt = str(info.get("quoteType", "")).upper()
                sector = {"ETF": "ETF", "MUTUALFUND": "Fondo", "INDEX": "Índice",
                          "CRYPTOCURRENCY": "Cripto", "CURRENCY": "Divisa"}.get(qt, sector)
            mktcap = safe_float(info, "marketCap")
            bq_score, bq_verdict, _, bq_mos = buffett_quality(info, close)
            # ── Campos Finviz desde el mismo info (sin llamadas extra) ──
            def gi(k, mult=1, dec=2):
                try:
                    v = float(info.get(k))
                    return round(v * mult, dec) if np.isfinite(v) else None
                except Exception:
                    return None
            xf = {
                "fpe": gi("forwardPE"), "peg": gi("pegRatio"),
                "ps": gi("priceToSalesTrailing12Months"), "pb": gi("priceToBook"),
                "div_yield": gi("dividendYield", 100 if (info.get("dividendYield") or 0) < 1 else 1),
                "payout": gi("payoutRatio", 100, 1),
                "eps_ttm": gi("trailingEps"), "beta": gi("beta"),
                "sales_g": gi("revenueGrowth", 100, 1),
                "gross_m": gi("grossMargins", 100, 1), "oper_m": gi("operatingMargins", 100, 1),
                "net_m": gi("profitMargins", 100, 1),
                "debt_eq": gi("debtToEquity", 0.01), "curr_ratio": gi("currentRatio"),
                "quick_ratio": gi("quickRatio"),
                "insider_own": gi("heldPercentInsiders", 100, 1),
                "inst_own": gi("heldPercentInstitutions", 100, 1),
                "short_float": gi("shortPercentOfFloat", 100, 1),
                "short_ratio": gi("shortRatio"),
                "analyst_rec": gi("recommendationMean"),
                "shares_out": gi("sharesOutstanding", 1e-6, 1),
                "float_shares": gi("floatShares", 1e-6, 1),
            }
            if xf["shares_out"] and xf["float_shares"]:
                xf["float_out"] = round(xf["float_shares"] / xf["shares_out"] * 100, 1)
            else:
                xf["float_out"] = None
        except Exception: pass
        # Conciencia de eventos: próximo earnings y ex-dividendo. Una señal
        # técnica justo antes de earnings es una moneda al aire con gap.
        earn_days, earn_date, exdiv_date = None, None, None
        try:
            cal = stock.calendar
            ed = None
            if isinstance(cal, dict):
                v = cal.get("Earnings Date") or cal.get("EarningsDate")
                if isinstance(v, (list, tuple)) and len(v) > 0:
                    ed = v[0]
                elif v is not None:
                    ed = v
                xd = cal.get("Ex-Dividend Date") or cal.get("ExDividendDate")
                if xd is not None:
                    xdate = pd.Timestamp(xd).date()
                    if 0 <= (xdate - datetime.now().date()).days <= 60:
                        exdiv_date = str(xdate)
            if ed is not None:
                edate = pd.Timestamp(ed).date()
                delta = (edate - datetime.now().date()).days
                if 0 <= delta <= 120:
                    earn_days, earn_date = int(delta), str(edate)
        except Exception:
            pass
        # Fuerza relativa vs SPY (momentum transversal 3M / 6M)
        rs_3m, rs_6m = None, None
        if spy_close is not None:
            try:
                if len(hist) >= 64 and len(spy_close) >= 64:
                    t63 = (hist["Close"].iloc[-1] / hist["Close"].iloc[-64] - 1) * 100
                    s63 = (spy_close.iloc[-1] / spy_close.iloc[-64] - 1) * 100
                    rs_3m = round(float(t63 - s63), 2)
                if len(hist) >= 127 and len(spy_close) >= 127:
                    t126 = (hist["Close"].iloc[-1] / hist["Close"].iloc[-127] - 1) * 100
                    s126 = (spy_close.iloc[-1] / spy_close.iloc[-127] - 1) * 100
                    rs_6m = round(float(t126 - s126), 2)
            except Exception: pass
        # ── Screener: performance extendida, señales y patrones ──
        scr_c = hist["Close"]
        def _perf(nb):
            try:
                return round(float(scr_c.iloc[-1] / scr_c.iloc[-nb - 1] - 1) * 100, 2) if len(scr_c) > nb else None
            except Exception:
                return None
        perf_3m, perf_6m, perf_1y = _perf(63), _perf(126), _perf(251)
        try:
            hi52 = float(scr_c.tail(252).max()); lo52 = float(scr_c.tail(252).min())
        except Exception:
            hi52, lo52 = None, None
        from_hi52 = round((close / hi52 - 1) * 100, 2) if hi52 else None
        from_lo52 = round((close / lo52 - 1) * 100, 2) if lo52 else None
        try:
            sma50v = float(scr_c.rolling(50).mean().iloc[-1]) if len(scr_c) >= 50 else None
            sma200v = float(scr_c.rolling(200).mean().iloc[-1]) if len(scr_c) >= 200 else None
        except Exception:
            sma50v, sma200v = None, None
        sma50_rel = round((close / sma50v - 1) * 100, 2) if sma50v else None
        sma200_rel = round((close / sma200v - 1) * 100, 2) if sma200v else None
        try:
            gap_v = round((float(hist["Open"].iloc[-1]) / float(scr_c.iloc[-2]) - 1) * 100, 2) if len(scr_c) >= 2 else None
            chg_open = round((close / float(hist["Open"].iloc[-1]) - 1) * 100, 2)
        except Exception:
            gap_v, chg_open = None, None
        try:
            rets = scr_c.pct_change()
            vol_w = round(float(rets.tail(5).std() * np.sqrt(252) * 100), 1) if len(scr_c) >= 6 else None
            vol_m = round(float(rets.tail(21).std() * np.sqrt(252) * 100), 1) if len(scr_c) >= 22 else None
        except Exception:
            vol_w, vol_m = None, None
        try:
            hi50 = float(scr_c.tail(50).max()); lo50 = float(scr_c.tail(50).min())
            from_hi50 = round((close / hi50 - 1) * 100, 2)
            from_lo50 = round((close / lo50 - 1) * 100, 2)
        except Exception:
            from_hi50, from_lo50 = None, None
        try:
            sma20v = float(scr_c.rolling(20).mean().iloc[-1]) if len(scr_c) >= 20 else None
            sma20_rel = round((close / sma20v - 1) * 100, 2) if sma20v else None
        except Exception:
            sma20_rel = None
        try:
            avg_vol = round(float(hist["Volume"].tail(63).mean()) / 1e6, 2)
        except Exception:
            avg_vol = None
        scr_signals = detect_signals(hist, rsi_v, rv, close, hi52, lo52, sma50v, sma200v, daily)
        try:
            scr_patterns = detect_patterns(hist)
        except Exception:
            scr_patterns = []
        pat_c = None
        if scr_patterns:
            try:
                pat_c = [round(float(x), 2) for x in scr_c.tail(140).values]
            except Exception:
                pat_c = None

        pe_gr, pe_pts = grade_pe(pe)
        roe_gr, roe_pts = grade_roe(roe)
        roa_gr, roa_pts = grade_roa(roa)
        eps_gr, eps_pts = grade_eps(eps_g)
        pts = [p for p in [pe_pts, roe_pts, roa_pts, eps_pts] if p is not None]
        fund_score = round(sum(pts) / (len(pts) * 3) * 100, 0) if pts else None
        state = compute_state(sc, ai_p, ext_v or 0, fund_score)
        # Projection
        tgt, upside, conf = compute_projection(close, 
            float(ind["ema50"].iloc[last]) if not pd.isna(ind["ema50"].iloc[last]) else close,
            float(ind["ema200"].iloc[last]) if not pd.isna(ind["ema200"].iloc[last]) else close,
            atr_v, rsi_v or 50, sc, ai_p, pe)
        # Market cap format
        mc_str = "N/A"
        if mktcap:
            if mktcap >= 1e12: mc_str = f"${mktcap/1e12:.1f}T"
            elif mktcap >= 1e9: mc_str = f"${mktcap/1e9:.0f}B"
            elif mktcap >= 1e6: mc_str = f"${mktcap/1e6:.0f}M"
        # Hessian Matrix computation
        hess_data = {}
        try:
            hess = compute_hessian(hist, window=20)
            h_fxx = float(hess["fxx"].iloc[-1]) if not pd.isna(hess["fxx"].iloc[-1]) else 0
            h_fyy = float(hess["fyy"].iloc[-1]) if not pd.isna(hess["fyy"].iloc[-1]) else 0
            h_fxy = float(hess["fxy"].iloc[-1]) if not pd.isna(hess["fxy"].iloc[-1]) else 0
            h_det = float(hess["det"].iloc[-1]) if not pd.isna(hess["det"].iloc[-1]) else 0
            h_trace = float(hess["trace"].iloc[-1]) if not pd.isna(hess["trace"].iloc[-1]) else 0
            h_lam1 = float(hess["lam1"].iloc[-1]) if not pd.isna(hess["lam1"].iloc[-1]) else 0
            h_lam2 = float(hess["lam2"].iloc[-1]) if not pd.isna(hess["lam2"].iloc[-1]) else 0
            h_curv = float(hess["curvature"].iloc[-1]) if not pd.isna(hess["curvature"].iloc[-1]) else 0
            h_class, h_icon = classify_hessian(h_fxx, h_det)
            hess_data = {
                "fxx": round(h_fxx, 4), "fyy": round(h_fyy, 4), "fxy": round(h_fxy, 4),
                "det": round(h_det, 4), "trace": round(h_trace, 4),
                "lam1": round(h_lam1, 4), "lam2": round(h_lam2, 4),
                "curvature": round(h_curv, 4),
                "class": h_class, "icon": h_icon,
            }
        except Exception: pass
        row = {
            "ticker": ticker, "name": name[:22], "close": round(close, 2),
            "score": int(sc), "ai": round(ai_p, 1),
            "state": state, "abc": abc,
            "rsi": round(rsi_v, 1) if rsi_v is not None else None,
            "adx": round(adx_v, 1) if adx_v is not None else None,
            "ext": round(ext_v, 1) if ext_v is not None else None,
            "rel_vol": round(rv, 2) if rv is not None else None,
            "daily": round(daily, 2) if daily is not None else None,
            "5d": round(five_d, 2) if five_d is not None else None,
            "20d": round(twenty_d, 2) if twenty_d is not None else None,
            "pe": round(pe, 1) if pe is not None else None, "pe_gr": pe_gr,
            "roe": round(roe, 1) if roe is not None else None, "roe_gr": roe_gr,
            "roa": round(roa, 1) if roa is not None else None, "roa_gr": roa_gr,
            "eps_g": round(eps_g, 1) if eps_g is not None else None, "eps_gr": eps_gr,
            "fund": fund_score, "sector": sector, "mktcap": mc_str,
            "atr": round(atr_v, 2) if atr_v is not None else None,
            "buffett": bq_score, "buffett_v": bq_verdict, "mos": bq_mos,
            "earn_days": earn_days, "earn_date": earn_date, "exdiv_date": exdiv_date,
            "perf_3m": perf_3m, "perf_6m": perf_6m, "perf_1y": perf_1y,
            "from_hi52": from_hi52, "from_lo52": from_lo52,
            "sma50_rel": sma50_rel, "sma200_rel": sma200_rel,
            "asof": asof,
            "signals": scr_signals, "patterns": scr_patterns, "pat_c": pat_c,
            "sma20_rel": sma20_rel, "from_hi50": from_hi50, "from_lo50": from_lo50,
            "gap": gap_v, "chg_open": chg_open, "vol_w": vol_w, "vol_m": vol_m,
            "avg_vol_m": avg_vol, "mktcap_b": round(mktcap / 1e9, 2) if mktcap else None,
            "fpe": xf.get("fpe"), "peg": xf.get("peg"), "ps": xf.get("ps"), "pb": xf.get("pb"),
            "div_yield": xf.get("div_yield"), "payout": xf.get("payout"),
            "eps_ttm": xf.get("eps_ttm"), "beta": xf.get("beta"), "sales_g": xf.get("sales_g"),
            "gross_m": xf.get("gross_m"), "oper_m": xf.get("oper_m"), "net_m": xf.get("net_m"),
            "debt_eq": xf.get("debt_eq"), "curr_ratio": xf.get("curr_ratio"),
            "quick_ratio": xf.get("quick_ratio"), "insider_own": xf.get("insider_own"),
            "inst_own": xf.get("inst_own"), "short_float": xf.get("short_float"),
            "short_ratio": xf.get("short_ratio"), "analyst_rec": xf.get("analyst_rec"),
            "shares_out": xf.get("shares_out"), "float_shares": xf.get("float_shares"),
            "float_out": xf.get("float_out"),
            "rs_3m": rs_3m, "rs_6m": rs_6m, "rs_rank": None,
            "target": tgt, "upside": upside, "proj_conf": conf,
            "hessian": hess_data,
        }
        try:
            row["fg"] = fg_block(row)
        except Exception:
            row["fg"] = None
        _ROW_CACHE[ticker] = row
        return row
    except Exception as e:
        print(f"  ERROR {ticker}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip heavy backtest (for quick updates)")
    parser.add_argument("--quick", action="store_true", help="Only refresh core groups (Watchlist + Índices) and skip backtest")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    print(f"FIGAND SCANNER PRO — Building data at {datetime.now()}")
    groups = GROUPS
    if args.quick:
        groups = {k: v for k, v in GROUPS.items() if k in ("🎯 Watchlist Core", "📊 Índices Mundiales")}
        args.skip_backtest = True
        print("  ⚡ Quick mode: solo grupos core, sin backtest")
    # SPY primero: ancla para régimen de mercado y fuerza relativa
    spy_hist = fetch_history("SPY")
    spy_close = spy_hist["Close"].tail(260) if spy_hist is not None and len(spy_hist) > 0 else None
    market_regime = None
    if spy_hist is not None and len(spy_hist) >= 210:
        try:
            market_regime = compute_market_regime(spy_hist)
            if market_regime:
                print(f"  {market_regime['icon']} Régimen: {market_regime['regime']} — SPY {market_regime['spy_vs_sma200_pct']:+.1f}% vs SMA200")
            else:
                print("  ⚠️ Régimen no calculado: datos del SPY incompletos")
        except Exception as e:
            print(f"  ⚠️ Régimen no calculado: {e}")
    groups_data = {}
    for group_name, tickers in groups.items():
        rows = []
        seen = set()
        for i, t in enumerate(tickers):
            if t in seen: continue
            seen.add(t)
            fresh = t not in _ROW_CACHE  # ya descargado en otro grupo → reusa cache
            print(f"  [{group_name}] {i+1}/{len(tickers)} {t}{'' if fresh else ' (cache)'}")
            row = get_stock_data(t, spy_close=spy_close)
            if row: rows.append(row)
            if fresh:
                time.sleep(0.2)
        groups_data[group_name] = rows
    # Fuerza relativa: ranking percentil 0-100 sobre el universo completo
    uniq = {}
    for rows in groups_data.values():
        for r in rows:
            uniq[r["ticker"]] = r
    rs_vals = sorted(r["rs_3m"] for r in uniq.values() if r.get("rs_3m") is not None)
    if len(rs_vals) >= 10:
        import bisect
        for r in uniq.values():
            if r.get("rs_3m") is not None:
                pos = bisect.bisect_left(rs_vals, r["rs_3m"])
                r["rs_rank"] = round(pos / max(1, len(rs_vals) - 1) * 100)
    # Señales transversales sobre el universo (estilo Finviz)
    try:
        rows_l = list(uniq.values())
        def _topset(key, n=20, reverse=True):
            vals = [r for r in rows_l if r.get(key) is not None]
            vals.sort(key=lambda r: r[key], reverse=reverse)
            return {r["ticker"] for r in vals[:n]}
        tg = _topset("daily", 20, True)
        tl = _topset("daily", 20, False)
        mv = _topset("vol_m", 25, True)
        ma = _topset("avg_vol_m", 25, True)
        for r in rows_l:
            s = r.get("signals") or []
            if r["ticker"] in tg: s.append("top_gainers")
            if r["ticker"] in tl: s.append("top_losers")
            if r["ticker"] in mv: s.append("most_volatile")
            if r["ticker"] in ma: s.append("most_active")
            r["signals"] = s
    except Exception as e:
        print(f"  ⚠️ señales transversales: {e}")

    # Column ranges for visual bars
    col_ranges = {}
    for gn, rows in groups_data.items():
        vals = lambda k: [r[k] for r in rows if r.get(k) is not None]
        for k in ["daily", "5d", "20d"]:
            v = vals(k)
            col_ranges.setdefault(gn, {})[k] = [min(v) if v else -5, max(v) if v else 5]
    path = os.path.join(args.out_dir, "snapshot.json")
    if args.quick and os.path.exists(path):
        # Merge: keep groups we did not refresh
        try:
            with open(path, "r", encoding="utf-8") as f:
                prev = json.load(f)
            merged_groups = prev.get("groups", {})
            merged_groups.update(groups_data)
            groups_data = merged_groups
            prev_ranges = prev.get("column_ranges", {})
            prev_ranges.update(col_ranges)
            col_ranges = prev_ranges
            if market_regime is None:
                market_regime = prev.get("market_regime")
        except Exception as e:
            print(f"  ⚠️ No se pudo fusionar snapshot previo: {e}")
    snapshot = {
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "market_regime": market_regime,
        "groups": groups_data,
        "column_ranges": col_ranges,
    }
    total_tickers = sum(len(r) for r in groups_data.values())
    
    # Safety: don't overwrite a working file with empty/broken data
    if total_tickers < 10 and os.path.exists(path):
        print(f"\n⚠️ Only {total_tickers} tickers loaded (expected 200+). Keeping existing snapshot.json.")
        print(f"  This usually means Yahoo Finance is rate-limiting or unavailable.")
    else:
        dump_json(snapshot, path)
        print(f"\nWrote {path} — {total_tickers} tickers processed")
    
    # Run real backtest with historical data (skip on quick 5-min updates)
    if not args.skip_backtest:
        run_full_backtest(groups_data, args.out_dir)
    else:
        print("  ⏭ Backtest skipped (--skip-backtest flag)")

if __name__ == "__main__":
    main()
