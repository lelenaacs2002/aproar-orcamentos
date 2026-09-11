from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from radar import analyze_snapshot
from trello_client import TrelloClient, TrelloError

try:
    import psycopg
except Exception:  # app continua em modo leitura se dependência/banco não estiver disponível
    psycopg = None


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
st.set_page_config(
    page_title="APROAR • Orçamentos",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False
if "fila_orcamentos" not in st.session_state:
    st.session_state["fila_orcamentos"] = "Cobrar Engenharia"

DARK = bool(st.session_state["dark_mode"])

THEME = (
    {
        "bg": "#0d1520",
        "surface": "#132131",
        "surface2": "#18293c",
        "navy": "#0d2238",
        "navy2": "#183754",
        "ink": "#f4f7fb",
        "muted": "#a9b8c8",
        "line": "#2a3b4f",
        "input": "#162536",
        "input_text": "#f4f7fb",
        "shadow": "rgba(0,0,0,.16)",
    }
    if DARK
    else {
        "bg": "#f5f7fb",
        "surface": "#ffffff",
        "surface2": "#f8fafc",
        "navy": "#122b44",
        "navy2": "#1a3b5b",
        "ink": "#142f49",
        "muted": "#6f8296",
        "line": "#d9e2ec",
        "input": "#ffffff",
        "input_text": "#18314a",
        "shadow": "rgba(21,44,68,.06)",
    }
)

st.markdown(
    f"""
<style>
:root {{
  color-scheme: {"dark" if DARK else "light"};
  --bg:{THEME['bg']};
  --surface:{THEME['surface']};
  --surface2:{THEME['surface2']};
  --navy:{THEME['navy']};
  --navy2:{THEME['navy2']};
  --ink:{THEME['ink']};
  --muted:{THEME['muted']};
  --line:{THEME['line']};
  --input:{THEME['input']};
  --input-text:{THEME['input_text']};
  --shadow:{THEME['shadow']};
  --orange:#ef7643;
  --orange-soft:{'#3a211a' if DARK else '#fff1ea'};
  --blue:#3977be;
  --blue-soft:{'#172d48' if DARK else '#eaf1fb'};
  --green:#259662;
  --green-soft:{'#173527' if DARK else '#eaf7f0'};
  --amber:#c47a20;
  --amber-soft:{'#3a2a16' if DARK else '#fff6e9'};
  --red:#c75151;
}}

html,body,[data-testid="stAppViewContainer"]{{background:var(--bg)!important;color:var(--ink)!important;}}
[data-testid="stHeader"]{{background:transparent!important;}}
[data-testid="collapsedControl"],[data-testid="stSidebar"]{{display:none!important;}}
#MainMenu,footer{{visibility:hidden;}}
.main .block-container{{max-width:1240px;padding-top:.4rem;padding-bottom:3rem;}}
p,label,h1,h2,h3,h4,h5,h6{{color:var(--ink);}}

.ap-topbar{{background:var(--navy);margin:-.45rem -1rem 1.4rem;padding:16px 24px;border-radius:0 0 16px 16px;}}
.ap-topbar-inner{{display:flex;align-items:center;justify-content:space-between;gap:18px;}}
.ap-brand{{display:flex;align-items:center;gap:14px;color:#fff;}}
.ap-logo{{width:40px;height:40px;border-radius:10px;background:var(--orange);display:grid;place-items:center;font-size:25px;font-weight:900;}}
.ap-brand-main{{font-size:18px;font-weight:900;letter-spacing:.12em;}}
.ap-brand-divider{{opacity:.35;font-size:25px;}}
.ap-brand-area{{font-size:14px;letter-spacing:.17em;}}
.ap-live{{border:1px solid rgba(255,255,255,.26);border-radius:9px;padding:6px 10px;color:#fff;font-size:12px;}}

.ap-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin:8px 0 10px;}}
.ap-kicker{{color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.14em;font-size:12px;margin-bottom:6px;}}
.ap-title{{color:var(--ink);font-size:28px;line-height:1.08;font-weight:900;letter-spacing:-.04em;margin:0;}}
.ap-dot{{color:var(--orange);}}
.ap-subtitle{{color:var(--muted);font-size:15px;margin-top:8px;max-width:820px;}}
.ap-small{{color:var(--muted);font-size:12px;}}
.ap-toolbar{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:0 8px 22px var(--shadow);margin-bottom:14px;}}
.ap-tip{{background:var(--surface);border:1px solid var(--line);border-left:4px solid #7ca7df;border-radius:12px;padding:11px 14px;color:var(--muted);font-size:13px;line-height:1.5;margin:0 0 18px;}}
.ap-legend{{display:flex;gap:12px;align-items:center;justify-content:flex-end;color:var(--muted);font-size:11px;margin-top:8px;}}
.ap-theme-wrap{{display:flex;align-items:center;justify-content:flex-end;gap:8px;}}
.ap-theme-icon{{font-size:12px;color:var(--muted);margin-top:18px;}}

.ap-metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0 18px;}}
.ap-metric{{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:0 8px 22px var(--shadow);}}
.ap-metric-top{{display:flex;align-items:center;justify-content:space-between;gap:10px;}}
.ap-metric-title{{font-size:13px;color:var(--muted);font-weight:700;}}
.ap-metric-num{{font-size:32px;font-weight:900;line-height:1;margin-top:8px;}}
.ap-metric-sub{{font-size:12px;color:var(--muted);margin-top:4px;}}
.orange{{color:var(--orange);}} .blue{{color:var(--blue);}} .green{{color:var(--green);}}

.ap-section-head{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:18px 0 10px;}}
.ap-section-title{{font-size:20px;font-weight:900;color:var(--ink);}}
.ap-section-count{{font-size:13px;color:var(--muted);}}
.ap-mini-muted{{font-size:12px;color:var(--muted);}}

.ap-card{{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:16px 18px;margin:12px 0;box-shadow:0 8px 22px var(--shadow);}}
.ap-card-top{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;}}
.ap-badges{{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-bottom:7px;}}
.ap-badge{{display:inline-flex;align-items:center;padding:5px 10px;border-radius:999px;font-size:11px;font-weight:800;}}
.ap-badge-orange{{background:var(--orange-soft);color:{'#ff9b70' if DARK else '#c95d2f'};}}
.ap-badge-blue{{background:var(--blue-soft);color:{'#8fc0ff' if DARK else '#24599b'};}}
.ap-badge-green{{background:var(--green-soft);color:{'#75d5a1' if DARK else '#1d8d58'};}}
.ap-badge-amber{{background:var(--amber-soft);color:{'#f3b765' if DARK else '#a96616'};}}
.ap-badge-gray{{background:var(--surface2);color:var(--muted);border:1px solid var(--line);}}
.ap-ref{{color:var(--muted);font-size:11px;font-weight:700;}}
.ap-card-title{{color:var(--ink);font-size:20px;font-weight:900;line-height:1.25;}}
.ap-card-meta{{color:var(--muted);font-size:13px;margin-top:6px;line-height:1.5;}}
.ap-card-meta b{{color:var(--ink);}}
.ap-card-right{{min-width:110px;text-align:right;color:var(--amber);font-size:13px;white-space:nowrap;font-weight:700;}}
.ap-card-grid{{display:grid;grid-template-columns:1.35fr .9fr;gap:14px;margin-top:14px;}}
.ap-box{{border:1px solid var(--line);border-radius:14px;padding:14px;background:var(--surface2);}}
.ap-box-title{{font-size:11px;color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;}}
.ap-box-text{{font-size:14px;color:var(--ink);line-height:1.55;}}
.ap-list{{margin:0;padding-left:18px;}}
.ap-list li{{margin:3px 0;color:var(--ink);}}
.ap-context{{margin-top:10px;font-size:12px;color:var(--muted);}}
.ap-saved{{margin-top:12px;background:var(--surface2);border:1px solid var(--line);border-radius:11px;padding:11px 12px;color:var(--muted);font-size:12px;line-height:1.55;}}
.ap-saved b{{color:var(--ink);}}
.ap-empty{{background:var(--surface);border:1px dashed var(--line);border-radius:14px;padding:22px;color:var(--muted);font-size:14px;}}
.ap-divider{{height:1px;background:var(--line);margin:14px 0 10px;}}
.ap-form-help{{font-size:12px;color:var(--muted);line-height:1.5;}}

/* SELECTS */
.stSelectbox div[data-baseweb="select"],
.stSelectbox div[data-baseweb="select"] > div,
.stSelectbox div[data-baseweb="select"] > div > div{{background-color:var(--input)!important;color:var(--input-text)!important;border-color:var(--line)!important;}}
.stSelectbox div[data-baseweb="select"]{{border:1px solid var(--line)!important;border-radius:11px!important;overflow:hidden;}}
.stSelectbox div[data-baseweb="select"] span,
.stSelectbox div[data-baseweb="select"] input,
.stSelectbox div[data-baseweb="select"] p{{color:var(--input-text)!important;-webkit-text-fill-color:var(--input-text)!important;opacity:1!important;}}
.stSelectbox div[data-baseweb="select"] svg{{fill:var(--input-text)!important;color:var(--input-text)!important;}}
ul[role="listbox"]{{background:var(--surface)!important;border:1px solid var(--line)!important;}}
li[role="option"],li[role="option"] *{{background:var(--surface)!important;color:var(--ink)!important;-webkit-text-fill-color:var(--ink)!important;}}
li[role="option"]:hover,li[role="option"]:hover *{{background:var(--surface2)!important;}}

/* Inputs */
.stTextArea textarea,.stTextInput input{{background:var(--input)!important;color:var(--input-text)!important;-webkit-text-fill-color:var(--input-text)!important;border:1px solid var(--line)!important;}}
.stTextArea textarea::placeholder,.stTextInput input::placeholder{{color:var(--muted)!important;opacity:.8!important;}}

/* BOTÕES */
div[data-testid="stButton"] > button{{background:var(--surface)!important;color:var(--ink)!important;border:1px solid var(--line)!important;border-radius:12px!important;box-shadow:none!important;font-weight:750!important;opacity:1!important;}}
div[data-testid="stButton"] > button *,div[data-testid="stButton"] > button p,div[data-testid="stButton"] > button span{{color:var(--ink)!important;-webkit-text-fill-color:var(--ink)!important;opacity:1!important;}}
div[data-testid="stButton"] > button:hover{{background:var(--surface2)!important;border-color:#9fb3c8!important;}}
div[data-testid="stButton"] > button[kind="primary"]{{background:var(--navy)!important;border-color:var(--navy)!important;color:#fff!important;}}
div[data-testid="stButton"] > button[kind="primary"] *,div[data-testid="stButton"] > button[kind="primary"] p{{color:#fff!important;-webkit-text-fill-color:#fff!important;}}

/* RADIO FILAS */
div[data-testid="stRadio"] > div[role="radiogroup"]{{display:grid!important;grid-template-columns:repeat(4,1fr);gap:10px;}}
div[data-testid="stRadio"] label{{background:var(--surface)!important;border:1px solid var(--line)!important;border-radius:12px!important;min-height:48px!important;padding:0 12px!important;display:flex!important;align-items:center!important;justify-content:center!important;}}
div[data-testid="stRadio"] label p,div[data-testid="stRadio"] label span{{color:var(--ink)!important;-webkit-text-fill-color:var(--ink)!important;opacity:1!important;font-size:13px!important;font-weight:750!important;text-align:center!important;}}
div[data-testid="stRadio"] label:has(input:checked){{background:var(--navy)!important;border-color:var(--navy)!important;}}
div[data-testid="stRadio"] label:has(input:checked) p,div[data-testid="stRadio"] label:has(input:checked) span{{color:#fff!important;-webkit-text-fill-color:#fff!important;}}
div[data-testid="stRadio"] input,div[data-testid="stRadio"] [data-baseweb="radio"] > div:first-child{{display:none!important;}}

/* TOGGLE */
div[data-testid="stToggle"]{{transform:scale(.75);transform-origin:right top;margin-top:4px;}}
div[data-testid="stToggle"] label,div[data-testid="stToggle"] label *{{color:var(--muted)!important;-webkit-text-fill-color:var(--muted)!important;font-size:11px!important;}}

/* Expander */
div[data-testid="stExpander"]{{background:transparent!important;border:none!important;box-shadow:none!important;}}
div[data-testid="stExpander"] details{{border:1px solid var(--line)!important;border-radius:14px!important;background:var(--surface2)!important;}}
div[data-testid="stExpander"] summary,div[data-testid="stExpander"] summary *{{color:var(--ink)!important;-webkit-text-fill-color:var(--ink)!important;font-weight:700!important;}}

/* Forms */
[data-testid="stForm"]{{background:var(--surface2)!important;border:1px solid var(--line)!important;border-radius:14px!important;padding:14px!important;}}

@media(max-width:900px){{
  .main .block-container{{padding-left:.8rem;padding-right:.8rem;}}
  .ap-topbar{{margin-left:-.8rem;margin-right:-.8rem;}}
  .ap-title{{font-size:31px;}}
  .ap-head{{display:block;}}
  .ap-brand-divider,.ap-live{{display:none;}}
  .ap-card-top{{display:block;}}
  .ap-card-right{{text-align:left;margin-top:8px;min-width:0;}}
  .ap-card-grid{{grid-template-columns:1fr;}}
  .ap-metrics{{grid-template-columns:1fr;}}
  div[data-testid="stRadio"] > div[role="radiogroup"]{{grid-template-columns:1fr 1fr;}}
}}
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# HELPERS
# =============================================================================
def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def safe_text(value: Any, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else fallback


def load_snapshot(force_nonce: int = 0) -> dict[str, Any]:
    board = secret("TRELLO_BOARD_URL", secret("TRELLO_BOARD", "https://trello.com/b/TX8hGvmI"))
    return TrelloClient(board=board).snapshot()


@st.cache_data(ttl=300, show_spinner=False)
def cached_snapshot(force_nonce: int = 0) -> dict[str, Any]:
    return load_snapshot(force_nonce)


def db_url() -> str:
    return str(secret("DATABASE_URL", "") or "").strip()


def db_available() -> bool:
    return bool(psycopg is not None and db_url())


def _db_error_message(exc: Exception) -> str:
    text = str(exc or "")
    if "postgresql://" in text:
        text = "falha na conexão com o banco"
    return text[:220]


@st.cache_data(ttl=30, show_spinner=False)
def load_review_states() -> dict[str, dict[str, Any]]:
    if not db_available():
        return {}
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select card_id, review_status, pending_owner_type, pending_reason,
                           last_chase_at, accepted_at, accepted_by, budget_owner, updated_at
                    from orcamento_review_state
                    """
                )
                cols = [d.name for d in cur.description]
                return {str(row[0]): dict(zip(cols, row)) for row in cur.fetchall()}
    except Exception:
        return {}


def parse_payload(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else {}
    except Exception:
        text = str(raw).strip()
        return {"items": [text]} if text else {}


def split_items(text: str) -> list[str]:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        item = raw.strip().lstrip("-•✓☐ ").strip()
        if item and item not in lines:
            lines.append(item)
    return lines


def gaps_to_items(gaps: Any) -> list[str]:
    raw = safe_text(gaps, "")
    if not raw:
        return []
    items = [x.strip() for x in raw.replace(" • ", ";").split(";") if x.strip()]
    return list(dict.fromkeys(items))


def summarize_items(items: list[str], max_items: int = 3) -> str:
    if not items:
        return "Defina os itens que precisam ser respondidos."
    if len(items) <= max_items:
        return "; ".join(items)
    return "; ".join(items[:max_items]) + f" (+{len(items) - max_items})"


def save_pending_definition(
    card_id: str,
    items: list[str],
    owner_type: str,
    actor: str,
    supervisor: str,
    note: str,
) -> tuple[bool, str]:
    if not db_available():
        return False, "Banco Neon não disponível. Confira DATABASE_URL e requirements.txt."
    if not items:
        return False, "Inclua pelo menos uma informação a solicitar."

    payload = {
        "items": items,
        "note": note.strip(),
        "supervisor": supervisor,
        "saved_by": actor,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(payload, ensure_ascii=False)
    review_status = "waiting_engineering" if owner_type == "engineering" else "waiting_external"

    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into orcamento_review_state
                        (card_id, review_status, pending_owner_type, pending_reason,
                         last_chase_at, accepted_at, accepted_by, updated_at)
                    values (%s, %s, %s, %s,
                            case when %s = 'engineering' then now() else null end,
                            null, null, now())
                    on conflict (card_id) do update set
                        review_status = excluded.review_status,
                        pending_owner_type = excluded.pending_owner_type,
                        pending_reason = excluded.pending_reason,
                        last_chase_at = case when excluded.pending_owner_type = 'engineering' then now() else orcamento_review_state.last_chase_at end,
                        accepted_at = null,
                        accepted_by = null,
                        updated_at = now()
                    """,
                    (card_id, review_status, owner_type, raw, owner_type),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log
                        (card_id, event_type, actor, owner_type, details, occurred_at)
                    values (%s, 'pending_definition_saved', %s, %s, %s, now())
                    """,
                    (card_id, actor, owner_type, raw),
                )
            conn.commit()
        load_review_states.clear()
        return True, "Pendências salvas."
    except Exception as exc:
        return False, f"Não foi possível salvar: {_db_error_message(exc)}"


def mark_ready(card_id: str, actor: str) -> tuple[bool, str]:
    if not db_available():
        return False, "Banco Neon não disponível."
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into orcamento_review_state
                        (card_id, review_status, pending_owner_type, pending_reason,
                         accepted_at, accepted_by, updated_at)
                    values (%s, 'accepted', 'budget', null, now(), %s, now())
                    on conflict (card_id) do update set
                        review_status = 'accepted',
                        pending_owner_type = 'budget',
                        pending_reason = null,
                        accepted_at = now(),
                        accepted_by = excluded.accepted_by,
                        updated_at = now()
                    """,
                    (card_id, actor),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log
                        (card_id, event_type, actor, owner_type, details, occurred_at)
                    values (%s, 'survey_accepted', %s, 'budget', 'Levantamento liberado para elaboração', now())
                    """,
                    (card_id, actor),
                )
            conn.commit()
        load_review_states.clear()
        return True, "Levantamento marcado como pronto para elaborar."
    except Exception as exc:
        return False, f"Não foi possível liberar: {_db_error_message(exc)}"


def reopen_review(card_id: str, actor: str) -> tuple[bool, str]:
    if not db_available():
        return False, "Banco Neon não disponível."
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into orcamento_review_state
                        (card_id, review_status, pending_owner_type, updated_at)
                    values (%s, 'pending', 'engineering', now())
                    on conflict (card_id) do update set
                        review_status = 'pending',
                        pending_owner_type = 'engineering',
                        pending_reason = null,
                        accepted_at = null,
                        accepted_by = null,
                        updated_at = now()
                    """,
                    (card_id,),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log
                        (card_id, event_type, actor, owner_type, details, occurred_at)
                    values (%s, 'review_reopened', %s, 'engineering', 'Conferência reaberta', now())
                    """,
                    (card_id, actor),
                )
            conn.commit()
        load_review_states.clear()
        return True, "Conferência reaberta."
    except Exception as exc:
        return False, f"Não foi possível reabrir: {_db_error_message(exc)}"


def apply_review_state(df: pd.DataFrame, states: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if df.empty or not states:
        return df
    out = df.copy()
    for idx, row in out.iterrows():
        cid = str(row.get("Card ID") or "")
        state = states.get(cid)
        if not state:
            continue
        status = str(state.get("review_status") or "")
        owner = str(state.get("pending_owner_type") or "")
        payload = parse_payload(state.get("pending_reason"))
        items = payload.get("items") or []
        if items:
            out.at[idx, "Pendências definidas"] = "; ".join(map(str, items))
        out.at[idx, "Status interno"] = status

        if status == "accepted":
            out.at[idx, "Fila"] = "Pronto para elaborar"
            out.at[idx, "Aguardando"] = "Orçamentos"
            out.at[idx, "Pendência / próxima ação"] = "Levantamento conferido e liberado para elaboração"
        elif status == "waiting_engineering" or (status == "pending" and owner == "engineering" and items):
            out.at[idx, "Fila"] = "Cobrar Engenharia"
            out.at[idx, "Aguardando"] = "Engenharia"
            if items:
                out.at[idx, "Pendência / próxima ação"] = "Solicitar ao supervisor: " + "; ".join(map(str, items))
        elif status == "waiting_external" or owner in {"client", "supplier", "specialist"}:
            out.at[idx, "Fila"] = "Aguardar terceiros"
            out.at[idx, "Aguardando"] = {"client": "Cliente", "supplier": "Fornecedor", "specialist": "Especialista"}.get(owner, "Terceiros")
            if items:
                out.at[idx, "Pendência / próxima ação"] = "Aguardar: " + "; ".join(map(str, items))
    return out


def render_topbar() -> None:
    st.markdown(
        """
        <div class="ap-topbar"><div class="ap-topbar-inner">
          <div class="ap-brand">
            <div class="ap-logo">A</div><div class="ap-brand-main">APROAR</div>
            <div class="ap-brand-divider">|</div><div class="ap-brand-area">ORÇAMENTOS</div>
          </div>
          <div class="ap-live">Central de levantamentos</div>
        </div></div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(conferir: int, cobrar: int, elaborar: int) -> None:
    st.markdown(
        f"""
        <div class="ap-metrics">
          <div class="ap-metric">
            <div class="ap-metric-top"><div class="ap-metric-title">Para conferir</div><div class="ap-mini-muted">retornos recebidos</div></div>
            <div class="ap-metric-num orange">{conferir:02d}</div>
            <div class="ap-metric-sub">Orçamentos precisa validar</div>
          </div>
          <div class="ap-metric">
            <div class="ap-metric-top"><div class="ap-metric-title">Cobrar Engenharia</div><div class="ap-mini-muted">pendências abertas</div></div>
            <div class="ap-metric-num blue">{cobrar:02d}</div>
            <div class="ap-metric-sub">itens a cobrar dos supervisores</div>
          </div>
          <div class="ap-metric">
            <div class="ap-metric-top"><div class="ap-metric-title">Pronto para elaborar</div><div class="ap-mini-muted">liberados</div></div>
            <div class="ap-metric-num green">{elaborar:02d}</div>
            <div class="ap-metric-sub">já podem seguir para orçamento</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fila_badge(fila: str) -> str:
    return {
        "Cobrar Engenharia": "ap-badge-orange",
        "Conferir retorno": "ap-badge-blue",
        "Pronto para elaborar": "ap-badge-green",
        "Aguardar terceiros": "ap-badge-amber",
    }.get(fila, "ap-badge-gray")


def render_card_summary(row: pd.Series, state: dict[str, Any] | None) -> None:
    fila = safe_text(row.get("Fila"))
    title = safe_text(row.get("Demanda"))
    unidade = safe_text(row.get("Unidade"))
    supervisor = safe_text(row.get("Engenharia"))
    etapa = safe_text(row.get("Etapa Trello"))
    prazo = safe_text(row.get("Situação do prazo"))
    next_action = safe_text(row.get("Pendência / próxima ação"))
    gaps_items = gaps_to_items(row.get("Possíveis lacunas"))
    last_reply = safe_text(row.get("Último retorno Engenharia"))
    waiting = safe_text(row.get("Aguardando"))
    service = safe_text(row.get("Tipo de serviço"))
    url = safe_text(row.get("URL"), "")
    ref = safe_text(row.get("Card ID"), "")[-4:] or "—"

    payload = parse_payload((state or {}).get("pending_reason")) if state else {}
    saved_items = payload.get("items") or []
    note = safe_text(payload.get("note"), "")
    display_items = saved_items or gaps_items
    source_label = "Definido por Orçamentos" if saved_items else "Sugestão do sistema"

    list_html = "".join(f"<li>{escape(str(item))}</li>" for item in display_items[:5]) or "<li>Defina os itens que faltam.</li>"
    more_html = f'<div class="ap-context">+{len(display_items)-5} itens</div>' if len(display_items) > 5 else ""
    note_html = f'<div class="ap-saved"><b>Observação interna:</b> {escape(note)}</div>' if note else ""
    reply_html = "" if last_reply == "—" else f'<div class="ap-context"><b>Último retorno:</b> {escape(last_reply)}</div>'
    link_html = f'<a href="{escape(url, quote=True)}" target="_blank">Abrir no Trello ↗</a>' if url else ""

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
              <div class="ap-card-meta"><b>Unidade:</b> {escape(unidade)} &nbsp;•&nbsp; <b>Supervisor:</b> {escape(supervisor)} &nbsp;•&nbsp; <b>Etapa:</b> {escape(etapa)}</div>
            </div>
            <div class="ap-card-right">{escape(prazo)}</div>
          </div>

          <div class="ap-card-grid">
            <div class="ap-box">
              <div class="ap-box-title">O que cobrar / conferir</div>
              <div class="ap-box-text">
                <ul class="ap-list">{list_html}</ul>
                {more_html}
              </div>
              <div class="ap-context"><b>Origem:</b> {escape(source_label)}</div>
              {reply_html}
            </div>
            <div class="ap-box">
              <div class="ap-box-title">Próxima ação</div>
              <div class="ap-box-text">{escape(next_action)}</div>
              <div class="ap-context"><b>Aguardando:</b> {escape(waiting)}</div>
              <div class="ap-context"><b>Serviço:</b> {escape(service)}</div>
              <div class="ap-context">{link_html}</div>
            </div>
          </div>
          {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# CARREGAMENTO
# =============================================================================
nonce = int(st.session_state.get("trello_nonce", 0))
try:
    snapshot = cached_snapshot(nonce)
except TrelloError as exc:
    render_topbar(); st.error(str(exc)); st.stop()
except Exception as exc:
    render_topbar(); st.error(f"Não foi possível carregar o Trello: {exc}"); st.stop()

trust_ready = bool(secret("TRUST_TRELLO_READY_LIST", False))
result = analyze_snapshot(snapshot, trust_trello_ready_list=trust_ready)
df = result.rows.copy()
states = load_review_states()
df = apply_review_state(df, states)

levantamento_stages = {
    "SOLICITADOS",
    "SOLICITADOS - PENDÊNCIAS CLIENTE",
    "SOLICITADOS – PENDÊNCIAS CLIENTE",
    "PARA ELABORAR ORÇAMENTO",
}
if not df.empty:
    mask = df["Etapa Trello"].astype(str).str.upper().isin({x.upper() for x in levantamento_stages})
    df = df[mask].copy()


# =============================================================================
# INTERFACE — SOMENTE SETOR DE ORÇAMENTOS
# =============================================================================
render_topbar()

h1, h2 = st.columns([8, 1.5])
with h1:
    st.markdown('<div class="ap-kicker">Orçamentos / Conferência de levantamentos</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="ap-title">Definir e cobrar levantamentos<span class="ap-dot">.</span></h1>', unsafe_allow_html=True)
    st.markdown('<div class="ap-subtitle">Menos leitura do card e mais decisão: aqui o setor define exatamente o que falta, de quem cobrar e o que já pode seguir para elaboração.</div>', unsafe_allow_html=True)
with h2:
    st.markdown('<div class="ap-theme-wrap"><div class="ap-theme-icon">◐</div></div>', unsafe_allow_html=True)
    st.toggle("Escuro", key="dark_mode", help="Alternar modo claro/escuro")

st.markdown('<div class="ap-toolbar">', unsafe_allow_html=True)
t1, t2, t3 = st.columns([1.1, 1.4, 4])
with t1:
    if st.button("↻ Atualizar", use_container_width=True):
        st.session_state["trello_nonce"] = int(st.session_state.get("trello_nonce", 0)) + 1
        cached_snapshot.clear(); st.rerun()
with t2:
    actor = st.selectbox("Operando como", ["Laisa", "Simeone", "César"], label_visibility="collapsed")
with t3:
    board_name = safe_text((snapshot.get("board") or {}).get("name"), "ORÇAMENTOS")
    db_status = "Neon conectado" if db_available() else "Neon indisponível"
    st.markdown(f'<div class="ap-small"><b>Quadro:</b> {escape(board_name)} &nbsp;•&nbsp; <b>Status:</b> {escape(db_status)}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown(
    """
    <div class="ap-tip">
      <b>Como usar:</b> escolha uma fila, abra a demanda, ajuste os itens do checklist e salve.
      O objetivo desta tela é sair do “parece que falta algo” para uma cobrança objetiva: <b>qual informação falta</b> e <b>quem precisa responder</b>.
    </div>
    """,
    unsafe_allow_html=True,
)

# FILTROS
f1, f2, f3, f4 = st.columns(4)
engineer_options = ["Todos"] + sorted([x for x in df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
stage_options = ["Todas"] + sorted([x for x in df.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
wait_options = ["Todos"] + sorted([x for x in df.get("Aguardando", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
with f1:
    filtro_eng = st.selectbox("Engenharia", engineer_options)
with f2:
    filtro_stage = st.selectbox("Etapa Trello", stage_options)
with f3:
    filtro_wait = st.selectbox("Aguardando", wait_options)
with f4:
    filtro_prazo = st.selectbox("Prazo", ["Todos", "Atrasados", "Hoje", "Até 2 dias", "Sem prazo"])

filtered = df.copy()
if not filtered.empty:
    if filtro_eng != "Todos":
        filtered = filtered[filtered["Engenharia"] == filtro_eng]
    if filtro_stage != "Todas":
        filtered = filtered[filtered["Etapa Trello"] == filtro_stage]
    if filtro_wait != "Todos":
        filtered = filtered[filtered["Aguardando"] == filtro_wait]
    dias = pd.to_numeric(filtered.get("Dias até prazo", pd.Series(index=filtered.index, dtype=float)), errors="coerce")
    if filtro_prazo == "Atrasados":
        filtered = filtered[dias < 0]
    elif filtro_prazo == "Hoje":
        filtered = filtered[dias == 0]
    elif filtro_prazo == "Até 2 dias":
        filtered = filtered[dias.between(0, 2, inclusive="both")]
    elif filtro_prazo == "Sem prazo":
        filtered = filtered[dias.isna()]

counts = filtered["Fila"].value_counts() if not filtered.empty else pd.Series(dtype=int)
render_metrics(int(counts.get("Conferir retorno", 0)), int(counts.get("Cobrar Engenharia", 0)), int(counts.get("Pronto para elaborar", 0)))

st.markdown(f'<div class="ap-section-head"><div class="ap-section-title">Fila de trabalho</div><div class="ap-section-count">{len(filtered)} demandas nos filtros atuais</div></div>', unsafe_allow_html=True)

queue_order = ["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar", "Aguardar terceiros"]
queue_labels = {
    "Cobrar Engenharia": f"Cobrar Engenharia ({int(counts.get('Cobrar Engenharia', 0))})",
    "Conferir retorno": f"Conferir retorno ({int(counts.get('Conferir retorno', 0))})",
    "Pronto para elaborar": f"Pronto para elaborar ({int(counts.get('Pronto para elaborar', 0))})",
    "Aguardar terceiros": f"Terceiros ({int(counts.get('Aguardar terceiros', 0))})",
}
reverse_labels = {v: k for k, v in queue_labels.items()}
current_queue = st.session_state.get("fila_orcamentos", "Cobrar Engenharia")
if current_queue not in queue_order:
    current_queue = "Cobrar Engenharia"
selected_label = st.radio(
    "Fila",
    [queue_labels[q] for q in queue_order],
    index=queue_order.index(current_queue),
    horizontal=True,
    label_visibility="collapsed",
)
selected_queue = reverse_labels[selected_label]
st.session_state["fila_orcamentos"] = selected_queue

queue_df = filtered[filtered["Fila"] == selected_queue].copy() if not filtered.empty else pd.DataFrame()
if queue_df.empty:
    st.markdown('<div class="ap-empty">Nenhuma demanda nesta fila com os filtros atuais.</div>', unsafe_allow_html=True)
else:
    if "Dias até prazo" in queue_df.columns:
        queue_df = queue_df.sort_values("Dias até prazo", ascending=True, na_position="last")

    for _, row in queue_df.iterrows():
        card_id = str(row.get("Card ID") or "")
        state = states.get(card_id)
        render_card_summary(row, state)

        payload = parse_payload((state or {}).get("pending_reason"))
        saved_items = payload.get("items") or []
        suggested_items = gaps_to_items(row.get("Possíveis lacunas"))
        initial_items = saved_items or suggested_items
        initial_text = "\n".join(f"- {x}" for x in initial_items)

        with st.expander("Definir o que solicitar / decidir próxima ação"):
            left, right = st.columns([1.05, 1])
            with left:
                st.markdown("**Checklist que vai para a cobrança**")
                st.markdown(
                    '<div class="ap-form-help">Escreva apenas o que o supervisor precisa responder. Um item por linha.</div>',
                    unsafe_allow_html=True,
                )
                pending_text = st.text_area(
                    "Informações que precisam ser respondidas",
                    value=initial_text,
                    height=170,
                    key=f"pending_{card_id}",
                    label_visibility="collapsed",
                    placeholder="- Altura da pintura\n- Acabamento da tinta\n- Área total em m²",
                )
                current_items = split_items(pending_text)
                st.markdown(
                    f'<div class="ap-saved"><b>Resumo da cobrança:</b> {escape(summarize_items(current_items))}</div>',
                    unsafe_allow_html=True,
                )

            with right:
                st.markdown("**Configuração da pendência**")
                owner_labels = {
                    "Engenharia / supervisor": "engineering",
                    "Cliente": "client",
                    "Fornecedor / prestador": "supplier",
                    "Especialista": "specialist",
                }
                current_owner = str((state or {}).get("pending_owner_type") or "engineering")
                owner_index = list(owner_labels.values()).index(current_owner) if current_owner in owner_labels.values() else 0
                owner_label = st.selectbox(
                    "Quem precisa responder?",
                    list(owner_labels.keys()),
                    index=owner_index,
                    key=f"owner_{card_id}",
                )
                note = st.text_input(
                    "Observação interna (opcional)",
                    value=str(payload.get("note") or ""),
                    key=f"note_{card_id}",
                    placeholder="Ex.: confirmar também com fornecedor de esquadria",
                )
                st.markdown(
                    f'<div class="ap-saved"><b>Vai ficar aguardando:</b> {escape(owner_label)}</div>',
                    unsafe_allow_html=True,
                )

            a1, a2, a3 = st.columns([1.4, 1.2, 1])
            with a1:
                if st.button("Salvar pendências", type="primary", use_container_width=True, key=f"save_{card_id}"):
                    ok, msg = save_pending_definition(
                        card_id=card_id,
                        items=split_items(pending_text),
                        owner_type=owner_labels[owner_label],
                        actor=actor,
                        supervisor=safe_text(row.get("Engenharia"), ""),
                        note=note,
                    )
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
            with a2:
                if st.button("Marcar pronto", use_container_width=True, key=f"ready_{card_id}"):
                    ok, msg = mark_ready(card_id, actor)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
            with a3:
                if st.button("Reabrir", use_container_width=True, key=f"reopen_{card_id}"):
                    ok, msg = reopen_review(card_id, actor)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()

            with st.expander("Ver contexto do card"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Próximo passo atual**")
                    st.write(safe_text(row.get("Pendência / próxima ação")))
                    st.write("**Sugestão automática de lacunas**")
                    gaps = suggested_items or ["Nenhuma sugestão automática."]
                    for item in gaps:
                        st.write(f"• {item}")
                with c2:
                    st.write("**Último retorno da Engenharia**")
                    st.write(safe_text(row.get("Último retorno Engenharia")))
                    st.write("**Aguardando / Serviço**")
                    st.write(f"{safe_text(row.get('Aguardando'))} • {safe_text(row.get('Tipo de serviço'))}")
                    url = safe_text(row.get("URL"), "")
                    if url and url != "—":
                        st.markdown(f"[Abrir no Trello ↗]({url})")

with st.expander("Ver tabela resumida"):
    cols = [
        "Demanda",
        "Unidade",
        "Engenharia",
        "Fila",
        "Etapa Trello",
        "Aguardando",
        "Pendência / próxima ação",
        "Situação do prazo",
        "Data visita",
    ]
    view = filtered[cols].copy() if not filtered.empty else pd.DataFrame(columns=cols)
    st.dataframe(view, use_container_width=True, hide_index=True)
