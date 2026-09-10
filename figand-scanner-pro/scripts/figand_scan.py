#!/usr/bin/env python3
"""
FIGAND SCAN — escaneo del universo COMPLETO de la hoja Listado.

Por qué existe este script aparte:
  El pipeline principal (build_data.py) descarga fundamentales con .info por
  cada ticker — imprescindible para Buffett/MOS, pero lento: inviable para
  11.500 símbolos. Los cuatro perfiles combo, en cambio, solo necesitan
  variables derivadas del PRECIO (earliness, fase, Markov, Dif EMA). Eso
  permite usar descarga por LOTES (yfinance.download), órdenes de magnitud
  más rápida, y cubrir todo el universo.

Cobertura rotatoria: cada ejecución procesa tantos lotes como permita el
presupuesto de tiempo y guarda dónde se quedó; la siguiente continúa desde
ahí. En pocas ejecuciones se recorre el universo entero sin reventar el
límite de GitHub Actions.

Salida: data/figand_scan.json — solo los tickers con al menos un perfil
combo activo, más los mejores por puntuación. No se guarda el universo
entero: sería enorme e inútil.
"""
import json, math, os, re, time, sys, warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
sys.path.insert(0, os.path.join(BASE, "scripts"))

BATCH = int(os.environ.get("FIGAND_BATCH", "120"))
BUDGET_MIN = float(os.environ.get("FIGAND_BUDGET_MIN", "30"))
INCLUDE_ETF = os.environ.get("FIGAND_INCLUDE_ETF", "1") != "0"
MAX_OUT = int(os.environ.get("FIGAND_MAX_OUT", "600"))

def json_safe(o):
    if isinstance(o, dict): return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [json_safe(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o): return None
    return o

def load(name, default):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def main():
    import pandas as pd, numpy as np, yfinance as yf
    import build_data as bd
    from figand_stats import cond_ok

    print("═" * 60 + "\nFIGAND SCAN — universo completo de la hoja Listado\n" + "═" * 60)
    universe = load("universe.json", {})
    profiles = load("figand_profiles.json", {}).get("perfiles", [])
    if not universe or not profiles:
        print("  ⚠️ Falta universe.json o figand_profiles.json — nada que escanear.")
        return

    # ── Selección de símbolos operables ──
    tickers = []
    for tk, u in universe.items():
        if not re.fullmatch(r"[A-Z]{1,5}", tk):
            continue                      # descarta warrants, units y preferentes
        is_etf = "Exchange Traded Fund" in (u[2] or "")
        if is_etf and not INCLUDE_ETF:
            continue
        tickers.append(tk)
    tickers.sort()
    print(f"  Universo total en Listado: {len(universe)} · operables: {len(tickers)}"
          f" (ETFs {'incluidos' if INCLUDE_ETF else 'excluidos'})")

    prev = load("figand_scan.json", {})
    start = int(prev.get("next_offset", 0)) % max(1, len(tickers))
    orden = tickers[start:] + tickers[:start]
    print(f"  Cobertura rotatoria: empieza en el índice {start} ({orden[0]})")

    t0 = time.time()
    rows, procesados, fallidos = {}, 0, 0
    for i in range(0, len(orden), BATCH):
        if (time.time() - t0) / 60 > BUDGET_MIN:
            print(f"  ⏱ Presupuesto de {BUDGET_MIN:.0f} min agotado — se continuará en la próxima ejecución.")
            break
        lote = orden[i:i + BATCH]
        try:
            df = yf.download(lote, period="2y", interval="1d", group_by="ticker",
                             auto_adjust=True, threads=True, progress=False)
        except Exception as e:
            print(f"  ⚠️ lote {i//BATCH+1}: {e}")
            fallidos += len(lote); continue
        for tk in lote:
            procesados += 1
            try:
                d = df[tk] if isinstance(df.columns, pd.MultiIndex) else df
                d = d.dropna()
                if d is None or len(d) < 210:
                    continue
                ind = bd.compute_score(d)
                last = -1
                close = float(d["Close"].iloc[last])
                if not np.isfinite(close) or close <= 0:
                    continue
                sc = float(ind["score"].iloc[last])
                ai = float(ind["ai"].iloc[last])
                ext = float(ind["ext"].iloc[last]) if not pd.isna(ind["ext"].iloc[last]) else 0.0
                rsi = float(ind["rsi"].iloc[last]) if not pd.isna(ind["rsi"].iloc[last]) else 50.0
                adx = float(ind["adx"].iloc[last]) if not pd.isna(ind["adx"].iloc[last]) else 15.0
                rv = float(ind["rel_vol"].iloc[last]) if not pd.isna(ind["rel_vol"].iloc[last]) else None
                c = d["Close"]
                d5 = round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2) if len(c) > 6 else None
                d20 = round(float(c.iloc[-1] / c.iloc[-21] - 1) * 100, 2) if len(c) > 21 else None
                s20 = float(c.rolling(20).mean().iloc[-1])
                s200 = float(c.rolling(200).mean().iloc[-1])
                # Sin fundamentales: se pasa un composite neutro para el estado.
                state = bd.compute_state(sc, ai, ext, 50)
                row = {
                    "ticker": tk, "close": round(close, 2),
                    "name": universe[tk][0], "sector": universe[tk][1],
                    "industry": universe[tk][2],
                    "score": round(sc), "ai": round(ai, 1), "state": state,
                    "rsi": round(rsi, 1), "adx": round(adx, 1),
                    "rel_vol": round(rv, 2) if rv else None,
                    "5d": d5, "20d": d20, "ext": round(ext, 1),
                    "sma20_rel": round((close / s20 - 1) * 100, 2) if s20 > 0 else None,
                    "sma200_rel": round((close / s200 - 1) * 100, 2) if s200 > 0 else None,
                    "fund": None, "upside": None, "sin_fundamentales": True,
                }
                row["fg"] = bd.fg_block(row)
                rows[tk] = row
            except Exception:
                fallidos += 1
        hechos = min(i + BATCH, len(orden))
        print(f"  lote {i//BATCH+1}: {hechos}/{len(orden)} · válidos {len(rows)} · "
              f"{(time.time()-t0)/60:.1f} min", flush=True)

    # ── Evaluación de perfiles (mismo criterio que el motor) ──
    hits = []
    for tk, r in rows.items():
        act = []
        for p in profiles:
            res = [cond_ok(cid, r["fg"]) for cid in p["cond"]]
            if all(x is True for x in res):
                act.append(p["id"])
        n_combo = sum(1 for p in profiles if p["id"] in act and p.get("combo"))
        if n_combo >= 1:
            r["perfiles"] = act
            r["n_combo"] = n_combo
            hits.append(r)
    hits.sort(key=lambda r: (-r["n_combo"], -(r.get("score") or 0)))
    salida = hits[:MAX_OUT]

    prev_rows = {r["ticker"]: r for r in prev.get("rows", [])}
    for r in salida:
        prev_rows[r["ticker"]] = r
    # Conservar resultados recientes de rondas anteriores hasta completar la vuelta
    combinado = sorted(prev_rows.values(), key=lambda r: (-(r.get("n_combo") or 0), -(r.get("score") or 0)))[:MAX_OUT * 2]

    out = {
        "generado": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "universo_total": len(tickers),
        "procesados_esta_ronda": procesados,
        "validos_esta_ronda": len(rows),
        "con_combo_esta_ronda": len(hits),
        "next_offset": (start + procesados) % max(1, len(tickers)),
        "cobertura_pct": round(procesados / max(1, len(tickers)) * 100, 1),
        "nota": "Universo completo del Listado sin fundamentales (los perfiles combo solo usan variables de precio). Cobertura rotatoria entre ejecuciones.",
        "rows": combinado,
    }
    with open(os.path.join(DATA, "figand_scan.json"), "w", encoding="utf-8") as f:
        json.dump(json_safe(out), f, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    print(f"\n  Procesados: {procesados} · válidos: {len(rows)} · con perfil combo: {len(hits)}")
    print(f"  Guardados en figand_scan.json: {len(combinado)} (acumulado entre rondas)")
    print(f"  Próxima ejecución continúa desde el índice {out['next_offset']}")

if __name__ == "__main__":
    main()
