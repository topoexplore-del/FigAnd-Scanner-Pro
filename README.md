# 🎯 FigAnd Scanner Pro v19 — Edición Profesional

Bloomberg-terminal style market scanner with real-time TradingView charts, quantitative scoring, AI probability model, fundamental analysis, and price projections.

**LONG ONLY** · Anti-repaint guaranteed · 120+ tickers across global markets

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Build scanner data (runs ~5-10 minutes)
python scripts/build_data.py --out-dir data

# 3. Preview locally
python -m http.server 8000
# Open http://localhost:8000
```

## Deploy to GitHub Pages (Recommended)

1. Push repo to GitHub
2. **Settings > Pages** → deploy from `main` branch
3. The GitHub Action refreshes data daily at 16:30 ET (after market close)
4. Run manually: **Actions > Refresh Scanner Data > Run workflow**

## Deploy to Streamlit Cloud (Alternative)

```bash
# Requires: streamlit in requirements
pip install streamlit
streamlit run app.py
```

## Features

| Feature | Description |
|---------|-------------|
| **Technical Score (0-100)** | EMA 50/200, RSI, ADX, Bollinger compression, OBV, volume, breakout setup |
| **AI Probability (5-95%)** | Sigmoid model: momentum Z-score, trend strength, volume regime |
| **Fundamental Grade** | P/E, ROE, ROA, EPS growth with traffic-light grading |
| **State Machine** | WAIT → ACCUM → ENTRY → ENTRY+ (fundamental-enhanced) |
| **Price Projections** | Quantitative targets based on ATR, momentum, and valuation |
| **TradingView Charts** | Real-time professional charts with MA% Ribbon + SPY overlay |
| **Multi-Chart Grid** | View entire sector at once |
| **Keyboard Navigation** | ↑↓ browse, M multichart, Esc single |
| **Anti-Repaint** | Only uses closed candles (verified with look-ahead test) |

## Fundamental Reference

| Metric | 🟢 Excellent | 🟡 Good | 🟠 Fair | 🔴 Weak |
|--------|-------------|---------|---------|---------|
| **P/E** | < 15 (Cheap) | 15-25 (Fair) | 25-40 (Pricey) | > 40 (Overvalued) |
| **ROE** | > 20% | 15-20% | 10-15% | < 10% |
| **ROA** | > 10% | 5-10% | 3-5% | < 3% |
| **EPS Growth** | > 25% | 10-25% | 0-10% | < 0% |

## Architecture

```
figand-scanner-pro/
├── index.html                 # Bloomberg terminal dashboard
├── scripts/build_data.py      # Data pipeline (technical + AI + fundamental)
├── data/snapshot.json          # Pre-computed scanner data
├── app.py                     # Streamlit wrapper (optional)
├── .github/workflows/         # Auto-refresh Mon-Fri 16:30 ET
└── requirements.txt
```

## 🎓 Nivel Profesional (FigAnd)

Esta edición añade sobre la base v18: **backtest de rigor institucional** (P&L neto tras costos configurables, validación walk-forward in-sample/out-of-sample, Sharpe por operación, máximo drawdown, benchmark SPY buy&hold como listón, histórico ampliado a 5 años incluyendo el bajista de 2022) y **conciencia de eventos** (calendario de earnings y ex-dividendo por ticker, blackout automático de alertas a ≤5 días del reporte, advertencias a ≤14 días). Detalles completos en `MANUAL_NIVEL_PRO.md`.

## 🎯 Pestaña COMBO — Motor estadístico FIGAND

Nueva pestaña que convierte el análisis del historial en reglas activas: escanea el universo, detecta qué acciones cumplen hoy las combinaciones que históricamente funcionaron, y las ordena por evidencia estadística. Incluye FIGAND Score 0-100, cuatro niveles de alerta, ficha explicativa por ticker, buscador por nombre de compañía y recálculo automático de los perfiles con `scripts/figand_stats.py`. El sistema original queda intacto: el motor vive en `figand_engine.js`, aislado. Detalle en `MANUAL_FIGAND.md`.

## 🔎 Screener estilo Finviz (nuevo)

Pestaña Screener en dashboard y app: **Order by** con ~55 métricas (performance semana→año, valoración P/E–PEG–P/S–P/B, dividendos, márgenes, deuda, insider/institutional ownership, short float, recomendación de analistas, volatilidad, distancias a SMAs y a máximos/mínimos…), **Signal** con Top Gainers/Losers, nuevos máximos/mínimos 52s, más volátiles/activas, volumen inusual, sobrecompra/sobreventa, cruces dorados, rupturas, earnings próximos, y **detección propia de 20+ patrones chartistas** (dobles/triples techos y suelos, HCH y su inverso, triángulos, cuñas, canales, rectángulos, banderas, banderines, taza con asa, soportes/resistencias). Ver `MANUAL_SCREENER.md`.

## 📱 App para iPhone (nueva)

El proyecto incluye una app móvil instalable (`movil.html` + PWA): ícono propio, pantalla completa, modo offline, sondeo automático cada 60 s de los datos publicados, gráficos en vivo de TradingView por ticker, y renderizado dinámico — **los cambios que hagas en los `.py` se reflejan en la app automáticamente** vía los JSON que generan los workflows. Instrucciones completas en `MANUAL_APP_IPHONE.md`. Al entrar desde un celular, el dashboard redirige solo a la versión móvil.

## ⚡ Importante: primer arranque

El `data/snapshot.json` incluido trae **valores DEMO** en las columnas nuevas (Buffett, MOS, RS) y un régimen marcado como DEMO, solo para que veas la interfaz v18 funcionando de inmediato. Para datos reales ejecuta:

```bash
python scripts/build_data.py --out-dir data
```

o lanza el workflow **Full Refresh + Backtest** en GitHub Actions. Ver `MANUAL_INSTALACION.md`.

## Novedades v18 — Régimen de mercado, Calidad Buffett y Fuerza Relativa

- **🟢🟡🔴 Filtro de Régimen de Mercado (Faber 2007)**: el sistema clasifica el mercado con el SPY vs su SMA200. En BEAR las alertas de compra se **suspenden automáticamente**; en NEUTRAL solo pasan señales con fuerza relativa alta. El backtest incluye el bucket `regime_filtered` que demuestra el edge del filtro contra la señal sin filtrar y contra el baseline.
- **🏰 Buffett Quality Score (0-100) + Margen de Seguridad**: diez chequeos al estilo Buffett/Munger (ROE>15%, margen bruto>40% como proxy de moat, deuda baja, FCF yield, etc.) con veredicto MOAT/QUALITY/PROMEDIO/DÉBIL, y MOS estimado con el Número de Graham (fallback por FCF).
- **📈 Fuerza Relativa vs SPY**: retorno 3M/6M en exceso del índice y ranking percentil 0-100 contra todo el universo (momentum transversal, Jegadeesh & Titman 1993).
- **⚖️ Tamaño de posición en cada alerta**: acciones sugeridas por cada $10k de capital arriesgando 1% hasta el stop.
- **📖 Manuales en español**: `MANUAL_INSTALACION.md` y `MANUAL_USO.md`.

## Mejoras v17.1

- **Caché global de datos**: cada ticker se descarga UNA vez (2 años) y se reutiliza para snapshot y backtest (~3x menos llamadas a Yahoo, menos rate-limiting).
- **Deduplicación de alertas**: `data/alerts_state.json` evita reenviar la misma señal varias veces el mismo día.
- **Zonas SL/TP basadas en ATR**: el stop ya no está a 0.5% de la entrada (ruido puro); ahora SL = entrada − 1.5·ATR, TP1/TP2 = +1/+2 ATR.
- **Baseline buy & hold en el backtest**: cada ticker incluye `baseline` por periodo. Si el win-rate de la estrategia no supera claramente el baseline, la señal no aporta edge real.
- **Modo `--quick`**: refresca solo Watchlist Core + Índices y fusiona con el snapshot existente (para los chequeos intradía).
- **Workflows corregidos**: el cron de cada 5 min era inviable (la build tarda >5 min y los datos son EOD por anti-repaint, así que no cambiaban intradía). Ahora: 3 chequeos/día con `--quick` + chequeo automático tras el refresh diario. Los chequeos rápidos ya no commitean el snapshot (evita inflar el repo).
- **Bugs corregidos**: valores 0.0 (RSI, daily%, P/E...) se convertían en `null` por chequeos de truthiness; cálculo Hessiano roto y costoso eliminado; tickers delistados/renombrados (PXD, FISV→FI, IACI, BF.B→BF-B); inyección de datos en Streamlit (`app.py`) que no funcionaba; email personal hardcodeado eliminado.

## Limitaciones conocidas (honestidad metodológica)

- El backtest usa **fundamentales actuales como proxy histórico** (sesgo de look-ahead en la capa 2; la API gratuita no da fundamentales históricos).
- Las señales se muestrean cada 5 barras y los retornos a distintos horizontes **se solapan**: los win-rates están autocorrelacionados y no equivalen a trades independientes. Compáralos siempre contra el `baseline`.
- El universo de tickers actual tiene **sesgo de supervivencia** (solo empresas que existen hoy).
- La "AI Probability" y la capa "Game Theory" son heurísticas calibradas a mano, no modelos entrenados ni probabilidad bayesiana formal.

## Disclaimer

This tool is for informational and educational purposes only. Not financial advice. All trading involves risk of capital loss.
