from __future__ import annotations

import os
from datetime import datetime
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from radar import ENGENHEIROS, analyze_snapshot
from trello_client import TrelloClient, TrelloError

st.set_page_config(page_title="APROAR • Radar de Orçamentos", page_icon="📐", layout="wide")

st.markdown("""
<style>
:root{
  --bg:#070b14;--surface:#0d1422;--surface2:#111b2d;--line:#22304a;
  --text:#f4f7fb;--muted:#8ea0ba;--blue:#2f74f5;--amber:#f59e0b;
  --green:#22c55e;--red:#ef4444;--cyan:#22d3ee;
}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg);color:var(--text)}
[data-testid="stHeader"]{background:rgba(7,11,20,.78);backdrop-filter:blur(14px)}
[data-testid="stSidebar"]{background:#09101d;border-right:1px solid var(--line)}
.main .block-container{max-width:1500px;padding-top:1.1rem;padding-bottom:4rem}
h1,h2,h3,h4{letter-spacing:-.025em}.stCaption,p,label{color:#cbd5e1}
.ap-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 20px;margin-bottom:18px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(135deg,#101a2d,#0b1220);box-shadow:0 18px 40px rgba(0,0,0,.22)}
.ap-brand{display:flex;align-items:center;gap:14px}.ap-mark{width:44px;height:44px;border-radius:13px;display:grid;place-items:center;font-weight:900;background:linear-gradient(145deg,#3b82f6,#1d4ed8);box-shadow:0 10px 25px rgba(37,99,235,.3)}
.ap-eyebrow{font-size:10px;letter-spacing:.16em;color:#60a5fa;font-weight:800}.ap-title{font-size:22px;font-weight:800;color:#fff}.ap-sub{font-size:12px;color:var(--muted);margin-top:3px}.ap-live{font-size:11px;font-weight:800;color:#86efac;border:1px solid rgba(34,197,94,.32);background:rgba(34,197,94,.08);padding:9px 12px;border-radius:999px;white-space:nowrap}
[data-testid="stMetric"]{background:linear-gradient(145deg,#111b2d,#0d1422);border:1px solid var(--line);border-radius:15px;padding:14px 16px;box-shadow:0 10px 25px rgba(0,0,0,.15)}
[data-testid="stMetricValue"]{font-weight:800}.stTabs [data-baseweb="tab-list"]{gap:6px;background:#0d1422;border:1px solid var(--line);padding:6px;border-radius:14px}.stTabs [data-baseweb="tab"]{border-radius:9px;color:#9fb0c8;font-weight:700}.stTabs [aria-selected="true"]{background:#1b3260!important;color:#fff!important}
.stButton>button,.stDownloadButton>button{border-radius:11px!important;border:1px solid var(--line)!important;background:#111b2d!important;color:#e5edf8!important;font-weight:700!important}.stButton>button:hover{border-color:#3b82f6!important}
.ap-card{border:1px solid var(--line);border-radius:15px;background:#0d1422;padding:15px 16px;margin:9px 0}.ap-card-top{display:flex;justify-content:space-between;gap:12px}.ap-card-title{font-weight:800;color:#fff;font-size:15px}.ap-card-meta{font-size:11px;color:#91a3bb;margin-top:4px}.ap-pend{margin-top:11px;padding:9px 10px;border-radius:10px;background:#111b2d;color:#d9e2ef;font-size:12px}.pill{display:inline-block;margin-right:5px;margin-top:7px;padding:4px 7px;border-radius:999px;font-size:10px;font-weight:800;border:1px solid var(--line);color:#b8c8de}.pill.red{border-color:rgba(239,68,68,.35);color:#fca5a5;background:rgba(239,68,68,.07)}.pill.amber{border-color:rgba(245,158,11,.35);color:#fcd34d;background:rgba(245,158,11,.07)}.pill.green{border-color:rgba(34,197,94,.35);color:#86efac;background:rgba(34,197,94,.07)}
.ap-note{font-size:12px;color:#a5b4c8;border-left:3px solid #3b82f6;padding:8px 10px;background:rgba(37,99,235,.06);border-radius:0 10px 10px 0;margin:8px 0 14px}
@media(max-width:700px){.main .block-container{padding:.75rem}.ap-head{padding:14px}.ap-live{display:none}.ap-title{font-size:18px}.ap-card-top{display:block}}
</style>
""", unsafe_allow_html=True)


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


def render_header(board_name: str = "Radar de Orçamentos") -> None:
    st.markdown(f"""
    <div class="ap-head">
      <div class="ap-brand"><div class="ap-mark">A</div><div>
        <div class="ap-eyebrow">APROAR ENGENHARIA • ORÇAMENTOS</div>
        <div class="ap-title">{escape(board_name)}</div>
        <div class="ap-sub">Cobranças, conferências e liberações sem perder o prazo original</div>
      </div></div>
      <div class="ap-live">● TRELLO SINCRONIZADO</div>
    </div>
    """, unsafe_allow_html=True)


def render_card(row: pd.Series) -> None:
    due = str(row.get("Situação do prazo", ""))
    due_class = "red" if "Atrasado" in due or "Vence hoje" in due else "amber" if "amanhã" in due or "Em 2d" in due else ""
    wait = str(row.get("Aguardando", ""))
    wait_class = "amber" if wait != "Engenharia" else ""
    url = str(row.get("URL", "") or "")
    link = f'<a href="{escape(url, quote=True)}" target="_blank">Abrir no Trello ↗</a>' if url else ""
    st.markdown(f"""
    <div class="ap-card">
      <div class="ap-card-top">
        <div><div class="ap-card-title">{escape(str(row.get('Demanda','')))}</div>
        <div class="ap-card-meta">{escape(str(row.get('Etapa Trello','')))} • Engenharia: <b>{escape(str(row.get('Engenharia','')))}</b></div></div>
        <div class="ap-card-meta">{link}</div>
      </div>
      <div>
        <span class="pill {due_class}">{escape(due)}</span>
        <span class="pill {wait_class}">Aguardando {escape(wait)}</span>
        <span class="pill">na etapa: {escape(str(row.get('Tempo na etapa (dias)','—')))}d</span>
      </div>
      <div class="ap-pend"><b>Próxima ação:</b> {escape(str(row.get('Pendência / próxima ação','')))}</div>
      <div class="ap-card-meta" style="margin-top:9px">Último comentário: {escape(str(row.get('Autor último comentário','—')))} • {escape(str(row.get('Último comentário em','—')))}</div>
    </div>
    """, unsafe_allow_html=True)


# Sidebar
with st.sidebar:
    st.markdown("### 📐 Orçamentos")
    st.caption("Radar operacional")
    st.divider()
    if st.button("🔄 Atualizar Trello", use_container_width=True):
        st.session_state["trello_nonce"] = int(st.session_state.get("trello_nonce", 0)) + 1
        cached_snapshot.clear()
        st.rerun()
    st.caption("Leitura pelo link do Trello, em cache por até 5 minutos. Use Atualizar Trello para forçar a leitura.")
    st.divider()
    st.markdown("**Regra de liberação**")
    st.caption("Retorno do engenheiro e 'Informações preenchidas = Sim' NÃO liberam automaticamente o orçamento.")

nonce = int(st.session_state.get("trello_nonce", 0))
try:
    snapshot = cached_snapshot(nonce)
except TrelloError as exc:
    render_header()
    st.error(str(exc))
    st.info("Configure apenas o link do quadro em `TRELLO_BOARD_URL` nos Secrets. Esta versão não exige API key/token para leitura.")
    st.stop()
except Exception as exc:
    render_header()
    st.error(f"Não foi possível carregar o Trello: {exc}")
    st.stop()

board = snapshot.get("board") or {}
render_header(str(board.get("name") or "Radar de Orçamentos"))

trust_ready = bool(secret("TRUST_TRELLO_READY_LIST", False))
result = analyze_snapshot(snapshot, trust_trello_ready_list=trust_ready)
df = result.rows.copy()

# Filtros
st.markdown("#### Radar de demandas")
f1, f2, f3, f4 = st.columns([1.2, 1.3, 1.2, 1.3])
engineer_options = ["Todos"] + sorted([x for x in df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
stage_options = ["Todas"] + sorted([x for x in df.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
wait_options = ["Todos"] + sorted([x for x in df.get("Aguardando", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
with f1:
    filtro_eng = st.selectbox("Engenharia", engineer_options)
with f2:
    filtro_etapa = st.selectbox("Etapa Trello", stage_options)
with f3:
    filtro_espera = st.selectbox("Aguardando", wait_options)
with f4:
    filtro_prazo = st.selectbox("Prazo", ["Todos", "Atrasados", "Hoje", "Até 2 dias", "Sem prazo"])

filtered = df.copy()
if not filtered.empty:
    if filtro_eng != "Todos": filtered = filtered[filtered["Engenharia"] == filtro_eng]
    if filtro_etapa != "Todas": filtered = filtered[filtered["Etapa Trello"] == filtro_etapa]
    if filtro_espera != "Todos": filtered = filtered[filtered["Aguardando"] == filtro_espera]
    if filtro_prazo == "Atrasados": filtered = filtered[pd.to_numeric(filtered["Dias até prazo"], errors="coerce") < 0]
    elif filtro_prazo == "Hoje": filtered = filtered[pd.to_numeric(filtered["Dias até prazo"], errors="coerce") == 0]
    elif filtro_prazo == "Até 2 dias": filtered = filtered[pd.to_numeric(filtered["Dias até prazo"], errors="coerce").between(0, 2)]
    elif filtro_prazo == "Sem prazo": filtered = filtered[filtered["Dias até prazo"].isna()]

# KPIs sobre filtro atual
counts = filtered["Fila"].value_counts() if not filtered.empty else pd.Series(dtype=int)
late_count = int((pd.to_numeric(filtered.get("Dias até prazo", pd.Series(dtype=float)), errors="coerce") < 0).sum()) if not filtered.empty else 0
k1, k2, k3, k4 = st.columns(4)
k1.metric("Cobrar Engenharia", int(counts.get("Cobrar Engenharia", 0)))
k2.metric("Conferir retorno", int(counts.get("Conferir retorno", 0)))
k3.metric("Pronto para elaborar", int(counts.get("Pronto para elaborar", 0)))
k4.metric("Atrasados", late_count)

if not trust_ready:
    st.markdown('<div class="ap-note"><b>Gate humano ativo:</b> cartões em “Para Elaborar Orçamento” continuam em <b>Conferir retorno</b> até existir uma confirmação manual inequívoca. Isso impede que a automação atual do Trello libere um orçamento apenas porque “Informações preenchidas?” foi marcado como Sim.</div>', unsafe_allow_html=True)

queue_tabs = st.tabs(["🔔 Cobrar Engenharia", "🔎 Conferir retorno", "✅ Pronto para elaborar", "⏳ Terceiros", "✍️ Em produção"])
queue_names = ["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar", "Aguardar terceiros", "Em produção"]
for tab, queue_name in zip(queue_tabs, queue_names):
    with tab:
        qdf = filtered[filtered["Fila"] == queue_name].copy() if not filtered.empty else pd.DataFrame()
        if qdf.empty:
            st.caption("Nenhuma demanda nesta fila com os filtros atuais.")
        else:
            for _, row in qdf.iterrows():
                render_card(row)

st.divider()
with st.expander("📊 Visão analítica das esperas"):
    if filtered.empty:
        st.caption("Sem dados para analisar.")
    else:
        analysis = filtered.groupby(["Aguardando", "Fila"], dropna=False).agg(
            Demandas=("Card ID", "count"),
            **{"Tempo médio na etapa (dias)": ("Tempo na etapa (dias)", "mean")}
        ).reset_index()
        st.dataframe(analysis, use_container_width=True, hide_index=True)
        st.caption("O tempo na etapa usa o último movimento de lista disponível nas atividades recentes do Trello. O prazo original do cartão permanece intacto.")

with st.expander("🧾 Dados carregados do Trello"):
    st.caption(f"Board: {board.get('name','')} • listas: {len(snapshot.get('lists') or [])} • cartões abertos: {len(snapshot.get('cards') or [])} • campos personalizados: {len(snapshot.get('custom_fields') or [])}")
    cols = ["Demanda", "Etapa Trello", "Engenharia", "Fila", "Aguardando", "Prazo", "Situação do prazo", "Responsável elaboração"]
    st.dataframe(filtered[cols] if not filtered.empty else pd.DataFrame(columns=cols), use_container_width=True, hide_index=True)
