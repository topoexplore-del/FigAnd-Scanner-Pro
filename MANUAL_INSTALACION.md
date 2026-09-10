# 📦 Manual de Instalación — FigAnd Scanner Pro v18

Este manual cubre las tres formas de instalar y desplegar el sistema, de la más simple a la más completa. La opción recomendada es **GitHub Pages + GitHub Actions**, porque automatiza todo (datos diarios, backtest y alertas) sin necesidad de un servidor.

## Requisitos previos

Necesitas Python 3.10 o superior (se recomienda 3.12), una cuenta de GitHub si vas a usar el despliegue automático, y conexión a internet (los datos vienen de Yahoo Finance, que es gratuito y no requiere API key). Opcionalmente: una cuenta de Gmail para las alertas por correo, un bot de Telegram para alertas por mensaje, y una API key gratuita de Finnhub (finnhub.io) como fuente secundaria de datos.

## Opción A — Ejecución local (para probar)

```bash
# 1. Descomprime el proyecto y entra a la carpeta
cd figand-scanner-pro

# 2. Crea un entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Instala las dependencias
pip install -r requirements.txt

# 4. Construye los datos (tarda 10-25 min la primera vez, ~480 tickers)
python scripts/build_data.py --out-dir data

#    Para una prueba rápida (solo Watchlist + Índices, sin backtest, ~3 min):
python scripts/build_data.py --out-dir data --quick

# 5. Levanta un servidor local y abre el dashboard
python -m http.server 8000
# Abre http://localhost:8000 en tu navegador
```

Para probar las alertas localmente (sin enviar nada, solo verlas en consola):

```bash
python scripts/check_alerts.py
```

## Opción B — GitHub Pages + Actions (recomendada)

Con esta opción el sistema se actualiza solo, todos los días, sin que tengas que encender nada.

**Paso 1 — Sube el repositorio.** Crea un repositorio nuevo en GitHub (puede ser privado, pero GitHub Pages gratuito requiere repositorio público) y sube todo el contenido de la carpeta:

```bash
cd figand-scanner-pro
git init
git add .
git commit -m "FigAnd Scanner Pro v18"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

**Paso 2 — Activa GitHub Pages.** En el repositorio ve a *Settings → Pages*, en "Source" elige *Deploy from a branch*, selecciona la rama `main` y carpeta `/ (root)`. En 1-2 minutos tu dashboard quedará en `https://TU_USUARIO.github.io/TU_REPO/`.

**Paso 3 — Permisos de Actions.** Ve a *Settings → Actions → General → Workflow permissions* y marca **Read and write permissions** (los workflows necesitan hacer commit de los datos actualizados).

**Paso 4 — Configura los secrets de alertas (opcional).** En *Settings → Secrets and variables → Actions → New repository secret*, crea los que necesites:

| Secret | Qué es | Cómo obtenerlo |
|---|---|---|
| `SMTP_USER` | Tu correo de Gmail | Tu dirección, ej. `tucorreo@gmail.com` |
| `SMTP_PASS` | Contraseña de aplicación | Google → Cuenta → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones |
| `ALERT_EMAIL` | Correo destino de las alertas | Puede ser el mismo `SMTP_USER` |
| `TELEGRAM_TOKEN` | Token del bot | Habla con @BotFather en Telegram → `/newbot` |
| `TELEGRAM_CHAT_ID` | Tu chat ID | Habla con @userinfobot en Telegram |
| `FINNHUB_KEY` | API key opcional | Registro gratis en finnhub.io |

Importante: para Gmail **no sirve tu contraseña normal** — debes generar una "contraseña de aplicación" (requiere tener activada la verificación en 2 pasos).

**Paso 5 — Primera ejecución manual.** Ve a *Actions → Full Refresh + Backtest (Daily) → Run workflow*. Esto descarga todos los datos, corre el backtest y publica el snapshot. A partir de ahí los workflows corren solos: el refresh completo de lunes a viernes ~21:30 UTC (tras el cierre de Wall Street) y el chequeo de alertas 3 veces al día con datos rápidos.

## Opción C — Streamlit Cloud (alternativa)

```bash
pip install streamlit
streamlit run app.py
```

Para Streamlit Cloud: sube el repo a GitHub, entra a share.streamlit.io, conecta el repositorio y apunta a `app.py`. Añade `streamlit` a `requirements.txt` antes de desplegar. Ten en cuenta que la primera ejecución construye los datos y puede tardar; GitHub Pages es más estable para este sistema.

## Verificación de la instalación

Tras la primera build deberías ver: `data/snapshot.json` (datos del scanner, con el campo `market_regime`), `data/backtest.json` (resultados históricos con los buckets `baseline`, `tech_signals` y `regime_filtered`), y `data/alerts.json` tras correr `check_alerts.py`. Si el dashboard muestra "Error loading data", espera 2 minutos a que GitHub Pages publique y recarga.

## Problemas frecuentes

**"Only N tickers loaded — Keeping existing snapshot"**: Yahoo Finance está limitando peticiones. El sistema protege el snapshot anterior automáticamente; reintenta en una hora.

**El email no llega**: revisa que `SMTP_PASS` sea una contraseña de aplicación (16 caracteres) y que `ALERT_EMAIL` esté definido. Mira el log del workflow en Actions para ver el error exacto.

**Telegram no envía**: el bot debe haber recibido al menos un mensaje tuyo primero (escríbele `/start`), y el `TELEGRAM_CHAT_ID` debe ser el numérico de @userinfobot.

**El workflow falla con "permission denied" al hacer push**: te faltó el Paso 3 (Workflow permissions → Read and write).
