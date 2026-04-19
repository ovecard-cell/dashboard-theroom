import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
from pathlib import Path
from datetime import date, timedelta
import anthropic

from data_processor import (
    load_dux_files,
    load_ventas_manuales,
    merge_ventas,
    ventas_por_dia,
    ventas_hoy,
    ventas_mes,
    proyeccion_mes,
    stock_nuevo_resumen,
)

# ── Configuración de página ────────────────────────────────────────────────────
st.set_page_config(
    page_title="The Room",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Auto-refresh cada 5 minutos (no pierde sesión) ───────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=300000, limit=None, key="auto_refresh")  # 300000ms = 5 min
except ImportError:
    pass  # Si no está instalado, no pasa nada

# ── Sistema de notificaciones persistentes (sobrevive st.rerun) ───────────────
def _mostrar_notificaciones():
    """Muestra y limpia notificaciones guardadas en session_state."""
    for msg in st.session_state.pop("_notifs", []):
        tipo = msg.get("tipo", "success")
        texto = msg.get("texto", "")
        if tipo == "success":
            st.success(texto)
        elif tipo == "warning":
            st.warning(texto)
        elif tipo == "error":
            st.error(texto)
        elif tipo == "info":
            st.info(texto)

def _notificar(texto, tipo="success"):
    """Encola una notificación que se mostrará después del próximo rerun."""
    if "_notifs" not in st.session_state:
        st.session_state["_notifs"] = []
    st.session_state["_notifs"].append({"texto": texto, "tipo": tipo})

# ── CSS completo ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Reset y base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

* { box-sizing: border-box; }

html, body, [class*="css"], .stApp {
    font-family: 'Inter', sans-serif !important;
    background-color: #0d0d14 !important;
    color: #e8e8f0 !important;
}

/* Ocultar elementos de Streamlit */
#MainMenu, footer, header, .stDeployButton,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; }

/* Contenedor principal */
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── Header de la app ── */
.app-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 18px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #ffffff12;
    margin-bottom: 0;
}
.app-header-left { display: flex; align-items: center; gap: 14px; }
.app-logo {
    width: 42px; height: 42px;
    background: linear-gradient(135deg, #e94560, #0f3460);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
}
.app-title { font-size: 1.4rem; font-weight: 800; color: #fff; letter-spacing: -0.5px; }
.app-subtitle { font-size: 0.75rem; color: #8888aa; margin-top: 1px; }
.app-date {
    background: #ffffff0f;
    border: 1px solid #ffffff14;
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 0.8rem;
    color: #aaaacc;
}

/* ── Navegación por tabs ── */
.nav-container {
    background: #12121e;
    border-bottom: 1px solid #ffffff0e;
    padding: 0 24px;
    display: flex;
    gap: 4px;
}

/* Tabs de Streamlit — override completo */
[data-testid="stTabs"] { background: transparent !important; }
[data-testid="stTabs"] > div:first-child {
    background: #12121e !important;
    border-bottom: 1px solid #ffffff0e !important;
    padding: 0 24px !important;
    gap: 4px !important;
}
button[data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    color: #6666aa !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    padding: 14px 20px !important;
    border-bottom: 2px solid transparent !important;
    transition: all 0.2s !important;
}
button[data-baseweb="tab"]:hover {
    color: #ccccee !important;
    background: #ffffff08 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #e94560 !important;
    border-bottom: 2px solid #e94560 !important;
    background: transparent !important;
}
[data-testid="stTabPanel"] {
    padding: 28px 28px !important;
    background: transparent !important;
}

/* ── Tarjetas de métricas ── */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}
.metric-card {
    background: #1a1a2e;
    border: 1px solid #ffffff0e;
    border-radius: 14px;
    padding: 20px 22px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, border-color 0.2s;
}
.metric-card:hover {
    transform: translateY(-2px);
    border-color: #ffffff20;
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 14px 14px 0 0;
}
.metric-card.verde::before { background: linear-gradient(90deg, #00c96b, #00ff9f); }
.metric-card.rojo::before { background: linear-gradient(90deg, #e94560, #ff6b6b); }
.metric-card.azul::before { background: linear-gradient(90deg, #3a86ff, #4ecdc4); }
.metric-card.amarillo::before { background: linear-gradient(90deg, #f7b731, #ffd32a); }
.metric-card.morado::before { background: linear-gradient(90deg, #8b5cf6, #c084fc); }

.metric-icon {
    font-size: 1.6rem;
    margin-bottom: 10px;
    display: block;
}
.metric-label {
    font-size: 0.72rem;
    color: #6666aa;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 600;
    margin-bottom: 6px;
}
.metric-value {
    font-size: 1.85rem;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -1px;
    line-height: 1;
}
.metric-sub {
    font-size: 0.75rem;
    color: #6666aa;
    margin-top: 6px;
}
.metric-delta-pos { color: #00c96b; font-weight: 600; }
.metric-delta-neg { color: #e94560; font-weight: 600; }

/* ── Alertas ── */
.alerta {
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 0.875rem;
    font-weight: 500;
    border: 1px solid;
}
.alerta-roja {
    background: #2d0a12;
    border-color: #e9456044;
    color: #ff8fa3;
}
.alerta-amarilla {
    background: #2a1f00;
    border-color: #f7b73144;
    color: #ffd97d;
}
.alerta-verde {
    background: #002d1a;
    border-color: #00c96b44;
    color: #6effc4;
}
.alerta-azul {
    background: #001a3a;
    border-color: #3a86ff44;
    color: #90c0ff;
}

/* ── Sección con título ── */
.seccion-titulo {
    font-size: 1rem;
    font-weight: 700;
    color: #ccccee;
    margin: 28px 0 14px 0;
    display: flex;
    align-items: center;
    gap: 8px;
}
.seccion-titulo::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #ffffff0a;
    margin-left: 8px;
}

/* ── Tabla personalizada ── */
.tabla-wrapper {
    background: #1a1a2e;
    border: 1px solid #ffffff0e;
    border-radius: 14px;
    overflow: hidden;
}
table.tabla-custom {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
}
table.tabla-custom thead tr {
    background: #12122a;
    border-bottom: 1px solid #ffffff10;
}
table.tabla-custom thead th {
    padding: 12px 16px;
    text-align: left;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #6666aa;
}
table.tabla-custom tbody tr {
    border-bottom: 1px solid #ffffff06;
    transition: background 0.15s;
}
table.tabla-custom tbody tr:hover { background: #ffffff05; }
table.tabla-custom tbody tr:last-child { border-bottom: none; }
table.tabla-custom tbody td {
    padding: 11px 16px;
    color: #ccccee;
}

/* ── Badges ── */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.badge-rojo { background: #e9456022; color: #ff8fa3; border: 1px solid #e9456044; }
.badge-verde { background: #00c96b22; color: #6effc4; border: 1px solid #00c96b44; }
.badge-amarillo { background: #f7b73122; color: #ffd97d; border: 1px solid #f7b73144; }
.badge-gris { background: #ffffff10; color: #8888aa; border: 1px solid #ffffff20; }
.badge-azul { background: #3a86ff22; color: #90c0ff; border: 1px solid #3a86ff44; }
.badge-naranja { background: #f7730022; color: #ffaa55; border: 1px solid #f7730044; }

/* ── Barra de progreso custom ── */
.progress-bar-bg {
    background: #ffffff0e;
    border-radius: 4px;
    height: 6px;
    overflow: hidden;
    min-width: 80px;
}
.progress-bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s;
}

/* ── Panel de cheques ── */
.cheque-card {
    background: #1a1a2e;
    border: 1px solid #ffffff0e;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: border-color 0.2s;
}
.cheque-card.urgente { border-left: 3px solid #e94560; }
.cheque-card.pronto { border-left: 3px solid #f7b731; }
.cheque-card.ok { border-left: 3px solid #00c96b; }
.cheque-card.pagado { border-left: 3px solid #444466; opacity: 0.6; }
.cheque-info { flex: 1; }
.cheque-proveedor { font-weight: 700; color: #eeeeff; font-size: 0.95rem; }
.cheque-concepto { font-size: 0.78rem; color: #6666aa; margin-top: 2px; }
.cheque-fecha { font-size: 0.78rem; color: #8888aa; margin-top: 4px; }
.cheque-monto {
    font-size: 1.3rem;
    font-weight: 800;
    color: #fff;
    text-align: right;
    margin-right: 16px;
}

/* ── Chat ── */
.chat-wrapper {
    background: #1a1a2e;
    border: 1px solid #ffffff0e;
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 16px;
    max-height: 500px;
    overflow-y: auto;
}
.chat-msg {
    margin-bottom: 14px;
    display: flex;
    gap: 10px;
    align-items: flex-start;
}
.chat-msg.user { flex-direction: row-reverse; }
.chat-avatar {
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px;
    flex-shrink: 0;
}
.chat-avatar.user { background: #e94560; }
.chat-avatar.ai { background: linear-gradient(135deg, #3a86ff, #8b5cf6); }
.chat-bubble {
    max-width: 75%;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 0.88rem;
    line-height: 1.5;
}
.chat-bubble.user {
    background: #e9456022;
    border: 1px solid #e9456033;
    color: #ffcccc;
    border-radius: 12px 4px 12px 12px;
}
.chat-bubble.ai {
    background: #ffffff0a;
    border: 1px solid #ffffff12;
    color: #ddddee;
    border-radius: 4px 12px 12px 12px;
}

/* ── Formulario login ── */
.stForm {
    background: #1a1a2e !important;
    border: 1px solid #ffffff10 !important;
    border-radius: 16px !important;
    padding: 24px !important;
    max-width: 420px !important;
    margin: 0 auto !important;
}
.stForm .stTextInput > div > div > input {
    background: #0d0d14 !important;
    border: 1px solid #3a86ff44 !important;
    border-radius: 10px !important;
    color: #eeeeff !important;
    padding: 12px 16px !important;
    font-size: 0.95rem !important;
}
.stForm .stTextInput > div > div > input:focus {
    border-color: #3a86ff !important;
    box-shadow: 0 0 0 2px #3a86ff33 !important;
}
.stForm [data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, #3a86ff, #2563eb) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    padding: 12px 20px !important;
    margin-top: 8px !important;
}
.stForm [data-testid="stFormSubmitButton"] > button:hover {
    opacity: 0.9 !important;
}
.stForm label {
    color: #aaaacc !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
}

/* ── Botones ── */
.stButton > button {
    background: linear-gradient(135deg, #e94560, #c73652) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 8px 18px !important;
    transition: opacity 0.2s, transform 0.1s !important;
}
.stButton > button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active { transform: translateY(0) !important; }

/* Botones secundarios */
.btn-secondary > button {
    background: #ffffff0e !important;
    color: #ccccee !important;
    border: 1px solid #ffffff18 !important;
}
.btn-secondary > button:hover {
    background: #ffffff18 !important;
}

/* ── Inputs ── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stNumberInput input,
.stDateInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #12122a !important;
    border: 1px solid #ffffff18 !important;
    border-radius: 8px !important;
    color: #eeeeff !important;
    font-family: 'Inter', sans-serif !important;
}
/* Number input botones +/- */
.stNumberInput > div > div {
    background: #12122a !important;
    border-radius: 8px !important;
}
.stNumberInput button {
    background: #1a1a2e !important;
    border: 1px solid #ffffff18 !important;
    color: #8888aa !important;
}
.stSelectbox > div > div,
.stSelectbox [data-baseweb="select"] {
    background: #12122a !important;
    border: 1px solid #ffffff18 !important;
    border-radius: 8px !important;
    color: #eeeeff !important;
}
/* Slider */
.stSlider > div > div > div {
    color: #eeeeff !important;
}
label { color: #8888aa !important; font-size: 0.8rem !important; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #1a1a2e !important;
    border: 1px solid #ffffff0e !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    color: #ccccee !important;
    font-weight: 600 !important;
    padding: 14px 18px !important;
}
[data-testid="stExpander"] summary:hover { background: #ffffff06 !important; }
[data-testid="stExpander"] > div {
    background: #1a1a2e !important;
    color: #ccccee !important;
}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
    color: #ccccee !important;
}
[data-testid="stExpander"] details {
    background: #1a1a2e !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #12121e !important;
    border-right: 1px solid #ffffff0e !important;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
}

/* ── Spinner / loading ── */
.stSpinner > div { border-top-color: #e94560 !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0d0d14; }
::-webkit-scrollbar-thumb { background: #333355; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #4444aa; }

/* ── Chat input nativo ── */
[data-testid="stChatInput"] > div {
    background: #1a1a2e !important;
    border: 1px solid #ffffff18 !important;
    border-radius: 12px !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: #eeeeff !important;
}
[data-testid="stChatMessageContainer"] {
    background: transparent !important;
}

/* ── Plotly charts ── */
.js-plotly-plot .plotly { background: transparent !important; }

/* ── Form ── */
[data-testid="stForm"] {
    background: #1a1a2e !important;
    border: 1px solid #ffffff0e !important;
    border-radius: 14px !important;
    padding: 20px !important;
}

/* ── Success / Error / Info ── */
.stSuccess, .stError, .stInfo, .stWarning {
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt(v: float) -> str:
    return f"${v:,.0f}"

def fmt_tabla(v: float) -> str:
    return f"${v:,.0f}"

MESES_ES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
            7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}

def fmt_fecha(d, estilo="corta"):
    """Formato unificado: corta=DD/MM/YYYY, larga=14 de Abril 2026, mes=Abril 2026"""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except Exception:
            return d
    if estilo == "corta":
        return d.strftime("%d/%m/%Y")
    elif estilo == "mes":
        return f"{MESES_ES.get(d.month, d.strftime('%B'))} {d.year}"
    else:
        return f"{d.day} de {MESES_ES.get(d.month, '')} {d.year}"


def metric_card(icono, label, valor, sub="", color="azul", delta=None, delta_pos=True):
    delta_html = ""
    if delta is not None:
        cls = "metric-delta-pos" if delta_pos else "metric-delta-neg"
        delta_html = f'<div class="{cls}" style="font-size:0.78rem;margin-top:4px">{delta}</div>'
    return f"""
    <div class="metric-card {color}">
        <span class="metric-icon">{icono}</span>
        <div class="metric-label">{label}</div>
        <div class="metric-value">{valor}</div>
        <div class="metric-sub">{sub}</div>
        {delta_html}
    </div>"""


def alerta_html(texto, nivel="roja", icono=None):
    iconos = {"roja": "🚨", "amarilla": "⚠️", "verde": "✅", "azul": "ℹ️"}
    i = icono or iconos.get(nivel, "•")
    st.markdown(
        f'<div class="alerta alerta-{nivel}"><span>{i}</span><span>{texto}</span></div>',
        unsafe_allow_html=True,
    )


def seccion(titulo):
    st.markdown(f'<div class="seccion-titulo">{titulo}</div>', unsafe_allow_html=True)


def progress_bar(pct, color="#00c96b"):
    pct = min(max(pct, 0), 100)
    return f"""
    <div style="background:#ffffff0e;border-radius:4px;height:6px;overflow:hidden;min-width:80px">
        <div style="width:{pct}%;background:{color};height:100%;border-radius:4px;transition:width 0.6s ease"></div>
    </div>"""


# ── Constantes ─────────────────────────────────────────────────────────────────
OBJETIVO_DIARIO = 300_000
COLORES = {"KAZUMA": "#3a86ff", "LISBON": "#8b5cf6", "DISTRICT": "#f7b731"}


# ── Sincronización GitHub (persistencia en la nube) ───────────────────────────
import base64
import requests as _req

_GITHUB_REPO = "ovecard-cell/dashboard-theroom"
_GITHUB_BRANCH = "main"

def _get_github_token():
    """Obtener token de GitHub desde secrets de Streamlit"""
    try:
        return st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        return os.environ.get("GITHUB_TOKEN", "")

def _sync_github(file_path: str, content: str, message: str = ""):
    """Commitear archivo al repo de GitHub via API. Solo actúa si hay token."""
    token = _get_github_token()
    if not token:
        return False
    api_url = f"https://api.github.com/repos/{_GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    # Obtener SHA actual del archivo (necesario para update)
    try:
        resp = _req.get(api_url, headers=headers, params={"ref": _GITHUB_BRANCH}, timeout=10)
        sha = resp.json().get("sha", "") if resp.status_code == 200 else ""
    except Exception:
        sha = ""
    if not message:
        message = f"Auto-save {file_path} desde dashboard"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": _GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    try:
        resp = _req.put(api_url, headers=headers, json=payload, timeout=15)
        return resp.status_code in (200, 201)
    except Exception:
        return False

def _sync_github_binary(file_path: str, content_bytes: bytes, message: str = ""):
    """Commitear archivo binario (ej: .xls) al repo de GitHub via API."""
    token = _get_github_token()
    if not token:
        return False
    api_url = f"https://api.github.com/repos/{_GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        resp = _req.get(api_url, headers=headers, params={"ref": _GITHUB_BRANCH}, timeout=10)
        sha = resp.json().get("sha", "") if resp.status_code == 200 else ""
    except Exception:
        sha = ""
    if not message:
        message = f"Auto-save {file_path} desde dashboard"
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": _GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    try:
        resp = _req.put(api_url, headers=headers, json=payload, timeout=15)
        return resp.status_code in (200, 201)
    except Exception:
        return False

def _save_json_and_sync(file_path: str, data, message: str = ""):
    """Guardar JSON localmente Y sincronizar a GitHub"""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    Path(file_path).write_text(content, encoding="utf-8")
    _sync_github(file_path, content, message)


# ── Carga de datos ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def get_ventas():
    return load_dux_files("data/ventas")


def get_cheques():
    p = Path("data/cheques.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_cheques(data):
    _save_json_and_sync("data/cheques.json", data, "Actualizar cheques desde dashboard")


def get_stock_ini():
    p = Path("data/stock_inicial.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def get_deuda():
    p = Path("data/deuda_personal.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_deuda(data):
    _save_json_and_sync("data/deuda_personal.json", data, "Actualizar deuda personal desde dashboard")


def get_bancos():
    p = Path("data/bancos.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_bancos(data):
    _save_json_and_sync("data/bancos.json", data, "Actualizar saldos bancarios desde dashboard")


def get_gastos():
    p = Path("data/gastos.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_gastos(data):
    _save_json_and_sync("data/gastos.json", data, "Actualizar gastos desde dashboard")


def get_meta():
    p = Path("data/meta_ads.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_meta(data):
    _save_json_and_sync("data/meta_ads.json", data, "Actualizar Meta Ads desde dashboard")


# ── API key ────────────────────────────────────────────────────────────────────
if "api_key" not in st.session_state:
    st.session_state.api_key = os.environ.get("ANTHROPIC_API_KEY", "")


# ── Login / Usuarios ──────────────────────────────────────────────────────────
# Usuarios: primero intenta Streamlit Secrets (seguro), si no, archivo local
try:
    _usuarios = st.secrets.get("usuarios", [])
    if _usuarios:
        _usuarios = [dict(u) for u in _usuarios]
except Exception:
    _usuarios = []
if not _usuarios:
    _p_users = Path("data/usuarios.json")
    _usuarios = json.loads(_p_users.read_text(encoding="utf-8")) if _p_users.exists() else []

# Permisos por rol: qué tabs ve cada uno
PERMISOS_ROL = {
    "dueno":     ["Resumen", "Resultados", "Movimientos", "Inconsistencias", "Stock", "Simulador", "Cheques", "Deuda Personal", "Chat IA", "Config"],
    "gerente":   ["Resumen", "Resultados", "Movimientos", "Inconsistencias", "Stock", "Simulador", "Cheques", "Deuda Personal", "Chat IA", "Config"],
    "admin":     ["Resumen", "Movimientos", "Inconsistencias", "Cheques", "Config"],
    "marketing": ["Resumen", "Stock"],
}

if "usuario_actual" not in st.session_state:
    st.session_state.usuario_actual = None
    st.session_state.rol_actual = None
    st.session_state.nombre_actual = None

# Si no hay usuarios configurados, acceso libre
if not _usuarios:
    st.session_state.usuario_actual = "admin"
    st.session_state.rol_actual = "dueno"
    st.session_state.nombre_actual = "Admin"

# Login
if st.session_state.usuario_actual is None:
    st.markdown("""
    <div style="display:flex;justify-content:center;align-items:center;min-height:60vh">
        <div style="background:#1a1a2e;border:1px solid #ffffff10;border-radius:20px;padding:40px 50px;
                    max-width:400px;width:100%;text-align:center">
            <div style="font-size:2rem;margin-bottom:8px">🏪</div>
            <div style="font-size:1.3rem;font-weight:800;color:#eeeeff;margin-bottom:4px">The Room</div>
            <div style="color:#8888aa;font-size:0.85rem;margin-bottom:24px">Dashboard — Iniciar sesion</div>
        </div>
    </div>""", unsafe_allow_html=True)
    with st.form("login_form"):
        _user_in = st.text_input("Usuario", placeholder="tu nombre de usuario")
        _pass_in = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", use_container_width=True):
            _match = [u for u in _usuarios if u["usuario"] == _user_in.lower().strip() and u["password"] == _pass_in]
            if _match:
                st.session_state.usuario_actual = _match[0]["usuario"]
                st.session_state.rol_actual = _match[0]["rol"]
                st.session_state.nombre_actual = _match[0]["nombre"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    st.stop()

# Usuario logueado
_nombre_u = st.session_state.nombre_actual
_rol_u    = st.session_state.rol_actual
_permisos = PERMISOS_ROL.get(_rol_u, [])

# Sidebar con info de sesión
with st.sidebar:
    st.markdown(f"""
    <div style="padding:12px 0">
        <div style="font-size:0.9rem;font-weight:700;color:#eeeeff">{_nombre_u}</div>
        <div style="font-size:0.75rem;color:#8888aa;text-transform:capitalize">{_rol_u}</div>
    </div>""", unsafe_allow_html=True)
    if st.button("Cerrar sesion", use_container_width=True):
        st.session_state.usuario_actual = None
        st.session_state.rol_actual = None
        st.session_state.nombre_actual = None
        st.rerun()

    st.markdown("---")
    st.markdown('<div style="font-size:0.75rem;color:#6666aa;margin-bottom:8px">EXPORTAR REPORTES</div>', unsafe_allow_html=True)

    if st.button("Generar reporte completo", use_container_width=True, key="btn_reporte"):
        st.session_state["mostrar_reporte"] = True
        st.rerun()


# ── Header ─────────────────────────────────────────────────────────────────────
hoy = date.today()
st.markdown(f"""
<div class="app-header">
    <div class="app-header-left">
        <div class="app-logo">🏪</div>
        <div>
            <div class="app-title">The Room</div>
            <div class="app-subtitle">La Rioja 943 — Corrientes</div>
        </div>
    </div>
    <div class="app-date">📅 {fmt_fecha(hoy, 'larga')} · {_nombre_u}</div>
</div>
""", unsafe_allow_html=True)

# Botón reporte siempre visible arriba
_col_rep, _col_esp = st.columns([1, 5])
with _col_rep:
    if st.button("📄 Exportar reporte", key="btn_rep_top"):
        st.session_state["mostrar_reporte"] = True
        st.rerun()


# ── Cargar datos ───────────────────────────────────────────────────────────────
with st.spinner("Cargando..."):
    df_dux    = get_ventas()
    df_manual = load_ventas_manuales()
    df        = merge_ventas(df_dux, df_manual)


# ── Garantizar columnas clave (evita KeyError en Streamlit Cloud) ─────────
_cols_requeridas = {
    "producto": "", "forma_pago": "", "marca": "", "rubro": "", "sub_rubro": "",
    "personal": "", "canal": "", "stock_tipo": "VIEJO", "proveedor_nuevo": "",
    "fecha_dia": pd.NaT, "fecha": pd.NaT,
    "neto": 0, "cantidad": 0, "costo": 0, "precio_lista": 0, "descuento": 0,
    "total_con_iva": 0, "ganancia": 0, "margen": 0,
}
for _col, _default in _cols_requeridas.items():
    if _col not in df.columns:
        df[_col] = _default

cheques  = get_cheques()
stock_ini = get_stock_ini()
sin_datos = df.empty

# ── Reporte exportable ─────────────────────────────────────────────────────────
if st.session_state.get("mostrar_reporte"):
    from data_processor import load_stock_dux as _lsd_r

    _stk_r = _lsd_r("data/stock_dux.xls")
    _bancos_r = get_bancos()
    _ult_b = _bancos_r[-1] if _bancos_r else {}
    _gastos_r = get_gastos()
    _cheques_r = get_cheques()
    _deuda_r = get_deuda()

    # Calcular datos
    _venta_neta = df["neto"].sum() if not df.empty else 0
    _venta_iva = df["total_con_iva"].sum() if not df.empty and "total_con_iva" in df.columns else _venta_neta * 1.21
    _dias_venta = df["fecha_dia"].nunique() if not df.empty else 0
    _prom_dia = _venta_neta / max(_dias_venta, 1)

    # Rentabilidad por marca
    _rent_txt = ""
    if not df.empty and not _stk_r.empty:
        MARCA_MAP_R = {"DANDY IND S.R.L.":"Lisbon","TARKUS TREND S.R.L.":"District","DACOB S.A":"Kazuma","VISTE VILO SRL, VISTE VILO":"Vilo","VINTAGE S A S. A.":"Vintage","GRUPO VEGAS":"Grupo Vegas"}
        _cm = {}
        for _, _rs in _stk_r.iterrows():
            _cm[_rs["producto"].upper()] = {"costo": _rs["costo_unit"], "marca": MARCA_MAP_R.get(_rs["proveedor_dux"], _rs["proveedor_dux"])}
        _rent_data = []
        for _, _rv in df.iterrows():
            _inf = _cm.get(str(_rv["producto"]).upper(), {})
            _c = _inf.get("costo", 0)
            _m = _inf.get("marca", "Sin marca")
            _rent_data.append({"marca": _m, "neto": _rv["neto"], "costo": _c * _rv["cantidad"], "gan": _rv["neto"] - _c * _rv["cantidad"]})
        import pandas as _pd_r
        _df_r = _pd_r.DataFrame(_rent_data)
        _pm = _df_r.groupby("marca").agg(neto=("neto","sum"), costo=("costo","sum"), gan=("gan","sum")).sort_values("gan", ascending=False)
        _pm["margen"] = (_pm["gan"] / _pm["neto"] * 100).round(1)
        for m, r in _pm.iterrows():
            _rent_txt += f"  - {m}: Venta ${r['neto']:,.0f} | Costo ${r['costo']:,.0f} | Ganancia ${r['gan']:,.0f} | Margen {r['margen']}%\n"

    # Gastos por categoría
    _gastos_abril = [g for g in _gastos_r if g["fecha"][:7] == f"{hoy.year}-{hoy.month:02d}"]
    from collections import defaultdict as _dd_r
    _gc = _dd_r(float)
    for g in _gastos_abril:
        _gc[g.get("categoria", "Otros")] += g["monto"]
    _gastos_txt = ""
    for cat, monto in sorted(_gc.items(), key=lambda x: -x[1]):
        _gastos_txt += f"  - {cat}: ${monto:,.0f}\n"

    # Cheques
    _chq_pend = [c for c in _cheques_r if c.get("estado") == "pendiente"]
    _chq_txt = ""
    for c in sorted(_chq_pend, key=lambda x: x["vencimiento"]):
        dias = (date.fromisoformat(c["vencimiento"]) - hoy).days
        estado = f"VENCIDO {abs(dias)}d" if dias < 0 else f"en {dias}d"
        _chq_txt += f"  - {c['id']} {c['proveedor']}: ${c['monto']:,.0f} — {estado} (vence {c['vencimiento']})\n"

    # Stock
    _stock_uds = int(_stk_r[_stk_r["cantidad"] > 0]["cantidad"].sum()) if not _stk_r.empty else 0
    _stock_val = _stk_r[_stk_r["cantidad"] > 0]["valor_total"].sum() if not _stk_r.empty else 0

    # Deuda
    _deuda_pend = [d for d in _deuda_r if d["estado"] == "pendiente" and d["monto"] > 0]
    _deuda_total = sum(d["monto"] for d in _deuda_pend)

    # ── Ventas diarias últimos 30 días ──────────────────────────────────────
    _ventas_dia_txt = ""
    if not df.empty:
        _df30 = df[df["fecha_dia"] >= (hoy - timedelta(days=30))]
        _por_dia_r = _df30.groupby("fecha_dia").agg(
            uds=("cantidad","sum"), neto=("neto","sum"), con_iva=("total_con_iva","sum")
        ).reset_index().sort_values("fecha_dia")
        for _, _rd in _por_dia_r.iterrows():
            _dia_sem = ["Lun","Mar","Mie","Jue","Vie","Sab","Dom"][_rd["fecha_dia"].weekday()]
            _ventas_dia_txt += f"  {_rd['fecha_dia']} ({_dia_sem}): {int(_rd['uds'])} uds — ${_rd['neto']:,.0f} sin IVA — ${_rd['con_iva']:,.0f} con IVA\n"

    # ── Top 10 productos ─────────────────────────────────────────────────────
    _top10_txt = ""
    if not df.empty:
        _df30t = df[df["fecha_dia"] >= (hoy - timedelta(days=30))]
        _top = _df30t.groupby("producto").agg(uds=("cantidad","sum"), neto=("neto","sum")).sort_values("uds", ascending=False).head(10)
        for _prod, _rt in _top.iterrows():
            _top10_txt += f"  {int(_rt['uds']):>3} uds — ${_rt['neto']:>10,.0f} — {_prod}\n"

    # ── Stock por producto con talle ──────────────────────────────────────────
    _stock_detalle_txt = ""
    _muertos_txt = ""
    if not _stk_r.empty:
        _stk_con = _stk_r[_stk_r["cantidad"] > 0].sort_values(["proveedor_dux", "producto"])
        MARCA_MAP_R2 = {"DANDY IND S.R.L.":"Lisbon","TARKUS TREND S.R.L.":"District","DACOB S.A":"Kazuma","VISTE VILO SRL, VISTE VILO":"Vilo","VINTAGE S A S. A.":"Vintage","GRUPO VEGAS":"Grupo Vegas"}
        _prov_actual = ""
        for _, _rs2 in _stk_con.iterrows():
            _marca = MARCA_MAP_R2.get(_rs2["proveedor_dux"], _rs2["proveedor_dux"])
            if _marca != _prov_actual:
                _stock_detalle_txt += f"\n  [{_marca}]\n"
                _prov_actual = _marca
            _stock_detalle_txt += f"  {int(_rs2['cantidad']):>3} uds — ${_rs2['costo_unit']:>8,.0f} costo — {_rs2['producto']}\n"

        # Productos muertos: en stock pero 0 ventas en 15+ días
        if not df.empty:
            _df15 = df[df["fecha_dia"] >= (hoy - timedelta(days=15))]
            _vendidos_15 = set(_df15["producto"].str.upper().unique()) if not _df15.empty else set()
            _muertos = _stk_con[~_stk_con["producto"].str.upper().isin(_vendidos_15)]
            if not _muertos.empty:
                for _, _rm in _muertos.iterrows():
                    _muertos_txt += f"  {int(_rm['cantidad']):>3} uds — {_rm['producto']} [{MARCA_MAP_R2.get(_rm['proveedor_dux'], _rm['proveedor_dux'])}]\n"

    # ── Velocidad de stock por marca ──────────────────────────────────────────
    _velocidad_txt = ""
    if not df.empty and not _stk_r.empty:
        _df_vel = df[df["fecha_dia"] >= (hoy - timedelta(days=30))]
        _stk_marca = _stk_r[_stk_r["cantidad"] > 0].copy()
        _stk_marca["marca"] = _stk_marca["proveedor_dux"].map(MARCA_MAP_R2).fillna(_stk_marca["proveedor_dux"])
        _stock_x_marca = _stk_marca.groupby("marca").agg(stock=("cantidad","sum")).reset_index()

        _df_vel2 = _df_vel.copy()
        if "marca" in _df_vel2.columns:
            _venta_marca = _df_vel2.groupby("marca").agg(vendido=("cantidad","sum")).reset_index()
        else:
            _venta_marca = pd.DataFrame(columns=["marca","vendido"])

        _vel = _stock_x_marca.merge(_venta_marca, on="marca", how="left").fillna(0)
        _dias_periodo = max((hoy - (hoy - timedelta(days=30))).days, 1)
        for _, _rv2 in _vel.iterrows():
            _vel_dia = _rv2["vendido"] / _dias_periodo
            _dias_rest = int(_rv2["stock"] / _vel_dia) if _vel_dia > 0 else 999
            _velocidad_txt += f"  {_rv2['marca']}: {int(_rv2['stock'])} en stock, {int(_rv2['vendido'])} vendidos en 30d, {_vel_dia:.1f}/dia, quedan ~{_dias_rest} dias\n"

    reporte = f"""# REPORTE THE ROOM — {fmt_fecha(hoy, 'larga')}

## VENTAS ({fmt_fecha(hoy, 'mes')})
- Neto sin IVA: ${_venta_neta:,.0f}
- Con IVA: ${_venta_iva:,.0f}
- Dias con venta: {_dias_venta}
- Promedio diario: ${_prom_dia:,.0f}
- Objetivo diario: $300.000 → cumplimiento {_prom_dia/300000*100:.0f}%

## VENTAS DIARIAS (ultimos 30 dias)
{_ventas_dia_txt}
## TOP 10 PRODUCTOS MAS VENDIDOS (ultimos 30 dias)
{_top10_txt}
## RENTABILIDAD POR MARCA
{_rent_txt}
## VELOCIDAD DE STOCK POR MARCA (ultimos 30 dias)
{_velocidad_txt}
## BANCOS (al {_ult_b.get('fecha','—')})
- BBVA Frances: ${_ult_b.get('BBVA Frances',0):,.0f}
- Banco Corrientes: ${_ult_b.get('Banco Corrientes',0):,.0f}
- Galicia: ${_ult_b.get('Galicia',0):,.0f}
- Santander: ${_ult_b.get('Santander',0):,.0f}
- Mercado Pago: ${_ult_b.get('Mercado Pago',0):,.0f}
- Efectivo: ${_ult_b.get('Efectivo Caja',0):,.0f}
- DEUDA BANCARIA TOTAL: ${abs(_ult_b.get('BBVA Frances',0)) + abs(_ult_b.get('Banco Corrientes',0)) + abs(_ult_b.get('Galicia',0)):,.0f}
- DISPONIBLE: ${max(_ult_b.get('Santander',0),0) + max(_ult_b.get('Mercado Pago',0),0) + _ult_b.get('Efectivo Caja',0):,.0f}

## GASTOS {fmt_fecha(hoy, 'mes').upper()} (cargados)
{_gastos_txt}- TOTAL: ${sum(_gc.values()):,.0f}

## CHEQUES PENDIENTES
{_chq_txt}
## STOCK ACTUAL POR PRODUCTO
- Unidades en local: {_stock_uds}
- Valor a costo: ${_stock_val:,.0f}
- Valor estimado venta (x2.3): ${_stock_val * 2.3:,.0f}
{_stock_detalle_txt}
## PRODUCTOS SIN VENTA EN 15+ DIAS (muertos)
{_muertos_txt if _muertos_txt else "  Ningun producto con stock lleva 15+ dias sin venderse\n"}
## DEUDA PERSONAL (negocio le debe a Gustavo)
- Total: ${_deuda_total:,.0f}

## IVA
- Debito fiscal (21% ventas): ${_venta_neta * 0.21:,.0f}
- Credito fiscal (facturas cargadas): $0
- A pagar: ${_venta_neta * 0.21:,.0f}
- Para no pagar: comprar ${_venta_neta:,.0f} neto con factura A

## SITUACION GENERAL
- Resultado bruto mercaderia: ganancia de ${sum(r['gan'] for _, r in _pm.iterrows()) if '_pm' in dir() else 0:,.0f} (margen ~{(_pm['margen'].mean() if '_pm' in dir() else 0):.0f}%)
- Gastos fijos mensuales estimados: ~$7.000.000
- Break-even mensual: ~$15.900.000 neto
- Ventas actuales proyectadas al mes: ${_prom_dia * 26:,.0f}
- Deficit proyectado: ${max(7000000 - _prom_dia * 26, 0):,.0f}
"""

    st.markdown(f"""
    <div style="background:#1a1a2e;border:1px solid #3a86ff44;border-radius:16px;padding:24px;margin:16px 0">
        <div style="color:#3a86ff;font-weight:700;font-size:1.1rem;margin-bottom:12px">Reporte generado — copialo y pegalo en Claude</div>
    </div>""", unsafe_allow_html=True)

    st.code(reporte, language="markdown")

    st.download_button(
        label="Descargar como archivo .txt",
        data=reporte,
        file_name=f"reporte_theroom_{hoy.isoformat()}.txt",
        mime="text/plain",
        use_container_width=True,
    )

    if st.button("Volver al dashboard", use_container_width=True, key="btn_volver_rep"):
        st.session_state["mostrar_reporte"] = False
        st.rerun()

    st.stop()


# ── Tabs según permisos del rol ───────────────────────────────────────────────
_ALL_TABS = [
    ("📊  Resumen",         "Resumen"),
    ("📈  Resultados",      "Resultados"),
    ("📋  Movimientos",     "Movimientos"),
    ("⚠️  Inconsistencias", "Inconsistencias"),
    ("👕  Stock",           "Stock"),
    ("🧮  Simulador",       "Simulador"),
    ("💳  Cheques",         "Cheques"),
    ("💼  Deuda Personal",  "Deuda Personal"),
    ("🤖  Chat IA",        "Chat IA"),
    ("⚙️  Config",         "Config"),
]
_tabs_visibles = [(label, key) for label, key in _ALL_TABS if key in _permisos]
_tab_labels = [label for label, _ in _tabs_visibles]
_tab_keys   = [key for _, key in _tabs_visibles]

_tabs_obj = st.tabs(_tab_labels)
_tab_map = dict(zip(_tab_keys, _tabs_obj))

# Asignar variables para compatibilidad (None si no tiene permiso)
tab1 = _tab_map.get("Resumen")
tab2 = _tab_map.get("Resultados")
tab3 = _tab_map.get("Movimientos")
tab4 = _tab_map.get("Inconsistencias")
tab5 = _tab_map.get("Stock")
tab5b = _tab_map.get("Simulador")
tab6 = _tab_map.get("Cheques")
tab7 = _tab_map.get("Deuda Personal")
tab8 = _tab_map.get("Chat IA")
tab9 = _tab_map.get("Config")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RESUMEN
# ══════════════════════════════════════════════════════════════════════════════
if tab1:
  with tab1:

    # ── Selector de período ───────────────────────────────────────────────────
    import calendar as _cal
    col_per, _ = st.columns([2, 5])
    with col_per:
        periodo = st.selectbox(
            "Período",
            ["Hoy", "Últimos 2 días", "Últimos 7 días", "Últimos 15 días", "Este mes", "Últimos 30 días", "Últimos 60 días"],
            index=4, label_visibility="collapsed",
        )

    if periodo == "Este mes":
        fecha_desde = date(hoy.year, hoy.month, 1)
        fecha_hasta = hoy
        label_periodo = fmt_fecha(hoy, "mes")
    elif periodo == "Últimos 2 días":
        fecha_desde = hoy - timedelta(days=1)
        fecha_hasta = hoy
        label_periodo = "Últimos 2 días"
    elif periodo == "Últimos 7 días":
        fecha_desde = hoy - timedelta(days=6)
        fecha_hasta = hoy
        label_periodo = "Últimos 7 días"
    elif periodo == "Últimos 15 días":
        fecha_desde = hoy - timedelta(days=14)
        fecha_hasta = hoy
        label_periodo = "Últimos 15 días"
    elif periodo == "Últimos 30 días":
        fecha_desde = hoy - timedelta(days=30)
        fecha_hasta = hoy
        label_periodo = "Últimos 30 días"
    elif periodo == "Últimos 60 días":
        fecha_desde = hoy - timedelta(days=60)
        fecha_hasta = hoy
        label_periodo = "Últimos 60 días"
    else:
        fecha_desde = hoy
        fecha_hasta = hoy
        label_periodo = "Hoy"

    # Filtrar df por período
    if not sin_datos:
        df_per = df[(df["fecha_dia"] >= fecha_desde) & (df["fecha_dia"] <= fecha_hasta)]
    else:
        df_per = df

    # ── Alertas de cheques ────────────────────────────────────────────────────
    cheques_pend = [c for c in cheques if c["estado"] == "pendiente"]
    venc_urgente = [
        c for c in cheques_pend
        if c.get("tipo","emitido") == "emitido"
        and (date.fromisoformat(c["vencimiento"]) - hoy).days <= 7
    ]
    for c in venc_urgente:
        dias = (date.fromisoformat(c["vencimiento"]) - hoy).days
        alerta_html(
            f"Cheque {c['id']} — {c['proveedor']} — {fmt(c['monto'])} vence "
            f"{'HOY' if dias == 0 else f'en {dias} dia' + ('s' if dias != 1 else '')}",
            "roja"
        )

    bancos_data = get_bancos()
    seccion("Bancos — saldos actuales")
    if bancos_data:
        ult = bancos_data[-1]
        fecha_banco = ult.get("fecha", "—")
        frances   = ult.get("BBVA Frances", ult.get("BBVA", 0))
        bctes     = ult.get("Banco Corrientes", 0)
        galicia   = ult.get("Galicia", 0)
        santander = ult.get("Santander", 0)
        mp        = ult.get("Mercado Pago", 0)
        efectivo  = ult.get("Efectivo Caja", 0)
        descubierto = abs(min(frances, 0)) + abs(min(bctes, 0)) + abs(min(galicia, 0))
        disponible  = max(santander, 0) + max(mp, 0) + efectivo

        row_b1 = st.columns(4)
        with row_b1[0]:
            st.markdown(metric_card("🏦", "BBVA Frances", fmt(frances),
                f"descubierto", "rojo" if frances < 0 else "verde"), unsafe_allow_html=True)
        with row_b1[1]:
            st.markdown(metric_card("🏦", "Banco Corrientes", fmt(bctes),
                f"descubierto", "rojo" if bctes < 0 else "verde"), unsafe_allow_html=True)
        with row_b1[2]:
            st.markdown(metric_card("🏦", "Galicia", fmt(galicia),
                f"al {fecha_banco}", "rojo" if galicia < 0 else "verde"), unsafe_allow_html=True)
        with row_b1[3]:
            st.markdown(metric_card("🏦", "Santander", fmt(santander),
                f"al {fecha_banco}", "verde" if santander > 0 else "rojo"), unsafe_allow_html=True)
        row_b2 = st.columns(4)
        with row_b2[0]:
            st.markdown(metric_card("💳", "Mercado Pago", fmt(mp),
                f"al {fecha_banco}", "verde" if mp > 0 else "rojo"), unsafe_allow_html=True)
        # ── Control de caja automático ────────────────────────────────────
        _p_ctrl = Path("data/control_caja.json")
        _ctrl = json.loads(_p_ctrl.read_text(encoding="utf-8")) if _p_ctrl.exists() else {}
        _ajuste_base = _ctrl.get("ajuste_base", 0)
        _fecha_corte = _ctrl.get("fecha_corte", "2026-01-01")

        # Calcular efectivo esperado: ajuste + ventas efectivo Dux - gastos efectivo
        if not df.empty:
            _ef_dux = df[df["forma_pago"].astype(str).str.upper().str.contains("EFECT", na=False)]
            _efectivo_dux_total = _ef_dux["neto"].sum()
        else:
            _efectivo_dux_total = 0
        _gastos_efectivo = sum(
            g["monto"] for g in get_gastos()
            if g.get("medio", "").lower() in ("efectivo", "efectivo caja")
            and g["fecha"] >= _fecha_corte
        )
        _efectivo_esperado = _ajuste_base + _efectivo_dux_total - _gastos_efectivo

        # Mostrar el efectivo esperado (no el manual de bancos.json)
        with row_b2[1]:
            st.markdown(metric_card("💵", "EFECTIVO / CAJA", fmt(_efectivo_esperado),
                f"Ventas {fmt(_efectivo_dux_total)} - Gastos {fmt(_gastos_efectivo)}", "verde" if _efectivo_esperado > 0 else "gris"), unsafe_allow_html=True)

        # Recalcular disponible con el efectivo correcto
        disponible = max(santander, 0) + max(mp, 0) + _efectivo_esperado

        with row_b2[2]:
            st.markdown(metric_card("💰", "Disponible real", fmt(disponible),
                f"Santander + MP + Caja", "azul"), unsafe_allow_html=True)
        with row_b2[3]:
            st.markdown(metric_card("🔴", "Deuda total", fmt(-descubierto),
                f"BBVA + Corrientes + Galicia", "rojo"), unsafe_allow_html=True)

        # ── Cuadro de control de caja ────────────────────────────────────
        _ultimo_arqueo = _ctrl.get("arqueos", [])[-1] if _ctrl.get("arqueos") else None
        if _ultimo_arqueo:
            _fecha_arq = _ultimo_arqueo["fecha"]
            _real_arq = _ultimo_arqueo["efectivo_real"]
            _dif_actual = _efectivo_esperado - _real_arq if _efectivo_esperado != _real_arq else 0

            # Solo mostrar si hay ventas nuevas después del último arqueo
            _ventas_post_arqueo = 0
            if not df.empty:
                _fecha_arq_date = date.fromisoformat(_fecha_arq)
                _ef_post = _ef_dux[_ef_dux["fecha_dia"] > date.fromisoformat(_fecha_corte)]
                _ventas_post_arqueo = _ef_post["neto"].sum()

        with st.expander(f"🔍 Control de caja — último arqueo: {_ultimo_arqueo['fecha'] if _ultimo_arqueo else 'ninguno'}", expanded=False):
            st.markdown(
                f'<div style="background:#1a1a2e;padding:14px 18px;border-radius:8px;border:1px solid #ffffff10">'
                f'<div style="display:flex;gap:30px;flex-wrap:wrap">'
                f'<div><span style="color:#6666aa;font-size:0.75rem;text-transform:uppercase">Efectivo según Dux</span>'
                f'<div style="color:#eeeeff;font-size:1.2rem;font-weight:700">{fmt(_efectivo_dux_total)}</div></div>'
                f'<div><span style="color:#6666aa;font-size:0.75rem;text-transform:uppercase">Ajuste base (14/04)</span>'
                f'<div style="color:#f7b731;font-size:1.2rem;font-weight:700">{fmt(_ajuste_base)}</div></div>'
                f'<div><span style="color:#6666aa;font-size:0.75rem;text-transform:uppercase">Esperado en caja</span>'
                f'<div style="color:#00c96b;font-size:1.2rem;font-weight:700">{fmt(_efectivo_esperado)}</div></div>'
                f'</div>'
                f'<div style="margin-top:12px;color:#8888aa;font-size:0.78rem">'
                f'Cada vez que se sube un .xls nuevo, este número se actualiza automáticamente. '
                f'Si Gabriela cuenta la caja y no coincide → hay un problema.</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            # Input para nuevo arqueo
            st.markdown('<div style="margin-top:12px">', unsafe_allow_html=True)
            _arq_cols = st.columns([2, 2, 1])
            with _arq_cols[0]:
                _nuevo_real = st.number_input("Efectivo real en caja $", step=1000, value=0, key="arqueo_real")
            with _arq_cols[1]:
                _nota_arq = st.text_input("Nota (opcional)", key="arqueo_nota")
            with _arq_cols[2]:
                st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                if st.button("Registrar arqueo", key="btn_arqueo"):
                    if _nuevo_real > 0:
                        _dif_arq = _nuevo_real - _efectivo_esperado
                        _nuevo_arqueo = {
                            "fecha": hoy.isoformat(),
                            "efectivo_real": _nuevo_real,
                            "efectivo_dux": round(_efectivo_dux_total),
                            "esperado": round(_efectivo_esperado),
                            "diferencia": round(_dif_arq),
                            "nota": _nota_arq or ""
                        }
                        _ctrl["arqueos"].append(_nuevo_arqueo)
                        _save_json_and_sync(str(_p_ctrl), _ctrl, "Arqueo de caja desde dashboard")

                        if abs(_dif_arq) < 500:
                            st.success(f"Caja cuadra. Diferencia: ${_dif_arq:,.0f}")
                        elif _dif_arq < 0:
                            st.error(f"FALTANTE: {fmt(abs(_dif_arq))} — hay menos plata de la que debería")
                        else:
                            st.warning(f"SOBRANTE: {fmt(_dif_arq)} — hay más plata de la que debería")
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            # Historial de arqueos
            if _ctrl.get("arqueos") and len(_ctrl["arqueos"]) > 1:
                st.markdown(
                    '<div style="margin-top:16px;font-size:0.75rem;color:#6666aa;text-transform:uppercase;'
                    'letter-spacing:1px;font-weight:600">Historial de arqueos</div>',
                    unsafe_allow_html=True
                )
                _arq_html = ""
                for _a in reversed(_ctrl["arqueos"]):
                    _d = _a.get("diferencia", 0)
                    _col_d = "#00c96b" if abs(_d) < 500 else "#e94560" if _d < 0 else "#f7b731"
                    _arq_html += (
                        f'<tr>'
                        f'<td>{_a["fecha"]}</td>'
                        f'<td style="text-align:right">{fmt(_a["efectivo_real"])}</td>'
                        f'<td style="text-align:right">{fmt(_a.get("esperado", _a.get("efectivo_dux", 0)))}</td>'
                        f'<td style="text-align:right;color:{_col_d};font-weight:700">{fmt(_d)}</td>'
                        f'<td style="color:#8888aa">{_a.get("nota", "")}</td>'
                        f'</tr>'
                    )
                st.markdown(
                    f'<div class="tabla-wrapper"><table class="tabla-custom"><thead><tr>'
                    f'<th>Fecha</th><th style="text-align:right">Real</th>'
                    f'<th style="text-align:right">Esperado</th>'
                    f'<th style="text-align:right">Diferencia</th><th>Nota</th>'
                    f'</tr></thead><tbody>{_arq_html}</tbody></table></div>',
                    unsafe_allow_html=True
                )
    else:
        alerta_html("Sin datos bancarios — actualizalos en Config", "azul")

    # ── Ventas del período ────────────────────────────────────────────────────
    seccion(f"Ventas — {label_periodo}")

    if not sin_datos and not df_per.empty:
        datos_hoy_  = ventas_hoy(df)
        neto_per    = df_per["neto"].sum()
        uds_per     = int(df_per["cantidad"].sum())
        dias_per    = df_per["fecha_dia"].nunique()
        prom_dia    = neto_per / dias_per if dias_per else 0

        # Proyección solo para "Este mes"
        if periodo == "Este mes":
            dias_mes  = _cal.monthrange(hoy.year, hoy.month)[1]
            proy_per  = prom_dia * dias_mes
        else:
            proy_per  = None

        total_urgente = sum(c["monto"] for c in venc_urgente)

        if datos_hoy_["neto"] > 0 and datos_hoy_["neto"] < OBJETIVO_DIARIO * 0.67:
            alerta_html(f"Ventas de hoy ({fmt(datos_hoy_['neto'])}) por debajo del objetivo ({fmt(OBJETIVO_DIARIO)})","amarilla")
        if datos_hoy_["neto"] >= OBJETIVO_DIARIO:
            alerta_html(f"Objetivo del dia cumplido — {fmt(datos_hoy_['neto'])} vendidos","verde")

        # Totales con y sin IVA
        iva_per = df_per["total_con_iva"].sum() if "total_con_iva" in df_per.columns else neto_per * 1.21
        iva_hoy = df[df["fecha_dia"] == date.today()]["total_con_iva"].sum() if "total_con_iva" in df.columns else datos_hoy_["neto"] * 1.21

        col1,col2,col3,col4 = st.columns(4)
        delta_hoy = datos_hoy_["neto"] - OBJETIVO_DIARIO
        with col1:
            st.markdown(metric_card("💰","Ventas hoy",fmt(iva_hoy),
                f"Sin IVA: {fmt(datos_hoy_['neto'])} · {datos_hoy_['cantidad']} uds",
                "verde" if datos_hoy_["neto"]>=OBJETIVO_DIARIO else "rojo",
                f"{'↑' if delta_hoy>=0 else '↓'} {fmt(abs(delta_hoy))} vs objetivo",delta_hoy>=0),unsafe_allow_html=True)
        with col2:
            st.markdown(metric_card("📅",f"Ventas {label_periodo}",fmt(iva_per),
                f"Sin IVA: {fmt(neto_per)} · {uds_per} uds","azul"),unsafe_allow_html=True)
        with col3:
            if proy_per:
                proy_con_iva = proy_per * (iva_per / neto_per) if neto_per > 0 else proy_per * 1.21
                st.markdown(metric_card("📈","Proyeccion del mes",fmt(proy_con_iva),
                    f"Sin IVA: {fmt(proy_per)} · {fmt(prom_dia)}/dia","morado" if proy_per>=9_000_000 else "amarillo"),unsafe_allow_html=True)
            else:
                st.markdown(metric_card("📈","Promedio diario",fmt(prom_dia*1.21),
                    f"Sin IVA: {fmt(prom_dia)}/dia","morado"),unsafe_allow_html=True)
        with col4:
            cob = neto_per - total_urgente
            st.markdown(metric_card("🔴" if total_urgente>0 else "✅",
                "Cheques proximos 7 dias",
                fmt(total_urgente) if total_urgente else "Sin vencimientos",
                f"Cobertura: {fmt(neto_per)} sin IVA",
                "rojo" if cob<0 else "verde",
                f"{'Deficit' if cob<0 else 'Superavit'} {fmt(abs(cob))}",cob>=0),unsafe_allow_html=True)

        # ── BLOQUE GRANDE: Resultado del período ──────────────────────────────
        gastos_data   = get_gastos()
        gastos_per    = [g for g in gastos_data
                         if date.fromisoformat(g["fecha"]) >= fecha_desde
                         and date.fromisoformat(g["fecha"]) <= fecha_hasta]
        total_gv      = sum(g["monto"] for g in gastos_per)
        GASTOS_FIJOS  = 7_000_000
        # Gastos fijos proporcionales al período
        dias_totales_per = (fecha_hasta - fecha_desde).days + 1
        gf_proporcional  = round(GASTOS_FIJOS / 30 * dias_totales_per)
        total_gastos_per = gf_proporcional + total_gv
        resultado        = neto_per - total_gastos_per
        pct_cubierto     = min(neto_per / total_gastos_per * 100, 100) if total_gastos_per else 0
        color_res        = "#00c96b" if resultado >= 0 else "#e94560"
        color_pct        = "#00c96b" if pct_cubierto >= 100 else "#f7b731" if pct_cubierto >= 70 else "#e94560"

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);
                    border:1px solid #ffffff12;border-radius:16px;
                    padding:28px 32px;margin:20px 0;position:relative;overflow:hidden">
            <div style="font-size:0.72rem;color:#6666aa;text-transform:uppercase;
                        letter-spacing:1.5px;margin-bottom:6px">
                Resultado del periodo — {label_periodo}
            </div>
            <div style="display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:20px">
                <div>
                    <div style="font-size:2.8rem;font-weight:900;color:{color_res};
                                letter-spacing:-2px;line-height:1">
                        {fmt(resultado)}
                    </div>
                    <div style="font-size:0.85rem;color:#8888aa;margin-top:4px">
                        {'Ganancia' if resultado>=0 else 'Perdida'} del periodo
                    </div>
                </div>
                <div style="flex:1;min-width:200px">
                    <div style="display:flex;justify-content:space-between;
                                font-size:0.78rem;color:#8888aa;margin-bottom:6px">
                        <span>Gastos cubiertos</span>
                        <span style="color:{color_pct};font-weight:700">{pct_cubierto:.0f}%</span>
                    </div>
                    <div style="background:rgba(255,255,255,0.06);border-radius:6px;height:10px;overflow:hidden">
                        <div style="width:{pct_cubierto:.0f}%;height:100%;
                                    background:linear-gradient(90deg,{color_pct},{color_pct}99);
                                    border-radius:6px;transition:width 0.5s"></div>
                    </div>
                    <div style="display:flex;justify-content:space-between;
                                font-size:0.72rem;color:#555577;margin-top:4px">
                        <span>$0</span><span>{fmt(total_gastos_per)}</span>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Gráfico ───────────────────────────────────────────────────────────
        vxd = ventas_por_dia(df_per)
        vxd["fecha_dia"] = pd.to_datetime(vxd["fecha_dia"])
        if "con_iva" not in vxd.columns:
            vxd["con_iva"] = vxd["neto"] * 1.21
        if not vxd.empty:
            colores_barras = [
                "#00c96b" if v >= OBJETIVO_DIARIO
                else "#f7b731" if v >= OBJETIVO_DIARIO * 0.67
                else "#e94560" for v in vxd["neto"]
            ]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=vxd["fecha_dia"], y=vxd["con_iva"],
                marker_color=colores_barras,
                text=[fmt(v) for v in vxd["con_iva"]],
                textposition="outside",
                textfont=dict(size=9, color="#aaaacc"),
                hovertemplate="<b>%{x|%d/%m}</b><br>Con IVA: %{text}<br>Sin IVA: $%{customdata:,.0f}<extra></extra>",
                customdata=vxd["neto"],
            ))
            fig.add_hline(y=OBJETIVO_DIARIO, line_dash="dot", line_color="#3a86ff",
                line_width=1.5,
                annotation_text=f"Objetivo {fmt(OBJETIVO_DIARIO)}",
                annotation_font_color="#3a86ff", annotation_font_size=11,
                annotation_position="top right",
            )
            if proy_per:
                fig.add_hline(y=proy_per / dias_mes if dias_mes else 0,
                    line_dash="dot", line_color="#8b5cf6", line_width=1,
                    annotation_text=f"Promedio actual {fmt(prom_dia)}/dia",
                    annotation_font_color="#8b5cf6", annotation_font_size=10,
                    annotation_position="bottom right",
                )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1a1a2e",
                font=dict(family="Inter", color="#888899", size=11),
                height=300, margin=dict(t=30, b=10, l=50, r=20),
                xaxis=dict(showgrid=False, tickformat="%d/%m",
                           linecolor="rgba(255,255,255,0.06)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickformat="$,.0f", linecolor="rgba(255,255,255,0.06)"),
                bargap=0.25,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    else:
        alerta_html("Sin datos de ventas — subi el .xls de Dux en la pestana Config","azul")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RESULTADOS (ventas vs gastos)
# ══════════════════════════════════════════════════════════════════════════════
if tab2:
  with tab2:
    import calendar as _cal2

    GASTOS_FIJOS_MES = 7_000_000

    if sin_datos:
        alerta_html("Subi el .xls de Dux para ver los resultados detallados", "azul")
    else:
        # ── Datos del mes actual ──────────────────────────────────────────────
        mes_inicio  = date(hoy.year, hoy.month, 1)
        dias_mes_t  = _cal2.monthrange(hoy.year, hoy.month)[1]
        dias_trans  = (hoy - mes_inicio).days + 1

        df_mes = df[(df["fecha_dia"] >= mes_inicio) & (df["fecha_dia"] <= hoy)]
        venta_acum  = df_mes["neto"].sum()
        venta_acum_iva = df_mes["total_con_iva"].sum() if "total_con_iva" in df_mes.columns else venta_acum * 1.21
        gasto_acum  = round(GASTOS_FIJOS_MES / dias_mes_t * dias_trans)
        gastos_extra = sum(
            g["monto"] for g in get_gastos()
            if date.fromisoformat(g["fecha"]) >= mes_inicio
            and date.fromisoformat(g["fecha"]) <= hoy
        )
        gasto_total_acum = gasto_acum + gastos_extra
        resultado_acum   = venta_acum_iva - gasto_total_acum
        proy_venta_mes   = (venta_acum_iva / dias_trans * dias_mes_t) if dias_trans > 0 else 0
        proy_venta_neto  = (venta_acum / dias_trans * dias_mes_t) if dias_trans > 0 else 0
        gasto_mes_total  = GASTOS_FIJOS_MES + sum(
            g["monto"] for g in get_gastos()
            if date.fromisoformat(g["fecha"]).month == hoy.month
            and date.fromisoformat(g["fecha"]).year == hoy.year
        )
        resultado_proy   = proy_venta_mes - gasto_mes_total
        pct_acum         = min(venta_acum / gasto_total_acum * 100, 100) if gasto_total_acum else 0
        color_res        = "#00c96b" if resultado_acum >= 0 else "#e94560"

        # ── KPIs del mes ─────────────────────────────────────────────────────
        seccion(f"Como va {fmt_fecha(hoy, 'mes')} — dia {dias_trans} de {dias_mes_t}")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(metric_card("💰","Ventas acumuladas",fmt(venta_acum_iva),
                f"Sin IVA: {fmt(venta_acum)} · {dias_trans} dias","verde"), unsafe_allow_html=True)
        with c2:
            st.markdown(metric_card("💸","Gastos acumulados",fmt(gasto_total_acum),
                f"Fijos {fmt(gasto_acum)} + extras {fmt(gastos_extra)}","rojo"), unsafe_allow_html=True)
        with c3:
            col_r = "verde" if resultado_acum >= 0 else "rojo"
            st.markdown(metric_card("📊","Resultado hasta hoy",fmt(resultado_acum),
                f"Con IVA · {'Ganancia' if resultado_acum >= 0 else 'Perdida'}",col_r), unsafe_allow_html=True)
        with c4:
            col_p = "verde" if resultado_proy >= 0 else "amarillo" if resultado_proy >= -1_000_000 else "rojo"
            st.markdown(metric_card("📈","Proyeccion fin de mes",fmt(proy_venta_mes),
                f"Sin IVA: {fmt(proy_venta_neto)} · Resultado {fmt(resultado_proy)}",col_p), unsafe_allow_html=True)

        # Barra de progreso: ventas vs gastos del mes
        st.markdown(f"""
        <div style="background:#1a1a2e;border:1px solid #ffffff0e;border-radius:14px;padding:20px 24px;margin:8px 0 20px 0">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px">
                <span style="color:#8888aa;font-size:0.82rem">Gastos cubiertos al dia {dias_trans}</span>
                <span style="font-size:0.9rem;font-weight:700;color:{color_res}">{pct_acum:.0f}%</span>
            </div>
            <div style="background:rgba(255,255,255,0.06);border-radius:6px;height:12px;overflow:hidden">
                <div style="width:{pct_acum:.0f}%;height:100%;background:linear-gradient(90deg,{color_res},{color_res}99);border-radius:6px"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:0.75rem;color:#555577">
                <span>$0</span>
                <span style="color:#e94560">Gastos: {fmt(gasto_total_acum)}</span>
                <span style="color:#00c96b">Ventas: {fmt(venta_acum)}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Break-even ────────────────────────────────────────────────────────
        falta_be = max(gasto_mes_total - venta_acum, 0)
        dias_restantes = max(dias_mes_t - dias_trans, 1)
        venta_diaria_be = falta_be / dias_restantes if falta_be > 0 else 0

        if falta_be > 0:
            st.markdown(f"""
            <div style="background:#e9456012;border:1px solid #e9456033;border-radius:12px;padding:16px 20px;margin:8px 0 16px 0">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
                    <div>
                        <div style="color:#ff8fa3;font-weight:700;font-size:0.9rem">Para llegar al break-even falta vender {fmt(falta_be)}</div>
                        <div style="color:#8888aa;font-size:0.82rem;margin-top:4px">Necesitas {fmt(venta_diaria_be)}/dia los proximos {dias_restantes} dias (gastos mes: {fmt(gasto_mes_total)})</div>
                    </div>
                    <div style="text-align:right">
                        <div style="font-size:0.72rem;color:#666688">Objetivo diario para empatar</div>
                        <div style="font-size:1.4rem;font-weight:800;color:#f7b731">{fmt(venta_diaria_be)}</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#00c96b12;border:1px solid #00c96b33;border-radius:12px;padding:16px 20px;margin:8px 0 16px 0">
                <div style="color:#6effc4;font-weight:700;font-size:0.9rem">Break-even alcanzado — las ventas cubren los gastos del mes</div>
            </div>""", unsafe_allow_html=True)

        # ── Destino de pagos ─────────────────────────────────────────────────
        seccion("A donde fue la plata — por medio de pago")

        if "forma_pago" in df_mes.columns:
            fp = df_mes["forma_pago"].astype(str).str.upper()

            def _suma_fp(mask_fp):
                sub_fp = df_mes[mask_fp]
                neto   = sub_fp["neto"].sum()
                c_iva  = sub_fp["total_con_iva"].sum() if "total_con_iva" in sub_fp.columns else neto * 1.21
                cant   = int(sub_fp["cantidad"].sum())
                return neto, c_iva, cant

            mask_san = fp.str.contains("SANTANDER", na=False)
            mask_mp  = fp.str.contains("MERCADO PAGO", na=False)
            mask_ef  = fp.str.contains("EFECTIVO", na=False)
            mask_oth = ~mask_san & ~mask_mp & ~mask_ef

            destinos = [
                ("🏦 Santander",      mask_san, "#3a86ff"),
                ("📱 Mercado Pago",   mask_mp,  "#00c96b"),
                ("💵 Efectivo / Caja",mask_ef,  "#f7b731"),
                ("🔄 Otros",          mask_oth, "#8b5cf6"),
            ]

            # Solo mostrar los que tienen plata
            destinos_con_dato = [(n, m, c) for n, m, c in destinos if df_mes[m]["neto"].sum() > 0]

            if destinos_con_dato:
                cols_fp = st.columns(len(destinos_con_dato))
                for i, (nombre, mask, color) in enumerate(destinos_con_dato):
                    neto_fp, iva_fp, cant_fp = _suma_fp(mask)
                    pct_fp = neto_fp / venta_acum * 100 if venta_acum > 0 else 0
                    with cols_fp[i]:
                        st.markdown(f"""
                        <div style="background:#1a1a2e;border:1px solid {color}44;border-radius:14px;
                                    padding:18px 20px;margin-bottom:12px;border-left:4px solid {color}">
                            <div style="font-size:0.78rem;color:#8888aa;margin-bottom:4px">{nombre}</div>
                            <div style="font-size:1.25rem;font-weight:800;color:{color}">{fmt(iva_fp)}</div>
                            <div style="font-size:0.72rem;color:#666688;margin-top:4px">
                                Sin IVA: {fmt(neto_fp)}<br>
                                {cant_fp} uds · {pct_fp:.0f}% del total
                            </div>
                            <div style="background:rgba(255,255,255,0.05);border-radius:4px;height:4px;margin-top:10px;overflow:hidden">
                                <div style="width:{pct_fp:.0f}%;height:100%;background:{color};border-radius:4px"></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                # Tabla de formas de pago sin categorizar (debug / detalle)
                with st.expander("Ver detalle de formas de pago"):
                    _agg_fp = {"neto": ("neto","sum"), "cantidad": ("cantidad","sum")}
                    if "total_con_iva" in df_mes.columns:
                        _agg_fp["con_iva"] = ("total_con_iva","sum")
                    detalle_fp = (
                        df_mes.groupby("forma_pago")
                        .agg(**_agg_fp)
                        .reset_index()
                        .sort_values("neto", ascending=False)
                    )
                    if "con_iva" not in detalle_fp.columns:
                        detalle_fp["con_iva"] = detalle_fp["neto"] * 1.21
                    rows_fp = ""
                    for _, r in detalle_fp.iterrows():
                        rows_fp += (
                            f'<tr><td style="font-size:0.78rem">{r["forma_pago"]}</td>'
                            f'<td style="color:#3a86ff;font-weight:700">{fmt(r["con_iva"])}</td>'
                            f'<td style="color:#8888aa">{fmt(r["neto"])}</td>'
                            f'<td style="color:#8888aa">{int(r["cantidad"])} uds</td></tr>'
                        )
                    st.markdown(
                        f'<div class="tabla-wrapper"><table class="tabla-custom">'
                        f'<thead><tr><th>Forma de pago</th><th>Neto</th><th>Uds</th></tr></thead>'
                        f'<tbody>{rows_fp}</tbody></table></div>',
                        unsafe_allow_html=True
                    )
            else:
                st.info("Sin datos de forma de pago en el periodo.")
        else:
            st.info("Carga el .xls de Dux para ver el destino de pagos.")

        # ── Grafico: ventas diarias vs gastos diarios acumulados ─────────────
        seccion("Ventas diarias vs gastos proporcionales")

        vxd_all = ventas_por_dia(df_mes)
        if not vxd_all.empty:
            vxd_all = vxd_all.sort_values("fecha_dia").copy()
            # Rellenar días sin ventas con 0 (desde el primer día del mes hasta hoy)
            rango_dias = pd.date_range(
                start=date(hoy.year, hoy.month, 1),
                end=hoy, freq="D"
            ).date
            vxd_all = (
                vxd_all.set_index("fecha_dia")
                .reindex(rango_dias, fill_value=0)
                .reset_index()
                .rename(columns={"index": "fecha_dia"})
            )
            gasto_x_dia = GASTOS_FIJOS_MES / dias_mes_t
            vxd_all["gasto_dia"] = gasto_x_dia
            if "con_iva" not in vxd_all.columns:
                vxd_all["con_iva"] = vxd_all["neto"] * 1.21
            vxd_all["venta_acum"] = vxd_all["con_iva"].cumsum()
            vxd_all["venta_acum_neto"] = vxd_all["neto"].cumsum()
            vxd_all["gasto_acum"] = [gasto_x_dia * (i+1) for i in range(len(vxd_all))]
            vxd_all["fecha_dt"]   = pd.to_datetime(vxd_all["fecha_dia"])

            fig2 = go.Figure()
            # Barras de ventas diarias (con IVA — plata real que entra)
            colores_v = [
                "#00c96b" if v >= OBJETIVO_DIARIO else
                "#f7b731" if v >= OBJETIVO_DIARIO * 0.67 else
                "#e94560" for v in vxd_all["neto"]
            ]
            fig2.add_trace(go.Bar(
                x=vxd_all["fecha_dt"], y=vxd_all["con_iva"],
                name="Venta con IVA",
                marker_color=colores_v,
                text=[f"{fmt(ci)}" for ci, n in zip(vxd_all["con_iva"], vxd_all["neto"])],
                textposition="outside",
                textfont=dict(size=8, color="#aaaacc"),
                hovertemplate="<b>%{x|%d/%m}</b><br>Con IVA: %{text}<br>Sin IVA: $%{customdata:,.0f}<extra></extra>",
                customdata=vxd_all["neto"],
                yaxis="y",
            ))
            # Linea acumulado ventas con IVA
            fig2.add_trace(go.Scatter(
                x=vxd_all["fecha_dt"], y=vxd_all["venta_acum"],
                name="Acum con IVA",
                line=dict(color="#00c96b", width=2, dash="solid"),
                hovertemplate="<b>%{x|%d/%m}</b><br>Acum con IVA: $%{y:,.0f}<br>Acum sin IVA: $%{customdata:,.0f}<extra></extra>",
                customdata=vxd_all["venta_acum_neto"],
                yaxis="y2",
            ))
            # Linea acumulado gastos
            fig2.add_trace(go.Scatter(
                x=vxd_all["fecha_dt"], y=vxd_all["gasto_acum"],
                name="Gastos acumulados",
                line=dict(color="#e94560", width=2, dash="dot"),
                hovertemplate="<b>%{x|%d/%m}</b><br>Acum gastos: $%{y:,.0f}<extra></extra>",
                yaxis="y2",
            ))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1a1a2e",
                font=dict(family="Inter", color="#888899", size=11),
                height=360,
                margin=dict(t=30, b=10, l=60, r=60),
                legend=dict(orientation="h", y=1.08, x=0,
                            bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
                xaxis=dict(showgrid=False, tickformat="%d/%m",
                           linecolor="rgba(255,255,255,0.06)"),
                yaxis=dict(title="Venta diaria", showgrid=True,
                           gridcolor="rgba(255,255,255,0.04)",
                           tickformat="$,.0f",
                           linecolor="rgba(255,255,255,0.06)"),
                yaxis2=dict(title="Acumulado", overlaying="y", side="right",
                            showgrid=False, tickformat="$,.0f",
                            linecolor="rgba(255,255,255,0.06)"),
                bargap=0.3,
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

        # ── Resumen mensual historico ─────────────────────────────────────────
        seccion("Historico mensual — ventas vs gastos")

        meses_hist = df.groupby(["anio","mes"]).agg(
            neto=("neto","sum"), cantidad=("cantidad","sum")
        ).reset_index().sort_values(["anio","mes"])

        if not meses_hist.empty:
            meses_hist["label"] = meses_hist.apply(
                lambda r: date(int(r["anio"]), int(r["mes"]), 1).strftime("%b %Y"), axis=1
            )
            meses_hist["gasto_est"] = GASTOS_FIJOS_MES
            meses_hist["resultado"] = meses_hist["neto"] - meses_hist["gasto_est"]
            meses_hist["color_r"]   = meses_hist["resultado"].apply(
                lambda v: "#00c96b" if v >= 0 else "#e94560"
            )

            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=meses_hist["label"], y=meses_hist["neto"],
                name="Ventas netas", marker_color="#3a86ff",
                hovertemplate="<b>%{x}</b><br>Ventas: $%{y:,.0f}<extra></extra>",
            ))
            fig3.add_trace(go.Bar(
                x=meses_hist["label"], y=meses_hist["gasto_est"],
                name="Gastos estimados", marker_color="#e94560",
                opacity=0.6,
                hovertemplate="<b>%{x}</b><br>Gastos: $%{y:,.0f}<extra></extra>",
            ))
            fig3.add_trace(go.Scatter(
                x=meses_hist["label"], y=meses_hist["resultado"],
                name="Resultado",
                mode="lines+markers",
                line=dict(color="#f7b731", width=2),
                marker=dict(size=7, color=meses_hist["color_r"].tolist()),
                hovertemplate="<b>%{x}</b><br>Resultado: $%{y:,.0f}<extra></extra>",
                yaxis="y",
            ))
            fig3.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1a1a2e",
                font=dict(family="Inter", color="#888899", size=11),
                height=320,
                margin=dict(t=30, b=10, l=60, r=20),
                barmode="group",
                legend=dict(orientation="h", y=1.08, x=0,
                            bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
                xaxis=dict(showgrid=False, linecolor="rgba(255,255,255,0.06)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickformat="$,.0f", linecolor="rgba(255,255,255,0.06)"),
                bargap=0.2, bargroupgap=0.1,
            )
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

            # Tabla resumen por mes
            rows_m = ""
            for _, r in meses_hist.iterrows():
                res = r["resultado"]
                col_r2 = "#00c96b" if res >= 0 else "#e94560"
                rows_m += (
                    f'<tr><td>{r["label"]}</td>'
                    f'<td style="color:#3a86ff;font-weight:700">{fmt(r["neto"])}</td>'
                    f'<td style="color:#e94560">{fmt(r["gasto_est"])}</td>'
                    f'<td style="color:{col_r2};font-weight:700">{fmt(res)}</td>'
                    f'<td style="color:#8888aa">{int(r["cantidad"])} uds</td></tr>'
                )
            st.markdown(
                f'<div class="tabla-wrapper"><table class="tabla-custom">'
                f'<thead><tr><th>Mes</th><th>Ventas</th><th>Gastos est.</th>'
                f'<th>Resultado</th><th>Unidades</th></tr></thead>'
                f'<tbody>{rows_m}</tbody></table></div>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MOVIMIENTOS (ventas + gastos)
# ══════════════════════════════════════════════════════════════════════════════
if tab3:
  with tab3:
    seccion("Todos los movimientos — ventas y gastos")

    # ── Filtros ───────────────────────────────────────────────────────────────
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1, 1, 1])
    filtro_tipo = f1.selectbox("Tipo", ["Todos", "Ventas", "Gastos"], key="mov_tipo")
    filtro_periodo = f2.selectbox("Período", [
        "Hoy", "Ayer", "Últimos 7 días", "Últimos 15 días", "Últimos 30 días",
        "Este mes", "Mes anterior", "Elegir día", "Todo"
    ], index=5, key="mov_periodo")
    filtro_medio = f3.selectbox("Medio / Banco", ["Todos", "Efectivo", "Mercado Pago", "Santander", "BBVA Frances", "Banco Corrientes", "Online"], key="mov_medio")
    filtro_comparar = f4.selectbox("Comparar con", [
        "Ningún período", "Período anterior", "Mes anterior", "Año anterior"
    ], key="mov_comparar")
    if filtro_periodo == "Elegir día":
        filtro_dia = f5.date_input("Día", value=hoy, key="mov_dia_especifico")
    else:
        f5.markdown("<div style='height:52px'></div>", unsafe_allow_html=True)

    # ── Construir lista unificada ─────────────────────────────────────────────
    movimientos_all = []

    # VENTAS desde Dux
    if not sin_datos:
        for _, rv in df.iterrows():
            fecha_v = rv["fecha_dia"] if hasattr(rv["fecha_dia"], "isoformat") else rv["fecha_dia"]
            fp = str(rv.get("forma_pago", "")).strip()
            canal = str(rv.get("canal", "Físico"))
            medio_v = "Online" if canal == "Online" else (
                "Mercado Pago" if "MERCADO" in fp.upper() else
                "Santander" if "SANTANDER" in fp.upper() else
                "Efectivo" if "EFECTIVO" in fp.upper() else
                fp if fp else "Físico"
            )
            movimientos_all.append({
                "fecha": str(fecha_v),
                "tipo": "VENTA",
                "concepto": str(rv.get("producto", "")),
                "monto": float(rv.get("neto", 0)),
                "con_iva": float(rv.get("total_con_iva", 0)),
                "medio": medio_v,
                "categoria": str(rv.get("rubro", "")),
                "cantidad": int(rv.get("cantidad", 0)),
            })

    # GASTOS desde gastos.json
    for g in get_gastos():
        movimientos_all.append({
            "fecha": g["fecha"],
            "tipo": "GASTO",
            "concepto": g["concepto"],
            "monto": -abs(g["monto"]),
            "medio": g.get("medio", "—"),
            "categoria": g.get("categoria", "Otros"),
            "cantidad": 0,
        })

    if not movimientos_all:
        alerta_html("Sin movimientos — subi el .xls de Dux y/o carga gastos", "azul")
    else:
        df_mov = pd.DataFrame(movimientos_all)
        df_mov["fecha"] = pd.to_datetime(df_mov["fecha"], errors="coerce")
        df_mov = df_mov.dropna(subset=["fecha"])
        df_mov["mes"] = df_mov["fecha"].dt.month
        df_mov["anio"] = df_mov["fecha"].dt.year

        # Aplicar filtros
        if filtro_tipo == "Ventas":
            df_mov = df_mov[df_mov["tipo"] == "VENTA"]
        elif filtro_tipo == "Gastos":
            df_mov = df_mov[df_mov["tipo"] == "GASTO"]

        # Filtro de período
        _hoy_ts = pd.Timestamp(hoy)
        if filtro_periodo == "Hoy":
            df_mov = df_mov[df_mov["fecha"].dt.date == hoy]
        elif filtro_periodo == "Ayer":
            df_mov = df_mov[df_mov["fecha"].dt.date == (hoy - timedelta(days=1))]
        elif filtro_periodo == "Últimos 7 días":
            df_mov = df_mov[df_mov["fecha"] >= _hoy_ts - pd.Timedelta(days=7)]
        elif filtro_periodo == "Últimos 15 días":
            df_mov = df_mov[df_mov["fecha"] >= _hoy_ts - pd.Timedelta(days=15)]
        elif filtro_periodo == "Últimos 30 días":
            df_mov = df_mov[df_mov["fecha"] >= _hoy_ts - pd.Timedelta(days=30)]
        elif filtro_periodo == "Este mes":
            df_mov = df_mov[(df_mov["mes"] == hoy.month) & (df_mov["anio"] == hoy.year)]
        elif filtro_periodo == "Mes anterior":
            _mes_ant = hoy.month - 1 if hoy.month > 1 else 12
            _anio_ant = hoy.year if hoy.month > 1 else hoy.year - 1
            df_mov = df_mov[(df_mov["mes"] == _mes_ant) & (df_mov["anio"] == _anio_ant)]
        elif filtro_periodo == "Elegir día":
            df_mov = df_mov[df_mov["fecha"].dt.date == filtro_dia]
        # "Todo" no filtra nada

        if filtro_medio != "Todos":
            df_mov = df_mov[df_mov["medio"].str.contains(filtro_medio, case=False, na=False)]

        df_mov = df_mov.sort_values("fecha", ascending=False)

        # ── KPIs ──────────────────────────────────────────────────────────────
        total_ventas = df_mov[df_mov["tipo"] == "VENTA"]["monto"].sum()
        total_gastos = abs(df_mov[df_mov["tipo"] == "GASTO"]["monto"].sum())
        resultado_mov = total_ventas - total_gastos
        ventas_iva  = df_mov[df_mov["tipo"] == "VENTA"]["con_iva"].sum() if "con_iva" in df_mov.columns else total_ventas * 1.21
        resultado_iva = ventas_iva - total_gastos
        iva_a_pagar = ventas_iva - total_ventas

        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.markdown(metric_card("💰", "Ventas", fmt(ventas_iva),
                f"Sin IVA: {fmt(total_ventas)}", "verde"), unsafe_allow_html=True)
        with k2:
            st.markdown(metric_card("💸", "Gastos", fmt(-total_gastos),
                f"{len(df_mov[df_mov['tipo']=='GASTO'])} movimientos", "rojo"), unsafe_allow_html=True)
        with k3:
            col_r = "verde" if resultado_iva >= 0 else "rojo"
            st.markdown(metric_card("📊", "Resultado con IVA", fmt(resultado_iva),
                f"Sin IVA: {fmt(resultado_mov)}", col_r), unsafe_allow_html=True)
        with k4:
            st.markdown(metric_card("🧾", "IVA a pagar", fmt(iva_a_pagar),
                "21% sobre ventas netas", "amarillo"), unsafe_allow_html=True)
        with k5:
            st.markdown(metric_card("📋", "Movimientos", str(len(df_mov)),
                "en el periodo", "azul"), unsafe_allow_html=True)

        # ── Calcular período de comparación ──────────────────────────────────
        _fecha_min = df_mov["fecha"].min()
        _fecha_max = df_mov["fecha"].max()
        _dias_periodo = max((_fecha_max - _fecha_min).days, 1) if len(df_mov) > 0 else 1
        df_comp = pd.DataFrame()
        _tiene_comp = False

        if filtro_comparar != "Ningún período" and len(df_mov) > 0:
            # Reconstruir movimientos completos (sin filtro de tipo/medio)
            _mov_all_raw = pd.DataFrame(movimientos_all)
            _mov_all_raw["fecha"] = pd.to_datetime(_mov_all_raw["fecha"], errors="coerce")
            _mov_all_raw = _mov_all_raw.dropna(subset=["fecha"])

            if filtro_comparar == "Período anterior":
                _comp_hasta = _fecha_min - pd.Timedelta(days=1)
                _comp_desde = _comp_hasta - pd.Timedelta(days=_dias_periodo)
            elif filtro_comparar == "Mes anterior":
                _mes_c = _fecha_min.month - 1 if _fecha_min.month > 1 else 12
                _anio_c = _fecha_min.year if _fecha_min.month > 1 else _fecha_min.year - 1
                _comp_desde = pd.Timestamp(date(_anio_c, _mes_c, 1))
                import calendar
                _ult_dia_c = calendar.monthrange(_anio_c, _mes_c)[1]
                _comp_hasta = pd.Timestamp(date(_anio_c, _mes_c, _ult_dia_c))
            elif filtro_comparar == "Año anterior":
                _comp_desde = _fecha_min - pd.DateOffset(years=1)
                _comp_hasta = _fecha_max - pd.DateOffset(years=1)

            df_comp = _mov_all_raw[
                (_mov_all_raw["fecha"] >= _comp_desde) & (_mov_all_raw["fecha"] <= _comp_hasta)
            ].copy()
            if filtro_tipo == "Ventas":
                df_comp = df_comp[df_comp["tipo"] == "VENTA"]
            elif filtro_tipo == "Gastos":
                df_comp = df_comp[df_comp["tipo"] == "GASTO"]
            if filtro_medio != "Todos":
                df_comp = df_comp[df_comp["medio"].str.contains(filtro_medio, case=False, na=False)]
            _tiene_comp = len(df_comp) > 0

        def _pct_cambio(actual, anterior):
            if anterior == 0:
                return ""
            pct = ((actual - anterior) / abs(anterior)) * 100
            color = "#00c96b" if pct >= 0 else "#e94560"
            signo = "+" if pct >= 0 else ""
            return f'<span style="color:{color};font-size:0.82rem;font-weight:700"> {signo}{pct:.0f}%</span>'

        # ── REPORTE DE VENTAS ─────────────────────────────────────────────────
        seccion("Reporte de ventas")
        _ventas_per = df_mov[df_mov["tipo"] == "VENTA"].copy()
        if not _ventas_per.empty:
            _total_vr = _ventas_per["monto"].sum()
            _cant_vr = len(_ventas_per)
            _ticket_vr = _total_vr / _cant_vr if _cant_vr else 0
            _uds_vr = int(_ventas_per["cantidad"].sum()) if "cantidad" in _ventas_per.columns else 0

            # Comparación ventas
            _comp_v_txt = ""
            _comp_t_txt = ""
            _comp_u_txt = ""
            if _tiene_comp:
                _vc = df_comp[df_comp["tipo"] == "VENTA"]
                _comp_v_txt = _pct_cambio(_total_vr, _vc["monto"].sum())
                _comp_t_txt = _pct_cambio(_ticket_vr, _vc["monto"].sum() / len(_vc) if len(_vc) else 0)
                _comp_u_txt = _pct_cambio(_cant_vr, len(_vc))

            rv1, rv2, rv3 = st.columns(3)
            with rv1:
                st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #00c96b33;border-radius:14px;padding:20px;border-left:4px solid #00c96b">
                    <div style="font-size:0.75rem;color:#00c96b;font-weight:700;text-transform:uppercase">Volumen de ventas</div>
                    <div style="font-size:1.8rem;font-weight:800;color:#eee;margin:6px 0">{fmt(_total_vr)} {_comp_v_txt}</div>
                    <div style="font-size:0.78rem;color:#8888aa">Sin IVA · {_cant_vr} operaciones</div>
                </div>''', unsafe_allow_html=True)
            with rv2:
                st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #3a86ff33;border-radius:14px;padding:20px;border-left:4px solid #3a86ff">
                    <div style="font-size:0.75rem;color:#3a86ff;font-weight:700;text-transform:uppercase">Ticket promedio</div>
                    <div style="font-size:1.8rem;font-weight:800;color:#eee;margin:6px 0">{fmt(_ticket_vr)} {_comp_t_txt}</div>
                    <div style="font-size:0.78rem;color:#8888aa">Por operación</div>
                </div>''', unsafe_allow_html=True)
            with rv3:
                st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #8b5cf633;border-radius:14px;padding:20px;border-left:4px solid #8b5cf6">
                    <div style="font-size:0.75rem;color:#8b5cf6;font-weight:700;text-transform:uppercase">Unidades vendidas</div>
                    <div style="font-size:1.8rem;font-weight:800;color:#eee;margin:6px 0">{_uds_vr} {_comp_u_txt}</div>
                    <div style="font-size:0.78rem;color:#8888aa">{_cant_vr} ventas</div>
                </div>''', unsafe_allow_html=True)

            # Gráfico diario de ventas
            _v_dia = _ventas_per.groupby(_ventas_per["fecha"].dt.date).agg(
                neto=("monto", "sum"), uds=("cantidad", "sum")
            ).reset_index()
            _v_dia.columns = ["fecha_dia", "neto", "uds"]
            _v_dia = _v_dia.sort_values("fecha_dia")
            _v_dia["fecha_dt"] = pd.to_datetime(_v_dia["fecha_dia"])

            fig_v = go.Figure()
            fig_v.add_trace(go.Scatter(
                x=_v_dia["fecha_dt"], y=_v_dia["neto"],
                fill="tozeroy", fillcolor="rgba(0,201,107,0.1)",
                line=dict(color="#00c96b", width=2.5),
                name="Ventas",
                hovertemplate="<b>%{x|%d/%m}</b><br>Ventas: $%{y:,.0f}<extra></extra>",
            ))
            if _tiene_comp:
                _vc_dia = df_comp[df_comp["tipo"] == "VENTA"].copy()
                if not _vc_dia.empty:
                    _vc_dia_g = _vc_dia.groupby(_vc_dia["fecha"].dt.date)["monto"].sum().reset_index()
                    _vc_dia_g.columns = ["fecha_dia", "neto"]
                    _vc_dia_g = _vc_dia_g.sort_values("fecha_dia")
                    # Alinear al mismo eje X usando día relativo
                    _vc_dia_g["dia_rel"] = range(len(_vc_dia_g))
                    _v_dia_plot = _v_dia.copy()
                    _v_dia_plot["dia_rel"] = range(len(_v_dia_plot))
                    _merged = _v_dia_plot.merge(_vc_dia_g[["dia_rel", "neto"]], on="dia_rel", how="left", suffixes=("", "_comp"))
                    if "neto_comp" in _merged.columns:
                        fig_v.add_trace(go.Scatter(
                            x=_merged["fecha_dt"], y=_merged["neto_comp"],
                            line=dict(color="#666688", width=1.5, dash="dot"),
                            name="Período anterior",
                            hovertemplate="<b>Comparación</b><br>$%{y:,.0f}<extra></extra>",
                        ))
            fig_v.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1a1a2e",
                font=dict(family="Inter", color="#888899", size=11),
                height=280, margin=dict(t=20, b=10, l=50, r=20),
                legend=dict(orientation="h", y=1.08, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
                xaxis=dict(showgrid=False, tickformat="%d/%m", linecolor="rgba(255,255,255,0.06)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickformat="$,.0f", linecolor="rgba(255,255,255,0.06)"),
            )
            st.plotly_chart(fig_v, use_container_width=True, config={"displayModeBar": False})

            # Desglose por medio de pago
            _v_medio = _ventas_per.groupby("medio").agg(total=("monto", "sum"), cant=("monto", "count")).reset_index()
            _v_medio = _v_medio.sort_values("total", ascending=False)
            _v_medio_total = _v_medio["total"].sum()
            _colores_medio = {"Efectivo": "#00c96b", "Mercado Pago": "#3a86ff", "Santander": "#e94560",
                              "BBVA Frances": "#f7b731", "Banco Corrientes": "#8b5cf6", "Online": "#4ecdc4"}
            _rows_mp = ""
            for _, _rm in _v_medio.iterrows():
                _pct_m = _rm["total"] / _v_medio_total * 100 if _v_medio_total else 0
                _col_m = _colores_medio.get(_rm["medio"], "#6666aa")
                _rows_mp += f'''<div style="margin:8px 0">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                        <span style="color:#ccc;font-weight:600;font-size:0.85rem">{_rm["medio"]}</span>
                        <span style="color:#eee;font-weight:700;font-size:0.85rem">{fmt_tabla(_rm["total"])} · {_pct_m:.0f}%</span>
                    </div>
                    <div style="background:#ffffff10;border-radius:4px;height:8px;overflow:hidden">
                        <div style="width:{_pct_m:.0f}%;height:100%;background:{_col_m};border-radius:4px"></div>
                    </div>
                </div>'''
            st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #ffffff10;border-radius:14px;padding:16px 20px;margin-top:8px">
                <div style="font-size:0.78rem;color:#8888aa;font-weight:700;text-transform:uppercase;margin-bottom:10px">Medios de pago</div>
                {_rows_mp}
            </div>''', unsafe_allow_html=True)
        else:
            alerta_html("Sin ventas en este período", "amarillo")

        # ── REPORTE DE GASTOS ─────────────────────────────────────────────────
        seccion("Reporte de gastos")
        _gastos_per = df_mov[df_mov["tipo"] == "GASTO"].copy()
        if not _gastos_per.empty:
            _total_gr = abs(_gastos_per["monto"].sum())
            _cant_gr = len(_gastos_per)
            _ticket_gr = _total_gr / _cant_gr if _cant_gr else 0

            _comp_g_txt = ""
            _comp_gt_txt = ""
            if _tiene_comp:
                _gc = df_comp[df_comp["tipo"] == "GASTO"]
                _comp_g_txt = _pct_cambio(_total_gr, abs(_gc["monto"].sum()))
                _comp_gt_txt = _pct_cambio(_cant_gr, len(_gc))

            rg1, rg2, rg3 = st.columns(3)
            with rg1:
                st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #e9456033;border-radius:14px;padding:20px;border-left:4px solid #e94560">
                    <div style="font-size:0.75rem;color:#e94560;font-weight:700;text-transform:uppercase">Total gastos</div>
                    <div style="font-size:1.8rem;font-weight:800;color:#eee;margin:6px 0">{fmt(_total_gr)} {_comp_g_txt}</div>
                    <div style="font-size:0.78rem;color:#8888aa">{_cant_gr} movimientos</div>
                </div>''', unsafe_allow_html=True)
            with rg2:
                st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #f7b73133;border-radius:14px;padding:20px;border-left:4px solid #f7b731">
                    <div style="font-size:0.75rem;color:#f7b731;font-weight:700;text-transform:uppercase">Gasto promedio</div>
                    <div style="font-size:1.8rem;font-weight:800;color:#eee;margin:6px 0">{fmt(_ticket_gr)}</div>
                    <div style="font-size:0.78rem;color:#8888aa">Por movimiento</div>
                </div>''', unsafe_allow_html=True)
            with rg3:
                st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #3a86ff33;border-radius:14px;padding:20px;border-left:4px solid #3a86ff">
                    <div style="font-size:0.75rem;color:#3a86ff;font-weight:700;text-transform:uppercase">Movimientos</div>
                    <div style="font-size:1.8rem;font-weight:800;color:#eee;margin:6px 0">{_cant_gr} {_comp_gt_txt}</div>
                    <div style="font-size:0.78rem;color:#8888aa">en el período</div>
                </div>''', unsafe_allow_html=True)

            # Gráfico diario de gastos
            _g_dia = _gastos_per.copy()
            _g_dia["monto_abs"] = _g_dia["monto"].abs()
            _g_dia = _g_dia.groupby(_g_dia["fecha"].dt.date).agg(total=("monto_abs", "sum"), cant=("monto_abs", "count")).reset_index()
            _g_dia.columns = ["fecha_dia", "total", "cant"]
            _g_dia = _g_dia.sort_values("fecha_dia")
            _g_dia["fecha_dt"] = pd.to_datetime(_g_dia["fecha_dia"])

            fig_g = go.Figure()
            fig_g.add_trace(go.Scatter(
                x=_g_dia["fecha_dt"], y=_g_dia["total"],
                fill="tozeroy", fillcolor="rgba(233,69,96,0.1)",
                line=dict(color="#e94560", width=2.5),
                name="Gastos",
                hovertemplate="<b>%{x|%d/%m}</b><br>Gastos: $%{y:,.0f}<extra></extra>",
            ))
            if _tiene_comp:
                _gc_dia = df_comp[df_comp["tipo"] == "GASTO"].copy()
                if not _gc_dia.empty:
                    _gc_dia["monto_abs"] = _gc_dia["monto"].abs()
                    _gc_dia_g = _gc_dia.groupby(_gc_dia["fecha"].dt.date)["monto_abs"].sum().reset_index()
                    _gc_dia_g.columns = ["fecha_dia", "total"]
                    _gc_dia_g = _gc_dia_g.sort_values("fecha_dia")
                    _gc_dia_g["dia_rel"] = range(len(_gc_dia_g))
                    _g_dia_plot = _g_dia.copy()
                    _g_dia_plot["dia_rel"] = range(len(_g_dia_plot))
                    _merged_g = _g_dia_plot.merge(_gc_dia_g[["dia_rel", "total"]], on="dia_rel", how="left", suffixes=("", "_comp"))
                    if "total_comp" in _merged_g.columns:
                        fig_g.add_trace(go.Scatter(
                            x=_merged_g["fecha_dt"], y=_merged_g["total_comp"],
                            line=dict(color="#666688", width=1.5, dash="dot"),
                            name="Período anterior",
                            hovertemplate="<b>Comparación</b><br>$%{y:,.0f}<extra></extra>",
                        ))
            fig_g.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1a1a2e",
                font=dict(family="Inter", color="#888899", size=11),
                height=280, margin=dict(t=20, b=10, l=50, r=20),
                legend=dict(orientation="h", y=1.08, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
                xaxis=dict(showgrid=False, tickformat="%d/%m", linecolor="rgba(255,255,255,0.06)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickformat="$,.0f", linecolor="rgba(255,255,255,0.06)"),
            )
            st.plotly_chart(fig_g, use_container_width=True, config={"displayModeBar": False})

            # Desglose por categoría
            _g_cat = _gastos_per.copy()
            _g_cat["monto_abs"] = _g_cat["monto"].abs()
            _g_cat = _g_cat.groupby("categoria").agg(total=("monto_abs", "sum"), cant=("monto_abs", "count")).reset_index()
            _g_cat = _g_cat.sort_values("total", ascending=False)
            _g_cat_total = _g_cat["total"].sum()
            _col_cats = {"AFIP / Impuestos": "#8b5cf6", "Gastos bancarios": "#e94560",
                         "Servicios (luz/gas/tel)": "#f7b731", "Sueldos": "#3a86ff",
                         "Alquiler": "#e94560", "Transporte": "#00c96b",
                         "Mercadería": "#4ecdc4", "Cheque debitado": "#ff6b6b", "Otros": "#6666aa"}
            _rows_gc = ""
            for _, _rg in _g_cat.iterrows():
                _pct_g = _rg["total"] / _g_cat_total * 100 if _g_cat_total else 0
                _col_g = _col_cats.get(_rg["categoria"], "#6666aa")
                _rows_gc += f'''<div style="margin:8px 0">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                        <span style="color:#ccc;font-weight:600;font-size:0.85rem">{_rg["categoria"]}</span>
                        <span style="color:#eee;font-weight:700;font-size:0.85rem">{fmt_tabla(_rg["total"])} · {_pct_g:.0f}%</span>
                    </div>
                    <div style="background:#ffffff10;border-radius:4px;height:8px;overflow:hidden">
                        <div style="width:{_pct_g:.0f}%;height:100%;background:{_col_g};border-radius:4px"></div>
                    </div>
                </div>'''
            st.markdown(f'''<div style="background:#1a1a2e;border:1px solid #ffffff10;border-radius:14px;padding:16px 20px;margin-top:8px">
                <div style="font-size:0.78rem;color:#8888aa;font-weight:700;text-transform:uppercase;margin-bottom:10px">Gastos por categoría</div>
                {_rows_gc}
            </div>''', unsafe_allow_html=True)
        else:
            alerta_html("Sin gastos en este período", "amarillo")

        # ── REPORTES POR BANCO / MEDIO ────────────────────────────────────────
        seccion("Reporte por banco / medio")
        _all_medios = sorted(df_mov["medio"].dropna().unique())
        _ult_bancos = get_bancos()[-1] if get_bancos() else {}
        _saldos_map = {
            "BBVA Frances": _ult_bancos.get("BBVA Frances", None),
            "Banco Corrientes": _ult_bancos.get("Banco Corrientes", None),
            "Galicia": _ult_bancos.get("Galicia", None),
            "Santander": _ult_bancos.get("Santander", None),
            "Mercado Pago": _ult_bancos.get("Mercado Pago", None),
            "Efectivo Caja": _ult_bancos.get("Efectivo Caja", None),
            "Efectivo": _ult_bancos.get("Efectivo Caja", None),
        }
        _iconos_banco = {"BBVA Frances": "🏦", "Banco Corrientes": "🏦", "Galicia": "🏦",
                         "Santander": "🏦", "Mercado Pago": "💳", "Efectivo": "💵",
                         "Online": "🌐", "Cuenta bancaria": "🏦"}

        for _medio_rep in _all_medios:
            _mov_m = df_mov[df_mov["medio"] == _medio_rep].copy()
            _ventas_m = _mov_m[_mov_m["tipo"] == "VENTA"]
            _gastos_m = _mov_m[_mov_m["tipo"] == "GASTO"]
            _total_ven_m = _ventas_m["monto"].sum()
            _total_gas_m = abs(_gastos_m["monto"].sum())
            _neto_m = _total_ven_m - _total_gas_m
            _cant_m = len(_mov_m)
            _icono = _iconos_banco.get(_medio_rep, "📋")
            _saldo = _saldos_map.get(_medio_rep)
            _saldo_txt = f" · Saldo actual: {fmt(_saldo)}" if _saldo is not None else ""

            with st.expander(f"{_icono} {_medio_rep} — {_cant_m} movs — Ingresos: {fmt(_total_ven_m)} | Egresos: {fmt(_total_gas_m)}{_saldo_txt}"):
                # KPIs del banco
                bk1, bk2, bk3 = st.columns(3)
                _col_neto = "#00c96b" if _neto_m >= 0 else "#e94560"
                with bk1:
                    st.markdown(f'''<div style="background:#0d0d14;border:1px solid #00c96b33;border-radius:12px;padding:14px;border-left:3px solid #00c96b">
                        <div style="font-size:0.72rem;color:#00c96b;font-weight:700">INGRESOS</div>
                        <div style="font-size:1.4rem;font-weight:800;color:#eee">{fmt(_total_ven_m)}</div>
                        <div style="font-size:0.72rem;color:#8888aa">{len(_ventas_m)} ventas</div>
                    </div>''', unsafe_allow_html=True)
                with bk2:
                    st.markdown(f'''<div style="background:#0d0d14;border:1px solid #e9456033;border-radius:12px;padding:14px;border-left:3px solid #e94560">
                        <div style="font-size:0.72rem;color:#e94560;font-weight:700">EGRESOS</div>
                        <div style="font-size:1.4rem;font-weight:800;color:#eee">{fmt(_total_gas_m)}</div>
                        <div style="font-size:0.72rem;color:#8888aa">{len(_gastos_m)} gastos</div>
                    </div>''', unsafe_allow_html=True)
                with bk3:
                    st.markdown(f'''<div style="background:#0d0d14;border:1px solid {_col_neto}33;border-radius:12px;padding:14px;border-left:3px solid {_col_neto}">
                        <div style="font-size:0.72rem;color:{_col_neto};font-weight:700">NETO</div>
                        <div style="font-size:1.4rem;font-weight:800;color:{_col_neto}">{fmt(_neto_m)}</div>
                        <div style="font-size:0.72rem;color:#8888aa">{"Saldo: " + fmt(_saldo) if _saldo is not None else "ingresos - egresos"}</div>
                    </div>''', unsafe_allow_html=True)

                # Gráfico diario del banco
                _bk_dia_v = _ventas_m.groupby(_ventas_m["fecha"].dt.date)["monto"].sum().reset_index()
                _bk_dia_v.columns = ["fecha_dia", "ingresos"]
                _bk_dia_g = _gastos_m.copy()
                _bk_dia_g["monto_abs"] = _bk_dia_g["monto"].abs()
                _bk_dia_g = _bk_dia_g.groupby(_bk_dia_g["fecha"].dt.date)["monto_abs"].sum().reset_index()
                _bk_dia_g.columns = ["fecha_dia", "egresos"]

                _bk_dia = pd.DataFrame({"fecha_dia": sorted(set(
                    list(_bk_dia_v["fecha_dia"]) + list(_bk_dia_g["fecha_dia"])
                ))})
                _bk_dia = _bk_dia.merge(_bk_dia_v, on="fecha_dia", how="left").merge(_bk_dia_g, on="fecha_dia", how="left").fillna(0)
                _bk_dia["fecha_dt"] = pd.to_datetime(_bk_dia["fecha_dia"])

                if len(_bk_dia) > 1:
                    fig_bk = go.Figure()
                    if _bk_dia["ingresos"].sum() > 0:
                        fig_bk.add_trace(go.Bar(
                            x=_bk_dia["fecha_dt"], y=_bk_dia["ingresos"],
                            name="Ingresos", marker_color="#00c96b",
                            hovertemplate="<b>%{x|%d/%m}</b><br>Ingreso: $%{y:,.0f}<extra></extra>",
                        ))
                    if _bk_dia["egresos"].sum() > 0:
                        fig_bk.add_trace(go.Bar(
                            x=_bk_dia["fecha_dt"], y=_bk_dia["egresos"],
                            name="Egresos", marker_color="#e94560",
                            hovertemplate="<b>%{x|%d/%m}</b><br>Egreso: $%{y:,.0f}<extra></extra>",
                        ))
                    fig_bk.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0d0d14",
                        font=dict(family="Inter", color="#888899", size=10),
                        height=220, margin=dict(t=10, b=10, l=50, r=10),
                        barmode="group",
                        legend=dict(orientation="h", y=1.1, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=9)),
                        xaxis=dict(showgrid=False, tickformat="%d/%m", linecolor="rgba(255,255,255,0.06)"),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickformat="$,.0f", linecolor="rgba(255,255,255,0.06)"),
                    )
                    st.plotly_chart(fig_bk, use_container_width=True, config={"displayModeBar": False})

                # Últimos movimientos del banco
                _ult_mov = _mov_m.sort_values("fecha", ascending=False).head(10)
                _rows_bk = ""
                for _, _rbk in _ult_mov.iterrows():
                    _es_v = _rbk["tipo"] == "VENTA"
                    _col_bk = "#00c96b" if _es_v else "#e94560"
                    _sig_bk = "+" if _es_v else ""
                    _fecha_bk = _rbk["fecha"].strftime("%d/%m") if hasattr(_rbk["fecha"], "strftime") else str(_rbk["fecha"])[:10]
                    _rows_bk += (
                        f'<tr><td style="white-space:nowrap;font-size:0.8rem">{_fecha_bk}</td>'
                        f'<td style="font-size:0.8rem">{str(_rbk["concepto"])[:45]}</td>'
                        f'<td style="text-align:right;color:{_col_bk};font-weight:700;font-size:0.8rem">{_sig_bk}{fmt_tabla(_rbk["monto"])}</td></tr>'
                    )
                st.markdown(
                    f'<div class="tabla-wrapper"><table class="tabla-custom">'
                    f'<thead><tr><th>Fecha</th><th>Concepto</th><th style="text-align:right">Monto</th></tr></thead>'
                    f'<tbody>{_rows_bk}</tbody></table></div>',
                    unsafe_allow_html=True)

        # ── Gastos del mes por categoría ──────────────────────────────────────
        seccion("Gastos del mes — a donde se va la plata")

        gastos_mes = [g for g in get_gastos()
            if g["fecha"][:7] == f"{hoy.year}-{hoy.month:02d}"]

        if gastos_mes:
            from collections import defaultdict as _dd
            _por_cat_g = _dd(lambda: {"monto": 0, "items": []})
            for g in gastos_mes:
                cat = g.get("categoria", "Otros")
                _por_cat_g[cat]["monto"] += g["monto"]
                _por_cat_g[cat]["items"].append(g)

            total_gastos_mes = sum(v["monto"] for v in _por_cat_g.values())

            # Colores por categoría
            _col_cat = {
                "AFIP / Impuestos": "#8b5cf6", "Gastos bancarios": "#e94560",
                "Servicios (luz/gas/tel)": "#f7b731", "Sueldos": "#3a86ff",
                "Alquiler": "#e94560", "Transporte": "#00c96b",
                "Mercadería": "#4ecdc4", "Cheque debitado": "#ff6b6b",
                "Otros": "#6666aa",
            }

            # Tabla resumen
            rows_gc = ""
            for cat, data in sorted(_por_cat_g.items(), key=lambda x: -x[1]["monto"]):
                pct = data["monto"] / total_gastos_mes * 100
                col = _col_cat.get(cat, "#6666aa")
                rows_gc += (
                    f'<tr>'
                    f'<td style="font-weight:600">{cat}</td>'
                    f'<td style="text-align:center">{len(data["items"])}</td>'
                    f'<td style="text-align:right;color:{col};font-weight:700">{fmt_tabla(data["monto"])}</td>'
                    f'<td style="text-align:right;color:#8888aa">{pct:.0f}%</td>'
                    f'</tr>'
                )
            rows_gc += (
                f'<tr style="border-top:2px solid #ffffff15">'
                f'<td style="font-weight:800;color:#eee">TOTAL GASTOS CARGADOS</td>'
                f'<td style="text-align:center">{len(gastos_mes)}</td>'
                f'<td style="text-align:right;color:#e94560;font-weight:800;font-size:1.05rem">{fmt_tabla(total_gastos_mes)}</td>'
                f'<td></td></tr>'
            )
            st.markdown(
                f'<div class="tabla-wrapper"><table class="tabla-custom">'
                f'<thead><tr><th>Categoria</th><th style="text-align:center">Movimientos</th>'
                f'<th style="text-align:right">Monto</th><th style="text-align:right">%</th></tr></thead>'
                f'<tbody>{rows_gc}</tbody></table></div>',
                unsafe_allow_html=True,
            )

            # Detalle por categoría con expander
            for cat, data in sorted(_por_cat_g.items(), key=lambda x: -x[1]["monto"]):
                with st.expander(f"{cat} — {fmt(data['monto'])} ({len(data['items'])} movimientos)"):
                    rows_det_g = ""
                    for g in sorted(data["items"], key=lambda x: x["fecha"]):
                        rows_det_g += (
                            f'<tr><td style="white-space:nowrap">{g["fecha"]}</td>'
                            f'<td style="font-size:0.82rem">{g["concepto"][:50]}</td>'
                            f'<td style="font-size:0.78rem;color:#8888aa">{g.get("medio","—")}</td>'
                            f'<td style="text-align:right;color:#e94560;font-weight:700">{fmt_tabla(g["monto"])}</td></tr>'
                        )
                    st.markdown(
                        f'<div class="tabla-wrapper"><table class="tabla-custom">'
                        f'<thead><tr><th>Fecha</th><th>Concepto</th><th>Medio</th><th style="text-align:right">Monto</th></tr></thead>'
                        f'<tbody>{rows_det_g}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("Sin gastos cargados este mes. Subilos en Config o cargalos aca abajo.")

        # ── Balance IVA ────────────────────────────────────────────────────────
        seccion("Balance IVA — cuanto vas a pagar")

        # IVA Débito: 21% sobre ventas netas — ESTO ES REAL
        iva_debito = total_ventas * 0.21

        # IVA Crédito: solo de facturas cargadas en data/facturas_compra.json
        _p_fact = Path("data/facturas_compra.json")
        facturas = json.loads(_p_fact.read_text(encoding="utf-8")) if _p_fact.exists() else []
        iva_credito_real = sum(f.get("iva", 0) for f in facturas)

        saldo_iva = iva_debito - iva_credito_real
        compra_para_cero = max(saldo_iva / 0.21, 0)

        iv1, iv2, iv3 = st.columns(3)
        with iv1:
            st.markdown(f"""
            <div style="background:#1a1a2e;border:1px solid #e9456044;border-radius:14px;padding:18px 20px;border-left:4px solid #e94560">
                <div style="font-size:0.78rem;color:#e94560;font-weight:700">IVA DEBITO FISCAL</div>
                <div style="font-size:0.72rem;color:#8888aa;margin:4px 0">21% sobre ventas netas — esto lo debes</div>
                <div style="font-size:1.5rem;font-weight:800;color:#e94560">{fmt(iva_debito)}</div>
                <div style="font-size:0.72rem;color:#666688;margin-top:4px">Ventas: {fmt(total_ventas)} x 21%</div>
            </div>""", unsafe_allow_html=True)
        with iv2:
            n_fact = len(facturas)
            sub_cred = f"{n_fact} factura{'s' if n_fact!=1 else ''} cargada{'s' if n_fact!=1 else ''}" if n_fact > 0 else "Sin facturas cargadas"
            st.markdown(f"""
            <div style="background:#1a1a2e;border:1px solid {'#00c96b' if n_fact > 0 else '#8888aa'}44;border-radius:14px;padding:18px 20px;border-left:4px solid {'#00c96b' if n_fact > 0 else '#8888aa'}">
                <div style="font-size:0.78rem;color:{'#00c96b' if n_fact > 0 else '#8888aa'};font-weight:700">IVA CREDITO FISCAL</div>
                <div style="font-size:0.72rem;color:#8888aa;margin:4px 0">Solo de facturas A de proveedores cargadas</div>
                <div style="font-size:1.5rem;font-weight:800;color:{'#00c96b' if n_fact > 0 else '#8888aa'}">{fmt(iva_credito_real)}</div>
                <div style="font-size:0.72rem;color:#666688;margin-top:4px">{sub_cred}</div>
            </div>""", unsafe_allow_html=True)
        with iv3:
            color_saldo = "#e94560" if saldo_iva > 0 else "#00c96b"
            texto_saldo = "A PAGAR" if saldo_iva > 0 else "A FAVOR"
            st.markdown(f"""
            <div style="background:#1a1a2e;border:1px solid {color_saldo}44;border-radius:14px;padding:18px 20px;border-left:4px solid {color_saldo}">
                <div style="font-size:0.78rem;color:{color_saldo};font-weight:700">SALDO IVA — {texto_saldo}</div>
                <div style="font-size:0.72rem;color:#8888aa;margin:4px 0">Debito - Credito</div>
                <div style="font-size:1.5rem;font-weight:800;color:{color_saldo}">{fmt(abs(saldo_iva))}</div>
                <div style="font-size:0.72rem;color:#666688;margin-top:4px">Debito {fmt(iva_debito)} - Credito {fmt(iva_credito_real)}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background:#f7b73112;border:1px solid #f7b73133;border-radius:12px;padding:16px 20px;margin:12px 0">
            <div style="color:#ffd97d;font-weight:700;font-size:0.9rem;margin-bottom:6px">
                Para no pagar IVA necesitas comprar mercaderia con factura A por {fmt(compra_para_cero)} + IVA
            </div>
            <div style="color:#8888aa;font-size:0.82rem">
                Cada compra con factura A te genera credito fiscal (21% del neto).
                Carga las facturas abajo para ir descontando del debito.
            </div>
        </div>""", unsafe_allow_html=True)

        # Formulario para cargar facturas de compra
        with st.expander("Cargar factura de compra (credito fiscal)"):
            with st.form("factura_iva", clear_on_submit=True):
                fi1, fi2, fi3 = st.columns(3)
                f_prov = fi1.text_input("Proveedor", placeholder="Ej: Kazuma, Lisbon")
                f_neto = fi2.number_input("Neto factura $", min_value=0, step=10000)
                f_fecha = fi3.date_input("Fecha factura", value=hoy)
                f_desc = st.text_input("Descripcion", placeholder="Ej: Factura A compra remeras marzo")
                if st.form_submit_button("Cargar factura", use_container_width=True):
                    if f_prov and f_neto > 0:
                        f_iva = round(f_neto * 0.21, 2)
                        facturas.append({
                            "fecha": f_fecha.isoformat(),
                            "proveedor": f_prov,
                            "neto": f_neto,
                            "iva": f_iva,
                            "total": f_neto + f_iva,
                            "descripcion": f_desc,
                        })
                        _save_json_and_sync(str(_p_fact), facturas, "Factura IVA cargada desde dashboard")
                        _notificar(f"✅ Factura cargada: {f_prov} — Neto {fmt(f_neto)} — IVA crédito {fmt(f_iva)}")
                        st.rerun()

        if facturas:
            with st.expander("Facturas cargadas"):
                rows_f = ""
                for f in facturas:
                    rows_f += f'<tr><td>{f["fecha"]}</td><td>{f["proveedor"]}</td><td>{fmt_tabla(f["neto"])}</td><td style="color:#00c96b;font-weight:700">{fmt_tabla(f["iva"])}</td><td>{f.get("descripcion","")}</td></tr>'
                st.markdown(
                    f'<div class="tabla-wrapper"><table class="tabla-custom">'
                    f'<thead><tr><th>Fecha</th><th>Proveedor</th><th>Neto</th><th>IVA Credito</th><th>Desc</th></tr></thead>'
                    f'<tbody>{rows_f}</tbody></table></div>',
                    unsafe_allow_html=True,
                )

        # ── Formulario para cargar gasto rapido ───────────────────────────────
        seccion("Cargar gasto rapido")
        with st.form("gasto_rapido", clear_on_submit=True):
            gr1, gr2 = st.columns([3, 1])
            gr_concepto = gr1.text_input("Concepto", placeholder="Ej: alquiler abril, sueldo Gabriela")
            gr_monto    = gr2.number_input("Monto $", min_value=0, step=1000)
            gr3, gr4 = st.columns(2)
            gr_cat      = gr3.selectbox("Categoria", [
                "Sueldos", "Alquiler", "Servicios (luz/gas/tel)", "AFIP / Impuestos",
                "Transporte", "Gastos bancarios", "Mercadería", "Tienda Nube", "Marketing", "Otros"
            ])
            gr_medio    = gr4.selectbox("Medio", ["Efectivo", "Banco Corrientes", "BBVA Frances", "Mercado Pago", "Santander"])
            if st.form_submit_button("Agregar gasto", use_container_width=True):
                if gr_concepto and gr_monto > 0:
                    gastos_act = get_gastos()
                    gastos_act.append({
                        "fecha": hoy.isoformat(),
                        "concepto": gr_concepto,
                        "monto": gr_monto,
                        "categoria": gr_cat,
                        "medio": gr_medio,
                        "notas": "Cargado manualmente",
                    })
                    save_gastos(gastos_act)
                    _notificar(f"✅ Gasto cargado: {gr_concepto} — {fmt(gr_monto)}")
                    st.rerun()
                else:
                    st.warning("Completa concepto y monto")

        # ── Tabla de movimientos ──────────────────────────────────────────────
        seccion(f"Detalle — {len(df_mov)} movimientos")

        rows_mov = ""
        for _, rm in df_mov.head(200).iterrows():
            es_venta = rm["tipo"] == "VENTA"
            color_m  = "#00c96b" if es_venta else "#e94560"
            signo    = "+" if es_venta else ""
            badge_t  = "badge-verde" if es_venta else "badge-rojo"
            label_t  = "Venta" if es_venta else "Gasto"
            fecha_txt = rm["fecha"].strftime("%d/%m/%Y") if hasattr(rm["fecha"], "strftime") else str(rm["fecha"])[:10]
            concepto_txt = str(rm["concepto"])[:60]
            cant_txt = f' ({int(rm["cantidad"])} uds)' if es_venta and rm["cantidad"] > 0 else ""

            rows_mov += (
                f'<tr>'
                f'<td style="white-space:nowrap">{fecha_txt}</td>'
                f'<td><span class="badge {badge_t}">{label_t}</span></td>'
                f'<td style="font-size:0.82rem">{concepto_txt}{cant_txt}</td>'
                f'<td style="font-size:0.78rem;color:#8888aa">{rm["medio"]}</td>'
                f'<td style="font-size:0.78rem;color:#8888aa">{rm["categoria"]}</td>'
                f'<td style="color:{color_m};font-weight:700;text-align:right">{signo}{fmt_tabla(rm["monto"])}</td>'
                f'</tr>'
            )

        st.markdown(
            f'<div class="tabla-wrapper"><table class="tabla-custom">'
            f'<thead><tr><th>Fecha</th><th>Tipo</th><th>Concepto</th><th>Medio</th><th>Categoria</th><th style="text-align:right">Monto</th></tr></thead>'
            f'<tbody>{rows_mov}</tbody></table></div>',
            unsafe_allow_html=True,
        )

        if len(df_mov) > 200:
            st.info(f"Mostrando los primeros 200 de {len(df_mov)} movimientos")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — INCONSISTENCIAS
# ══════════════════════════════════════════════════════════════════════════════
if tab4:
  with tab4:
    seccion("Inconsistencias y pendientes — resolver para que cierre todo")

    problemas = []

    # Saldo Santander (usado en varias validaciones)
    _bancos_inc = get_bancos()
    saldo_sant = _bancos_inc[-1].get("Santander", 0) if _bancos_inc else 0

    # ── 1. Cheque vencido ────────────────────────────────────────────────────
    for ch in cheques:
        if ch.get("estado") == "pendiente" and ch.get("tipo") == "emitido":
            dias_v = (date.fromisoformat(ch["vencimiento"]) - hoy).days
            if dias_v < 0:
                problemas.append({
                    "prioridad": "URGENTE",
                    "color": "#e94560",
                    "titulo": f"Cheque {ch['id']} VENCIDO hace {abs(dias_v)} dias",
                    "detalle": f"{ch['proveedor']} — {fmt(ch['monto'])} — vencio el {ch['vencimiento']}. Si se presenta y no hay fondos, queda en BCRA.",
                    "accion": "Negociar con el proveedor o asegurar fondos en la cuenta",
                    "resuelto_key": f"chk_vencido_{ch['id']}",
                    "tabla": f'<table class="tabla-custom"><thead><tr><th>Cheque</th><th>Proveedor</th><th>Vencimiento</th><th>Monto</th><th>Estado</th></tr></thead><tbody><tr><td>{ch["id"]}</td><td>{ch["proveedor"]}</td><td>{ch["vencimiento"]}</td><td style="color:#e94560;font-weight:700">{fmt(ch["monto"])}</td><td style="color:#e94560">Vencido {abs(dias_v)}d</td></tr></tbody></table>',
                })
            elif dias_v <= 3:
                problemas.append({
                    "prioridad": "URGENTE",
                    "color": "#e94560",
                    "titulo": f"Cheque {ch['id']} vence en {dias_v} dia{'s' if dias_v!=1 else ''}",
                    "detalle": f"{ch['proveedor']} — {fmt(ch['monto'])} — vence el {ch['vencimiento']}.",
                    "accion": "Verificar que haya fondos en Santander para cubrirlo",
                    "resuelto_key": f"chk_prox_{ch['id']}",
                    "tabla": f'<table class="tabla-custom"><thead><tr><th>Cheque</th><th>Proveedor</th><th>Vencimiento</th><th>Monto</th><th>Saldo Santander</th></tr></thead><tbody><tr><td>{ch["id"]}</td><td>{ch["proveedor"]}</td><td>{ch["vencimiento"]}</td><td style="color:#e94560;font-weight:700">{fmt(ch["monto"])}</td><td style="color:#00c96b">{fmt(saldo_sant)}</td></tr></tbody></table>',
                })

    # ── 2. Fondos insuficientes para cheques de abril ────────────────────────
    cheques_abril = [c for c in cheques
        if c.get("estado") == "pendiente" and c.get("tipo") == "emitido"
        and c["vencimiento"][:7] == "2026-04"]
    total_cheques_abril = sum(c["monto"] for c in cheques_abril)
    if total_cheques_abril > saldo_sant and total_cheques_abril > 0:
        rows_chq = ""
        for c in cheques_abril:
            d_ch = (date.fromisoformat(c["vencimiento"]) - hoy).days
            est_ch = f"VENCIDO {abs(d_ch)}d" if d_ch < 0 else f"en {d_ch}d"
            col_ch = "#e94560" if d_ch <= 3 else "#f7b731"
            rows_chq += f'<tr><td>{c["id"]}</td><td>{c["proveedor"]}</td><td>{c["vencimiento"]}</td><td style="color:{col_ch}">{est_ch}</td><td style="color:#e94560;font-weight:700">{fmt(c["monto"])}</td></tr>'
        rows_chq += f'<tr style="border-top:2px solid #ffffff15"><td colspan="4" style="font-weight:700;color:#eee">TOTAL CHEQUES ABRIL</td><td style="color:#e94560;font-weight:700">{fmt(total_cheques_abril)}</td></tr>'
        rows_chq += f'<tr><td colspan="4" style="color:#00c96b">Saldo Santander disponible</td><td style="color:#00c96b;font-weight:700">{fmt(saldo_sant)}</td></tr>'
        rows_chq += f'<tr><td colspan="4" style="color:#f7b731;font-weight:700">FALTANTE</td><td style="color:#f7b731;font-weight:700">{fmt(total_cheques_abril - saldo_sant)}</td></tr>'
        tabla_fondos = f'<table class="tabla-custom"><thead><tr><th>Cheque</th><th>Proveedor</th><th>Vence</th><th>Estado</th><th>Monto</th></tr></thead><tbody>{rows_chq}</tbody></table>'
        problemas.append({
            "prioridad": "CRITICO",
            "color": "#e94560",
            "titulo": f"Fondos insuficientes para cheques de abril",
            "detalle": f"Cheques abril: {fmt(total_cheques_abril)} vs Santander: {fmt(saldo_sant)}. Faltan {fmt(total_cheques_abril - saldo_sant)}.",
            "accion": "Generar ingresos o transferir plata de otra cuenta antes de los vencimientos",
            "resuelto_key": "fondos_cheques_abril",
            "tabla": tabla_fondos,
        })

    # ── 3. Ventas con tarjeta POS pendientes (NO MP Cuotas — esas son inmediatas) ─
    if not sin_datos:
        fp_upper = df["forma_pago"].astype(str).str.upper()
        # Solo tarjetas POS reales (no MP cuotas que se acreditan inmediato)
        mask_pos_real = fp_upper.str.contains("NARANJA|VISA|MASTER|AMEX|CABAL", na=False) & ~fp_upper.str.contains("MERCADO", na=False)
        if mask_pos_real.any():
            pos_neto = df[mask_pos_real]["neto"].sum()
            pos_iva = pos_neto * 1.21
            problemas.append({
                "prioridad": "INFO",
                "color": "#f7b731",
                "titulo": f"Ventas con tarjeta POS pendientes de cobro: {fmt(pos_iva)} con IVA",
                "detalle": f"Tarjetas del POS (no MP) se acreditan en 18-30 dias. Esta plata todavia no entro al banco.",
                "accion": "No contar con esta plata para pagos inmediatos",
                "resuelto_key": "tc_pendientes",
            })

    # ── 4. Gastos fijos sin cargar ───────────────────────────────────────────
    gastos_cargados = get_gastos()
    categorias_cargadas = set(g.get("categoria", "") for g in gastos_cargados if g["fecha"][:7] == "2026-04")
    gastos_faltantes = {
        "Sueldos": ("Sueldos Gabriela + Sofia", 2100000),
        "Alquiler": ("Alquiler local La Rioja 943", 925000),
    }
    for cat, (desc, monto_est) in gastos_faltantes.items():
        tiene = any(cat.lower() in g.get("concepto","").lower() or cat.lower() in g.get("categoria","").lower()
                    for g in gastos_cargados if g["fecha"][:7] == "2026-04")
        if not tiene:
            problemas.append({
                "prioridad": "PENDIENTE",
                "color": "#f7b731",
                "titulo": f"{desc} — NO CARGADO (~{fmt(monto_est)})",
                "detalle": f"Este gasto fijo no aparece en abril. Si ya se pago, cargalo. Si no se pago, tene en cuenta que falta.",
                "accion": f"Cargar en Movimientos o decime cuanto fue y lo agrego",
                "resuelto_key": f"gasto_{cat}",
            })

    # ── 5. Dias sin ventas en Dux ────────────────────────────────────────────
    if not sin_datos:
        dias_con_venta = set(df["fecha_dia"].unique())
        primer_dia = min(dias_con_venta)
        todos_los_dias = set()
        d = primer_dia
        while d <= hoy:
            if d.weekday() < 6:  # lunes a sabado
                todos_los_dias.add(d)
            d += __import__("datetime").timedelta(days=1)
        dias_sin = todos_los_dias - dias_con_venta
        if dias_sin:
            dias_sin_str = ", ".join(d.strftime("%d/%m") for d in sorted(dias_sin))
            problemas.append({
                "prioridad": "VERIFICAR",
                "color": "#8b5cf6",
                "titulo": f"{len(dias_sin)} dia(s) sin ventas en Dux",
                "detalle": f"Dias: {dias_sin_str}. Puede ser que el local estuvo cerrado o falta cargar el .xls actualizado.",
                "accion": "Si hubo ventas esos dias, subi un .xls de Dux que los incluya",
                "resuelto_key": "dias_sin_ventas",
            })

    # ── 6. Ventas sin forma de pago ──────────────────────────────────────────
    if not sin_datos:
        sin_fp = df[df["forma_pago"].astype(str).str.strip().isin(["", "nan", "None"])]
        if len(sin_fp) > 0:
            monto_sin_fp = sin_fp["neto"].sum()
            rows_sfp = ""
            for _, rv in sin_fp.iterrows():
                f_txt = rv["fecha_dia"].strftime("%d/%m") if hasattr(rv["fecha_dia"], "strftime") else str(rv["fecha_dia"])
                rows_sfp += f'<tr><td>{f_txt}</td><td>{rv["producto"]}</td><td style="text-align:right">{fmt(rv["neto"])}</td><td>{rv.get("canal","")}</td></tr>'
            tabla_sfp = (f'<table class="tabla-custom"><thead><tr><th>Fecha</th><th>Producto</th><th>Neto</th><th>Canal</th></tr></thead>'
                         f'<tbody>{rows_sfp}</tbody></table>')
            problemas.append({
                "prioridad": "VERIFICAR",
                "color": "#8b5cf6",
                "titulo": f"{len(sin_fp)} ventas sin forma de pago ({fmt(monto_sin_fp)})",
                "detalle": "Estas ventas no tienen medio de pago registrado en Dux. No se puede saber a que banco fueron.",
                "accion": "Verificar en Dux y completar la forma de pago",
                "resuelto_key": "sin_forma_pago",
                "tabla": tabla_sfp,
            })

    # ── 7. Ventas manuales con IVA mezclado ──────────────────────────────────
    from data_processor import load_ventas_manuales
    df_man = load_ventas_manuales()
    if not df_man.empty and not sin_datos:
        # Comparar un dia que tenga ambos
        dias_ambos = set(df["fecha_dia"].unique()) & set(df_man["fecha_dia"].unique())
        if dias_ambos:
            d_test = sorted(dias_ambos)[0]
            neto_dux = df[df["fecha_dia"] == d_test]["neto"].sum()
            neto_man = df_man[df_man["fecha_dia"] == d_test]["neto"].sum()
            ratio = neto_man / neto_dux if neto_dux > 0 else 0
            if 1.15 < ratio < 1.25:
                problemas.append({
                    "prioridad": "DATO ERRONEO",
                    "color": "#e94560",
                    "titulo": "Ventas manuales parecen estar CON IVA (deberian ser sin IVA)",
                    "detalle": f"Dia {d_test}: Dux dice neto ${neto_dux:,.0f}, manual dice ${neto_man:,.0f}. Ratio {ratio:.2f}x = parece ser con IVA 21%.",
                    "accion": "Corregir ventas_manuales.json dividiendo montos por 1.21, o decime y lo corrijo yo",
                    "resuelto_key": "ventas_manuales_iva",
                })

    # ── 8. Stock sin movimiento ──────────────────────────────────────────────
    if stock_ini:
        df_stock_check = stock_nuevo_resumen(df, stock_ini)
        for _, r in df_stock_check.iterrows():
            if r["Vendidos"] == 0 and r["Días transcurridos"] >= 14:
                costo_parado = 0
                for item in stock_ini:
                    if item["proveedor"] == r["Proveedor"] and item["tipo"] == r["Tipo"]:
                        costo_parado = item["costo_unit"] * item["stock_inicial"]
                precio_venta_est = costo_parado * 2.3
                problemas.append({
                    "prioridad": "ATENCION",
                    "color": "#f7b731",
                    "titulo": f"{r['Proveedor']} — {r['Tipo']}: 0 ventas en {r['Días transcurridos']} dias",
                    "detalle": f"{int(r['Stock Inicial'])} unidades paradas. Costo: {fmt(costo_parado)}. Plata que no rota.",
                    "accion": "Revisar precio, ubicacion en local, publicar online, o liquidar",
                    "resuelto_key": f"stock_{r['Proveedor']}_{r['Tipo']}",
                    "tabla": f'<table class="tabla-custom"><thead><tr><th>Dato</th><th>Valor</th></tr></thead><tbody>'
                        f'<tr><td>Proveedor</td><td>{r["Proveedor"]}</td></tr>'
                        f'<tr><td>Producto</td><td>{r["Tipo"]}</td></tr>'
                        f'<tr><td>Unidades</td><td>{int(r["Stock Inicial"])}</td></tr>'
                        f'<tr><td>Dias en local</td><td style="color:#e94560">{r["Días transcurridos"]} dias sin vender una unidad</td></tr>'
                        f'<tr><td>Costo invertido</td><td style="color:#e94560;font-weight:700">{fmt(costo_parado)}</td></tr>'
                        f'<tr><td>Precio venta estimado (x2.3)</td><td>{fmt(precio_venta_est)}</td></tr>'
                        f'<tr><td>Sugerencia</td><td style="color:#f7b731">Bajar precio, armar combo, publicar en Tienda Nube, o mover a vidriera</td></tr>'
                        f'</tbody></table>',
                })

    # ── 9. Meta Ads sin datos ────────────────────────────────────────────────
    meta_data = get_meta() if 'get_meta' in dir() else []
    if not meta_data or len(meta_data) < 3:
        problemas.append({
            "prioridad": "PENDIENTE",
            "color": "#8b5cf6",
            "titulo": "Meta Ads sin datos reales cargados",
            "detalle": "No hay datos de inversion y ROAS de las campanas activas. Sin esto no se puede medir el retorno.",
            "accion": "Pasame una captura de Meta Ads y lo cargo",
            "resuelto_key": "meta_ads",
        })

    # ── Renderizar ───────────────────────────────────────────────────────────
    # Ordenar por prioridad
    orden_prio = {"CRITICO": 0, "URGENTE": 1, "DATO ERRONEO": 2, "ATENCION": 3, "PENDIENTE": 4, "VERIFICAR": 5, "INFO": 6}
    problemas.sort(key=lambda p: orden_prio.get(p["prioridad"], 99))

    # KPIs
    n_urgentes = len([p for p in problemas if p["prioridad"] in ("CRITICO", "URGENTE", "DATO ERRONEO")])
    n_pendientes = len([p for p in problemas if p["prioridad"] in ("PENDIENTE", "ATENCION")])
    n_verificar = len([p for p in problemas if p["prioridad"] in ("VERIFICAR", "INFO")])

    ki1, ki2, ki3, ki4 = st.columns(4)
    with ki1:
        st.markdown(metric_card("🔴", "Urgentes", str(n_urgentes), "resolver ya", "rojo"), unsafe_allow_html=True)
    with ki2:
        st.markdown(metric_card("🟡", "Pendientes", str(n_pendientes), "cargar datos", "amarillo"), unsafe_allow_html=True)
    with ki3:
        st.markdown(metric_card("🟣", "Verificar", str(n_verificar), "chequear info", "morado"), unsafe_allow_html=True)
    with ki4:
        st.markdown(metric_card("📋", "Total", str(len(problemas)), "inconsistencias", "azul"), unsafe_allow_html=True)

    for p in problemas:
        resuelto = st.session_state.get(p["resuelto_key"], False)

        if resuelto:
            st.markdown(f"""
            <div style="background:#1a1a2e;border:1px solid #00c96b33;border-radius:12px;padding:14px 20px;
                        margin:6px 0;opacity:0.5;border-left:4px solid #00c96b">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="color:#00c96b;font-weight:700;font-size:0.85rem">✓ RESUELTO — {p['titulo']}</span>
                </div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#1a1a2e;border:1px solid {p['color']}33;border-radius:12px;padding:16px 20px;
                        margin:8px 0;border-left:4px solid {p['color']}">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                    <span class="badge" style="background:{p['color']}22;color:{p['color']};border:1px solid {p['color']}44;
                        padding:2px 10px;border-radius:6px;font-size:0.72rem;font-weight:700">{p['prioridad']}</span>
                </div>
                <div style="color:#eeeeff;font-weight:700;font-size:0.92rem;margin-bottom:6px">{p['titulo']}</div>
                <div style="color:#8888aa;font-size:0.82rem;margin-bottom:8px">{p['detalle']}</div>
                <div style="color:{p['color']};font-size:0.8rem;font-weight:600">→ {p['accion']}</div>
            </div>""", unsafe_allow_html=True)

        if not resuelto and p.get("tabla"):
            with st.expander("Ver detalle"):
                st.markdown(f'<div class="tabla-wrapper">{p["tabla"]}</div>', unsafe_allow_html=True)

        col_res, _ = st.columns([1, 5])
        with col_res:
            if not resuelto:
                if st.button("Marcar resuelto", key=f"btn_{p['resuelto_key']}"):
                    st.session_state[p["resuelto_key"]] = True
                    st.rerun()
            else:
                if st.button("Reabrir", key=f"btn_re_{p['resuelto_key']}"):
                    st.session_state[p["resuelto_key"]] = False
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — STOCK
# ══════════════════════════════════════════════════════════════════════════════
if tab5:
  with tab5:
    if not stock_ini:
        st.info("Sin datos de stock inicial.")
    else:
        df_stock = stock_nuevo_resumen(df, stock_ini)

        # Alertas — todas las líneas de stock nuevo
        for _, r in df_stock.iterrows():
            vel = r["Vel/día"]
            pct = r["% Vendido"]
            dias = r["Días transcurridos"]
            quedan = int(r["Quedan"])
            ini = int(r["Stock Inicial"])
            vend = int(r["Vendidos"])
            ds = r["Días de stock"]

            if vend == 0:
                alerta_html(
                    f"{r['Proveedor']} — {r['Tipo']}: SIN VENTAS en {dias} días ({ini} uds paradas) → Revisar precio / visibilidad / ubicación",
                    "roja"
                )
            elif pct >= 50:
                alerta_html(
                    f"{r['Proveedor']} — {r['Tipo']}: {pct}% vendido ({quedan} restantes, vel {vel:.2f}/día) → Considerar reposición",
                    "verde"
                )
            elif vel < 0.15:
                alerta_html(
                    f"{r['Proveedor']} — {r['Tipo']}: MUY LENTO — {vend}/{ini} vendidos en {dias} días (vel {vel:.2f}/día) → Empujar o bajar precio",
                    "amarilla"
                )
            elif vel < 0.3:
                alerta_html(
                    f"{r['Proveedor']} — {r['Tipo']}: LENTO — {vend}/{ini} vendidos en {dias} días (vel {vel:.2f}/día, quedan {quedan} para ~{ds if ds != '∞' else '∞'}d)",
                    "amarilla"
                )
            else:
                alerta_html(
                    f"{r['Proveedor']} — {r['Tipo']}: OK — {vend}/{ini} vendidos (vel {vel:.2f}/día, quedan {quedan})",
                    "azul"
                )

        # ── Reporte exportable por proveedor ─────────────────────────────────
        seccion("Reporte por proveedor")
        _prov_colores_rep = {"KAZUMA": "#3a86ff", "LISBON": "#8b5cf6", "DISTRICT": "#f7b731"}

        _cols_prov_tabs = st.columns(4)
        if "prov_reporte_sel" not in st.session_state:
            st.session_state["prov_reporte_sel"] = "TODOS"
        for _ci, _opt in enumerate(["TODOS", "KAZUMA", "LISBON", "DISTRICT"]):
            with _cols_prov_tabs[_ci]:
                _activo = st.session_state.get("prov_reporte_sel") == _opt
                _color_btn = _prov_colores_rep.get(_opt, "#e94560")
                if _activo:
                    st.markdown(
                        f'<div style="background:{_color_btn};color:#fff;text-align:center;padding:8px 0;'
                        f'border-radius:8px;font-weight:700;font-size:0.85rem;letter-spacing:1px">{_opt}</div>',
                        unsafe_allow_html=True,
                    )
                if st.button(_opt if not _activo else " ", key=f"btn_prov_{_opt}",
                             use_container_width=True, disabled=_activo):
                    st.session_state["prov_reporte_sel"] = _opt
                    st.rerun()

        _prov_reporte = st.session_state.get("prov_reporte_sel", "TODOS")
        _provs_mostrar = ["KAZUMA", "LISBON", "DISTRICT"] if _prov_reporte == "TODOS" else [_prov_reporte]

        for _prov_r in _provs_mostrar:
            _prov_data = df_stock[df_stock["Proveedor"] == _prov_r]
            if _prov_data.empty:
                continue

            _t_ini = int(_prov_data["Stock Inicial"].sum())
            _t_vend = int(_prov_data["Vendidos"].sum())
            _t_quedan = int(_prov_data["Quedan"].sum())
            _t_neto = _prov_data["Neto $"].sum()
            _t_pct = round(_t_vend / _t_ini * 100, 1) if _t_ini > 0 else 0
            _t_dias = int(_prov_data["Días transcurridos"].iloc[0])
            _prov_color = _prov_colores_rep.get(_prov_r, "#aaa")

            # Card header del proveedor
            st.markdown(f'''<div style="background:linear-gradient(135deg, {_prov_color}15, {_prov_color}08);
                border:1px solid {_prov_color}40;border-radius:12px;padding:18px 22px;margin:18px 0 8px 0">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
                    <div>
                        <span style="font-size:1.2rem;font-weight:800;color:{_prov_color};letter-spacing:1px">{_prov_r}</span>
                        <span style="color:#8888aa;font-size:0.8rem;margin-left:12px">{_t_dias} dias en tienda</span>
                    </div>
                    <div style="display:flex;gap:24px;flex-wrap:wrap">
                        <div style="text-align:center">
                            <div style="font-size:1.3rem;font-weight:800;color:#00c96b">{_t_vend}<span style="color:#555;font-weight:400;font-size:0.8rem">/{_t_ini}</span></div>
                            <div style="font-size:0.65rem;color:#6666aa;text-transform:uppercase;letter-spacing:1px">vendidos</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:1.3rem;font-weight:800;color:#e94560">{_t_quedan}</div>
                            <div style="font-size:0.65rem;color:#6666aa;text-transform:uppercase;letter-spacing:1px">quedan</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:1.3rem;font-weight:800;color:#fff">{_t_pct}%</div>
                            <div style="font-size:0.65rem;color:#6666aa;text-transform:uppercase;letter-spacing:1px">rotacion</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:1.3rem;font-weight:800;color:#f7b731">{fmt(_t_neto)}</div>
                            <div style="font-size:0.65rem;color:#6666aa;text-transform:uppercase;letter-spacing:1px">facturado</div>
                        </div>
                    </div>
                </div>
                <div style="margin-top:12px;background:#ffffff08;border-radius:6px;height:8px;overflow:hidden">
                    <div style="width:{min(_t_pct, 100)}%;height:100%;background:linear-gradient(90deg,{_prov_color},{_prov_color}cc);
                        border-radius:6px;transition:width 0.5s"></div>
                </div>
            </div>''', unsafe_allow_html=True)

            # Tabla de productos
            _rows_html = ""
            for _, _r in _prov_data.iterrows():
                _v = int(_r["Vendidos"])
                _i = int(_r["Stock Inicial"])
                _q = int(_r["Quedan"])
                _p = _r["% Vendido"]
                _vel = _r["Vel/día"]
                _ds = _r["Días de stock"]
                _n = _r["Neto $"]

                if _v == 0:
                    _badge = '<span style="background:#e9456020;color:#e94560;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:600">SIN VENTAS</span>'
                elif _p >= 60:
                    _badge = '<span style="background:#00c96b20;color:#00c96b;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:600">REPONER</span>'
                elif _vel >= 0.5:
                    _badge = '<span style="background:#00c96b20;color:#00c96b;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:600">RAPIDO</span>'
                elif _vel >= 0.15:
                    _badge = '<span style="background:#3a86ff20;color:#3a86ff;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:600">NORMAL</span>'
                else:
                    _badge = '<span style="background:#f7b73120;color:#f7b731;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:600">LENTO</span>'

                _bar_pct = min(_p, 100)
                _bar_color = "#00c96b" if _p >= 40 else _prov_color if _p >= 15 else "#e94560"

                _rows_html += f'''<tr style="border-bottom:1px solid #ffffff06">
                    <td style="padding:10px 8px;color:#eeeeff;font-size:0.84rem;font-weight:500">{_r["Tipo"]}</td>
                    <td style="padding:10px 4px;text-align:center;color:#8888aa;font-size:0.82rem">{_i}</td>
                    <td style="padding:10px 4px;text-align:center;color:#00c96b;font-weight:700;font-size:0.88rem">{_v}</td>
                    <td style="padding:10px 4px;text-align:center;color:#e94560;font-weight:600;font-size:0.84rem">{_q}</td>
                    <td style="padding:10px 8px;min-width:100px">
                        <div style="background:#ffffff08;border-radius:4px;height:6px;overflow:hidden">
                            <div style="width:{_bar_pct}%;height:100%;background:{_bar_color};border-radius:4px"></div>
                        </div>
                        <div style="font-size:0.65rem;color:#6666aa;text-align:center;margin-top:2px">{_p:.0f}%</div>
                    </td>
                    <td style="padding:10px 4px;text-align:center;color:#fff;font-weight:600;font-size:0.84rem">{_vel:.2f}</td>
                    <td style="padding:10px 4px;text-align:center;color:#8888aa;font-size:0.8rem">{_ds}d</td>
                    <td style="padding:10px 4px;text-align:right;color:#f7b731;font-weight:600;font-size:0.84rem">{fmt(_n)}</td>
                    <td style="padding:10px 4px;text-align:center">{_badge}</td>
                </tr>'''

            st.markdown(f'''<table style="width:100%;border-collapse:collapse;margin:0 0 4px 0">
                <thead><tr style="border-bottom:2px solid {_prov_color}30">
                    <th style="text-align:left;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Producto</th>
                    <th style="text-align:center;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Ini</th>
                    <th style="text-align:center;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Vend</th>
                    <th style="text-align:center;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Quedan</th>
                    <th style="text-align:center;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Avance</th>
                    <th style="text-align:center;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Vel/dia</th>
                    <th style="text-align:center;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Stock p/</th>
                    <th style="text-align:right;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Neto</th>
                    <th style="text-align:center;padding:8px;color:#6666aa;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;font-weight:600">Estado</th>
                </tr></thead>
                <tbody>{_rows_html}</tbody>
            </table>''', unsafe_allow_html=True)

            # Detalle de ventas individuales (expandible)
            if not df.empty:
                _nuevos_prov = df[(df["stock_tipo"] == "NUEVO") & (df["proveedor_nuevo"] == _prov_r)]
                if not _nuevos_prov.empty:
                    with st.expander(f"Ver {len(_nuevos_prov)} ventas individuales de {_prov_r}"):
                        _det_html = ""
                        for _, _v in _nuevos_prov.sort_values("fecha").iterrows():
                            _canal_color = "#3a86ff" if _v["canal"] == "Online" else "#8888aa"
                            _det_html += f'''<tr style="border-bottom:1px solid #ffffff06">
                                <td style="padding:6px 8px;color:#8888aa;font-size:0.78rem">{str(_v["fecha"])[:10]}</td>
                                <td style="padding:6px 8px;color:#eeeeff;font-size:0.82rem">{_v["producto"]}</td>
                                <td style="padding:6px 4px;text-align:center;color:#00c96b;font-weight:600">{int(_v["cantidad"])}</td>
                                <td style="padding:6px 4px;text-align:right;color:#f7b731;font-weight:600;font-size:0.82rem">{fmt(_v["neto"])}</td>
                                <td style="padding:6px 4px;text-align:center;color:{_canal_color};font-size:0.78rem">{_v["canal"]}</td>
                            </tr>'''
                        st.markdown(f'''<table style="width:100%;border-collapse:collapse">
                            <thead><tr style="border-bottom:1px solid #ffffff10">
                                <th style="text-align:left;padding:6px 8px;color:#6666aa;font-size:0.65rem;text-transform:uppercase">Fecha</th>
                                <th style="text-align:left;padding:6px 8px;color:#6666aa;font-size:0.65rem;text-transform:uppercase">Producto</th>
                                <th style="text-align:center;padding:6px 4px;color:#6666aa;font-size:0.65rem;text-transform:uppercase">Cant</th>
                                <th style="text-align:right;padding:6px 4px;color:#6666aa;font-size:0.65rem;text-transform:uppercase">Neto</th>
                                <th style="text-align:center;padding:6px 4px;color:#6666aa;font-size:0.65rem;text-transform:uppercase">Canal</th>
                            </tr></thead>
                            <tbody>{_det_html}</tbody>
                        </table>''', unsafe_allow_html=True)

        # Boton de descarga (genera texto plano para compartir)
        def _generar_txt_proveedor(prov_filtro, df_stock_data, df_ventas):
            _provs = ["KAZUMA", "LISBON", "DISTRICT"] if prov_filtro == "TODOS" else [prov_filtro]
            _l = [f"THE ROOM ARGENTINA — Reporte de stock — {hoy.strftime('%d/%m/%Y')}", ""]
            for _pv in _provs:
                _pd = df_stock_data[df_stock_data["Proveedor"] == _pv]
                if _pd.empty:
                    continue
                _ti = int(_pd["Stock Inicial"].sum())
                _tv = int(_pd["Vendidos"].sum())
                _tq = int(_pd["Quedan"].sum())
                _tn = _pd["Neto $"].sum()
                _tp = round(_tv / _ti * 100, 1) if _ti > 0 else 0
                _td = int(_pd["Días transcurridos"].iloc[0])
                _l += [f"{_pv} — {_td} dias — {_tv}/{_ti} vendidos ({_tp}%) — quedan {_tq} — ${_tn:,.0f} neto", ""]
                _l.append(f"{'Producto':<40} {'Ini':>4} {'Vend':>5} {'Qued':>5} {'%':>6} {'Vel/d':>6} {'Stock p/':>8} {'Neto $':>12} {'Estado':>10}")
                _l.append("-" * 105)
                for _, _r in _pd.iterrows():
                    _v = int(_r["Vendidos"]); _i = int(_r["Stock Inicial"]); _q = int(_r["Quedan"])
                    _e = "SIN VENTAS" if _v == 0 else "REPONER" if _r["% Vendido"] >= 60 else "RAPIDO" if _r["Vel/día"] >= 0.5 else "NORMAL" if _r["Vel/día"] >= 0.15 else "LENTO"
                    _l.append(f"{str(_r['Tipo']):<40} {_i:>4} {_v:>5} {_q:>5} {_r['% Vendido']:>5.1f}% {_r['Vel/día']:>6.2f} {str(_r['Días de stock']):>8}d ${_r['Neto $']:>11,.0f} {_e:>10}")
                if not df_ventas.empty:
                    _nv = df_ventas[(df_ventas["stock_tipo"] == "NUEVO") & (df_ventas["proveedor_nuevo"] == _pv)]
                    if not _nv.empty:
                        _l += ["", f"Detalle de ventas {_pv}:"]
                        for _, _vr in _nv.sort_values("fecha").iterrows():
                            _l.append(f"  {str(_vr['fecha'])[:10]}  {_vr['producto']:<45} {int(_vr['cantidad']):>3} uds  ${_vr['neto']:>9,.0f}  {_vr['canal']}")
                _sv = _pd[_pd["Vendidos"] == 0]
                if not _sv.empty:
                    _l.append("")
                    for _, _svr in _sv.iterrows():
                        _l.append(f"  !! {_svr['Tipo']} — {int(_svr['Stock Inicial'])} uds, {int(_svr['Días transcurridos'])} dias SIN VENDER")
                _l.append("")
            return "\n".join(_l)

        _rep_txt = _generar_txt_proveedor(_prov_reporte, df_stock, df)
        st.download_button(
            label=f"Descargar reporte {_prov_reporte} (.txt)",
            data=_rep_txt,
            file_name=f"reporte_stock_{_prov_reporte.lower()}_{hoy.isoformat()}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        # Resumen total nuevo
        seccion("Resumen stock nuevo")
        totales = df_stock.groupby("Proveedor").agg(
            Inicial=("Stock Inicial", "sum"),
            Vendidos=("Vendidos", "sum"),
            Quedan=("Quedan", "sum"),
            Neto=("Neto $", "sum"),
        ).reset_index()

        cols = st.columns(len(totales))
        for i, (_, r) in enumerate(totales.iterrows()):
            pct = r["Vendidos"] / r["Inicial"] * 100 if r["Inicial"] > 0 else 0
            col_name = list(COLORES.keys())[i % len(COLORES)]
            color_key = ["azul", "morado", "amarillo"][i % 3]
            with cols[i]:
                st.markdown(metric_card(
                    "👕", r["Proveedor"],
                    f"{int(r['Vendidos'])}/{int(r['Inicial'])} uds",
                    f"{pct:.0f}% vendido · {fmt(r['Neto'])} neto",
                    color_key,
                ), unsafe_allow_html=True)

        # Detalle por proveedor
        for proveedor in ["KAZUMA", "LISBON", "DISTRICT"]:
            sub = df_stock[df_stock["Proveedor"] == proveedor].copy()
            if sub.empty:
                continue

            tot_ini  = sub["Stock Inicial"].sum()
            tot_vend = sub["Vendidos"].sum()
            pct_prov = round(tot_vend / tot_ini * 100, 1) if tot_ini > 0 else 0
            seccion(f"{proveedor} — {int(tot_vend)}/{int(tot_ini)} uds vendidas ({pct_prov}%)")

            hc = st.columns([3, 1, 1, 1, 2, 1, 1, 1, 2])
            for lbl, col in zip(
                ["Producto","Inicial","Vendidos","Quedan","Avance","Vel/dia","Para","Neto","Estado"],
                hc,
            ):
                col.markdown(
                    f'<div style="font-size:0.67rem;color:#6666aa;text-transform:uppercase;'
                    f'letter-spacing:1px;padding:4px 0;font-weight:600">{lbl}</div>',
                    unsafe_allow_html=True,
                )

            for _, r in sub.iterrows():
                pct        = r["% Vendido"]
                vel        = r["Vel/día"]
                dias_st    = r["Días de stock"]
                dias_txt   = str(dias_st) if dias_st != "∞" else "∞"
                bar_c      = "#00c96b" if pct >= 50 else "#3a86ff" if pct >= 20 else "#e94560"
                neto_txt   = fmt(r["Neto $"])
                tipo_txt   = r["Tipo"]
                ini_txt    = int(r["Stock Inicial"])
                vend_txt   = int(r["Vendidos"])
                quedan_txt = int(r["Quedan"])

                if pct >= 60:
                    bcls, btxt = "badge-verde",    "Reposicion"
                elif r["Vendidos"] == 0:
                    bcls, btxt = "badge-rojo",     "Sin ventas"
                elif isinstance(dias_st, int) and dias_st < 30:
                    bcls, btxt = "badge-amarillo", "Stock bajo"
                elif isinstance(dias_st, int) and dias_st > 120:
                    bcls, btxt = "badge-naranja",  "Lento"
                else:
                    bcls, btxt = "badge-gris",     "Normal"

                rc = st.columns([3, 1, 1, 1, 2, 1, 1, 1, 2])
                rc[0].markdown(f'<div style="color:#eeeeff;font-weight:600;font-size:0.88rem;padding:5px 0">{tipo_txt}</div>', unsafe_allow_html=True)
                rc[1].markdown(f'<div style="color:#aaaacc;padding:5px 0;text-align:center">{ini_txt}</div>', unsafe_allow_html=True)
                rc[2].markdown(f'<div style="color:#00c96b;font-weight:700;padding:5px 0;text-align:center">{vend_txt}</div>', unsafe_allow_html=True)
                rc[3].markdown(f'<div style="color:#aaaacc;padding:5px 0;text-align:center">{quedan_txt}</div>', unsafe_allow_html=True)
                rc[4].markdown(
                    f'<div style="padding:7px 0"><div style="background:rgba(255,255,255,0.06);'
                    f'border-radius:3px;height:5px;overflow:hidden"><div style="width:{pct:.0f}%;'
                    f'height:100%;background:{bar_c};border-radius:3px"></div></div>'
                    f'<span style="font-size:0.74rem;color:#8888aa">{pct:.0f}%</span></div>',
                    unsafe_allow_html=True)
                rc[5].markdown(f'<div style="color:#8888aa;padding:5px 0;text-align:center">{vel:.2f}/d</div>', unsafe_allow_html=True)
                if dias_txt == "∞":
                    dias_disp = "∞"
                else:
                    _d = int(dias_txt)
                    if _d > 365:
                        dias_disp = f"~{_d//365}a"
                    elif _d > 60:
                        dias_disp = f"~{_d//30}m"
                    else:
                        dias_disp = f"{_d}d"
                rc[6].markdown(f'<div style="color:#8888aa;padding:5px 0;text-align:center">{dias_disp}</div>', unsafe_allow_html=True)
                rc[7].markdown(f'<div style="color:#fff;font-weight:700;padding:5px 0;text-align:right">{neto_txt}</div>', unsafe_allow_html=True)
                rc[8].markdown(f'<span class="badge {bcls}">{btxt}</span>', unsafe_allow_html=True)

            st.markdown('<hr style="border:none;border-top:1px solid #ffffff08;margin:6px 0 18px 0">', unsafe_allow_html=True)

        # ── Velocidad por producto individual (desde Dux) ────────────────────
        seccion("Velocidad por producto — detalle individual")

        if sin_datos:
            alerta_html("Subi el .xls de Dux para ver el detalle por producto", "azul")
        else:
            # Tomamos todos los productos del período actual (nuevo + viejo)
            # para mostrar qué vendió y qué no
            from datetime import timedelta
            _fecha_ini_stock = min(
                pd.Timestamp(item["fecha_ingreso"]) for item in stock_ini
            ).date()

            # Productos nuevos vendidos: de Dux desde la fecha del primer ingreso
            nuevos_dux = df[df["stock_tipo"] == "NUEVO"].copy() if not df.empty else pd.DataFrame()

            if not nuevos_dux.empty:
                # Agrupar por producto
                prod_vel = (
                    nuevos_dux.groupby("producto")
                    .agg(
                        vendidos=("cantidad", "sum"),
                        neto=("neto", "sum"),
                        proveedor=("proveedor_nuevo", "first"),
                    )
                    .reset_index()
                    .sort_values("vendidos", ascending=False)
                )

                # Calcular días desde ingreso del proveedor
                prov_fechas = {item["proveedor"]: pd.Timestamp(item["fecha_ingreso"]).date() for item in stock_ini}
                def _dias_prov(prov):
                    fi = prov_fechas.get(prov, _fecha_ini_stock)
                    return max((hoy - fi).days, 1)

                prod_vel["dias"] = prod_vel["proveedor"].apply(_dias_prov)
                prod_vel["vel"] = prod_vel["vendidos"] / prod_vel["dias"]

                # Ahora buscar todos los productos del stock_inicial que NO aparecen en Dux
                # (prefijos de cada item)
                todos_prefijos = []
                for item in stock_ini:
                    for p in item["prefijos"]:
                        todos_prefijos.append({
                            "prefijo": p.upper(),
                            "proveedor": item["proveedor"],
                            "fecha_ingreso": item["fecha_ingreso"],
                        })

                productos_en_dux = set(prod_vel["producto"].str.upper())
                sin_venta_rows = []
                for pfx_item in todos_prefijos:
                    # Ver si algún producto con este prefijo aparece en Dux
                    tiene = any(p.startswith(pfx_item["prefijo"]) for p in productos_en_dux)
                    if not tiene:
                        dias_pfx = max((hoy - pd.Timestamp(pfx_item["fecha_ingreso"]).date()).days, 1)
                        sin_venta_rows.append({
                            "producto": pfx_item["prefijo"] + " (sin ventas en Dux)",
                            "vendidos": 0,
                            "neto": 0.0,
                            "proveedor": pfx_item["proveedor"],
                            "dias": dias_pfx,
                            "vel": 0.0,
                        })

                if sin_venta_rows:
                    prod_vel = pd.concat(
                        [prod_vel, pd.DataFrame(sin_venta_rows)],
                        ignore_index=True
                    ).sort_values(["proveedor", "vendidos"], ascending=[True, False])

                # Header tabla
                hv = st.columns([4, 1, 1, 1, 1, 2])
                for lbl, col in zip(["Producto", "Prov.", "Días", "Vendidos", "Vel/día", "Estado"], hv):
                    col.markdown(
                        f'<div style="font-size:0.67rem;color:#6666aa;text-transform:uppercase;'
                        f'letter-spacing:1px;padding:4px 0;font-weight:600">{lbl}</div>',
                        unsafe_allow_html=True,
                    )

                prov_colores = {"KAZUMA": "#3a86ff", "LISBON": "#8b5cf6", "DISTRICT": "#f7b731"}
                _ultimo_prov = None
                for _, r in prod_vel.iterrows():
                    if r["proveedor"] != _ultimo_prov:
                        st.markdown(
                            f'<div style="font-size:0.7rem;font-weight:700;color:{prov_colores.get(str(r["proveedor"]),"#aaaacc")};'
                            f'text-transform:uppercase;letter-spacing:1px;padding:6px 0 2px 0;'
                            f'border-top:1px solid #ffffff08;margin-top:4px">{r["proveedor"]}</div>',
                            unsafe_allow_html=True,
                        )
                        _ultimo_prov = r["proveedor"]

                    vel_v = r["vel"]
                    vend_v = int(r["vendidos"])

                    if vend_v == 0:
                        bcls2, btxt2 = "badge-rojo", "Sin ventas"
                        vel_color = "#e94560"
                    elif vel_v >= 1.0:
                        bcls2, btxt2 = "badge-verde", "Rapido"
                        vel_color = "#00c96b"
                    elif vel_v >= 0.3:
                        bcls2, btxt2 = "badge-gris", "Normal"
                        vel_color = "#aaaacc"
                    else:
                        bcls2, btxt2 = "badge-naranja", "Lento"
                        vel_color = "#ffaa55"

                    rv = st.columns([4, 1, 1, 1, 1, 2])
                    rv[0].markdown(f'<div style="color:#eeeeff;font-size:0.84rem;padding:4px 0">{r["producto"]}</div>', unsafe_allow_html=True)
                    rv[1].markdown(f'<div style="color:{prov_colores.get(str(r["proveedor"]),"#aaaacc")};font-size:0.8rem;padding:4px 0;font-weight:600">{r["proveedor"]}</div>', unsafe_allow_html=True)
                    rv[2].markdown(f'<div style="color:#666688;font-size:0.8rem;padding:4px 0;text-align:center">{int(r["dias"])}d</div>', unsafe_allow_html=True)
                    rv[3].markdown(f'<div style="color:#00c96b;font-weight:700;font-size:0.88rem;padding:4px 0;text-align:center">{vend_v}</div>', unsafe_allow_html=True)
                    rv[4].markdown(f'<div style="color:{vel_color};font-weight:700;font-size:0.88rem;padding:4px 0;text-align:center">{vel_v:.2f}</div>', unsafe_allow_html=True)
                    rv[5].markdown(f'<span class="badge {bcls2}">{btxt2}</span>', unsafe_allow_html=True)
            else:
                alerta_html("No hay productos del stock nuevo en el Dux aún — verificá que los archivos cargados incluyan ventas del período", "amarillo")

        # ── Velocidad detallada por SKU (talle/color) — Compras 2026 ────────
        from data_processor import load_stock_dux
        df_stock_dux = load_stock_dux("data/stock_dux.xls")

        if not df_stock_dux.empty and stock_ini:
            seccion("Velocidad por SKU — detalle talle/color (Compras 2026)")
            st.markdown(
                '<div style="color:#8888aa;font-size:0.78rem;margin-bottom:12px">'
                'Cruce entre stock actual de Dux y ventas registradas. Datos precisos al último .xls cargado.</div>',
                unsafe_allow_html=True
            )

            _all_prefixes = []
            for _item in stock_ini:
                for _p in _item["prefijos"]:
                    _all_prefixes.append((_p.upper(), _item["proveedor"], _item["tipo"],
                                          _item["costo_unit"], _item["fecha_ingreso"]))

            for _prov_vel in ["KAZUMA", "LISBON", "DISTRICT"]:
                _prov_prefixes = [(p, pr, t, c, f) for p, pr, t, c, f in _all_prefixes if pr == _prov_vel]
                if not _prov_prefixes:
                    continue

                _fecha_ing = pd.Timestamp(_prov_prefixes[0][4]).date()
                _dias_tr = max((hoy - _fecha_ing).days, 1)

                # Recopilar SKUs de este proveedor
                _sku_rows = []
                for _pfx, _pr, _tipo, _costo_u, _fi in _prov_prefixes:
                    _mask_stk = df_stock_dux["producto"].str.upper().str.startswith(_pfx)
                    _sub_stk = df_stock_dux[_mask_stk]
                    for _, _rs in _sub_stk.iterrows():
                        _prod_name = _rs["producto"]
                        _stock_act = int(_rs["cantidad"])
                        # Ventas de este SKU exacto
                        if not df.empty:
                            _v_mask = df["producto"].str.upper() == _prod_name.upper()
                            _vendidos_sku = int(df.loc[_v_mask, "cantidad"].sum())
                            _neto_sku = df.loc[_v_mask, "neto"].sum()
                        else:
                            _vendidos_sku = 0
                            _neto_sku = 0
                        _stock_ini_sku = _stock_act + _vendidos_sku
                        _vel_sku = _vendidos_sku / _dias_tr
                        _dias_stock_sku = round(_stock_act / _vel_sku) if _vel_sku > 0 else 9999
                        _ganancia_sku = _neto_sku - (_costo_u * _vendidos_sku)
                        _margen_sku = (_ganancia_sku / _neto_sku * 100) if _neto_sku > 0 else 0

                        _sku_rows.append({
                            "producto": _prod_name,
                            "tipo": _tipo,
                            "stock_ini": _stock_ini_sku,
                            "vendidos": _vendidos_sku,
                            "stock_act": _stock_act,
                            "vel": _vel_sku,
                            "dias_stock": _dias_stock_sku,
                            "neto": _neto_sku,
                            "ganancia": _ganancia_sku,
                            "margen": _margen_sku,
                            "costo_u": _costo_u,
                        })

                if not _sku_rows:
                    continue

                _total_ini = sum(r["stock_ini"] for r in _sku_rows)
                _total_vend = sum(r["vendidos"] for r in _sku_rows)
                _total_quedan = sum(r["stock_act"] for r in _sku_rows)
                _total_neto = sum(r["neto"] for r in _sku_rows)
                _pct_prov = round(_total_vend / _total_ini * 100, 1) if _total_ini > 0 else 0
                _vel_prov = _total_vend / _dias_tr
                _costo_parado = sum(r["stock_act"] * r["costo_u"] for r in _sku_rows)

                _prov_colors = {"KAZUMA": "#3a86ff", "LISBON": "#8b5cf6", "DISTRICT": "#f7b731"}
                _pc = _prov_colors.get(_prov_vel, "#aaaacc")

                st.markdown(
                    f'<div style="margin:18px 0 8px 0;padding:10px 14px;border-left:3px solid {_pc};'
                    f'background:rgba(255,255,255,0.03);border-radius:0 6px 6px 0">'
                    f'<span style="font-weight:700;color:{_pc};font-size:1rem">{_prov_vel}</span>'
                    f'<span style="color:#8888aa;font-size:0.82rem;margin-left:16px">'
                    f'Ingresó {_fecha_ing.strftime("%d/%m")} · {_dias_tr} días · '
                    f'{_total_vend}/{_total_ini} vendidos ({_pct_prov}%) · '
                    f'Vel {_vel_prov:.2f}/día · '
                    f'Neto {fmt(_total_neto)} · '
                    f'Costo parado {fmt(_costo_parado)}'
                    f'</span></div>',
                    unsafe_allow_html=True
                )

                # Tabla de SKUs
                _rows_html = ""
                _sku_rows_sorted = sorted(_sku_rows, key=lambda x: (-x["vendidos"], x["producto"]))
                for _sr in _sku_rows_sorted:
                    if _sr["stock_act"] == 0 and _sr["vendidos"] == 0:
                        continue  # SKU agotado y sin data
                    _v = _sr["vendidos"]
                    _sa = _sr["stock_act"]
                    _vel_s = _sr["vel"]
                    _ds = _sr["dias_stock"]

                    # Color de estado
                    if _v == 0 and _sa > 0:
                        _est = '<span style="color:#e94560;font-weight:700">SIN VENTA</span>'
                        _row_bg = "rgba(233,69,96,0.05)"
                    elif _vel_s >= 0.5:
                        _est = '<span style="color:#00c96b;font-weight:700">ROTA BIEN</span>'
                        _row_bg = "rgba(0,201,107,0.05)"
                    elif _vel_s >= 0.15:
                        _est = '<span style="color:#aaaacc">NORMAL</span>'
                        _row_bg = "transparent"
                    elif _sa == 0:
                        _est = '<span style="color:#00c96b;font-weight:700">AGOTADO</span>'
                        _row_bg = "rgba(0,201,107,0.08)"
                    else:
                        _est = '<span style="color:#ffaa55;font-weight:700">LENTO</span>'
                        _row_bg = "rgba(255,170,85,0.05)"

                    _ds_txt = f"{_ds}d" if _ds < 9999 else "∞"
                    if isinstance(_ds, int) and _ds > 365:
                        _ds_txt = f"+1a"
                    elif isinstance(_ds, int) and _ds > 90:
                        _ds_txt = f"~{_ds//30}m"

                    _rows_html += (
                        f'<tr style="background:{_row_bg}">'
                        f'<td style="font-size:0.82rem">{_sr["producto"]}</td>'
                        f'<td style="text-align:center;color:#8888aa">{_sr["stock_ini"]}</td>'
                        f'<td style="text-align:center;color:#00c96b;font-weight:700">{_v}</td>'
                        f'<td style="text-align:center;color:#eeeeff">{_sa}</td>'
                        f'<td style="text-align:center;color:{"#00c96b" if _vel_s >= 0.3 else "#e94560" if _vel_s == 0 else "#ffaa55"};font-weight:600">{_vel_s:.2f}</td>'
                        f'<td style="text-align:center;color:#8888aa">{_ds_txt}</td>'
                        f'<td style="text-align:right">{fmt(_sr["neto"]) if _sr["neto"] > 0 else "-"}</td>'
                        f'<td style="text-align:center">{_est}</td>'
                        f'</tr>'
                    )

                st.markdown(
                    f'<div class="tabla-wrapper"><table class="tabla-custom">'
                    f'<thead><tr>'
                    f'<th>Producto (talle/color)</th>'
                    f'<th style="text-align:center">Ini</th>'
                    f'<th style="text-align:center">Vend</th>'
                    f'<th style="text-align:center">Stock</th>'
                    f'<th style="text-align:center">Vel/día</th>'
                    f'<th style="text-align:center">Para</th>'
                    f'<th style="text-align:right">Neto</th>'
                    f'<th style="text-align:center">Estado</th>'
                    f'</tr></thead><tbody>{_rows_html}</tbody></table></div>',
                    unsafe_allow_html=True
                )

        # ── Inventario completo desde Dux ─────────────────────────────────────

        if not df_stock_dux.empty:
            con_stock = df_stock_dux[df_stock_dux["cantidad"] > 0].copy()
            seccion(f"Inventario completo — {int(con_stock['cantidad'].sum())} uds · {fmt(con_stock['valor_total'].sum())} a costo")

            # KPIs de stock
            ks1, ks2, ks3, ks4 = st.columns(4)
            with ks1:
                st.markdown(metric_card("📦", "SKUs con stock", str(len(con_stock)), f"de {len(df_stock_dux)} totales", "azul"), unsafe_allow_html=True)
            with ks2:
                st.markdown(metric_card("👕", "Unidades", str(int(con_stock["cantidad"].sum())), "en el local", "verde"), unsafe_allow_html=True)
            with ks3:
                st.markdown(metric_card("💰", "Valor a costo", fmt(con_stock["valor_total"].sum()), "precio de compra", "amarillo"), unsafe_allow_html=True)
            with ks4:
                val_venta_est = con_stock["valor_total"].sum() * 2.3
                st.markdown(metric_card("🏷", "Valor venta est.", fmt(val_venta_est), "markup x2.3", "morado"), unsafe_allow_html=True)

            # Por rubro
            seccion("Stock por rubro")
            por_rubro = con_stock.groupby("rubro").agg(
                uds=("cantidad","sum"), valor=("valor_total","sum"), skus=("producto","count")
            ).sort_values("valor", ascending=False)
            rows_rub = ""
            for rub, r in por_rubro.iterrows():
                pct = r["valor"] / con_stock["valor_total"].sum() * 100
                rows_rub += f'<tr><td style="font-weight:600">{rub}</td><td style="text-align:center">{int(r["skus"])}</td><td style="text-align:center">{int(r["uds"])}</td><td style="text-align:right">{fmt(r["valor"])}</td><td style="text-align:right;color:#8888aa">{pct:.0f}%</td></tr>'
            st.markdown(
                f'<div class="tabla-wrapper"><table class="tabla-custom"><thead><tr><th>Rubro</th><th style="text-align:center">SKUs</th><th style="text-align:center">Uds</th><th style="text-align:right">Valor costo</th><th style="text-align:right">%</th></tr></thead><tbody>{rows_rub}</tbody></table></div>',
                unsafe_allow_html=True
            )

            # Mapeo razón social → marca
            MARCA_MAP = {
                "DANDY IND S.R.L.": "Lisbon",
                "TARKUS TREND S.R.L.": "District",
                "DACOB S.A": "Kazuma",
                "VISTE VILO SRL, VISTE VILO": "Vilo",
                "VISTE VILO SRL": "Vilo",
                "VINTAGE S A S. A.": "Vintage",
                "GRUPO VEGAS": "Grupo Vegas",
                "MANKI": "Manki",
                "KLHO MEN S.A.S.": "Klho Men",
                "ZERO ES TRES S.A.": "Zero es Tres",
                "SYNDICATE": "Syndicate",
                "PUPEMODA S.R.L.": "Pupemoda",
                "BBN S.R.L.": "BBN",
                "WILD S.A.": "Wild",
                "BOND JEANS S.R.L": "Bond Jeans",
            }
            def _marca(prov_dux):
                return MARCA_MAP.get(prov_dux, prov_dux)

            con_stock["marca"] = con_stock["proveedor_dux"].apply(_marca)

            # Por proveedor
            seccion("Stock por marca")
            por_prov_s = con_stock.groupby("marca").agg(
                uds=("cantidad","sum"), valor=("valor_total","sum"), skus=("producto","count")
            ).sort_values("valor", ascending=False)
            rows_prov = ""
            for prov_s, r in por_prov_s.iterrows():
                rows_prov += f'<tr><td style="font-weight:600">{prov_s}</td><td style="text-align:center">{int(r["skus"])}</td><td style="text-align:center">{int(r["uds"])}</td><td style="text-align:right">{fmt(r["valor"])}</td></tr>'
            st.markdown(
                f'<div class="tabla-wrapper"><table class="tabla-custom"><thead><tr><th>Marca</th><th style="text-align:center">SKUs</th><th style="text-align:center">Uds</th><th style="text-align:right">Valor costo</th></tr></thead><tbody>{rows_prov}</tbody></table></div>',
                unsafe_allow_html=True
            )

            # ── Rentabilidad por marca ─────────────────────────────────────────
            seccion("Rentabilidad por marca — donde conviene invertir")

            if not sin_datos:
                # Cruzar ventas con costos del stock Dux
                _costo_map = {}
                for _, _rs in df_stock_dux.iterrows():
                    _costo_map[_rs["producto"].upper()] = {"costo": _rs["costo_unit"], "marca": _marca(_rs["proveedor_dux"])}

                _rent_rows = []
                for _, _rv in df.iterrows():
                    _prod_up = str(_rv["producto"]).upper()
                    _info = _costo_map.get(_prod_up, {})
                    _costo_u = _info.get("costo", _rv.get("costo", 0) if "costo" in df.columns else 0)
                    _marca_v = _info.get("marca", "Sin marca")
                    _neto_v = _rv["neto"]
                    _cant_v = _rv["cantidad"]
                    _gan = _neto_v - (_costo_u * _cant_v)
                    _rent_rows.append({"marca": _marca_v, "producto": _prod_up, "neto": _neto_v, "costo_total": _costo_u * _cant_v, "ganancia": _gan, "cantidad": _cant_v})

                _df_rent = pd.DataFrame(_rent_rows)
                if not _df_rent.empty:
                    _por_marca = _df_rent.groupby("marca").agg(
                        neto=("neto","sum"), costo=("costo_total","sum"),
                        ganancia=("ganancia","sum"), uds=("cantidad","sum"),
                    ).sort_values("ganancia", ascending=False)
                    _por_marca["margen"] = (_por_marca["ganancia"] / _por_marca["neto"] * 100).round(1)

                    # Separar nuevo vs viejo
                    _df_rent["stock_tipo"] = df["stock_tipo"].values[:len(_df_rent)] if len(_df_rent) <= len(df) else "VIEJO"
                    # Re-merge stock_tipo from original df
                    _df_rent_m = _df_rent.copy()
                    _df_rent_m["stock_tipo"] = df["stock_tipo"].values

                    _rent_nuevo = _df_rent_m[_df_rent_m["stock_tipo"] == "NUEVO"]
                    _rent_viejo = _df_rent_m[_df_rent_m["stock_tipo"] == "VIEJO"]

                    def _tabla_rent(df_r, titulo, emoji):
                        if df_r.empty:
                            return
                        pm = df_r.groupby("marca").agg(
                            neto=("neto","sum"), costo=("costo_total","sum"),
                            ganancia=("ganancia","sum"), uds=("cantidad","sum"),
                        ).sort_values("ganancia", ascending=False)
                        pm["margen"] = (pm["ganancia"] / pm["neto"] * 100).round(1)
                        total_gan = pm["ganancia"].sum()
                        total_neto = pm["neto"].sum()
                        total_margen = total_gan / total_neto * 100 if total_neto > 0 else 0

                        st.markdown(f"""
                        <div style="background:#1a1a2e;border:1px solid #ffffff0e;border-radius:12px;padding:14px 20px;margin:8px 0">
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                                <span style="color:#eeeeff;font-weight:700;font-size:0.95rem">{emoji} {titulo}</span>
                                <span style="color:#00c96b;font-weight:700;font-size:1.1rem">Ganancia: {fmt(total_gan)} ({total_margen:.0f}%)</span>
                            </div>
                        </div>""", unsafe_allow_html=True)

                        rows_r = ""
                        for m, r in pm.iterrows():
                            cg = "#00c96b" if r["ganancia"] > 0 else "#e94560"
                            cm = "#00c96b" if r["margen"] > 25 else "#f7b731" if r["margen"] > 15 else "#e94560"
                            rows_r += (
                                f'<tr><td style="font-weight:700">{m}</td>'
                                f'<td style="text-align:right">{fmt(r["neto"])}</td>'
                                f'<td style="text-align:right;color:#8888aa">{fmt(r["costo"])}</td>'
                                f'<td style="text-align:right;color:{cg};font-weight:700">{fmt(r["ganancia"])}</td>'
                                f'<td style="text-align:center;color:{cm};font-weight:700">{r["margen"]:.0f}%</td>'
                                f'<td style="text-align:center">{int(r["uds"])}</td></tr>'
                            )
                        rows_r += (
                            f'<tr style="border-top:2px solid #ffffff15">'
                            f'<td style="font-weight:800;color:#eee">TOTAL</td>'
                            f'<td style="text-align:right;font-weight:700">{fmt(total_neto)}</td>'
                            f'<td></td>'
                            f'<td style="text-align:right;color:#00c96b;font-weight:800">{fmt(total_gan)}</td>'
                            f'<td style="text-align:center;font-weight:700">{total_margen:.0f}%</td>'
                            f'<td style="text-align:center">{int(pm["uds"].sum())}</td></tr>'
                        )
                        st.markdown(
                            f'<div class="tabla-wrapper"><table class="tabla-custom">'
                            f'<thead><tr><th>Marca</th><th style="text-align:right">Venta</th>'
                            f'<th style="text-align:right">Costo</th><th style="text-align:right">Ganancia</th>'
                            f'<th style="text-align:center">Margen</th><th style="text-align:center">Uds</th></tr></thead>'
                            f'<tbody>{rows_r}</tbody></table></div>',
                            unsafe_allow_html=True,
                        )
                        return pm

                    pm_nuevo = _tabla_rent(_rent_nuevo, "Stock NUEVO 2026 — lo que compraste este ano", "🆕")
                    pm_viejo = _tabla_rent(_rent_viejo, "Stock VIEJO (temporadas anteriores)", "📦")

                    # Tabla de rentabilidad general (todas las marcas)
                    rows_rent = ""
                    mejor_marca = _por_marca.index[0] if len(_por_marca) > 0 else ""
                    for m, r in _por_marca.iterrows():
                        color_g = "#00c96b" if r["ganancia"] > 0 else "#e94560"
                        color_m = "#00c96b" if r["margen"] > 25 else "#f7b731" if r["margen"] > 15 else "#e94560"
                        star = " *" if m == mejor_marca else ""
                        rows_rent += (
                            f'<tr>'
                            f'<td style="font-weight:700">{m}{star}</td>'
                            f'<td style="text-align:right">{fmt(r["neto"])}</td>'
                            f'<td style="text-align:right;color:#8888aa">{fmt(r["costo"])}</td>'
                            f'<td style="text-align:right;color:{color_g};font-weight:700">{fmt(r["ganancia"])}</td>'
                            f'<td style="text-align:center;color:{color_m};font-weight:700">{r["margen"]:.0f}%</td>'
                            f'<td style="text-align:center">{int(r["uds"])}</td>'
                            f'</tr>'
                        )
                    st.markdown(
                        f'<div class="tabla-wrapper"><table class="tabla-custom">'
                        f'<thead><tr><th>Marca</th><th style="text-align:right">Venta neta</th>'
                        f'<th style="text-align:right">Costo</th><th style="text-align:right">Ganancia</th>'
                        f'<th style="text-align:center">Margen</th><th style="text-align:center">Uds</th></tr></thead>'
                        f'<tbody>{rows_rent}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

                    # Recomendación
                    if mejor_marca:
                        _m_data = _por_marca.loc[mejor_marca]
                        st.markdown(f"""
                        <div style="background:#00c96b12;border:1px solid #00c96b33;border-radius:12px;padding:16px 20px;margin:12px 0">
                            <div style="color:#00c96b;font-weight:700;font-size:0.92rem;margin-bottom:6px">
                                Mejor marca para invertir: {mejor_marca}
                            </div>
                            <div style="color:#8888aa;font-size:0.82rem">
                                Genera {fmt(_m_data["ganancia"])} de ganancia con {_m_data["margen"]:.0f}% de margen.
                                Si compras mas de esta marca, cada $100K invertidos te dejan ~${_m_data["margen"]*1000:.0f} de ganancia neta.
                            </div>
                        </div>""", unsafe_allow_html=True)

                    # Top productos más rentables
                    with st.expander("Top 15 productos mas rentables"):
                        _por_prod = _df_rent.groupby(["marca","producto"]).agg(
                            neto=("neto","sum"), costo=("costo_total","sum"),
                            ganancia=("ganancia","sum"), uds=("cantidad","sum"),
                        ).sort_values("ganancia", ascending=False).head(15)
                        rows_top = ""
                        for (m, p), r in _por_prod.iterrows():
                            mg = r["ganancia"] / r["neto"] * 100 if r["neto"] > 0 else 0
                            rows_top += f'<tr><td style="font-weight:600">{m}</td><td style="font-size:0.8rem">{p}</td><td style="text-align:right;color:#00c96b;font-weight:700">{fmt(r["ganancia"])}</td><td style="text-align:center">{mg:.0f}%</td><td style="text-align:center">{int(r["uds"])}</td></tr>'
                        st.markdown(
                            f'<div class="tabla-wrapper"><table class="tabla-custom">'
                            f'<thead><tr><th>Marca</th><th>Producto</th><th style="text-align:right">Ganancia</th><th style="text-align:center">Margen</th><th style="text-align:center">Uds</th></tr></thead>'
                            f'<tbody>{rows_top}</tbody></table></div>',
                            unsafe_allow_html=True,
                        )

            # Guardar datos de rentabilidad para el tab Simulador
            if pm_nuevo is not None and not pm_nuevo.empty:
                st.session_state["_pm_nuevo"] = pm_nuevo

            # Simuladores movidos al tab Simulador

            # Detalle por marca con velocidad de venta
            seccion("Detalle por marca — velocidad de venta")

            # Cruzar con ventas Dux
            ventas_por_prod = {}
            if not sin_datos:
                _vpp = df.groupby("producto").agg(vendidos=("cantidad","sum"), neto=("neto","sum"), primera=("fecha_dia","min")).reset_index()
                for _, rv in _vpp.iterrows():
                    ventas_por_prod[rv["producto"].upper()] = {"vendidos": int(rv["vendidos"]), "neto": rv["neto"], "primera": rv["primera"]}

            for prov_s in por_prov_s.index:
                sub_prov = con_stock[con_stock["marca"] == prov_s].sort_values("rubro")
                total_uds_p = int(sub_prov["cantidad"].sum())
                total_val_p = sub_prov["valor_total"].sum()

                with st.expander(f"{prov_s} — {total_uds_p} uds · {fmt(total_val_p)}"):
                    rows_det = ""
                    for _, rp in sub_prov.iterrows():
                        prod_up = rp["producto"].upper()
                        venta_info = ventas_por_prod.get(prod_up, {})
                        vendidos = venta_info.get("vendidos", 0)
                        neto_v = venta_info.get("neto", 0)

                        if vendidos > 0:
                            dias_v = max((hoy - venta_info["primera"]).days, 1)
                            vel = vendidos / dias_v
                            if vel >= 0.5:
                                badge = '<span class="badge badge-verde">Rapido</span>'
                            elif vel >= 0.15:
                                badge = '<span class="badge badge-gris">Normal</span>'
                            else:
                                badge = '<span class="badge badge-naranja">Lento</span>'
                            vel_txt = f"{vel:.2f}/d"
                        else:
                            badge = '<span class="badge badge-rojo">Sin ventas</span>' if int(rp["cantidad"]) > 0 else '<span class="badge badge-gris">Agotado</span>'
                            vel_txt = "—"

                        stock_actual = int(rp["cantidad"])
                        color_stock = "#e94560" if stock_actual <= 1 and stock_actual > 0 else "#00c96b" if stock_actual > 3 else "#f7b731" if stock_actual > 0 else "#666688"

                        rows_det += (
                            f'<tr>'
                            f'<td style="font-size:0.8rem">{rp["producto"]}</td>'
                            f'<td style="font-size:0.75rem;color:#8888aa">{rp["rubro"]}</td>'
                            f'<td style="text-align:center;color:{color_stock};font-weight:700">{stock_actual}</td>'
                            f'<td style="text-align:center;color:#00c96b">{vendidos}</td>'
                            f'<td style="text-align:center;color:#8888aa">{vel_txt}</td>'
                            f'<td style="text-align:center">{badge}</td>'
                            f'<td style="text-align:right;font-size:0.8rem">{fmt(rp["valor_total"])}</td>'
                            f'</tr>'
                        )

                    st.markdown(
                        f'<div class="tabla-wrapper"><table class="tabla-custom">'
                        f'<thead><tr><th>Producto</th><th>Rubro</th><th style="text-align:center">Stock</th>'
                        f'<th style="text-align:center">Vendidos</th><th style="text-align:center">Vel</th>'
                        f'<th style="text-align:center">Estado</th><th style="text-align:right">Costo</th></tr></thead>'
                        f'<tbody>{rows_det}</tbody></table></div>',
                        unsafe_allow_html=True
                    )

        else:
            seccion("Inventario por prenda — control de stock")
            st.markdown(
                '<div style="color:#8888aa;font-size:0.82rem;margin-bottom:12px">'
                'Subi el archivo de Valorizacion de Stock de Dux para ver el inventario completo.'
                '</div>', unsafe_allow_html=True
            )

        inventario_dux = {}

        if not sin_datos:
            for prov in ["KAZUMA", "LISBON", "DISTRICT"]:
                nuevo_prov = df[(df["stock_tipo"] == "NUEVO") & (df["proveedor_nuevo"] == prov)]
                if nuevo_prov.empty:
                    # Mostrar solo del stock_inicial que tiene 0 ventas
                    items_prov = [it for it in stock_ini if it["proveedor"] == prov]
                    if items_prov:
                        with st.expander(f"{prov} — 0 vendidos de {sum(it['stock_inicial'] for it in items_prov)} unidades"):
                            for it in items_prov:
                                st.markdown(f'<div style="color:#e94560;font-size:0.85rem;padding:4px 0">{it["tipo"]}: {it["stock_inicial"]} uds — 0 vendidas — SIN MOVIMIENTO</div>', unsafe_allow_html=True)
                    continue

                det_prov = nuevo_prov.groupby("producto").agg(
                    vendidos=("cantidad", "sum"),
                    neto=("neto", "sum"),
                    primera_venta=("fecha_dia", "min"),
                    ultima_venta=("fecha_dia", "max"),
                ).reset_index().sort_values("vendidos", ascending=False)

                total_vend_prov = int(det_prov["vendidos"].sum())
                total_ini_prov = sum(it["stock_inicial"] for it in stock_ini if it["proveedor"] == prov)
                quedan_prov = total_ini_prov - total_vend_prov

                with st.expander(f"{prov} — {total_vend_prov} vendidos de {total_ini_prov} ({quedan_prov} quedan)"):
                    rows_inv = ""
                    for _, rp in det_prov.iterrows():
                        prod_name = rp["producto"]
                        vend = int(rp["vendidos"])
                        stock_dux = inventario_dux.get(prod_name, "?")
                        dias_desde = max((hoy - rp["primera_venta"]).days, 1)
                        vel = vend / dias_desde

                        if vel >= 1:
                            vel_badge = '<span class="badge badge-verde">Rapido</span>'
                        elif vel >= 0.3:
                            vel_badge = '<span class="badge badge-gris">Normal</span>'
                        elif vend > 0:
                            vel_badge = '<span class="badge badge-naranja">Lento</span>'
                        else:
                            vel_badge = '<span class="badge badge-rojo">Sin ventas</span>'

                        stock_txt = str(stock_dux) if stock_dux != "?" else '<span style="color:#f7b731">?</span>'
                        rows_inv += (
                            f'<tr>'
                            f'<td style="font-size:0.82rem">{prod_name}</td>'
                            f'<td style="text-align:center;color:#00c96b;font-weight:700">{vend}</td>'
                            f'<td style="text-align:center">{stock_txt}</td>'
                            f'<td style="text-align:center;color:#8888aa">{vel:.2f}/d</td>'
                            f'<td style="text-align:center">{vel_badge}</td>'
                            f'<td style="text-align:right">{fmt(rp["neto"])}</td>'
                            f'</tr>'
                        )

                    # Productos del stock_inicial que NO se vendieron
                    productos_vendidos = set(det_prov["producto"].str.upper())
                    for it in stock_ini:
                        if it["proveedor"] != prov:
                            continue
                        for pfx in it["prefijos"]:
                            tiene = any(p.startswith(pfx.upper()) for p in productos_vendidos)
                            if not tiene:
                                stock_txt = str(inventario_dux.get(pfx, "?")) if inventario_dux.get(pfx) else '<span style="color:#f7b731">?</span>'
                                rows_inv += (
                                    f'<tr style="opacity:0.6">'
                                    f'<td style="font-size:0.82rem;color:#e94560">{pfx} (sin ventas en Dux)</td>'
                                    f'<td style="text-align:center;color:#e94560">0</td>'
                                    f'<td style="text-align:center">{stock_txt}</td>'
                                    f'<td style="text-align:center;color:#e94560">0.00/d</td>'
                                    f'<td style="text-align:center"><span class="badge badge-rojo">Sin ventas</span></td>'
                                    f'<td style="text-align:right">$0</td>'
                                    f'</tr>'
                                )

                    st.markdown(
                        f'<div class="tabla-wrapper"><table class="tabla-custom">'
                        f'<thead><tr><th>Producto (talle/color)</th><th style="text-align:center">Vendidos</th>'
                        f'<th style="text-align:center">Stock Dux</th><th style="text-align:center">Vel/dia</th>'
                        f'<th style="text-align:center">Estado</th><th style="text-align:right">Neto</th></tr></thead>'
                        f'<tbody>{rows_inv}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

            # Alerta para subir inventario de Dux
            if not inventario_dux:
                st.markdown(f"""
                <div style="background:#3a86ff12;border:1px solid #3a86ff33;border-radius:10px;padding:14px 16px;margin:12px 0">
                    <div style="color:#90c0ff;font-weight:700;font-size:0.88rem;margin-bottom:4px">
                        Para control antirrobo: subi el reporte de stock de Dux
                    </div>
                    <div style="color:#8888aa;font-size:0.82rem">
                        En Dux anda a Reportes - Consulta de stock - Exportar .xls. Subilo en Config y cruzo automaticamente
                        stock real vs vendido. Si no cuadra, algo se perdio.
                    </div>
                </div>""", unsafe_allow_html=True)

        # Stock viejo
        if not sin_datos:
            seccion("Stock viejo")
            viejo = df[df["stock_tipo"] == "VIEJO"]
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(metric_card("📦", "Unidades vendidas", str(int(viejo["cantidad"].sum())), "stock viejo", "gris" if True else "azul"), unsafe_allow_html=True)
            with col2:
                st.markdown(metric_card("💵", "Neto generado", fmt(viejo["neto"].sum()), "de stock viejo", "azul"), unsafe_allow_html=True)
            with col3:
                ticket = viejo["neto"].sum() / max(len(viejo), 1)
                st.markdown(metric_card("🧾", "Ticket promedio", fmt(ticket), "por transacción", "morado"), unsafe_allow_html=True)

            with st.expander(f"Ver {int(viejo['cantidad'].sum())} productos vendidos del stock viejo"):
                det_viejo = viejo.groupby("producto").agg(
                    vendidos=("cantidad","sum"), neto=("neto","sum")
                ).sort_values("vendidos", ascending=False)
                rows_vj = ""
                for prod, rv in det_viejo.iterrows():
                    rows_vj += f'<tr><td>{prod}</td><td style="text-align:center">{int(rv["vendidos"])}</td><td style="text-align:right">{fmt(rv["neto"])}</td></tr>'
                st.markdown(
                    f'<div class="tabla-wrapper"><table class="tabla-custom">'
                    f'<thead><tr><th>Producto</th><th style="text-align:center">Uds</th><th style="text-align:right">Neto</th></tr></thead>'
                    f'<tbody>{rows_vj}</tbody></table></div>',
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5B — SIMULADOR
# ══════════════════════════════════════════════════════════════════════════════
if tab5b:
  with tab5b:

    # ── Simulador de precios y costos ─────────────────────────────────────
    seccion("Simulador de precios — cuanto ganas por venta")
    st.markdown('<div style="color:#8888aa;font-size:0.85rem;margin-bottom:16px">Pone el costo, el markup y el canal. Te muestra exactamente cuanto te queda despues de impuestos, comisiones y costos.</div>', unsafe_allow_html=True)

    _p_costos = Path("data/costos_tienda.json")
    if _p_costos.exists():
        _costos = json.loads(_p_costos.read_text(encoding="utf-8"))
        _imp = _costos["impuestos"]
        _com = _costos["comisiones_mp"]
        _fijos = _costos["costos_fijos_venta"]
        _desc = _costos["descuentos"]

        with st.form("simulador_precio"):
            sp1, sp2, sp3 = st.columns(3)
            sim_costo = sp1.number_input("Costo ($)", min_value=1000, step=1000, value=10000)
            sim_markup = sp2.number_input("Markup", min_value=1.0, max_value=5.0, step=0.1, value=2.5)
            sim_canal = sp3.selectbox("Canal de venta", ["Local (efectivo)", "Local (transferencia)", "Online 3 cuotas", "Online 6 cuotas", "Online 9 cuotas"])

            if st.form_submit_button("Calcular", use_container_width=True):
                pvp = sim_costo * sim_markup
                iva_costo = sim_costo * _imp["iva_costo"]
                iibb = pvp * _imp["iibb_rentas"]
                imp_cd = pvp * _imp["imp_credito_debito"]
                cuota_mes = 0

                if sim_canal == "Local (efectivo)":
                    precio_real = pvp * (1 - _desc["efectivo"])
                    com_financiera = com_pasarela = com_plataforma = envio = publicidad = 0
                elif sim_canal == "Local (transferencia)":
                    precio_real = pvp * (1 - _desc["transferencia"])
                    com_financiera = com_pasarela = com_plataforma = envio = publicidad = 0
                else:
                    precio_real = pvp
                    com_pasarela = pvp * _com["pasarela"]
                    com_plataforma = pvp * _com["plataforma"]
                    envio = _fijos["envio_promedio"]
                    publicidad = _fijos["publicidad_ecommerce"]
                    if "3 cuotas" in sim_canal:
                        com_financiera = pvp * _com["cuotas_3"]
                        cuota_mes = pvp / 3
                    elif "6 cuotas" in sim_canal:
                        com_financiera = pvp * _com["cuotas_6"]
                        cuota_mes = pvp / 6
                    else:
                        com_financiera = pvp * _com["cuotas_9"]
                        cuota_mes = pvp / 9

                packaging = _fijos["packaging"]
                total_costos = sim_costo + iva_costo + iibb + imp_cd + com_financiera + com_pasarela + com_plataforma + packaging + envio + publicidad
                ganancia = precio_real - total_costos
                rentabilidad = ganancia / precio_real * 100 if precio_real > 0 else 0
                color_gan = "#00c96b" if ganancia > 0 else "#e94560"

                cuota_txt = f" · Cuota: {fmt(cuota_mes)}/mes" if cuota_mes > 0 else ""
                st.markdown(f"""
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0">
                    <div style="background:rgba(58,134,255,0.08);border:1px solid #3a86ff44;border-radius:12px;padding:16px 20px">
                        <div style="font-size:0.75rem;color:#6666aa">PVP LISTA</div>
                        <div style="font-size:1.6rem;font-weight:800;color:#3a86ff">{fmt(pvp)}</div>
                        <div style="font-size:0.78rem;color:#666688">Costo ${sim_costo:,.0f} x {sim_markup}{cuota_txt}</div>
                    </div>
                    <div style="background:rgba({'0,201,107' if ganancia > 0 else '233,69,96'},0.08);border:1px solid {color_gan}44;border-radius:12px;padding:16px 20px">
                        <div style="font-size:0.75rem;color:#6666aa">GANANCIA NETA ({sim_canal})</div>
                        <div style="font-size:1.6rem;font-weight:800;color:{color_gan}">{fmt(ganancia)}</div>
                        <div style="font-size:0.78rem;color:#666688">Cobras {fmt(precio_real)} · Costos {fmt(total_costos)} · Margen {rentabilidad:.0f}%</div>
                    </div>
                </div>""", unsafe_allow_html=True)

                # Desglose
                seccion("Desglose de costos")
                items_c = [
                    ("Costo producto", sim_costo, "#3a86ff"),
                    ("IVA sobre costo (10.5%)", iva_costo, "#8b5cf6"),
                    ("IIBB / Rentas (4.5%)", iibb, "#8b5cf6"),
                    ("Imp credito/debito (0.6%)", imp_cd, "#8b5cf6"),
                    ("Packaging", packaging, "#6666aa"),
                ]
                if com_pasarela > 0:
                    items_c.append(("Pasarela MP (5.07%)", com_pasarela, "#f7b731"))
                    items_c.append(("Plataforma Tienda Nube (1%)", com_plataforma, "#f7b731"))
                if com_financiera > 0:
                    items_c.append(("Comision financiera cuotas", com_financiera, "#e94560"))
                if envio > 0:
                    items_c.append(("Envio promedio", envio, "#6666aa"))
                if publicidad > 0:
                    items_c.append(("Publicidad por venta", publicidad, "#6666aa"))

                rows_sc = ""
                for nombre, val, col in items_c:
                    pct_c = val / precio_real * 100 if precio_real > 0 else 0
                    rows_sc += f'<tr><td>{nombre}</td><td style="text-align:right;color:{col};font-weight:600">{fmt(val)}</td><td style="text-align:right;color:#8888aa">{pct_c:.1f}%</td></tr>'
                rows_sc += f'<tr style="border-top:2px solid #ffffff15"><td style="font-weight:700;color:#eee">TOTAL COSTOS</td><td style="text-align:right;color:#e94560;font-weight:700">{fmt(total_costos)}</td><td style="text-align:right;color:#e94560">{total_costos/precio_real*100:.0f}%</td></tr>'
                rows_sc += f'<tr><td style="font-weight:700;color:#eee">PRECIO COBRADO</td><td style="text-align:right;color:#3a86ff;font-weight:700">{fmt(precio_real)}</td><td></td></tr>'
                rows_sc += f'<tr><td style="font-weight:800;color:#eee;font-size:1.05rem">GANANCIA NETA</td><td style="text-align:right;color:{color_gan};font-weight:800;font-size:1.1rem">{fmt(ganancia)}</td><td style="text-align:right;color:{color_gan};font-weight:700">{rentabilidad:.0f}%</td></tr>'
                st.markdown(
                    f'<div class="tabla-wrapper"><table class="tabla-custom"><thead><tr><th>Concepto</th><th style="text-align:right">Monto</th><th style="text-align:right">% del precio</th></tr></thead>'
                    f'<tbody>{rows_sc}</tbody></table></div>',
                    unsafe_allow_html=True,
                )

        # ── Tabla comparativa todos los canales ──────────────────────────────
        seccion("Comparativa — mismo producto por todos los canales")
        _costo_comp = sim_costo if "sim_costo" in dir() else 10000
        _markup_comp = sim_markup if "sim_markup" in dir() else 2.5
        _pvp_comp = _costo_comp * _markup_comp

        canales = [
            ("Efectivo (-15%)", _pvp_comp * 0.85, 0, 0, 0, 0),
            ("Transferencia (-10%)", _pvp_comp * 0.90, 0, 0, 0, 0),
            ("Online 3 cuotas", _pvp_comp, _pvp_comp*_com["pasarela"], _pvp_comp*_com["cuotas_3"], _pvp_comp*_com["plataforma"], _fijos["envio_promedio"]+_fijos["publicidad_ecommerce"]),
            ("Online 6 cuotas", _pvp_comp, _pvp_comp*_com["pasarela"], _pvp_comp*_com["cuotas_6"], _pvp_comp*_com["plataforma"], _fijos["envio_promedio"]+_fijos["publicidad_ecommerce"]),
            ("Online 9 cuotas", _pvp_comp, _pvp_comp*_com["pasarela"], _pvp_comp*_com["cuotas_9"], _pvp_comp*_com["plataforma"], _fijos["envio_promedio"]+_fijos["publicidad_ecommerce"]),
        ]

        _iva_c = _costo_comp * _imp["iva_costo"]
        _base_costos = _costo_comp + _iva_c + _fijos["packaging"]

        rows_comp = ""
        mejor_gan = -999999
        mejor_canal = ""
        for canal, precio, pasarela, financ, plat, extras in canales:
            _iibb_c = _pvp_comp * _imp["iibb_rentas"]
            _icd_c = _pvp_comp * _imp["imp_credito_debito"]
            tot = _base_costos + _iibb_c + _icd_c + pasarela + financ + plat + extras
            gan = precio - tot
            rent = gan / precio * 100 if precio > 0 else 0
            cg = "#00c96b" if gan > 0 else "#e94560"
            if gan > mejor_gan:
                mejor_gan = gan
                mejor_canal = canal
            star = " ★" if gan >= mejor_gan and gan > 0 else ""
            rows_comp += (
                f'<tr>'
                f'<td style="font-weight:700;color:#eeeeff;font-size:0.9rem">{canal}{star}</td>'
                f'<td style="text-align:right;color:#3a86ff;font-weight:600;font-size:0.9rem">{fmt(precio)}</td>'
                f'<td style="text-align:right;color:#e94560;font-size:0.85rem">{fmt(tot)}</td>'
                f'<td style="text-align:right;color:{cg};font-weight:800;font-size:0.95rem">{fmt(gan)}</td>'
                f'<td style="text-align:center;color:{cg};font-weight:700;font-size:0.9rem">{rent:.0f}%</td>'
                f'</tr>'
            )

        st.markdown(f'<div style="color:#666688;font-size:0.82rem;margin-bottom:8px">Producto: costo ${_costo_comp:,.0f} x {_markup_comp} = PVP ${_pvp_comp:,.0f}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="tabla-wrapper"><table class="tabla-custom">'
            f'<thead><tr>'
            f'<th style="min-width:160px">Canal de venta</th>'
            f'<th style="text-align:right">Cobras</th>'
            f'<th style="text-align:right">Costos totales</th>'
            f'<th style="text-align:right">Ganancia neta</th>'
            f'<th style="text-align:center">Margen</th>'
            f'</tr></thead>'
            f'<tbody>{rows_comp}</tbody></table></div>',
            unsafe_allow_html=True,
        )
        if mejor_gan > 0:
            st.markdown(f'<div style="color:#00c96b;font-size:0.82rem;margin-top:6px;font-weight:600">★ Mejor canal: {mejor_canal} — {fmt(mejor_gan)} de ganancia</div>', unsafe_allow_html=True)

    # ── Simulador de promos / combos ─────────────────────────────────────
    seccion("Simulador de promos — combos, 2x1, descuentos")
    st.markdown('<div style="color:#8888aa;font-size:0.85rem;margin-bottom:16px">Arma una promo y fijate si te conviene o perdes plata.</div>', unsafe_allow_html=True)

    _p_costos2 = Path("data/costos_tienda.json")
    if _p_costos2.exists():
        _costos2 = json.loads(_p_costos2.read_text(encoding="utf-8"))
        _imp2 = _costos2["impuestos"]

        with st.form("simulador_promo"):
            tipo_promo = st.selectbox("Tipo de promo", [
                "Descuento %", "2x1 (llevas 2, pagas 1)", "2x3 (llevas 3, pagas 2)",
                "Combo precio fijo", "Segunda unidad al 50%"
            ])

            pp1, pp2 = st.columns(2)
            promo_costo1 = pp1.number_input("Costo prod 1 ($)", min_value=1000, step=1000, value=10000, key="pc1")
            promo_pvp1   = pp2.number_input("PVP prod 1 ($)", min_value=1000, step=1000, value=25000, key="ppvp1")

            pp3, pp4 = st.columns(2)
            promo_costo2 = pp3.number_input("Costo prod 2 ($)", min_value=0, step=1000, value=10000, key="pc2")
            promo_pvp2   = pp4.number_input("PVP prod 2 ($)", min_value=0, step=1000, value=25000, key="ppvp2")

            if tipo_promo == "Descuento %":
                promo_desc = st.slider("Descuento %", 5, 70, 20)
            elif tipo_promo == "Combo precio fijo":
                promo_combo_precio = st.number_input("Precio del combo $", min_value=1000, step=1000, value=35000)

            promo_canal = st.selectbox("Canal", ["Local (efectivo)", "Local (transferencia)", "Online 3 cuotas", "Online 6 cuotas"], key="promo_canal")

            if st.form_submit_button("Calcular promo", use_container_width=True):
                # Calcular según tipo
                if tipo_promo == "Descuento %":
                    uds_vendidas = 1
                    costo_total_p = promo_costo1
                    pvp_sin_desc = promo_pvp1
                    precio_promo = promo_pvp1 * (1 - promo_desc / 100)
                    desc_txt = f"{promo_desc}% OFF"

                elif tipo_promo == "2x1 (llevas 2, pagas 1)":
                    uds_vendidas = 2
                    costo_total_p = promo_costo1 + promo_costo2
                    pvp_sin_desc = promo_pvp1 + promo_pvp2
                    precio_promo = max(promo_pvp1, promo_pvp2)  # paga el más caro
                    desc_txt = "2x1"

                elif tipo_promo == "2x3 (llevas 3, pagas 2)":
                    uds_vendidas = 3
                    costo_total_p = promo_costo1 * 2 + promo_costo2  # 2 del prod1 + 1 del prod2
                    pvp_sin_desc = promo_pvp1 * 2 + promo_pvp2
                    precio_promo = promo_pvp1 + promo_pvp2  # paga 2 de 3
                    desc_txt = "3x2"

                elif tipo_promo == "Combo precio fijo":
                    uds_vendidas = 2
                    costo_total_p = promo_costo1 + promo_costo2
                    pvp_sin_desc = promo_pvp1 + promo_pvp2
                    precio_promo = promo_combo_precio
                    desc_txt = f"Combo ${promo_combo_precio:,.0f}"

                elif tipo_promo == "Segunda unidad al 50%":
                    uds_vendidas = 2
                    costo_total_p = promo_costo1 + promo_costo2
                    pvp_sin_desc = promo_pvp1 + promo_pvp2
                    precio_promo = promo_pvp1 + promo_pvp2 * 0.5
                    desc_txt = "2da al 50%"

                # Descuento aplicado
                if promo_canal == "Local (efectivo)":
                    precio_cobrado = precio_promo * 0.85
                elif promo_canal == "Local (transferencia)":
                    precio_cobrado = precio_promo * 0.90
                else:
                    precio_cobrado = precio_promo

                # Costos
                iva_c = costo_total_p * _imp2["iva_costo"]
                iibb_p = precio_promo * _imp2["iibb_rentas"]
                icd_p = precio_promo * _imp2["imp_credito_debito"]
                packaging_p = 400 * uds_vendidas

                com_fin = 0
                com_pas = 0
                com_plat = 0
                envio_p = 0
                pub_p = 0
                if "Online" in promo_canal:
                    com_pas = precio_promo * _costos2["comisiones_mp"]["pasarela"]
                    com_plat = precio_promo * _costos2["comisiones_mp"]["plataforma"]
                    envio_p = _costos2["costos_fijos_venta"]["envio_promedio"]
                    pub_p = _costos2["costos_fijos_venta"]["publicidad_ecommerce"]
                    if "3 cuotas" in promo_canal:
                        com_fin = precio_promo * _costos2["comisiones_mp"]["cuotas_3"]
                    elif "6 cuotas" in promo_canal:
                        com_fin = precio_promo * _costos2["comisiones_mp"]["cuotas_6"]

                total_costos_p = costo_total_p + iva_c + iibb_p + icd_p + packaging_p + com_fin + com_pas + com_plat + envio_p + pub_p
                ganancia_p = precio_cobrado - total_costos_p
                rent_p = ganancia_p / precio_cobrado * 100 if precio_cobrado > 0 else 0
                desc_pct = (1 - precio_promo / pvp_sin_desc) * 100 if pvp_sin_desc > 0 else 0

                color_gp = "#00c96b" if ganancia_p > 0 else "#e94560"
                gan_por_ud = ganancia_p / uds_vendidas

                # Resultado
                st.markdown(f"""
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0">
                    <div style="background:rgba(247,183,49,0.08);border:1px solid #f7b73144;border-radius:12px;padding:16px 20px">
                        <div style="font-size:0.75rem;color:#6666aa">PROMO: {desc_txt}</div>
                        <div style="font-size:1.6rem;font-weight:800;color:#f7b731">{fmt(precio_promo)}</div>
                        <div style="font-size:0.78rem;color:#666688">Sin promo: {fmt(pvp_sin_desc)} · Descuento real: {desc_pct:.0f}% · {uds_vendidas} uds</div>
                    </div>
                    <div style="background:rgba({'0,201,107' if ganancia_p > 0 else '233,69,96'},0.08);border:1px solid {color_gp}44;border-radius:12px;padding:16px 20px">
                        <div style="font-size:0.75rem;color:#6666aa">GANANCIA ({promo_canal})</div>
                        <div style="font-size:1.6rem;font-weight:800;color:{color_gp}">{fmt(ganancia_p)}</div>
                        <div style="font-size:0.78rem;color:#666688">Margen {rent_p:.0f}% · {fmt(gan_por_ud)} por unidad · Cobras {fmt(precio_cobrado)}</div>
                    </div>
                </div>""", unsafe_allow_html=True)

                # Veredicto
                if ganancia_p > 0:
                    st.markdown(f"""
                    <div style="background:#00c96b12;border:1px solid #00c96b33;border-radius:12px;padding:14px 20px;margin:10px 0">
                        <span style="color:#6effc4;font-weight:700">LA PROMO CONVIENE</span>
                        <span style="color:#8888aa"> — ganas {fmt(ganancia_p)} ({rent_p:.0f}% margen). Moves {uds_vendidas} unidades y sacas {fmt(gan_por_ud)} por prenda.</span>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background:#e9456012;border:1px solid #e9456033;border-radius:12px;padding:14px 20px;margin:10px 0">
                        <span style="color:#ff8fa3;font-weight:700">PERDES PLATA</span>
                        <span style="color:#8888aa"> — esta promo te deja {fmt(ganancia_p)} de perdida. Baja el descuento o subi el precio base.</span>
                    </div>""", unsafe_allow_html=True)

                # Desglose
                with st.expander("Ver desglose de la promo"):
                    rows_pr = ""
                    for n, v in [("Costo mercaderia", costo_total_p), ("IVA costo (10.5%)", iva_c),
                        ("IIBB (4.5%)", iibb_p), ("Imp cred/deb (0.6%)", icd_p), ("Packaging", packaging_p)]:
                        rows_pr += f'<tr><td>{n}</td><td style="text-align:right;color:#e94560">{fmt(v)}</td></tr>'
                    if com_pas > 0:
                        for n, v in [("Pasarela MP", com_pas), ("Plataforma TN", com_plat), ("Comision cuotas", com_fin), ("Envio", envio_p), ("Publicidad", pub_p)]:
                            if v > 0:
                                rows_pr += f'<tr><td>{n}</td><td style="text-align:right;color:#f7b731">{fmt(v)}</td></tr>'
                    rows_pr += f'<tr style="border-top:2px solid #ffffff15"><td style="font-weight:700;color:#eee">TOTAL COSTOS</td><td style="text-align:right;color:#e94560;font-weight:700">{fmt(total_costos_p)}</td></tr>'
                    rows_pr += f'<tr><td style="font-weight:700;color:#eee">COBRAS</td><td style="text-align:right;color:#3a86ff;font-weight:700">{fmt(precio_cobrado)}</td></tr>'
                    rows_pr += f'<tr><td style="font-weight:800;color:#eee">GANANCIA</td><td style="text-align:right;color:{color_gp};font-weight:800;font-size:1.1rem">{fmt(ganancia_p)}</td></tr>'
                    st.markdown(
                        f'<div class="tabla-wrapper"><table class="tabla-custom"><thead><tr><th>Concepto</th><th style="text-align:right">Monto</th></tr></thead>'
                        f'<tbody>{rows_pr}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

    # ── Simulador de compra por marca ─────────────────────────────────────
    seccion("Simulador de compra — si invierto en una marca, cuanto me deja?")

    pm_nuevo = st.session_state.get("_pm_nuevo")
    if pm_nuevo is not None and not pm_nuevo.empty:
        with st.form("simulador_compra"):
            sc1, sc2 = st.columns(2)
            sim_marca = sc1.selectbox("Marca", list(pm_nuevo.index))
            sim_inversion = sc2.number_input("Inversion neta ($)", min_value=100000, step=100000, value=500000)
            if st.form_submit_button("Simular compra", use_container_width=True):
                _m_info = pm_nuevo.loc[sim_marca]
                margen_m = _m_info["margen"] / 100
                ganancia_est = sim_inversion * margen_m
                venta_est = sim_inversion * (1 + margen_m)
                iva_credito_est = sim_inversion * 0.21
                vel_marca = _m_info["uds"] / max((hoy - date(2026, 3, 26)).days, 1)
                uds_est = sim_inversion / (_m_info["costo"] / max(_m_info["uds"], 1))
                dias_vender = uds_est / vel_marca if vel_marca > 0 else 9999

                r1, r2, r3, r4 = st.columns(4)
                with r1:
                    st.markdown(metric_card("💰", "Ganancia estimada", fmt(ganancia_est), f"margen {_m_info['margen']:.0f}%", "verde"), unsafe_allow_html=True)
                with r2:
                    st.markdown(metric_card("🛒", "Venta generada", fmt(venta_est), "neto sin IVA", "azul"), unsafe_allow_html=True)
                with r3:
                    st.markdown(metric_card("🧾", "IVA credito", fmt(iva_credito_est), "21% sobre la compra", "amarillo"), unsafe_allow_html=True)
                with r4:
                    d_txt = f"{dias_vender:.0f} dias" if dias_vender < 9999 else "sin datos"
                    st.markdown(metric_card("📅", "Tiempo para vender", d_txt, f"~{uds_est:.0f} unidades", "morado"), unsafe_allow_html=True)
    else:
        st.info("Necesita datos de ventas Dux para simular compra por marca")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — CHEQUES
# ══════════════════════════════════════════════════════════════════════════════
if tab6:
  with tab6:
    emitidos = [c for c in cheques if c.get("tipo", "emitido") == "emitido"]
    por_negociar = [c for c in cheques if c.get("tipo") == "por_negociar"]
    pendientes = [c for c in cheques if c["estado"] == "pendiente"]

    total_emitido = sum(c["monto"] for c in emitidos if c["estado"] == "pendiente")
    total_negociar = sum(c["monto"] for c in por_negociar if c["estado"] == "pendiente")
    prox_30 = sum(
        c["monto"] for c in emitidos
        if c["estado"] == "pendiente"
        and (date.fromisoformat(c["vencimiento"]) - hoy).days <= 30
    )

    # KPIs
    seccion("Resumen")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card("💳", "Cheques emitidos", fmt(total_emitido),
                                f"{len([c for c in emitidos if c['estado']=='pendiente'])} pendientes", "rojo"), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card("🤝", "Por negociar", fmt(total_negociar),
                                "Dilatar hasta mayo", "amarillo"), unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card("📆", "Próximos 30 días", fmt(prox_30),
                                "solo emitidos", "morado"), unsafe_allow_html=True)
    with col4:
        if not sin_datos:
            neto_mes = ventas_mes(df)["neto"]
            cob = neto_mes - prox_30
            st.markdown(metric_card(
                "🏦", "Cobertura con ventas del mes", fmt(neto_mes),
                f"{'Superavit' if cob >= 0 else 'Deficit'} {fmt(abs(cob))}",
                "verde" if cob >= 0 else "rojo",
            ), unsafe_allow_html=True)
        else:
            st.markdown(metric_card("📊", "Ventas del mes", "Sin datos", "", "azul"), unsafe_allow_html=True)

    def _render_cheque_lista(lista, prefijo_key):
        for i, c in enumerate(lista):
            idx_global = cheques.index(c)
            venc = date.fromisoformat(c["vencimiento"])
            dias = (venc - hoy).days
            pagado = c["estado"] == "pagado"

            if pagado:
                clase, dias_txt = "pagado", "Pagado"
                badge = '<span class="badge badge-gris">Pagado</span>'
            elif dias < 0:
                clase, dias_txt = "urgente", f"Vencido hace {abs(dias)} dias"
                badge = '<span class="badge badge-rojo">Vencido</span>'
            elif dias <= 3:
                clase = "urgente"
                dias_txt = "HOY" if dias == 0 else f"{dias} dia{'s' if dias!=1 else ''}"
                badge = '<span class="badge badge-rojo">Urgente</span>'
            elif dias <= 7:
                clase, dias_txt = "urgente", f"{dias} dias"
                badge = '<span class="badge badge-rojo">Esta semana</span>'
            elif dias <= 30:
                clase, dias_txt = "pronto", f"{dias} dias"
                badge = '<span class="badge badge-amarillo">Este mes</span>'
            else:
                clase, dias_txt = "ok", f"{dias} dias"
                badge = '<span class="badge badge-verde">OK</span>'

            col_c, col_b = st.columns([7, 1])
            with col_c:
                st.markdown(f"""
                <div class="cheque-card {clase}">
                    <div class="cheque-info">
                        <div class="cheque-proveedor">{c['id']} &mdash; {c['proveedor']}</div>
                        <div class="cheque-concepto">{c.get('concepto','')}</div>
                        <div class="cheque-fecha">Vence: {venc.strftime('%d/%m/%Y')} &middot; {dias_txt}</div>
                    </div>
                    <div class="cheque-monto">{fmt(c['monto'])}</div>
                    {badge}
                </div>""", unsafe_allow_html=True)
            with col_b:
                st.markdown("<div style='margin-top:12px'>", unsafe_allow_html=True)
                if not pagado:
                    if st.button("Pago", key=f"{prefijo_key}_pagar_{i}", use_container_width=True):
                        cheques[idx_global]["estado"] = "pagado"
                        save_cheques(cheques)
                        st.rerun()
                else:
                    if st.button("Reabrir", key=f"{prefijo_key}_rev_{i}", use_container_width=True):
                        cheques[idx_global]["estado"] = "pendiente"
                        save_cheques(cheques)
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    # Cheques emitidos
    seccion("Cheques emitidos — hay que pagarlos si o si")
    _render_cheque_lista(emitidos, "em")

    # Por negociar
    if por_negociar:
        seccion("Por negociar — dilatar, hablar desde mayo")
        _render_cheque_lista(por_negociar, "neg")

    # Agregar cheque
    seccion("Agregar cheque")
    with st.form("nuevo_cheque", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nro      = c1.text_input("Numero", placeholder="#220")
        proveedor_new = c2.text_input("Proveedor")
        concepto_new  = c3.text_input("Concepto")
        c4, c5, c6 = st.columns(3)
        monto_new  = c4.number_input("Monto ($)", min_value=0, step=10000)
        venc_new   = c5.date_input("Vencimiento")
        tipo_new   = c6.selectbox("Tipo", ["emitido", "por_negociar"],
                                  format_func=lambda x: "Emitido" if x=="emitido" else "Por negociar")
        if st.form_submit_button("Agregar cheque", use_container_width=True):
            if proveedor_new and monto_new > 0:
                cheques.append({
                    "id": nro or f"#{len(cheques)+200}",
                    "proveedor": proveedor_new,
                    "concepto": concepto_new,
                    "vencimiento": venc_new.isoformat(),
                    "monto": int(monto_new),
                    "tipo": tipo_new,
                    "estado": "pendiente",
                })
                save_cheques(cheques)
                _notificar("✅ Cheque agregado correctamente")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — DEUDA PERSONAL
# ══════════════════════════════════════════════════════════════════════════════
if tab7:
  with tab7:
    deuda_list = get_deuda()
    pend = [d for d in deuda_list if d["estado"] == "pendiente" and d["monto"] > 0]
    d_2026      = [d for d in pend if d.get("periodo") == "2026"]
    d_hist      = [d for d in pend if d.get("periodo") == "2022-2025"]
    d_prest     = [d for d in pend if d.get("periodo") == "prestamos"]
    sum_2026    = sum(d["monto"] for d in d_2026)
    sum_hist    = sum(d["monto"] for d in d_hist)
    sum_prest   = sum(d["monto"] for d in d_prest)
    sum_total_d = sum_2026 + sum_hist + sum_prest

    seccion("Deuda personal — plata que el negocio te debe")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(metric_card("💰", "TOTAL DEUDA", fmt(sum_total_d), "todo lo que pusiste", "rojo"), unsafe_allow_html=True)
    with k2:
        st.markdown(metric_card("📅", "Plata 2026", fmt(sum_2026), f"{len(d_2026)} movimientos", "amarillo"), unsafe_allow_html=True)
    with k3:
        st.markdown(metric_card("🗂", "Historico 2022-2025", fmt(sum_hist), f"{len(d_hist)} movimientos", "morado"), unsafe_allow_html=True)
    with k4:
        st.markdown(metric_card("🏠", "Prestamos grandes", fmt(sum_prest), f"{len(d_prest)} prestamos", "azul"), unsafe_allow_html=True)

    def _tabla_deuda(titulo, items, color, emoji):
        seccion(f"{emoji} {titulo}")
        if not items:
            st.info("Sin datos")
            return
        sub = sum(d["monto"] for d in items)
        rows = ""
        for d in sorted(items, key=lambda x: x.get("fecha",""), reverse=True):
            rows += f'<tr><td style="white-space:nowrap">{d["fecha"]}</td><td>{d["concepto"]}</td><td style="font-size:0.78rem;color:#8888aa">{d.get("categoria","—")}</td><td style="color:{color};font-weight:700;text-align:right">{fmt(d["monto"])}</td></tr>'
        rows += f'<tr style="border-top:2px solid #ffffff15"><td colspan="3" style="font-weight:700;color:#eee">SUBTOTAL</td><td style="color:{color};font-weight:800;text-align:right;font-size:1.1rem">{fmt(sub)}</td></tr>'
        st.markdown(f'<div class="tabla-wrapper"><table class="tabla-custom"><thead><tr><th>Fecha</th><th>Concepto</th><th>Categoria</th><th style="text-align:right">Monto</th></tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)

    _tabla_deuda("Plata que pusiste en 2026", d_2026, "#f7b731", "📅")
    _tabla_deuda("Inversion historica 2022-2025", d_hist, "#8b5cf6", "🗂")
    _tabla_deuda("Prestamos grandes", d_prest, "#3a86ff", "🏠")

    usd_items = [d for d in pend if "USD" in d.get("concepto","").upper() or "dolar" in d.get("concepto","").lower()]
    if usd_items:
        st.markdown('<div style="background:#f7b73112;border:1px solid #f7b73133;border-radius:10px;padding:12px 16px;margin:8px 0"><span style="color:#ffd97d;font-size:0.85rem">Nota: hay deuda en dolares que no esta convertida en el total.</span></div>', unsafe_allow_html=True)

    # ── Proyección de recupero ────────────────────────────────────────────────
    seccion("Proyeccion de recupero — cuando recuperas tu plata")
    if not sin_datos:
        _gan_diaria = 0
        # Calcular ganancia diaria real desde Dux
        _costo_map_d = {}
        from data_processor import load_stock_dux as _lsd
        _df_stk_d = _lsd("data/stock_dux.xls")
        if not _df_stk_d.empty:
            for _, _rs in _df_stk_d.iterrows():
                _costo_map_d[_rs["producto"].upper()] = _rs["costo_unit"]
        _gan_total = 0
        for _, _rv in df.iterrows():
            _c = _costo_map_d.get(str(_rv["producto"]).upper(), 0)
            _gan_total += _rv["neto"] - (_c * _rv["cantidad"])

        _dias_data = max(df["fecha_dia"].nunique(), 1)
        _gan_diaria = _gan_total / _dias_data
        _gan_mensual = _gan_diaria * 26  # 26 dias laborales

        # Meses para recuperar
        _meses_recupero = sum_total_d / _gan_mensual if _gan_mensual > 0 else 9999
        _anios_recupero = _meses_recupero / 12

        pr1, pr2, pr3, pr4 = st.columns(4)
        with pr1:
            st.markdown(metric_card("📈", "Ganancia diaria", fmt(_gan_diaria),
                f"promedio {_dias_data} dias con datos", "verde" if _gan_diaria > 0 else "rojo"), unsafe_allow_html=True)
        with pr2:
            st.markdown(metric_card("📅", "Ganancia mensual", fmt(_gan_mensual),
                "26 dias laborales", "verde" if _gan_mensual > 0 else "rojo"), unsafe_allow_html=True)
        with pr3:
            st.markdown(metric_card("💰", "Deuda total", fmt(sum_total_d),
                "lo que el negocio te debe", "rojo"), unsafe_allow_html=True)
        with pr4:
            if _meses_recupero < 9999:
                if _anios_recupero < 1:
                    tiempo_txt = f"{_meses_recupero:.0f} meses"
                else:
                    tiempo_txt = f"{_anios_recupero:.1f} anos"
                st.markdown(metric_card("🎯", "Tiempo recupero", tiempo_txt,
                    "a este ritmo de ganancia", "amarillo"), unsafe_allow_html=True)
            else:
                st.markdown(metric_card("🎯", "Tiempo recupero", "Sin datos",
                    "necesita mas ventas", "rojo"), unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background:#1a1a2e;border:1px solid #ffffff0e;border-radius:12px;padding:16px 20px;margin:8px 0">
            <div style="color:#8888aa;font-size:0.82rem">
                A la ganancia actual de <b style="color:#00c96b">{fmt(_gan_diaria)}/dia</b>,
                necesitas <b style="color:#f7b731">{_meses_recupero:.0f} meses</b> para recuperar los {fmt(sum_total_d)}.
                Si duplicas la venta diaria (objetivo $300K/dia), baja a <b style="color:#00c96b">{_meses_recupero/2:.0f} meses</b>.
            </div>
        </div>""", unsafe_allow_html=True)

    seccion("Registrar plata que pusiste")
    CATEGORIAS_DEUDA = [
        "Cobertura cheques", "Cobertura descubierto", "Sueldos", "Tarjeta",
        "Marketing", "Legal", "Software", "Local", "Inversion inicial",
        "Prestamo grande", "Otros",
    ]
    with st.form("nueva_deuda", clear_on_submit=True):
        d1, d2 = st.columns(2)
        concepto_d = d1.text_input("Concepto", placeholder="Ej: pague el sueldo de Sofia")
        cat_d      = d2.selectbox("Categoria", CATEGORIAS_DEUDA)
        d3, d4, d5 = st.columns(3)
        fecha_d    = d3.date_input("Fecha del pago", value=hoy)
        monto_d    = d4.number_input("Monto ($)", min_value=0, step=10000)
        periodo_d  = d5.selectbox("Periodo", ["2026", "2022-2025", "prestamos"])
        if st.form_submit_button("Agregar", use_container_width=True):
            if monto_d > 0 and concepto_d:
                nuevo_id = max((d["id"] for d in deuda_list), default=0) + 1
                deuda_list.append({
                    "id": nuevo_id,
                    "fecha": fecha_d.isoformat(),
                    "monto": int(monto_d),
                    "concepto": concepto_d,
                    "categoria": cat_d,
                    "periodo": periodo_d,
                    "estado": "pendiente",
                })
                save_deuda(deuda_list)
                _notificar(f"✅ Registrado — {concepto_d} {fmt(monto_d)}")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — CHAT IA
# ══════════════════════════════════════════════════════════════════════════════
if tab8:
  with tab8:
    api_key = st.session_state.api_key

    if not api_key:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px">
            <div style="font-size:3rem;margin-bottom:16px">🔑</div>
            <div style="font-size:1.1rem;font-weight:700;color:#ccccee;margin-bottom:8px">
                API Key requerida
            </div>
            <div style="color:#6666aa;font-size:0.9rem">
                Ingresá tu Anthropic API Key en la pestaña <strong>⚙️ Config</strong>.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        def build_context():
            lines = [
                "# The Room Argentina — Datos actuales del negocio",
                f"Fecha: {hoy.strftime('%d/%m/%Y')}",
                "",
            ]
            if not sin_datos:
                dh = ventas_hoy(df)
                dm = ventas_mes(df)
                proy = proyeccion_mes(df)
                lines += [
                    "## Ventas",
                    f"- Hoy: ${dh['neto']:,.0f} ({dh['cantidad']} unidades)",
                    f"- Mes actual: ${dm['neto']:,.0f} ({dm['dias_con_venta']} días con venta)",
                    f"- Proyección del mes: ${proy:,.0f}",
                    f"- Objetivo diario: $300.000",
                    "",
                    "## Últimos 14 días",
                ]
                vxd = ventas_por_dia(df)
                for _, r in vxd.tail(14).iterrows():
                    lines.append(f"- {r['fecha_dia']}: ${r['neto']:,.0f} ({int(r['cantidad'])} uds)")
                lines.append("")

                if stock_ini:
                    ds = stock_nuevo_resumen(df if not sin_datos else pd.DataFrame(), stock_ini)
                    lines.append("## Stock nuevo")
                    for _, r in ds.iterrows():
                        lines.append(
                            f"- {r['Proveedor']} {r['Tipo']}: "
                            f"{r['Vendidos']}/{r['Stock Inicial']} vendidos, "
                            f"quedan {r['Quedan']}, {r['Vel/día']}/día, "
                            f"stock para {r['Días de stock']} días"
                        )
                    lines.append("")
            else:
                lines.append("(Sin datos de ventas cargados)")
                lines.append("")

            if cheques:
                lines.append("## Cheques pendientes")
                for c in cheques:
                    if c["estado"] == "pendiente":
                        venc = date.fromisoformat(c["vencimiento"])
                        dias = (venc - hoy).days
                        lines.append(f"- {c['id']} {c['proveedor']}: ${c['monto']:,.0f} vence {venc.strftime('%d/%m/%Y')} ({dias} días)")
                lines.append("")

            lines += [
                "## Contexto del negocio",
                "- Gastos fijos: ~$7.000.000/mes",
                "- Necesitás $300.000/día como mínimo",
                "- Hot Sale mayo ~19/05 | Día del Padre junio ~22/06",
                "- Las camisas manga larga son el 60% de ventas online",
                "- ROAS Meta histórico: 3.2x global, 5-9x campañas específicas",
                "- Markup: 2.5x remeras, 2.3x resto",
                "- Pauta Meta activa desde 09/04 con $20.000/día",
                "- Deuda bancaria: ~$19.75M en descubierto",
            ]
            return "\n".join(lines)

        if "mensajes" not in st.session_state:
            st.session_state.mensajes = []

        # Sugerencias rápidas
        seccion("Preguntas frecuentes")
        sugerencias = [
            "¿Llegamos a cubrir el cheque del 15?",
            "¿Qué producto conviene reponer para el Hot Sale?",
            "¿Cómo va el mes comparado con el objetivo?",
            "¿Cuánto tengo que vender esta semana para cerrar el mes bien?",
        ]
        cols_sug = st.columns(len(sugerencias))
        for i, sug in enumerate(sugerencias):
            with cols_sug[i]:
                if st.button(sug, key=f"sug_{i}", use_container_width=True):
                    st.session_state.mensajes.append({"role": "user", "content": sug})
                    st.rerun()

        seccion("Conversación")

        # Historial
        for msg in st.session_state.mensajes:
            with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
                st.markdown(msg["content"])

        # Input
        if prompt := st.chat_input("Preguntá sobre ventas, stock, cheques, estrategia..."):
            st.session_state.mensajes.append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)

            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner(""):
                    try:
                        cliente = anthropic.Anthropic(api_key=api_key)
                        resp = cliente.messages.create(
                            model="claude-opus-4-5",
                            max_tokens=1024,
                            system=(
                                "Sos el asistente de gestión de The Room Argentina, tienda de ropa masculina en Corrientes. "
                                "Tenés acceso a los datos reales del negocio. "
                                "Respondé siempre en español, de forma concisa y con números concretos. "
                                "Si hay un problema urgente (cheque que vencer, ventas bajas), marcalo claramente. "
                                "No uses introducciones largas, ir al punto.\n\n"
                                + build_context()
                            ),
                            messages=[{"role": m["role"], "content": m["content"]}
                                      for m in st.session_state.mensajes],
                        )
                        respuesta = resp.content[0].text
                        st.markdown(respuesta)
                        st.session_state.mensajes.append({"role": "assistant", "content": respuesta})
                    except Exception as e:
                        st.error(f"Error: {e}")

        if st.session_state.mensajes:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️  Limpiar conversación"):
                st.session_state.mensajes = []
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 9 — CONFIG
# ══════════════════════════════════════════════════════════════════════════════
if tab9:
  with tab9:
    # Mostrar notificaciones persistentes (dentro de Config para que se vean)
    _mostrar_notificaciones()

    # ── EXPORTAR REPORTE ──────────────────────────────────────────────────────
    seccion("Exportar reporte para analizar")
    st.markdown(
        '<div style="color:#8888aa;font-size:0.85rem;margin-bottom:12px">'
        'Genera un reporte completo con toda la data del negocio. '
        'Copialo y pegalo en Claude para que te haga un analisis estrategico.'
        '</div>', unsafe_allow_html=True
    )
    if st.button("Generar reporte completo", use_container_width=True, key="btn_reporte_config"):
        st.session_state["mostrar_reporte"] = True
        st.rerun()

    # ── TASAS Y COSTOS (editables) ────────────────────────────────────────
    seccion("Tasas, comisiones y costos — editables")
    st.markdown('<div style="color:#8888aa;font-size:0.82rem;margin-bottom:12px">Cambia los valores si suben o bajan las tasas. Se usan en el Simulador.</div>', unsafe_allow_html=True)

    _p_costos_cfg = Path("data/costos_tienda.json")
    _costos_cfg = json.loads(_p_costos_cfg.read_text(encoding="utf-8")) if _p_costos_cfg.exists() else {}

    with st.form("editar_tasas", clear_on_submit=False):
        st.markdown('<div style="color:#3a86ff;font-weight:700;font-size:0.85rem;margin-bottom:8px">IMPUESTOS</div>', unsafe_allow_html=True)
        ti1, ti2, ti3 = st.columns(3)
        _iva_c_cfg = ti1.number_input("IVA sobre costo %", min_value=0.0, max_value=50.0, step=0.5, value=_costos_cfg.get("impuestos",{}).get("iva_costo",0.105)*100)
        _iibb_cfg = ti2.number_input("IIBB / Rentas %", min_value=0.0, max_value=20.0, step=0.5, value=_costos_cfg.get("impuestos",{}).get("iibb_rentas",0.045)*100)
        _icd_cfg = ti3.number_input("Imp cred/deb %", min_value=0.0, max_value=5.0, step=0.1, value=_costos_cfg.get("impuestos",{}).get("imp_credito_debito",0.006)*100)

        st.markdown('<div style="color:#f7b731;font-weight:700;font-size:0.85rem;margin:12px 0 8px 0">COMISIONES MERCADO PAGO</div>', unsafe_allow_html=True)
        tc1, tc2, tc3, tc4, tc5 = st.columns(5)
        _pas_cfg = tc1.number_input("Pasarela %", min_value=0.0, max_value=20.0, step=0.1, value=_costos_cfg.get("comisiones_mp",{}).get("pasarela",0.0507)*100)
        _c3_cfg = tc2.number_input("3 cuotas %", min_value=0.0, max_value=30.0, step=0.1, value=_costos_cfg.get("comisiones_mp",{}).get("cuotas_3",0.0651)*100)
        _c6_cfg = tc3.number_input("6 cuotas %", min_value=0.0, max_value=40.0, step=0.1, value=_costos_cfg.get("comisiones_mp",{}).get("cuotas_6",0.1242)*100)
        _c9_cfg = tc4.number_input("9 cuotas %", min_value=0.0, max_value=50.0, step=0.1, value=_costos_cfg.get("comisiones_mp",{}).get("cuotas_9",0.2049)*100)
        _pl_cfg = tc5.number_input("Plataforma %", min_value=0.0, max_value=10.0, step=0.1, value=_costos_cfg.get("comisiones_mp",{}).get("plataforma",0.01)*100)

        st.markdown('<div style="color:#00c96b;font-weight:700;font-size:0.85rem;margin:12px 0 8px 0">COSTOS FIJOS POR VENTA</div>', unsafe_allow_html=True)
        tf1, tf2, tf3 = st.columns(3)
        _pack_cfg = tf1.number_input("Packaging $", min_value=0, step=100, value=_costos_cfg.get("costos_fijos_venta",{}).get("packaging",400))
        _pub_cfg = tf2.number_input("Publicidad por venta $", min_value=0, step=500, value=_costos_cfg.get("costos_fijos_venta",{}).get("publicidad_ecommerce",4000))
        _env_cfg = tf3.number_input("Envio promedio $", min_value=0, step=500, value=_costos_cfg.get("costos_fijos_venta",{}).get("envio_promedio",5000))

        st.markdown('<div style="color:#8b5cf6;font-weight:700;font-size:0.85rem;margin:12px 0 8px 0">DESCUENTOS</div>', unsafe_allow_html=True)
        td1, td2 = st.columns(2)
        _desc_ef_cfg = td1.number_input("Descuento efectivo %", min_value=0.0, max_value=50.0, step=1.0, value=_costos_cfg.get("descuentos",{}).get("efectivo",0.15)*100)
        _desc_tr_cfg = td2.number_input("Descuento transferencia %", min_value=0.0, max_value=50.0, step=1.0, value=_costos_cfg.get("descuentos",{}).get("transferencia",0.10)*100)

        if st.form_submit_button("Guardar tasas", use_container_width=True):
            _nuevo_costos = {
                "impuestos": {
                    "iva_costo": round(_iva_c_cfg / 100, 4),
                    "iibb_rentas": round(_iibb_cfg / 100, 4),
                    "imp_credito_debito": round(_icd_cfg / 100, 4),
                },
                "comisiones_mp": {
                    "pasarela": round(_pas_cfg / 100, 4),
                    "cuotas_3": round(_c3_cfg / 100, 4),
                    "cuotas_6": round(_c6_cfg / 100, 4),
                    "cuotas_9": round(_c9_cfg / 100, 4),
                    "plataforma": round(_pl_cfg / 100, 4),
                },
                "costos_fijos_venta": {
                    "packaging": int(_pack_cfg),
                    "publicidad_ecommerce": int(_pub_cfg),
                    "envio_promedio": int(_env_cfg),
                },
                "descuentos": {
                    "efectivo": round(_desc_ef_cfg / 100, 2),
                    "transferencia": round(_desc_tr_cfg / 100, 2),
                },
                "markup": _costos_cfg.get("markup", {"remeras": 2.5, "default": 2.3}),
            }
            _save_json_and_sync(str(_p_costos_cfg), _nuevo_costos, "Actualizar tasas desde dashboard")
            _notificar("✅ Tasas actualizadas correctamente")
            st.rerun()



    # ── SUBIR GASTOS Y COMPRAS DE DUX ───────────────────────────────────────
    seccion("Subir gastos y compras de Dux")
    st.markdown(
        '<div style="color:#8888aa;font-size:0.85rem;margin-bottom:12px">'
        'Subi el .xls de <b>Consulta de Compras Detallada</b> de Dux. Lee tanto GASTOS (luz, sueldos, etc.) '
        'como COMPRAS (mercaderia). No duplica lo que ya esta cargado ni lo que vino de los extractos bancarios.'
        '</div>', unsafe_allow_html=True
    )

    compras_file = st.file_uploader(
        "Consulta de Compras Detallada (.xls)",
        type=["xls", "xlsx"],
        key="compras_dux",
    )

    if compras_file:
        with st.spinner("Procesando gastos..."):
            from data_processor import load_compras_dux
            gastos_nuevos_dux = load_compras_dux(compras_file.getvalue())

        if not gastos_nuevos_dux:
            st.warning(f"✅ Archivo '{compras_file.name}' leído correctamente, pero no se encontraron gastos nuevos. Verificá que sea Consulta de Compras Detallada.")
        else:
            # Deduplicar contra gastos existentes
            gastos_existentes = get_gastos()
            claves_existentes = set()
            for g in gastos_existentes:
                claves_existentes.add((g["fecha"], round(g["monto"], 2)))

            agregados = 0
            duplicados = 0
            for g in gastos_nuevos_dux:
                clave = (g["fecha"], round(g["monto"], 2))
                if clave not in claves_existentes:
                    gastos_existentes.append(g)
                    claves_existentes.add(clave)
                    agregados += 1
                else:
                    duplicados += 1

            if agregados > 0:
                save_gastos(gastos_existentes)
                st.success(f"✅ Archivo '{compras_file.name}' procesado — {agregados} gastos nuevos cargados, {duplicados} duplicados omitidos")

                with st.expander(f"Ver {agregados} gastos nuevos"):
                    rows_cn = ""
                    for g in gastos_nuevos_dux:
                        rows_cn += f'<tr><td>{g["fecha"]}</td><td style="font-size:0.82rem">{g["concepto"][:50]}</td><td>{g["categoria"]}</td><td>{g["medio"]}</td><td style="text-align:right;color:#e94560;font-weight:700">{fmt_tabla(g["monto"])}</td></tr>'
                    st.markdown(
                        f'<div class="tabla-wrapper"><table class="tabla-custom">'
                        f'<thead><tr><th>Fecha</th><th>Concepto</th><th>Categoria</th><th>Medio</th><th style="text-align:right">Monto</th></tr></thead>'
                        f'<tbody>{rows_cn}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info(f"✅ Archivo '{compras_file.name}' leído — todos los gastos ya estaban cargados ({duplicados} duplicados)")

    # ── SUBIR ARCHIVO DUX ────────────────────────────────────────────────────
    seccion("Subir archivo de ventas (Dux)")

    # Paso 1: seleccionar archivo
    uploaded = st.file_uploader(
        "1. Elegir el archivo .xls exportado de Dux (podés subir varios a la vez)",
        type=["xls", "xlsx"],
        accept_multiple_files=True,
    )

    # Paso 2: botón para guardar
    if uploaded:
        st.markdown(
            f"<div style='color:#f7b731;font-size:0.9rem;margin:4px 0 8px 0'>"
            f"{len(uploaded)} archivo{'s' if len(uploaded)!=1 else ''} listo{'s' if len(uploaded)!=1 else ''} "
            f"para procesar</div>",
            unsafe_allow_html=True,
        )
        if st.button("Guardar y procesar", use_container_width=True):
            Path("data/ventas").mkdir(parents=True, exist_ok=True)
            guardados = []
            for f in uploaded:
                # Renombrar automáticamente con las fechas del reporte
                nombre_final = f.name
                try:
                    import xlrd as _xlrd_rename
                    _wb_r = _xlrd_rename.open_workbook(file_contents=f.getvalue())
                    _ws_r = _wb_r.sheet_by_index(0)
                    _fechas_r = []
                    _col_fecha_r = None
                    for j in range(_ws_r.ncols):
                        if "Fecha Comp" in str(_ws_r.cell(2, j).value):
                            _col_fecha_r = j
                            break
                    if _col_fecha_r is not None:
                        for i in range(3, _ws_r.nrows):
                            _fv = _ws_r.cell(i, _col_fecha_r).value
                            if isinstance(_fv, float) and _fv > 0:
                                _fechas_r.append(_xlrd_rename.xldate_as_datetime(_fv, _wb_r.datemode).date())
                    if _fechas_r:
                        _desde = min(_fechas_r)
                        _hasta = max(_fechas_r)
                        ext = Path(f.name).suffix
                        nombre_final = f"ventas_{_desde.strftime('%d-%m')}_{_hasta.strftime('%d-%m')}{ext}"
                except Exception:
                    pass
                dest = Path("data/ventas") / nombre_final
                dest.write_bytes(f.getvalue())
                _sync_github_binary(f"data/ventas/{nombre_final}", f.getvalue(), f"Subir ventas {nombre_final} desde dashboard")
                guardados.append(nombre_final)
            st.cache_data.clear()
            n = len(guardados)
            _notificar(f"✅ {'Archivo' if n==1 else str(n)+' archivos'} de ventas subido{'s' if n>1 else ''} correctamente: {', '.join(guardados)}")
            st.rerun()

    # Info de archivos en servidor
    archivos_xls = list(Path("data/ventas").glob("*.xls")) + list(Path("data/ventas").glob("*.xlsx"))

    if archivos_xls:
        # Leer datos frescos para mostrar resumen
        _df_info = load_dux_files("data/ventas")
        _dias_info = _df_info["fecha_dia"].nunique() if not _df_info.empty else 0
        _neto_info = _df_info["neto"].sum() if not _df_info.empty else 0
        _desde = _df_info["fecha_dia"].min() if not _df_info.empty else "—"
        _hasta = _df_info["fecha_dia"].max() if not _df_info.empty else "—"

        st.markdown(f"""
        <div style="background:#1a1a2e;border:1px solid #00c96b33;border-radius:12px;
                    padding:16px 20px;margin:12px 0;border-left:3px solid #00c96b">
            <div style="color:#00c96b;font-weight:700;font-size:0.9rem;margin-bottom:8px">
                Datos cargados en el sistema
            </div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
                <div>
                    <div style="color:#6666aa;font-size:0.7rem">ARCHIVOS</div>
                    <div style="color:#fff;font-weight:700;font-size:1.2rem">{len(archivos_xls)}</div>
                </div>
                <div>
                    <div style="color:#6666aa;font-size:0.7rem">DIAS CON VENTA</div>
                    <div style="color:#fff;font-weight:700;font-size:1.2rem">{_dias_info}</div>
                </div>
                <div>
                    <div style="color:#6666aa;font-size:0.7rem">TOTAL NETO</div>
                    <div style="color:#00c96b;font-weight:700;font-size:1.2rem">{fmt(_neto_info)}</div>
                </div>
                <div>
                    <div style="color:#6666aa;font-size:0.7rem">RANGO</div>
                    <div style="color:#fff;font-weight:700;font-size:0.85rem">{_desde} al {_hasta}</div>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)

        with st.expander(f"Archivos en el servidor ({len(archivos_xls)})"):
            for f in sorted(archivos_xls):
                col_fn, col_del = st.columns([5, 1])
                col_fn.markdown(
                    f"<span style='color:#8888aa;font-size:0.85rem'>{f.name}</span>",
                    unsafe_allow_html=True,
                )
                if col_del.button("Borrar", key=f"del_{f.name}"):
                    f.unlink()
                    st.cache_data.clear()
                    st.rerun()
    else:
        alerta_html("No hay archivos cargados todavia — subi el .xls de Dux arriba", "azul")

    # ── EXTRACTO BANCARIO ────────────────────────────────────────────────────
    seccion("Subir extracto bancario")
    st.markdown(
        '<div style="color:#8888aa;font-size:0.85rem;margin-bottom:12px">'
        'Baja el extracto desde el homebanking (Corrientes, BBVA Frances, Santander, MP) '
        'en formato Excel o PDF y subilo aca. Selecciona el banco y hace clic en Procesar.'
        '</div>', unsafe_allow_html=True
    )

    BANCOS_OPCIONES = ["Banco Corrientes", "BBVA Frances", "Galicia", "Santander", "Mercado Pago"]
    banco_sel = st.selectbox("Banco del extracto", BANCOS_OPCIONES)

    extracto_file = st.file_uploader(
        f"Extracto de {banco_sel} (.xls / .xlsx / .csv / .pdf)",
        type=["xls", "xlsx", "csv", "pdf"],
        key="extracto_banco",
    )

    if extracto_file:
        if st.button(f"Procesar extracto {banco_sel}", use_container_width=True):
            from data_processor import parsear_extracto_corrientes

            if extracto_file.name.endswith(".pdf"):
                st.warning("Los PDF no se procesan automaticamente todavia. Mandamelo por chat y lo cargo yo.")
            else:
                try:
                    with st.spinner(f"Procesando extracto de {banco_sel}..."):
                        resultado = parsear_extracto_corrientes(extracto_file.getvalue(), extracto_file.name)

                    if "error" in resultado:
                        st.error(f"No se pudo leer el extracto: {resultado['error']}")
                    else:
                        saldo_nuevo   = resultado["saldo_actual"]
                        movs          = resultado["movimientos"]
                        gastos_nuevos = resultado["gastos_nuevos"]
                        resumen       = resultado["resumen"]

                        # Actualizar saldo del banco seleccionado en bancos.json
                        bancos_data = get_bancos()
                        ult_banco   = bancos_data[-1].copy() if bancos_data else {}
                        ult_banco["fecha"]     = hoy.isoformat()
                        ult_banco[banco_sel]   = int(saldo_nuevo)
                        ult_banco["notas"]     = f"Saldo {banco_sel} importado de {extracto_file.name}"
                        bancos_data.append(ult_banco)
                        save_bancos(bancos_data)

                        # Agregar gastos nuevos a gastos.json (sin duplicar, sin transferencias)
                        gastos_existentes = get_gastos()
                        claves_existentes = {
                            (g["fecha"], g["concepto"], g["monto"]) for g in gastos_existentes
                        }
                        _CUIT_PROPIO = "30717936279"
                        _FILTRO_TRANSFER = ("TRANSF", "TRF:", "BRUDER", "THE ROOM")
                        nuevos_agregados = 0
                        transferencias_filtradas = 0
                        for g in gastos_nuevos:
                            g["medio"] = banco_sel
                            # Filtro de seguridad: rechazar transferencias internas
                            _txt = f"{g.get('concepto','')} {g.get('notas','')}".upper()
                            if _CUIT_PROPIO in _txt or any(p in _txt for p in _FILTRO_TRANSFER):
                                transferencias_filtradas += 1
                                continue
                            clave = (g["fecha"], g["concepto"], g["monto"])
                            if clave not in claves_existentes:
                                gastos_existentes.append(g)
                                claves_existentes.add(clave)
                                nuevos_agregados += 1
                        save_gastos(gastos_existentes)

                        # Notificación persistente
                        _msg_transf = f" | {transferencias_filtradas} transferencias internas ignoradas" if transferencias_filtradas else ""
                        _notificar(
                            f"✅ Extracto de {banco_sel} procesado correctamente — "
                            f"Saldo: {fmt(saldo_nuevo)} | "
                            f"{resumen['cant_movimientos']} movimientos | "
                            f"{nuevos_agregados} gastos cargados | "
                            f"Total débitos: {fmt(resumen['total_debitos'])}"
                            f"{_msg_transf}"
                        )
                        st.rerun()
                except Exception as e:
                    st.error(f"Error procesando extracto: {e}")

    # ── SALDOS BANCARIOS ─────────────────────────────────────────────────────
    seccion("Actualizar saldos bancarios")
    st.markdown("""
    <div style="color:#8888aa;font-size:0.85rem;margin-bottom:12px">
        Ingresá los saldos actuales de cada banco (negativo si esta en rojo).
    </div>""", unsafe_allow_html=True)

    bancos_data = get_bancos()
    ult = bancos_data[-1] if bancos_data else {}

    with st.form("saldo_banco", clear_on_submit=True):
        b1, b2, b3 = st.columns(3)
        frances_f = b1.number_input("BBVA Frances $", step=100000, value=ult.get("BBVA Frances", ult.get("BBVA", 0)))
        bctes_f   = b2.number_input("Banco Corrientes $",    step=100000, value=ult.get("Banco Corrientes", 0))
        gal_f     = b3.number_input("Galicia $",             step=100000, value=ult.get("Galicia", 0))
        b4, b5, b6 = st.columns(3)
        sant_f    = b4.number_input("Santander $",           step=100000, value=ult.get("Santander", 0))
        mp_f      = b5.number_input("Mercado Pago $",        step=10000,  value=ult.get("Mercado Pago", 0))
        ef_f      = b6.number_input("Efectivo / Caja $",     step=10000,  value=ult.get("Efectivo Caja", 0))
        nota_b  = st.text_input("Nota (opcional)", placeholder="Ej: actualizado del homebanking")
        if st.form_submit_button("Guardar saldos de hoy", use_container_width=True):
            bancos_data.append({
                "fecha": hoy.isoformat(),
                "BBVA Frances": int(frances_f),
                "Banco Corrientes": int(bctes_f),
                "Galicia": int(gal_f),
                "Santander": int(sant_f), "Mercado Pago": int(mp_f),
                "Efectivo Caja": int(ef_f),
                "notas": nota_b,
            })
            save_bancos(bancos_data)
            _notificar("✅ Saldos bancarios guardados correctamente")
            st.rerun()

    if len(bancos_data) > 1:
        with st.expander("Historial de saldos"):
            rows_b = ""
            for b in reversed(bancos_data[-10:]):
                total_b = b.get("BBVA",0)+b.get("Banco Corrientes",0)+b.get("Santander",0)+b.get("Mercado Pago",0)
                color_t = "#00c96b" if total_b >= 0 else "#e94560"
                rows_b += f"""<tr>
                    <td>{b['fecha']}</td>
                    <td>{fmt(b.get('BBVA',0))}</td>
                    <td>{fmt(b.get('Banco Corrientes',0))}</td>
                    <td>{fmt(b.get('Santander',0))}</td>
                    <td>{fmt(b.get('Mercado Pago',0))}</td>
                    <td style="color:{color_t};font-weight:700">{fmt(total_b)}</td>
                </tr>"""
            st.markdown(f"""
            <div class="tabla-wrapper">
            <table class="tabla-custom">
                <thead><tr>
                    <th>Fecha</th><th>BBVA</th><th>Ctes</th>
                    <th>Santander</th><th>MP</th><th>Total</th>
                </tr></thead>
                <tbody>{rows_b}</tbody>
            </table></div>""", unsafe_allow_html=True)

    # ── VENTA MANUAL ─────────────────────────────────────────────────────────
    seccion("Cargar venta del dia (alternativa a Dux)")
    with st.form("venta_manual", clear_on_submit=True):
        vm1, vm2, vm3, vm4 = st.columns(4)
        fecha_vm = vm1.date_input("Fecha", value=hoy)
        neto_vm  = vm2.number_input("Neto $ (sin IVA)", min_value=0, step=1000)
        cant_vm  = vm3.number_input("Unidades", min_value=0, step=1)
        canal_vm = vm4.selectbox("Canal", ["Físico", "Online"])
        if st.form_submit_button("Guardar venta", use_container_width=True):
            if neto_vm > 0:
                p_vm = Path("data/ventas_manuales.json")
                vm_data = json.loads(p_vm.read_text(encoding="utf-8")) if p_vm.exists() else []
                vm_data = [v for v in vm_data if v["fecha"] != fecha_vm.isoformat()]
                vm_data.append({"fecha": fecha_vm.isoformat(), "neto": int(neto_vm),
                                "cantidad": int(cant_vm), "canal": canal_vm})
                vm_data.sort(key=lambda x: x["fecha"])
                _save_json_and_sync(str(p_vm), vm_data, "Venta manual cargada desde dashboard")
                st.cache_data.clear()
                _notificar(f"✅ Venta del {fecha_vm.strftime('%d/%m')} guardada — {fmt(neto_vm)}")
                st.rerun()

    # ── GASTOS ───────────────────────────────────────────────────────────────
    seccion("Cargar gasto")
    with st.form("nuevo_gasto", clear_on_submit=True):
        g1, g2, g3 = st.columns(3)
        concepto_g = g1.text_input("Concepto", placeholder="Alquiler, sueldo, AFIP...")
        monto_g    = g2.number_input("Monto $", min_value=0, step=1000)
        fecha_g    = g3.date_input("Fecha", value=hoy)
        if st.form_submit_button("Guardar gasto", use_container_width=True):
            if monto_g > 0 and concepto_g:
                gastos_data = get_gastos()
                gastos_data.append({"fecha": fecha_g.isoformat(),
                                    "concepto": concepto_g, "monto": int(monto_g)})
                save_gastos(gastos_data)
                _notificar(f"✅ {concepto_g} — {fmt(monto_g)} guardado")
                st.rerun()

    gastos_data = get_gastos()
    if gastos_data:
        with st.expander(f"Gastos cargados ({len(gastos_data)})"):
            rows_g2 = ""
            for i, g in enumerate(reversed(gastos_data[-20:])):
                rows_g2 += f"""<tr>
                    <td>{g['fecha']}</td>
                    <td>{g['concepto']}</td>
                    <td style="color:#e94560;font-weight:700">{fmt_tabla(g['monto'])}</td>
                </tr>"""
            st.markdown(f"""
            <div class="tabla-wrapper">
            <table class="tabla-custom">
                <thead><tr><th>Fecha</th><th>Concepto</th><th>Monto</th></tr></thead>
                <tbody>{rows_g2}</tbody>
            </table></div>""", unsafe_allow_html=True)

    # ── API KEY ───────────────────────────────────────────────────────────────
    seccion("Anthropic API Key (chat IA)")
    nueva_key = st.text_input(
        "API Key", type="password",
        value=st.session_state.api_key, placeholder="sk-ant-...",
    )
    if nueva_key != st.session_state.api_key:
        st.session_state.api_key = nueva_key
        st.success("Guardada")

    col_ref, _ = st.columns([1, 3])
    with col_ref:
        if st.button("Actualizar todo", use_container_width=True):
            st.cache_data.clear()
            _notificar("✅ Datos actualizados")
            st.rerun()
