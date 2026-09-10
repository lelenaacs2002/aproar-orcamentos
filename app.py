from __future__ import annotations

import os
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from radar import analyze_snapshot
from trello_client import TrelloClient, TrelloError


st.set_page_config(
    page_title="APROAR • Orçamentos",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False

if "fila_orcamentos" not in st.session_state:
    st.session_state["fila_orcamentos"] = "Conferir retorno"

DARK = bool(st.session_state["dark_mode"])

if DARK:
    THEME = {
        "bg": "#0d1520",
        "surface": "#132131",
        "surface2": "#18293c",
        "navy": "#0d2238",
        "navy2": "#183754",
        "ink": "#f4f7fb",
        "muted": "#a7b6c7",
        "line": "#2a3b4f",
        "input": "#162536",
        "input_text": "#f4f7fb",
        "shadow": "rgba(0,0,0,.18)",
    }
else:
    THEME = {
        "bg": "#f4f6f8",
        "surface": "#ffffff",
        "surface2": "#f8fafc",
        "navy": "#122b44",
        "navy2": "#1a3b5b",
        "ink": "#142f49",
        "muted": "#6f8296",
        "line": "#d8e0e8",
        "input": "#ffffff",
        "input_text": "#18314a",
        "shadow": "rgba(21,44,68,.06)",
    }

st.markdown(
    f"""
<style>
:root {{
    --bg:{THEME["bg"]};
    --surface:{THEME["surface"]};
    --surface2:{THEME["surface2"]};
    --navy:{THEME["navy"]};
    --navy2:{THEME["navy2"]};
    --ink:{THEME["ink"]};
    --muted:{THEME["muted"]};
    --line:{THEME["line"]};
    --input:{THEME["input"]};
    --input-text:{THEME["input_text"]};
    --shadow:{THEME["shadow"]};
    --orange:#ef7643;
    --orange-soft:#fff1ea;
    --blue:#24599b;
    --blue-soft:#eaf1fb;
    --green:#1d8d58;
    --green-soft:#eaf7f0;
    --amber:#bf741b;
    --amber-soft:#fff6e9;
    --red:#c75151;
}}

html, body, [data-testid="stAppViewContainer"] {{
    background:var(--bg) !important;
    color:var(--ink) !important;
}}
[data-testid="stHeader"] {{background:transparent !important;}}
[data-testid="collapsedControl"], [data-testid="stSidebar"] {{display:none !important;}}
#MainMenu, footer {{visibility:hidden;}}
.main .block-container {{
    max-width:1320px;
    padding-top:.5rem;
    padding-bottom:3rem;
}}
p, label, h1, h2, h3, h4, h5, h6 {{color:var(--ink);}}

.ap-topbar {{
    background:var(--navy);
    margin:-.5rem -1rem 1.65rem -1rem;
    padding:17px 24px;
    border-radius:0 0 16px 16px;
}}
.ap-topbar-inner {{display:flex;align-items:center;justify-content:space-between;gap:18px;}}
.ap-brand {{display:flex;align-items:center;gap:14px;color:white;}}
.ap-logo {{
    width:40px;height:40px;border-radius:10px;background:var(--orange);
    display:grid;place-items:center;font-size:25px;font-weight:900;
}}
.ap-brand-main {{font-size:18px;font-weight:900;letter-spacing:.12em;}}
.ap-brand-divider {{opacity:.35;font-size:25px;}}
.ap-brand-area {{font-size:14px;letter-spacing:.17em;}}
.ap-live {{
    border:1px solid rgba(255,255,255,.28);
    border-radius:9px;padding:6px 10px;color:white;font-size:12px;
}}

.ap-kicker {{
    color:var(--muted);font-weight:800;text-transform:uppercase;
    letter-spacing:.14em;font-size:12px;margin-bottom:8px;
}}
.ap-title {{
    color:var(--ink);font-size:36px;line-height:1.05;font-weight:900;
    letter-spacing:-.04em;margin:0;
}}
.ap-dot {{color:var(--orange);}}
.ap-subtitle {{color:var(--muted);font-size:16px;margin-top:8px;}}
.ap-sync {{color:var(--muted);font-size:12px;margin-top:7px;}}

.ap-rule {{
    background:var(--surface);border:1px solid var(--line);
    border-left:4px solid #7ca7df;border-radius:12px;
    padding:12px 14px;color:var(--muted);font-size:13px;
    line-height:1.5;margin:14px 0 20px;
}}

.ap-metrics {{
    display:grid;grid-template-columns:repeat(3,1fr);
    background:var(--surface);border:1px solid var(--line);
    border-radius:16px;overflow:hidden;margin:20px 0 28px;
    box-shadow:0 8px 22px var(--shadow);
}}
.ap-metric {{
    display:flex;align-items:center;gap:16px;padding:22px 26px;
    border-right:1px solid var(--line);min-height:86px;
}}
.ap-metric:last-child {{border-right:none;}}
.ap-metric-num {{font-size:28px;font-weight:900;min-width:42px;}}
.ap-metric-label {{color:var(--muted);font-size:15px;}}
.orange {{color:var(--orange);}}
.blue {{color:var(--blue);}}
.green {{color:var(--green);}}

.ap-section-head {{
    display:flex;justify-content:space-between;align-items:center;
    gap:16px;margin:26px 0 12px;
}}
.ap-section-title {{font-size:20px;font-weight:900;color:var(--ink);}}
.ap-section-count {{font-size:13px;color:var(--muted);}}

.ap-card {{
    background:var(--surface);border:1px solid var(--line);
    border-radius:16px;padding:18px 20px;margin:12px 0;
    box-shadow:0 8px 22px var(--shadow);
}}
.ap-card-top {{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;}}
.ap-badges {{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-bottom:9px;}}
.ap-badge {{
    display:inline-flex;align-items:center;padding:5px 10px;
    border-radius:999px;font-size:11px;font-weight:800;
}}
.ap-badge-orange {{background:var(--orange-soft);color:#c95d2f;}}
.ap-badge-blue {{background:var(--blue-soft);color:var(--blue);}}
.ap-badge-green {{background:var(--green-soft);color:var(--green);}}
.ap-badge-amber {{background:var(--amber-soft);color:var(--amber);}}
.ap-badge-gray {{background:var(--surface2);color:var(--muted);border:1px solid var(--line);}}
.ap-ref {{color:var(--muted);font-size:11px;font-weight:700;}}
.ap-card-title {{color:var(--ink);font-size:17px;font-weight:900;line-height:1.3;}}
.ap-card-meta {{color:var(--muted);font-size:13px;margin-top:5px;line-height:1.55;}}
.ap-card-meta b {{color:var(--ink);}}
.ap-card-right {{
    min-width:150px;text-align:right;color:var(--amber);
    font-size:13px;white-space:nowrap;
}}
.ap-card-block {{margin-top:13px;padding-top:12px;border-top:1px solid var(--line);}}
.ap-card-label {{
    color:var(--muted);text-transform:uppercase;letter-spacing:.08em;
    font-size:10px;font-weight:800;margin-bottom:5px;
}}
.ap-card-text {{color:var(--ink);font-size:13px;line-height:1.55;}}
.ap-card-text a {{color:var(--blue);font-weight:700;text-decoration:none;}}
.ap-empty {{
    background:var(--surface);border:1px dashed var(--line);
    border-radius:14px;padding:22px;color:var(--muted);font-size:14px;
}}

/* SELECTS — fixa as cores independentemente do tema nativo do Streamlit */
div[data-baseweb="select"] > div {{
    background:var(--input) !important;
    color:var(--input-text) !important;
    border-color:var(--line) !important;
    border-radius:11px !important;
    min-height:46px !important;
}}
div[data-baseweb="select"] span {{color:var(--input-text) !important;}}
div[data-baseweb="select"] svg {{fill:var(--input-text) !important;}}
ul[role="listbox"] {{
    background:var(--surface) !important;
    border:1px solid var(--line) !important;
}}
li[role="option"] {{
    background:var(--surface) !important;
    color:var(--ink) !important;
}}
li[role="option"]:hover {{background:var(--surface2) !important;}}

/* BOTÕES — evita o preto do tema nativo */
div[data-testid="stButton"] > button {{
    background:var(--surface) !important;
    color:var(--ink) !important;
    border:1px solid var(--line) !important;
    border-radius:11px !important;
    box-shadow:none !important;
    font-weight:700 !important;
}}
div[data-testid="stButton"] > button:hover {{
    background:var(--surface2) !important;
    color:var(--ink) !important;
    border-color:#9fb3c8 !important;
}}
div[data-testid="stButton"] > button p {{color:inherit !important;}}

/* FILAS em formato de botões */
div[data-testid="stRadio"] > div[role="radiogroup"] {{
    display:grid !important;
    grid-template-columns:repeat(5,1fr);
    gap:10px;
}}
div[data-testid="stRadio"] label {{
    background:var(--surface) !important;
    border:1px solid var(--line) !important;
    border-radius:11px !important;
    min-height:46px !important;
    padding:0 12px !important;
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
}}
div[data-testid="stRadio"] label:has(input:checked) {{
    background:var(--navy) !important;
    border-color:var(--navy) !important;
}}
div[data-testid="stRadio"] label:has(input:checked) p {{color:#fff !important;}}
div[data-testid="stRadio"] label p {{
    color:var(--ink) !important;
    font-size:13px !important;
    font-weight:700 !important;
}}
div[data-testid="stRadio"] input,
div[data-testid="stRadio"] [data-baseweb="radio"] > div:first-child {{
    display:none !important;
}}

/* TOGGLE pequeno */
.ap-theme-caption {{
    text-align:right;color:var(--muted);font-size:10px;margin-bottom:-2px;
}}
div[data-testid="stToggle"] {{
    transform:scale(.82);
    transform-origin:right top;
}}
div[data-testid="stToggle"] label {{
    color:var(--muted) !important;
    font-size:11px !important;
}}

div[data-testid="stExpander"] {{
    background:var(--surface) !important;
    border:1px solid var(--line) !important;
    border-radius:13px !important;
}}

@media (max-width:900px) {{
    .main .block-container {{padding-left:.8rem;padding-right:.8rem;}}
    .ap-topbar {{margin-left:-.8rem;margin-right:-.8rem;}}
    .ap-card-top {{display:block;}}
    .ap-title {{font-size:30px;}}
    .ap-card-right {{text-align:left;margin-top:10px;min-width:0;}}
    .ap-metrics {{grid-template-columns:1fr;}}
    .ap-metric {{border-right:none;border-bottom:1px solid var(--line);}}
    .ap-metric:last-child {{border-bottom:none;}}
    div[data-testid="stRadio"] > div[role="radiogroup"] {{grid-template-columns:1fr 1fr;}}
    .ap-brand-divider,.ap-live {{display:none;}}
}}
</style>
""",
    unsafe_allow_html=True,
)


def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def load_snapshot(force_nonce: int = 0) -> dict[str, Any]:
    board = secret(
        "TRELLO_BOARD_URL",
        secret("TRELLO_BOARD", "https://trello.com/b/TX8hGvmI"),
    )
    return TrelloClient(board=board).snapshot()


@st.cache_data(ttl=300, show_spinner=False)
def cached_snapshot(force_nonce: int = 0) -> dict[str, Any]:
    return load_snapshot(force_nonce)


def safe_text(value: Any, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else fallback


def fila_badge(fila: str) -> str:
    return {
        "Cobrar Engenharia": "ap-badge-orange",
        "Conferir retorno": "ap-badge-blue",
        "Pronto para elaborar": "ap-badge-green",
        "Aguardar terceiros": "ap-badge-amber",
        "Em produção": "ap-badge-gray",
    }.get(fila, "ap-badge-gray")


def render_topbar() -> None:
    st.markdown(
        """
        <div class="ap-topbar">
          <div class="ap-topbar-inner">
            <div class="ap-brand">
              <div class="ap-logo">A</div>
              <div class="ap-brand-main">APROAR</div>
              <div class="ap-brand-divider">|</div>
              <div class="ap-brand-area">ORÇAMENTOS</div>
            </div>
            <div class="ap-live">Trello conectado</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(conferir: int, aguardando: int, elaborar: int) -> None:
    st.markdown(
        f"""
        <div class="ap-metrics">
          <div class="ap-metric">
            <div class="ap-metric-num orange">{conferir:02d}</div>
            <div class="ap-metric-label">Para conferir</div>
          </div>
          <div class="ap-metric">
            <div class="ap-metric-num blue">{aguardando:02d}</div>
            <div class="ap-metric-label">Aguardando resposta</div>
          </div>
          <div class="ap-metric">
            <div class="ap-metric-num green">{elaborar:02d}</div>
            <div class="ap-metric-label">Para elaborar</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_card(row: pd.Series) -> None:
    fila = safe_text(row.get("Fila"))
    title = safe_text(row.get("Demanda"))
    unidade = safe_text(row.get("Unidade"))
    supervisor = safe_text(row.get("Engenharia"))
    etapa = safe_text(row.get("Etapa Trello"))
    prazo = safe_text(row.get("Situação do prazo"))
    next_action = safe_text(row.get("Pendência / próxima ação"))
    gaps = safe_text(row.get("Possíveis lacunas"))
    last_reply = safe_text(row.get("Último retorno Engenharia"))
    last_author = safe_text(row.get("Autor último comentário"))
    last_date = safe_text(row.get("Último comentário em"))
    service = safe_text(row.get("Tipo de serviço"))
    waiting = safe_text(row.get("Aguardando"))
    url = safe_text(row.get("URL"), "")
    ref = safe_text(row.get("Card ID"), "")[-4:] or "—"

    link_html = (
        f'<a href="{escape(url, quote=True)}" target="_blank">Abrir no Trello ↗</a>'
        if url else ""
    )

    gaps_html = ""
    if gaps != "—":
        gaps_html = f"""
        <div class="ap-card-block">
          <div class="ap-card-label">O que ainda precisa ser conferido</div>
          <div class="ap-card-text">{escape(gaps)}</div>
        </div>
        """

    reply_html = ""
    if last_reply != "—":
        reply_html = f"""
        <div class="ap-card-block">
          <div class="ap-card-label">Último retorno da Engenharia</div>
          <div class="ap-card-text">{escape(last_reply)}</div>
        </div>
        """

    st.markdown(
        f"""
        <div class="ap-card">
          <div class="ap-card-top">
            <div style="flex:1;min-width:0;">
              <div class="ap-badges">
                <span class="ap-badge {fila_badge(fila)}">{escape(fila)}</span>
                <span class="ap-ref">REF. {escape(ref)}</span>
              </div>
              <div class="ap-card-title">{escape(title)}</div>
              <div class="ap-card-meta">
                <b>Unidade:</b> {escape(unidade)}
                &nbsp; • &nbsp;
                <b>Supervisor:</b> {escape(supervisor)}
                &nbsp; • &nbsp;
                <b>Etapa Trello:</b> {escape(etapa)}
              </div>
            </div>
            <div class="ap-card-right">{escape(prazo)}</div>
          </div>

          <div class="ap-card-block">
            <div class="ap-card-label">Próximo passo</div>
            <div class="ap-card-text">{escape(next_action)}</div>
          </div>

          {gaps_html}
          {reply_html}

          <div class="ap-card-block">
            <div class="ap-card-text">
              <b>Aguardando:</b> {escape(waiting)}
              &nbsp; • &nbsp;
              <b>Serviço:</b> {escape(service)}
              &nbsp; • &nbsp;
              {link_html}
            </div>
          </div>

          <div class="ap-card-block">
            <div class="ap-card-label">Última movimentação</div>
            <div class="ap-card-text">{escape(last_author)} • {escape(last_date)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


nonce = int(st.session_state.get("trello_nonce", 0))

try:
    snapshot = cached_snapshot(nonce)
except TrelloError as exc:
    render_topbar()
    st.error(str(exc))
    st.info("Confira `TRELLO_BOARD_URL` nos Secrets do Streamlit.")
    st.stop()
except Exception as exc:
    render_topbar()
    st.error(f"Não foi possível carregar o Trello: {exc}")
    st.stop()

trust_ready = bool(secret("TRUST_TRELLO_READY_LIST", False))
result = analyze_snapshot(snapshot, trust_trello_ready_list=trust_ready)
df = result.rows.copy()

render_topbar()

head_left, head_right = st.columns([8, 1.05])

with head_left:
    st.markdown('<div class="ap-kicker">Orçamentos / Conferência</div>', unsafe_allow_html=True)
    st.markdown(
        '<h1 class="ap-title">Conferir levantamentos<span class="ap-dot">.</span></h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ap-subtitle">Veja quem cobrar, o que falta e quais demandas já podem seguir para elaboração.</div>',
        unsafe_allow_html=True,
    )

with head_right:
    st.markdown('<div class="ap-theme-caption">Tema</div>', unsafe_allow_html=True)
    st.toggle(
        "🌙",
        key="dark_mode",
        help="Alternar entre modo claro e escuro",
    )

sync_left, sync_right = st.columns([1.15, 8])

with sync_left:
    if st.button("↻ Atualizar", use_container_width=True):
        st.session_state["trello_nonce"] = int(st.session_state.get("trello_nonce", 0)) + 1
        cached_snapshot.clear()
        st.rerun()

with sync_right:
    board_name = safe_text((snapshot.get("board") or {}).get("name"), "ORÇAMENTOS")
    st.markdown(
        f'<div class="ap-sync">Quadro: <b>{escape(board_name)}</b> • leitura em cache por até 5 minutos.</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="ap-rule">
      <b>Regra de liberação:</b> um retorno do supervisor não libera o orçamento sozinho.
      Primeiro Orçamentos confere se as informações realmente são suficientes; só depois
      a demanda entra em “Pronto para elaborar”.
    </div>
    """,
    unsafe_allow_html=True,
)

f1, f2, f3, f4 = st.columns(4)

engineer_options = ["Todos"] + sorted(
    [x for x in df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique() if x]
)
stage_options = ["Todas"] + sorted(
    [x for x in df.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x]
)
wait_options = ["Todos"] + sorted(
    [x for x in df.get("Aguardando", pd.Series(dtype=str)).dropna().astype(str).unique() if x]
)

with f1:
    filtro_eng = st.selectbox("Engenharia", engineer_options)
with f2:
    filtro_stage = st.selectbox("Etapa Trello", stage_options)
with f3:
    filtro_wait = st.selectbox("Aguardando", wait_options)
with f4:
    filtro_prazo = st.selectbox(
        "Prazo",
        ["Todos", "Atrasados", "Hoje", "Até 2 dias", "Sem prazo"],
    )

filtered = df.copy()

if not filtered.empty:
    if filtro_eng != "Todos":
        filtered = filtered[filtered["Engenharia"] == filtro_eng]
    if filtro_stage != "Todas":
        filtered = filtered[filtered["Etapa Trello"] == filtro_stage]
    if filtro_wait != "Todos":
        filtered = filtered[filtered["Aguardando"] == filtro_wait]

    dias = pd.to_numeric(
        filtered.get("Dias até prazo", pd.Series(index=filtered.index, dtype=float)),
        errors="coerce",
    )

    if filtro_prazo == "Atrasados":
        filtered = filtered[dias < 0]
    elif filtro_prazo == "Hoje":
        filtered = filtered[dias == 0]
    elif filtro_prazo == "Até 2 dias":
        filtered = filtered[dias.between(0, 2, inclusive="both")]
    elif filtro_prazo == "Sem prazo":
        filtered = filtered[dias.isna()]

counts = (
    filtered["Fila"].value_counts()
    if not filtered.empty
    else pd.Series(dtype=int)
)

render_metrics(
    int(counts.get("Conferir retorno", 0)),
    int(counts.get("Cobrar Engenharia", 0)),
    int(counts.get("Pronto para elaborar", 0)),
)

st.markdown(
    f"""
    <div class="ap-section-head">
      <div class="ap-section-title">Fila de levantamentos</div>
      <div class="ap-section-count">{len(filtered)} demandas</div>
    </div>
    """,
    unsafe_allow_html=True,
)

queue_order = [
    "Cobrar Engenharia",
    "Conferir retorno",
    "Pronto para elaborar",
    "Aguardar terceiros",
    "Em produção",
]

queue_labels = {
    "Cobrar Engenharia": f"Cobrar Engenharia · {int(counts.get('Cobrar Engenharia', 0))}",
    "Conferir retorno": f"Conferir retorno · {int(counts.get('Conferir retorno', 0))}",
    "Pronto para elaborar": f"Pronto para elaborar · {int(counts.get('Pronto para elaborar', 0))}",
    "Aguardar terceiros": f"Terceiros · {int(counts.get('Aguardar terceiros', 0))}",
    "Em produção": f"Em produção · {int(counts.get('Em produção', 0))}",
}

reverse_labels = {label: queue for queue, label in queue_labels.items()}

current_queue = st.session_state.get("fila_orcamentos", "Conferir retorno")
if current_queue not in queue_order:
    current_queue = "Conferir retorno"

selected_label = st.radio(
    "Fila",
    [queue_labels[q] for q in queue_order],
    index=queue_order.index(current_queue),
    horizontal=True,
    label_visibility="collapsed",
)

selected_queue = reverse_labels[selected_label]
st.session_state["fila_orcamentos"] = selected_queue

queue_df = (
    filtered[filtered["Fila"] == selected_queue].copy()
    if not filtered.empty
    else pd.DataFrame()
)

if queue_df.empty:
    st.markdown(
        '<div class="ap-empty">Nenhuma demanda nesta fila com os filtros atuais.</div>',
        unsafe_allow_html=True,
    )
else:
    if "Dias até prazo" in queue_df.columns:
        queue_df = queue_df.sort_values(
            by="Dias até prazo",
            ascending=True,
            na_position="last",
        )

    for _, row in queue_df.iterrows():
        render_card(row)

with st.expander("Ver tabela de conferência"):
    cols = [
        "Demanda",
        "Unidade",
        "Engenharia",
        "Fila",
        "Etapa Trello",
        "Aguardando",
        "Pendência / próxima ação",
        "Possíveis lacunas",
        "Situação do prazo",
        "Data visita",
    ]

    view = (
        filtered[cols].copy()
        if not filtered.empty
        else pd.DataFrame(columns=cols)
    )

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
    )
