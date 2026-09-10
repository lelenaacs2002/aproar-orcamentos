from __future__ import annotations

import os
from datetime import datetime
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from radar import ENGENHEIROS, ORCAMENTOS, analyze_snapshot
from trello_client import TrelloClient, TrelloError

st.set_page_config(
    page_title="APROAR • Orçamentos",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
:root{
  --navy:#122841;
  --navy2:#193556;
  --ink:#14304b;
  --muted:#6d7f95;
  --bg:#f3f5f8;
  --line:#d9e0e7;
  --white:#ffffff;
  --orange:#ef7a45;
  --orange-soft:#fdf0e9;
  --blue:#1e4f8f;
  --blue-soft:#e9f0fb;
  --green:#1b8f5a;
  --green-soft:#ecf8f1;
  --amber:#c9771a;
  --amber-soft:#fff6eb;
  --red:#c95050;
  --red-soft:#fff0f0;
}
html, body, [data-testid="stAppViewContainer"]{
  background:var(--bg);
  color:var(--ink);
}
[data-testid="stHeader"]{background:transparent;}
[data-testid="collapsedControl"]{display:none;}
[data-testid="stSidebar"]{display:none;}
.main .block-container{
  max-width:1280px;
  padding-top:0.6rem;
  padding-bottom:3rem;
}

#MainMenu, footer {visibility:hidden;}

a{color:var(--blue);text-decoration:none;}
a:hover{text-decoration:underline;}

.ap-nav{
  background:var(--navy);
  color:#fff;
  border-radius:0 0 18px 18px;
  padding:18px 26px;
  margin:-0.6rem -1rem 2rem -1rem;
}
.ap-nav-inner{display:flex;align-items:center;justify-content:space-between;gap:18px;}
.ap-brand{display:flex;align-items:center;gap:16px;}
.ap-logo{
  width:42px;height:42px;border-radius:10px;background:var(--orange);
  display:grid;place-items:center;font-weight:900;font-size:28px;color:#fff;
}
.ap-brand-name{font-size:18px;font-weight:800;letter-spacing:.12em;}
.ap-brand-divider{opacity:.35;font-size:26px;line-height:1;}
.ap-brand-section{font-size:15px;letter-spacing:.18em;text-transform:uppercase;}
.ap-proto{border:1px solid rgba(255,255,255,.35);padding:7px 14px;border-radius:10px;font-size:14px;}

.ap-section-nav{margin-bottom:20px;padding-bottom:18px;border-bottom:1px solid var(--line);}
.stRadio > div{gap:0.8rem;}
.stRadio [role="radiogroup"]{display:flex;gap:12px;}
.stRadio [data-baseweb="radio"]{background:transparent;}
.stRadio [data-testid="stMarkdownContainer"] p{font-size:16px;font-weight:600;color:#516478;}
.stRadio label{
  background:transparent;border:none;padding:0;margin:0;
}
.stRadio label:has(input:checked){
  background:var(--navy);padding:12px 20px;border-radius:12px;
}
.stRadio label:has(input:checked) [data-testid="stMarkdownContainer"] p{color:white!important;}
.stRadio input{display:none;}

.ap-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:8px;}
.ap-kicker{color:#6f8298;font-weight:700;letter-spacing:.16em;font-size:13px;text-transform:uppercase;margin-bottom:12px;}
.ap-title{font-size:36px;font-weight:900;letter-spacing:-.04em;margin:0;color:var(--ink);}
.ap-title-dot{color:var(--orange);}
.ap-subtitle{font-size:17px;color:#63778d;margin:6px 0 16px;}
.ap-helper{font-size:14px;color:#74879b;margin-bottom:16px;}

.stSelectbox label, .stMultiSelect label{font-size:14px;font-weight:600;color:#576b80;}
.stSelectbox [data-baseweb="select"], .stMultiSelect [data-baseweb="select"]{
  background:var(--white);
  border:1px solid var(--line);
  border-radius:12px;
}
.stSelectbox > div[data-baseweb="select"] div, .stMultiSelect > div[data-baseweb="select"] div{color:#183149;}

.stButton > button{
  background:var(--navy);
  color:#fff;
  border:none;
  border-radius:12px;
  font-weight:700;
  padding:.7rem 1rem;
  box-shadow:none;
}
.stButton > button:hover{background:var(--navy2);color:#fff;}
.stButton > button[kind="secondary"]{background:#fff;color:var(--ink);border:1px solid var(--line);}

.ap-count-wrap{margin:18px 0 26px;}
.ap-count-grid{display:grid;grid-template-columns:repeat(3,1fr);background:#fff;border:1px solid var(--line);border-radius:18px;overflow:hidden;}
.ap-count-item{padding:24px 28px;min-height:98px;display:flex;align-items:center;gap:18px;border-right:1px solid var(--line);}
.ap-count-item:last-child{border-right:none;}
.ap-count-num{font-size:28px;font-weight:900;line-height:1;min-width:42px;}
.ap-count-label{font-size:15px;color:#61758a;}
.ap-count-num.orange{color:var(--orange);} .ap-count-num.blue{color:var(--blue);} .ap-count-num.green{color:var(--green);}

.ap-chip-row{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 16px;}
.ap-chip{display:inline-flex;align-items:center;gap:8px;padding:10px 16px;border-radius:12px;border:1px solid var(--line);background:#fff;color:#37506a;font-weight:700;}
.ap-chip.active{background:var(--blue-soft);border-color:#bfd0eb;color:var(--blue);}
.ap-chip small{font-size:14px;color:#6d7f95;}

.ap-card{
  background:#fff;border:1px solid var(--line);border-radius:18px;padding:20px 22px;margin-bottom:14px;
}
.ap-card-top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;}
.ap-badges{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;}
.ap-badge{display:inline-block;padding:6px 12px;border-radius:999px;font-size:12px;font-weight:800;}
.ap-badge.orange{background:var(--orange-soft);color:#c76133;}
.ap-badge.blue{background:var(--blue-soft);color:var(--blue);}
.ap-badge.green{background:var(--green-soft);color:var(--green);}
.ap-badge.amber{background:var(--amber-soft);color:var(--amber);}
.ap-badge.red{background:var(--red-soft);color:var(--red);}
.ap-badge.gray{background:#f0f3f7;color:#607388;}
.ap-ref{font-size:12px;font-weight:700;color:#94a3b3;}
.ap-card-title{font-size:18px;font-weight:900;color:var(--ink);line-height:1.25;margin:0 0 6px;}
.ap-card-meta{font-size:14px;color:#6a7d92;line-height:1.6;}
.ap-card-meta b{color:var(--ink);}
.ap-card-block{margin-top:14px;padding-top:14px;border-top:1px solid #edf1f5;}
.ap-card-label{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#7e8ea2;margin-bottom:6px;}
.ap-card-text{font-size:14px;color:#29425b;line-height:1.6;}
.ap-card-right{white-space:nowrap;text-align:right;font-size:15px;color:#ca7a22;min-width:165px;}
.ap-empty{background:#fff;border:1px dashed #cad5df;border-radius:16px;padding:24px;color:#6f8298;}
.ap-note{background:#f8fbff;border:1px solid #d9e7f8;border-left:4px solid #7ba7e8;border-radius:14px;padding:14px 16px;margin-bottom:18px;color:#4f6780;font-size:14px;line-height:1.55;}

.ap-small{font-size:13px;color:#7b8da0;}
.ap-form-demo{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px 16px;margin-top:14px;color:#6d7f95;}

[data-testid="stExpander"]{
  background:#fff;border:1px solid var(--line);border-radius:16px;
}

@media (max-width: 900px){
  .ap-nav{padding:16px 18px;}
  .ap-brand-divider{display:none;}
  .ap-brand-name{font-size:16px;letter-spacing:.08em;}
  .ap-brand-section{font-size:13px;}
  .ap-nav-inner,.ap-toolbar,.ap-card-top{display:block;}
  .ap-title{font-size:30px;}
  .ap-card-right{margin-top:10px;text-align:left;min-width:auto;}
  .ap-count-grid{grid-template-columns:1fr;}
  .ap-count-item{border-right:none;border-bottom:1px solid var(--line);} .ap-count-item:last-child{border-bottom:none;}
}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def load_snapshot(force_nonce: int = 0) -> dict[str, Any]:
    board = secret("TRELLO_BOARD_URL", secret("TRELLO_BOARD", "https://trello.com/b/TX8hGvmI"))
    client = TrelloClient(board=board)
    return client.snapshot()


@st.cache_data(ttl=300, show_spinner=False)
def cached_snapshot(force_nonce: int = 0) -> dict[str, Any]:
    return load_snapshot(force_nonce)


def safe_text(value: Any, fallback: str = "—") -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return fallback
    return text


def html(text: Any) -> str:
    return escape(safe_text(text))


def due_badge_class(value: str) -> str:
    t = (value or "").lower()
    if "atras" in t:
        return "red"
    if "hoje" in t or "vence" in t:
        return "amber"
    return "gray"


def queue_badge_class(queue: str) -> str:
    return {
        "Cobrar Engenharia": "orange",
        "Conferir retorno": "blue",
        "Pronto para elaborar": "green",
        "Aguardar terceiros": "amber",
        "Em produção": "gray",
    }.get(queue, "gray")


def action_for_engineer(row: pd.Series) -> str:
    queue = safe_text(row.get("Fila"), "")
    next_action = safe_text(row.get("Pendência / próxima ação"), "")
    visit = safe_text(row.get("Data visita"), "")
    if queue == "Conferir retorno":
        return "Aguardando conferência"
    if "agendar" in next_action.lower() or visit == "—":
        return "Agendar visita"
    if queue == "Cobrar Engenharia":
        return "Complementar"
    return "Preencher"


def render_top_nav() -> None:
    st.markdown(
        """
        <div class="ap-nav">
          <div class="ap-nav-inner">
            <div class="ap-brand">
              <div class="ap-logo">A</div>
              <div class="ap-brand-name">APROAR</div>
              <div class="ap-brand-divider">|</div>
              <div class="ap-brand-section">ORÇAMENTOS</div>
            </div>
            <div class="ap-proto">Protótipo</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(items: list[tuple[int, str, str]]) -> None:
    blocks = []
    for value, label, color in items:
        blocks.append(
            f'<div class="ap-count-item"><div class="ap-count-num {color}">{int(value):02d}</div>'
            f'<div class="ap-count-label">{escape(label)}</div></div>'
        )
    st.markdown(f'<div class="ap-count-wrap"><div class="ap-count-grid">{"".join(blocks)}</div></div>', unsafe_allow_html=True)


def render_queue_buttons(queue_counts: dict[str, int], current: str, key_prefix: str = "q") -> str:
    col1, col2, col3, col4, col5 = st.columns(5)
    mapping = [
        (col1, "Cobrar Engenharia", "Cobrar Engenharia"),
        (col2, "Conferir retorno", "Conferir retorno"),
        (col3, "Pronto para elaborar", "Pronto para elaborar"),
        (col4, "Aguardar terceiros", "Terceiros"),
        (col5, "Em produção", "Em produção"),
    ]
    chosen = current
    for col, qname, label in mapping:
        with col:
            if st.button(f"{label}  {int(queue_counts.get(qname, 0))}", key=f"{key_prefix}_{qname}", use_container_width=True):
                chosen = qname
    return chosen


def render_orcamento_card(row: pd.Series) -> None:
    fila = safe_text(row.get("Fila"))
    badge = queue_badge_class(fila)
    prazo = safe_text(row.get("Situação do prazo"))
    prazo_class = due_badge_class(prazo)
    title = safe_text(row.get("Demanda"))
    ref = safe_text(row.get("Card ID"), "")[-4:]
    unidade = safe_text(row.get("Unidade"))
    engenharia = safe_text(row.get("Engenharia"))
    etapa = safe_text(row.get("Etapa Trello"))
    aguardando = safe_text(row.get("Aguardando"))
    gaps = safe_text(row.get("Possíveis lacunas"))
    next_action = safe_text(row.get("Pendência / próxima ação"))
    last_reply = safe_text(row.get("Último retorno Engenharia"))
    last_author = safe_text(row.get("Autor último comentário"))
    last_date = safe_text(row.get("Último comentário em"))
    service = safe_text(row.get("Tipo de serviço"))
    link = safe_text(row.get("URL"), "")
    link_html = f'<a href="{escape(link, quote=True)}" target="_blank">Abrir no Trello ↗</a>' if link else ""

    extra = ""
    if gaps != "—":
        extra += f'<div class="ap-card-block"><div class="ap-card-label">O que falta</div><div class="ap-card-text">{escape(gaps)}</div></div>'
    if last_reply != "—":
        extra += f'<div class="ap-card-block"><div class="ap-card-label">Último retorno da engenharia</div><div class="ap-card-text">{escape(last_reply)}</div></div>'

    st.markdown(
        f"""
        <div class="ap-card">
          <div class="ap-card-top">
            <div style="flex:1;min-width:0;">
              <div class="ap-badges">
                <span class="ap-badge {badge}">{escape(fila)}</span>
                <span class="ap-ref">REF. {escape(ref) if ref else '—'}</span>
              </div>
              <div class="ap-card-title">{escape(title)}</div>
              <div class="ap-card-meta">
                <b>Unidade:</b> {escape(unidade)} &nbsp;&nbsp;•&nbsp;&nbsp;
                <b>Supervisor:</b> {escape(engenharia)} &nbsp;&nbsp;•&nbsp;&nbsp;
                <b>Etapa Trello:</b> {escape(etapa)}
              </div>
            </div>
            <div class="ap-card-right">Prazo ilustrativo: {escape(prazo)}</div>
          </div>
          <div class="ap-card-block">
            <div class="ap-card-label">Próximo passo</div>
            <div class="ap-card-text">{escape(next_action)}</div>
          </div>
          <div class="ap-card-block">
            <div class="ap-card-text"><b>Aguardando:</b> {escape(aguardando)} &nbsp;&nbsp;•&nbsp;&nbsp; <b>Serviço:</b> {escape(service)} &nbsp;&nbsp;•&nbsp;&nbsp; {link_html}</div>
          </div>
          {extra}
          <div class="ap-card-block">
            <div class="ap-card-label">Última movimentação</div>
            <div class="ap-card-text">{escape(last_author)} • {escape(last_date)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_engineering_card(row: pd.Series) -> None:
    action = action_for_engineer(row)
    badge_class = {
        "Complementar": "orange",
        "Agendar visita": "blue",
        "Preencher": "green",
        "Aguardando conferência": "amber",
    }.get(action, "gray")
    ref = safe_text(row.get("Card ID"), "")[-4:]
    title = safe_text(row.get("Demanda"))
    prazo = safe_text(row.get("Situação do prazo"))
    next_action = safe_text(row.get("Pendência / próxima ação"))
    gaps = safe_text(row.get("Possíveis lacunas"))
    unidade = safe_text(row.get("Unidade"))
    service = safe_text(row.get("Tipo de serviço"))
    link = safe_text(row.get("URL"), "")
    link_html = f'<a href="{escape(link, quote=True)}" target="_blank">Abrir no Trello ↗</a>' if link else ""

    st.markdown(
        f"""
        <div class="ap-card">
          <div class="ap-card-top">
            <div style="flex:1;min-width:0;">
              <div class="ap-badges">
                <span class="ap-badge {badge_class}">{escape(action)}</span>
                <span class="ap-ref">REF. {escape(ref) if ref else '—'}</span>
              </div>
              <div class="ap-card-title">{escape(title)}</div>
              <div class="ap-card-meta"><b>Unidade:</b> {escape(unidade)} &nbsp;&nbsp;•&nbsp;&nbsp; <b>Serviço:</b> {escape(service)}</div>
            </div>
            <div class="ap-card-right">Prazo ilustrativo: {escape(prazo)}</div>
          </div>
          <div class="ap-card-block">
            <div class="ap-card-label">O que precisa de você</div>
            <div class="ap-card-text">{escape(next_action)}</div>
          </div>
          <div class="ap-card-block">
            <div class="ap-card-label">Pontos para conferir</div>
            <div class="ap-card-text">{escape(gaps)}</div>
          </div>
          <div class="ap-card-block"><div class="ap-card-text">{link_html}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Data load
# -----------------------------------------------------------------------------
nonce = int(st.session_state.get("trello_nonce", 0))
try:
    snapshot = cached_snapshot(nonce)
except TrelloError as exc:
    render_top_nav()
    st.error(str(exc))
    st.info("Configure apenas `TRELLO_BOARD_URL` nos Secrets. Esta leitura usa o link do quadro.")
    st.stop()
except Exception as exc:
    render_top_nav()
    st.error(f"Não foi possível carregar o Trello: {exc}")
    st.stop()

trust_ready = bool(secret("TRUST_TRELLO_READY_LIST", False))
result = analyze_snapshot(snapshot, trust_trello_ready_list=trust_ready)
df = result.rows.copy()
if df.empty:
    df = pd.DataFrame(columns=[
        "Fila", "Demanda", "Etapa Trello", "Unidade", "Engenharia", "Tipo de serviço",
        "Pendência / próxima ação", "Possíveis lacunas", "Aguardando", "Situação do prazo",
        "URL", "Card ID", "Último retorno Engenharia", "Autor último comentário",
        "Último comentário em", "Data visita",
    ])

# -----------------------------------------------------------------------------
# Top shell
# -----------------------------------------------------------------------------
render_top_nav()

nav_choice = st.radio(
    "Seção",
    ["Engenharia", "Orçamentos"],
    index=1,
    horizontal=True,
    label_visibility="collapsed",
)

st.markdown('<div class="ap-section-nav"></div>', unsafe_allow_html=True)

# actions row
c_action1, c_action2 = st.columns([1, 5])
with c_action1:
    if st.button("Atualizar dados", use_container_width=True):
        st.session_state["trello_nonce"] = int(st.session_state.get("trello_nonce", 0)) + 1
        cached_snapshot.clear()
        st.rerun()
with c_action2:
    board_name = safe_text((snapshot.get("board") or {}).get("name"), "Quadro de Orçamentos")
    st.markdown(
        f'<div class="ap-small">Leitura pelo link do Trello • cache de até 5 minutos • quadro: <b>{escape(board_name)}</b></div>',
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Engenharia view
# -----------------------------------------------------------------------------
if nav_choice == "Engenharia":
    eng_options = [e for e in ENGENHEIROS if e != "Gabriel"] + ["Gabriel"]
    chosen_eng = st.selectbox("Visualizar como", eng_options, index=0)
    eng_df = df[df.get("Engenharia", pd.Series(dtype=str)).astype(str) == chosen_eng].copy()
    eng_df = eng_df[eng_df["Fila"].isin(["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar"])].copy()
    if not eng_df.empty:
        eng_df["Ação Engenharia"] = eng_df.apply(action_for_engineer, axis=1)
    else:
        eng_df["Ação Engenharia"] = []

    st.markdown('<div class="ap-kicker">Engenharia / Levantamentos</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="ap-title">Meus levantamentos<span class="ap-title-dot">.</span></h1>', unsafe_allow_html=True)
    st.markdown('<div class="ap-subtitle">O próximo passo de cada orçamento começa aqui.</div>', unsafe_allow_html=True)
    st.markdown('<div class="ap-helper">Ambiente de demonstração • as informações continuam vindo do Trello, mas esta tela organiza só o que o engenheiro precisa ver.</div>', unsafe_allow_html=True)

    if st.button("Experimentar formulário por serviço"):
        st.info("Próxima etapa: abrir o formulário de levantamento por tipo de serviço, com botão de melhorar texto com IA.")

    action_counts = eng_df["Ação Engenharia"].value_counts() if not eng_df.empty else pd.Series(dtype=int)
    render_metrics([
        (int(action_counts.get("Complementar", 0)), "Complementar", "orange"),
        (int(action_counts.get("Agendar visita", 0)), "Agendar visita", "blue"),
        (int(action_counts.get("Preencher", 0)), "Preencher", "green"),
    ])

    st.markdown(
        f'<div class="ap-toolbar"><div><h3 style="margin:0;color:var(--ink);font-size:20px;">O que precisa de você</h3></div>'
        f'<div class="ap-small">{len(eng_df)} pendências</div></div>',
        unsafe_allow_html=True,
    )

    if eng_df.empty:
        st.markdown('<div class="ap-empty">Nenhuma pendência para este engenheiro nos filtros atuais.</div>', unsafe_allow_html=True)
    else:
        order = {"Complementar": 0, "Agendar visita": 1, "Preencher": 2, "Aguardando conferência": 3}
        eng_df = eng_df.sort_values(by="Ação Engenharia", key=lambda s: s.map(order).fillna(9))
        for _, row in eng_df.iterrows():
            render_engineering_card(row)

# -----------------------------------------------------------------------------
# Orçamentos view
# -----------------------------------------------------------------------------
else:
    viewer = st.selectbox("Visualizar como", ["Laisa", "Simeone", "César"], index=0)
    st.markdown('<div class="ap-kicker">Orçamentos / Conferência</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="ap-title">Conferir levantamentos<span class="ap-title-dot">.</span></h1>', unsafe_allow_html=True)
    st.markdown('<div class="ap-subtitle">Receba as informações e encaminhe cada demanda para o próximo passo.</div>', unsafe_allow_html=True)
    st.markdown('<div class="ap-helper">Tela simplificada para cobrança, conferência e liberação. O foco é mostrar com clareza quem cobrar, o que falta e o que já pode seguir.</div>', unsafe_allow_html=True)

    if st.button("Experimentar formulário por serviço", key="form_demo_orc"):
        st.info("Na próxima etapa, essa ação pode abrir um card demonstrativo com o formulário adaptado por serviço.")

    # Filters
    f1, f2, f3, f4 = st.columns(4)
    engineer_options = ["Todos"] + sorted([x for x in df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    stage_options = ["Todas"] + sorted([x for x in df.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    wait_options = ["Todos"] + sorted([x for x in df.get("Aguardando", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    prazo_options = ["Todos", "Atrasados", "Hoje", "Até 2 dias", "Sem prazo"]

    with f1:
        filtro_eng = st.selectbox("Engenharia", engineer_options)
    with f2:
        filtro_stage = st.selectbox("Etapa Trello", stage_options)
    with f3:
        filtro_wait = st.selectbox("Aguardando", wait_options)
    with f4:
        filtro_prazo = st.selectbox("Prazo", prazo_options)

    filtered = df.copy()
    if not filtered.empty:
        if filtro_eng != "Todos":
            filtered = filtered[filtered["Engenharia"] == filtro_eng]
        if filtro_stage != "Todas":
            filtered = filtered[filtered["Etapa Trello"] == filtro_stage]
        if filtro_wait != "Todos":
            filtered = filtered[filtered["Aguardando"] == filtro_wait]

        dias = pd.to_numeric(filtered.get("Dias até prazo", pd.Series(dtype=float)), errors="coerce")
        if filtro_prazo == "Atrasados":
            filtered = filtered[dias < 0]
        elif filtro_prazo == "Hoje":
            filtered = filtered[dias == 0]
        elif filtro_prazo == "Até 2 dias":
            filtered = filtered[dias.between(0, 2, inclusive="both")]
        elif filtro_prazo == "Sem prazo":
            filtered = filtered[dias.isna()]

    queue_counts = filtered["Fila"].value_counts() if not filtered.empty else pd.Series(dtype=int)
    render_metrics([
        (int(queue_counts.get("Conferir retorno", 0)), "Para conferir", "orange"),
        (int(queue_counts.get("Cobrar Engenharia", 0)), "Aguardando resposta", "blue"),
        (int(queue_counts.get("Pronto para elaborar", 0)), "Para elaborar", "green"),
    ])

    st.markdown(
        f'<div class="ap-toolbar"><div><h3 style="margin:0;color:var(--ink);font-size:20px;">Fila de levantamentos</h3></div>'
        f'<div class="ap-small">{len(filtered)} levantamentos</div></div>',
        unsafe_allow_html=True,
    )

    if "orc_queue" not in st.session_state:
        st.session_state["orc_queue"] = "Conferir retorno"
    st.session_state["orc_queue"] = render_queue_buttons(queue_counts.to_dict(), st.session_state["orc_queue"], key_prefix="orcq")

    selected_queue = st.session_state["orc_queue"]
    queue_filtered = filtered[filtered["Fila"] == selected_queue].copy() if not filtered.empty else pd.DataFrame()

    st.markdown(
        '<div class="ap-note"><b>Regra de liberação:</b> um comentário novo não libera sozinho. Primeiro entra em conferência. Só depois de validado por Orçamentos a demanda deve seguir para elaboração.</div>',
        unsafe_allow_html=True,
    )

    if queue_filtered.empty:
        st.markdown('<div class="ap-empty">Nenhuma demanda nesta fila com os filtros atuais.</div>', unsafe_allow_html=True)
    else:
        for _, row in queue_filtered.iterrows():
            render_orcamento_card(row)

    with st.expander("Ver tabela de conferência"):
        cols = [
            "Demanda", "Unidade", "Engenharia", "Fila", "Etapa Trello", "Aguardando",
            "Pendência / próxima ação", "Possíveis lacunas", "Situação do prazo", "Data visita",
        ]
        view = filtered[cols].copy() if not filtered.empty else pd.DataFrame(columns=cols)
        st.dataframe(view, use_container_width=True, hide_index=True)
