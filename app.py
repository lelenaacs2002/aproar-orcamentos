from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import streamlit as st

from radar import ENGENHEIROS, analyze_snapshot
from trello_client import TrelloClient, TrelloError

try:
    import psycopg
except Exception:
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
    st.session_state.dark_mode = False
if "selected_card_id" not in st.session_state:
    st.session_state.selected_card_id = ""
if "modulo" not in st.session_state:
    st.session_state.modulo = "Radar de levantamentos"

DARK = bool(st.session_state.dark_mode)

COLORS = (
    {
        "bg": "#0b1420",
        "surface": "#111f2f",
        "surface2": "#172739",
        "text": "#f4f7fb",
        "muted": "#a9b8c8",
        "line": "#2a3e53",
        "navy": "#0c253e",
        "input": "#142638",
        "input_text": "#f4f7fb",
    }
    if DARK
    else {
        "bg": "#f4f7fb",
        "surface": "#ffffff",
        "surface2": "#f8fafc",
        "text": "#15314d",
        "muted": "#6b7f94",
        "line": "#d9e3ed",
        "navy": "#102d4a",
        "input": "#ffffff",
        "input_text": "#17324d",
    }
)

st.markdown(
    f"""
<style>
:root {{
  color-scheme:{'dark' if DARK else 'light'};
  --bg:{COLORS['bg']}; --surface:{COLORS['surface']}; --surface2:{COLORS['surface2']};
  --text:{COLORS['text']}; --muted:{COLORS['muted']}; --line:{COLORS['line']};
  --navy:{COLORS['navy']}; --input:{COLORS['input']}; --input-text:{COLORS['input_text']};
  --orange:#f26b36; --orange-soft:{'#382117' if DARK else '#fff1ea'};
  --blue:#2468b4; --blue-soft:{'#142d4b' if DARK else '#edf4fd'};
  --green:#168a55; --green-soft:{'#173729' if DARK else '#edf8f2'};
  --amber:#bb711d; --amber-soft:{'#382a18' if DARK else '#fff7e9'};
  --red:#c84f4f; --red-soft:{'#3a2020' if DARK else '#fff0f0'};
}}

html,body,[data-testid="stAppViewContainer"]{{background:var(--bg)!important;color:var(--text)!important;}}
[data-testid="stHeader"]{{background:transparent!important;}}
[data-testid="collapsedControl"],[data-testid="stSidebar"]{{display:none!important;}}
#MainMenu,footer{{visibility:hidden;}}
.main .block-container{{max-width:1520px;padding-top:.45rem;padding-bottom:2.5rem;}}
p,label,h1,h2,h3,h4,h5,h6{{color:var(--text);}}

.ap-topbar{{background:var(--navy);margin:-.45rem -1rem 1.25rem;padding:15px 24px;border-radius:0 0 16px 16px;}}
.ap-topbar-inner{{display:flex;align-items:center;justify-content:space-between;gap:20px;}}
.ap-brand{{display:flex;align-items:center;gap:13px;color:#fff;}}
.ap-logo{{width:38px;height:38px;border-radius:9px;background:var(--orange);display:grid;place-items:center;font-size:24px;font-weight:900;}}
.ap-brand-main{{font-size:17px;font-weight:900;letter-spacing:.12em;}}
.ap-brand-area{{font-size:13px;letter-spacing:.15em;opacity:.95;}}
.ap-sep{{opacity:.35;font-size:22px;}}
.ap-status{{color:#e9f3ff;font-size:12px;border:1px solid rgba(255,255,255,.25);border-radius:999px;padding:6px 10px;}}

.ap-kicker{{font-size:11px;text-transform:uppercase;letter-spacing:.14em;font-weight:800;color:var(--muted);margin-bottom:5px;}}
.ap-title{{font-size:30px;font-weight:900;letter-spacing:-.04em;color:var(--text);line-height:1.08;margin:0;}}
.ap-dot{{color:var(--orange);}}
.ap-sub{{font-size:14px;color:var(--muted);margin-top:6px;}}
.ap-mini{{font-size:11px;color:var(--muted);}}
.ap-section-title{{font-size:17px;font-weight:900;color:var(--text);margin:4px 0 2px;}}
.ap-column-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;}}
.ap-column-title{{font-size:14px;font-weight:900;color:var(--text);}}
.ap-count{{font-size:11px;color:var(--muted);background:var(--surface2);border:1px solid var(--line);padding:3px 7px;border-radius:999px;}}
.ap-empty{{padding:22px 12px;text-align:center;color:var(--muted);font-size:13px;}}
.ap-detail-title{{font-size:19px;font-weight:900;line-height:1.3;color:var(--text);}}
.ap-detail-meta{{font-size:12px;color:var(--muted);line-height:1.55;margin-top:4px;}}
.ap-pill{{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:800;margin-right:5px;}}
.ap-pill-orange{{background:var(--orange-soft);color:{'#ff9d78' if DARK else '#c75528'};}}
.ap-pill-blue{{background:var(--blue-soft);color:{'#91c2ff' if DARK else '#245e9f'};}}
.ap-pill-green{{background:var(--green-soft);color:{'#7ed8a7' if DARK else '#16794d'};}}
.ap-pill-amber{{background:var(--amber-soft);color:{'#f0bd76' if DARK else '#9a5f17'};}}
.ap-pill-red{{background:var(--red-soft);color:{'#ff9898' if DARK else '#b74343'};}}
.ap-message{{background:var(--surface2);border:1px solid var(--line);border-radius:12px;padding:11px 12px;color:var(--text);font-size:12px;line-height:1.55;white-space:pre-wrap;}}
.ap-help{{background:var(--blue-soft);border:1px solid var(--line);border-radius:12px;padding:10px 12px;color:var(--muted);font-size:12px;line-height:1.45;}}
.ap-flow{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:8px 0 14px;}}
.ap-flow-step{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 12px;}}
.ap-flow-step b{{font-size:12px;color:var(--text);}} .ap-flow-step span{{display:block;font-size:10px;color:var(--muted);margin-top:2px;}}

/* containers */
div[data-testid="stVerticalBlockBorderWrapper"]{{border-color:var(--line)!important;border-radius:14px!important;background:var(--surface)!important;}}
div[data-testid="stVerticalBlockBorderWrapper"] > div{{background:transparent!important;}}

/* selects / inputs */
div[data-baseweb="select"] > div{{background:var(--input)!important;color:var(--input-text)!important;border:1px solid var(--line)!important;border-radius:10px!important;}}
div[data-baseweb="select"] span,div[data-baseweb="select"] p,div[data-baseweb="select"] input{{color:var(--input-text)!important;-webkit-text-fill-color:var(--input-text)!important;opacity:1!important;}}
div[data-baseweb="select"] svg{{fill:var(--input-text)!important;color:var(--input-text)!important;}}
ul[role="listbox"]{{background:var(--surface)!important;border:1px solid var(--line)!important;}}
li[role="option"],li[role="option"] *{{background:var(--surface)!important;color:var(--text)!important;-webkit-text-fill-color:var(--text)!important;}}
li[role="option"]:hover,li[role="option"]:hover *{{background:var(--surface2)!important;}}
.stTextInput input,.stTextArea textarea,[data-testid="stDateInput"] input{{background:var(--input)!important;color:var(--input-text)!important;-webkit-text-fill-color:var(--input-text)!important;border-color:var(--line)!important;}}
.stTextInput input::placeholder,.stTextArea textarea::placeholder{{color:var(--muted)!important;}}

/* buttons */
div[data-testid="stButton"] > button{{background:var(--surface)!important;color:var(--text)!important;border:1px solid var(--line)!important;border-radius:10px!important;font-weight:750!important;box-shadow:none!important;}}
div[data-testid="stButton"] > button *,div[data-testid="stButton"] > button p,div[data-testid="stButton"] > button span{{color:var(--text)!important;-webkit-text-fill-color:var(--text)!important;opacity:1!important;}}
div[data-testid="stButton"] > button:hover{{background:var(--surface2)!important;border-color:#9eb1c4!important;}}
div[data-testid="stButton"] > button[kind="primary"]{{background:var(--navy)!important;color:#fff!important;border-color:var(--navy)!important;}}
div[data-testid="stButton"] > button[kind="primary"] *,div[data-testid="stButton"] > button[kind="primary"] p{{color:#fff!important;-webkit-text-fill-color:#fff!important;}}

/* metrics */
div[data-testid="stMetric"]{{background:var(--surface)!important;border:1px solid var(--line)!important;border-radius:14px!important;padding:12px 14px!important;box-shadow:none!important;}}
div[data-testid="stMetricLabel"] *{{color:var(--muted)!important;}}
div[data-testid="stMetricValue"] *{{color:var(--text)!important;font-weight:900!important;}}

/* checkboxes */
div[data-testid="stCheckbox"] label span{{color:var(--text)!important;}}

/* toggle */
div[data-testid="stToggle"]{{transform:scale(.78);transform-origin:right top;}}
div[data-testid="stToggle"] label,div[data-testid="stToggle"] label *{{color:var(--muted)!important;-webkit-text-fill-color:var(--muted)!important;font-size:11px!important;}}

/* tabs */
.stTabs [data-baseweb="tab-list"]{{gap:8px;background:transparent;}}
.stTabs [data-baseweb="tab"]{{background:var(--surface)!important;border:1px solid var(--line)!important;border-radius:10px!important;padding:8px 14px!important;}}
.stTabs [aria-selected="true"]{{background:var(--navy)!important;}}
.stTabs [aria-selected="true"] *{{color:#fff!important;}}

@media(max-width:1050px){{
  .main .block-container{{padding-left:.8rem;padding-right:.8rem;}}
  .ap-topbar{{margin-left:-.8rem;margin-right:-.8rem;}}
  .ap-flow{{grid-template-columns:1fr;}}
}}
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# UTILITÁRIOS
# =============================================================================
def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def safe_text(value: Any, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else fallback


def trim(text: Any, size: int = 82) -> str:
    value = safe_text(text, "")
    return value if len(value) <= size else value[: size - 1].rstrip() + "…"


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


def parse_payload(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else {}
    except Exception:
        text = str(raw).strip()
        return {"items": [text]} if text else {}


def split_items(text: str) -> list[str]:
    result: list[str] = []
    for raw in str(text or "").splitlines():
        item = raw.strip().lstrip("-•✓☐ ").strip()
        if item and item not in result:
            result.append(item)
    return result


def gaps_to_items(gaps: Any) -> list[str]:
    raw = safe_text(gaps, "")
    if not raw:
        return []
    items = [x.strip() for x in raw.replace(" • ", ";").split(";") if x.strip()]
    return list(dict.fromkeys(items))


def due_score(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 99999.0


def due_label(row: pd.Series) -> str:
    value = safe_text(row.get("Situação do prazo"), "Sem prazo")
    return value


def short_name(row: pd.Series) -> str:
    title = safe_text(row.get("Demanda"), "Demanda")
    unit = safe_text(row.get("Unidade"), "")
    if " | " in title:
        first = title.split(" | ")[0].strip()
        if len(first) > 50:
            first = first[:49].rstrip() + "…"
        return first
    return trim(title, 54) or unit or "Demanda"


def engineer_options(df: pd.DataFrame) -> list[str]:
    names = [x for x in ENGENHEIROS if x != "Gabriel"] + ["Gabriel"]
    actual = [x for x in df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique() if x and x != "Não identificado"]
    return list(dict.fromkeys(["Não identificado"] + names + sorted(actual)))


# =============================================================================
# NEON — ESTADO OPERACIONAL
# =============================================================================
@st.cache_data(ttl=20, show_spinner=False)
def load_review_states() -> dict[str, dict[str, Any]]:
    if not db_available():
        return {}
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select card_id, review_status, pending_owner_type, pending_reason,
                           last_chase_at, last_engineer_response_at, accepted_at,
                           accepted_by, budget_owner, updated_at
                    from orcamento_review_state
                    """
                )
                cols = [d.name for d in cur.description]
                return {str(r[0]): dict(zip(cols, r)) for r in cur.fetchall()}
    except Exception:
        return {}


def save_definition(
    card_id: str,
    items: list[str],
    supervisor: str,
    actor: str,
    note: str,
    response_due: date | None,
    message: str,
    status: str = "waiting_engineering",
) -> tuple[bool, str]:
    if not db_available():
        return False, "Neon não está disponível."
    if not items:
        return False, "Defina pelo menos um item que precisa ser respondido."

    payload = {
        "items": items,
        "supervisor": supervisor,
        "note": note.strip(),
        "response_due": response_due.isoformat() if response_due else None,
        "message": message.strip(),
        "saved_by": actor,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(payload, ensure_ascii=False)
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into orcamento_review_state
                        (card_id, review_status, pending_owner_type, pending_reason,
                         accepted_at, accepted_by, updated_at)
                    values (%s, %s, 'engineering', %s, null, null, now())
                    on conflict (card_id) do update set
                        review_status=excluded.review_status,
                        pending_owner_type='engineering',
                        pending_reason=excluded.pending_reason,
                        accepted_at=null,
                        accepted_by=null,
                        updated_at=now()
                    """,
                    (card_id, status, raw),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log(card_id,event_type,actor,owner_type,details,occurred_at)
                    values (%s,'definition_saved',%s,'engineering',%s,now())
                    """,
                    (card_id, actor, raw),
                )
            conn.commit()
        load_review_states.clear()
        return True, "Definição salva."
    except Exception as exc:
        return False, f"Não foi possível salvar: {str(exc)[:180]}"


def register_chase(card_id: str, actor: str, message: str) -> tuple[bool, str]:
    if not db_available():
        return False, "Neon não está disponível."
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update orcamento_review_state
                    set last_chase_at=now(), review_status='waiting_engineering',
                        pending_owner_type='engineering', updated_at=now()
                    where card_id=%s
                    """,
                    (card_id,),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log(card_id,event_type,actor,owner_type,details,occurred_at)
                    values (%s,'chase_registered',%s,'engineering',%s,now())
                    """,
                    (card_id, actor, message),
                )
            conn.commit()
        load_review_states.clear()
        return True, "Cobrança registrada."
    except Exception as exc:
        return False, f"Não foi possível registrar: {str(exc)[:180]}"


def return_unresolved(
    card_id: str,
    unresolved: list[str],
    supervisor: str,
    actor: str,
    note: str,
    message: str,
) -> tuple[bool, str]:
    return save_definition(
        card_id=card_id,
        items=unresolved,
        supervisor=supervisor,
        actor=actor,
        note=note,
        response_due=None,
        message=message,
        status="waiting_engineering",
    )


def mark_ready(card_id: str, actor: str) -> tuple[bool, str]:
    if not db_available():
        return False, "Neon não está disponível."
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into orcamento_review_state
                        (card_id,review_status,pending_owner_type,pending_reason,accepted_at,accepted_by,updated_at)
                    values (%s,'accepted','budget',null,now(),%s,now())
                    on conflict(card_id) do update set
                        review_status='accepted', pending_owner_type='budget', pending_reason=null,
                        accepted_at=now(), accepted_by=excluded.accepted_by, updated_at=now()
                    """,
                    (card_id, actor),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log(card_id,event_type,actor,owner_type,details,occurred_at)
                    values (%s,'survey_accepted',%s,'budget','Levantamento liberado para elaboração',now())
                    """,
                    (card_id, actor),
                )
            conn.commit()
        load_review_states.clear()
        return True, "Levantamento liberado para elaboração."
    except Exception as exc:
        return False, f"Não foi possível liberar: {str(exc)[:180]}"


def assign_budget_owner(card_id: str, actor: str, owner: str) -> tuple[bool, str]:
    if not db_available():
        return False, "Neon não está disponível."
    try:
        with psycopg.connect(db_url(), connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update orcamento_review_state
                    set budget_owner=%s, updated_at=now()
                    where card_id=%s
                    """,
                    (owner, card_id),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log(card_id,event_type,actor,owner_type,details,occurred_at)
                    values (%s,'budget_owner_assigned',%s,'budget',%s,now())
                    """,
                    (card_id, actor, owner),
                )
            conn.commit()
        load_review_states.clear()
        return True, f"Responsável pela elaboração: {owner}."
    except Exception as exc:
        return False, f"Não foi possível atribuir: {str(exc)[:180]}"


def apply_review_states(df: pd.DataFrame, states: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if df.empty or not states:
        return df
    out = df.copy()
    for idx, row in out.iterrows():
        card_id = str(row.get("Card ID") or "")
        state = states.get(card_id)
        if not state:
            continue
        payload = parse_payload(state.get("pending_reason"))
        saved_supervisor = str(payload.get("supervisor") or "").strip()
        items = payload.get("items") or []
        status = str(state.get("review_status") or "")
        owner_type = str(state.get("pending_owner_type") or "")

        if saved_supervisor:
            out.at[idx, "Engenharia"] = saved_supervisor
        if items:
            out.at[idx, "Pendências definidas"] = "; ".join(map(str, items))
        out.at[idx, "Status interno"] = status

        if status == "accepted":
            out.at[idx, "Fila"] = "Pronto para elaborar"
            out.at[idx, "Aguardando"] = "Orçamentos"
            out.at[idx, "Pendência / próxima ação"] = "Definir responsável e iniciar elaboração"
        elif status == "waiting_engineering" or (status == "pending" and owner_type == "engineering" and items):
            out.at[idx, "Fila"] = "Cobrar Engenharia"
            out.at[idx, "Aguardando"] = "Engenharia"
            if items:
                out.at[idx, "Pendência / próxima ação"] = "Cobrar: " + "; ".join(map(str, items))
    return out


# =============================================================================
# UI HELPERS
# =============================================================================
def topbar() -> None:
    st.markdown(
        """
        <div class="ap-topbar"><div class="ap-topbar-inner">
          <div class="ap-brand">
            <div class="ap-logo">A</div>
            <div class="ap-brand-main">APROAR</div><div class="ap-sep">|</div>
            <div class="ap-brand-area">ORÇAMENTOS</div>
          </div>
          <div class="ap-status">Central de levantamentos</div>
        </div></div>
        """,
        unsafe_allow_html=True,
    )


def queue_pill(queue: str) -> str:
    css = {
        "Cobrar Engenharia": "ap-pill-orange",
        "Conferir retorno": "ap-pill-blue",
        "Pronto para elaborar": "ap-pill-green",
    }.get(queue, "ap-pill-amber")
    return f'<span class="ap-pill {css}">{queue}</span>'


def card_items(row: pd.Series, state: dict[str, Any] | None) -> list[str]:
    payload = parse_payload((state or {}).get("pending_reason"))
    saved = [str(x) for x in (payload.get("items") or []) if str(x).strip()]
    return saved or gaps_to_items(row.get("Possíveis lacunas"))


def build_message(row: pd.Series, items: list[str], supervisor: str, response_due: date | None) -> str:
    name = supervisor if supervisor and supervisor != "Não identificado" else ""
    greeting = f"Olá, {name}." if name else "Olá."
    title = short_name(row)
    unit = safe_text(row.get("Unidade"), "")
    bullets = "\n".join(f"• {item}" for item in items) if items else "• Informações do levantamento"
    due_text = f"\nSe possível, responder até {response_due.strftime('%d/%m/%Y')}." if response_due else ""
    return (
        f"{greeting}\n\n"
        f"Para avançarmos com o orçamento de “{title}”"
        + (f" — {unit}" if unit and unit != "—" else "")
        + ", precisamos confirmar:\n\n"
        + bullets
        + due_text
        + "\n\nPor favor, responda especificamente esses pontos para conseguirmos liberar o levantamento."
    )


def render_board_card(row: pd.Series, state: dict[str, Any] | None, queue: str) -> None:
    card_id = str(row.get("Card ID") or "")
    items = card_items(row, state)
    supervisor = safe_text(row.get("Engenharia"), "Não identificado")
    unit = safe_text(row.get("Unidade"), "Não mapeada")
    due = due_label(row)

    with st.container(border=True):
        st.markdown(queue_pill(queue), unsafe_allow_html=True)
        st.markdown(f"**{short_name(row)}**")
        st.caption(f"{unit} • {supervisor} • {due}")

        if queue == "Cobrar Engenharia":
            st.caption("Falta: " + (" · ".join(items[:3]) if items else "definir a cobrança"))
        elif queue == "Conferir retorno":
            last = safe_text(row.get("Último retorno Engenharia"), "Retorno recebido; conferir conteúdo.")
            st.caption("Retorno: " + trim(last, 115))
        else:
            owner = safe_text((state or {}).get("budget_owner"), "Sem responsável")
            st.caption(f"Levantamento liberado • elaboração: {owner}")

        if st.button("Abrir demanda", key=f"open_{queue}_{card_id}", use_container_width=True):
            st.session_state.selected_card_id = card_id
            st.rerun()


def selected_row(df: pd.DataFrame, card_id: str) -> pd.Series | None:
    if df.empty or not card_id:
        return None
    rows = df[df["Card ID"].astype(str) == str(card_id)]
    if rows.empty:
        return None
    return rows.iloc[0]


def render_detail(row: pd.Series, state: dict[str, Any] | None, actor: str, all_df: pd.DataFrame) -> None:
    card_id = str(row.get("Card ID") or "")
    queue = safe_text(row.get("Fila"))
    payload = parse_payload((state or {}).get("pending_reason"))
    items = card_items(row, state)
    saved_supervisor = str(payload.get("supervisor") or safe_text(row.get("Engenharia"), "Não identificado"))
    url = safe_text(row.get("URL"), "")

    st.markdown(queue_pill(queue), unsafe_allow_html=True)
    st.markdown(f'<div class="ap-detail-title">{escape(safe_text(row.get("Demanda")))}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ap-detail-meta"><b>Unidade:</b> {escape(safe_text(row.get("Unidade")))} &nbsp;•&nbsp; '
        f'<b>Supervisor:</b> {escape(safe_text(row.get("Engenharia")))} &nbsp;•&nbsp; '
        f'<b>Etapa Trello:</b> {escape(safe_text(row.get("Etapa Trello")))}<br>'
        f'<b>Prazo:</b> {escape(due_label(row))}</div>',
        unsafe_allow_html=True,
    )

    if url and url != "—":
        st.link_button("Abrir no Trello ↗", url, use_container_width=True)

    st.divider()

    if queue == "Cobrar Engenharia":
        st.markdown("#### Definir a cobrança")
        st.caption("Essa lista será a definição oficial do que o supervisor precisa responder.")

        initial = "\n".join(f"- {x}" for x in items)
        pending_text = st.text_area(
            "Itens que precisam ser respondidos",
            value=initial,
            height=150,
            key=f"items_{card_id}",
            placeholder="- Altura da pintura\n- Acabamento da tinta\n- Área total em m²",
        )
        current_items = split_items(pending_text)

        engs = engineer_options(all_df)
        current_idx = engs.index(saved_supervisor) if saved_supervisor in engs else 0
        supervisor = st.selectbox("Quem responde?", engs, index=current_idx, key=f"sup_{card_id}")
        response_due = st.date_input(
            "Prazo para resposta",
            value=date.today() + timedelta(days=2),
            key=f"resp_due_{card_id}",
        )
        note = st.text_input(
            "Observação interna (opcional)",
            value=str(payload.get("note") or ""),
            key=f"note_{card_id}",
        )

        suggested_message = build_message(row, current_items, supervisor, response_due)
        stored_message = str(payload.get("message") or "").strip()
        message = st.text_area(
            "Mensagem para o supervisor",
            value=stored_message or suggested_message,
            height=190,
            key=f"msg_{card_id}",
        )
        st.markdown(
            '<div class="ap-help"><b>Como funcionará:</b> hoje o botão registra a cobrança e salva exatamente os itens. '
            'Quando o portal dos engenheiros for criado, esses mesmos itens aparecerão para ele responder um por um.</div>',
            unsafe_allow_html=True,
        )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Salvar definição", type="primary", use_container_width=True, key=f"save_{card_id}"):
                ok, msg = save_definition(card_id, current_items, supervisor, actor, note, response_due, message)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
        with b2:
            if st.button("Registrar cobrança", use_container_width=True, key=f"chase_{card_id}"):
                if not state or not parse_payload(state.get("pending_reason")).get("items"):
                    ok, msg = save_definition(card_id, current_items, supervisor, actor, note, response_due, message)
                    if not ok:
                        st.error(msg)
                    else:
                        ok, msg = register_chase(card_id, actor, message)
                else:
                    ok, msg = register_chase(card_id, actor, message)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

        last_chase = (state or {}).get("last_chase_at")
        if last_chase:
            st.caption(f"Última cobrança registrada: {last_chase}")

    elif queue == "Conferir retorno":
        st.markdown("#### Revisar retorno")
        st.caption("Compare o que foi pedido com o que o supervisor respondeu.")

        last_reply = safe_text(row.get("Último retorno Engenharia"), "Nenhum texto de retorno foi identificado.")
        st.markdown("**Último retorno da Engenharia**")
        st.markdown(f'<div class="ap-message">{last_reply}</div>', unsafe_allow_html=True)

        st.markdown("**Itens que precisam ser validados**")
        if not items:
            st.info("Ainda não existe uma lista estruturada salva para esta demanda. Você pode definir uma abaixo.")
            items = gaps_to_items(row.get("Possíveis lacunas"))

        resolved: list[str] = []
        for i, item in enumerate(items):
            if st.checkbox(f"Atendido — {item}", key=f"review_{card_id}_{i}"):
                resolved.append(item)
        unresolved = [x for x in items if x not in resolved]

        note = st.text_input("Observação da revisão (opcional)", key=f"review_note_{card_id}")
        st.caption(f"Atendidos: {len(resolved)} • ainda faltam: {len(unresolved)}")

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Devolver o que falta", use_container_width=True, key=f"return_{card_id}"):
                if not unresolved:
                    st.warning("Todos os itens foram marcados como atendidos. Use “Marcar pronto”.")
                else:
                    message = build_message(row, unresolved, saved_supervisor, None)
                    ok, msg = return_unresolved(card_id, unresolved, saved_supervisor, actor, note, message)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
        with b2:
            if st.button("Marcar pronto", type="primary", use_container_width=True, key=f"ready_{card_id}"):
                ok, msg = mark_ready(card_id, actor)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

    elif queue == "Pronto para elaborar":
        st.markdown("#### Pronto para elaborar")
        accepted_by = safe_text((state or {}).get("accepted_by"), "Orçamentos")
        accepted_at = safe_text((state or {}).get("accepted_at"), "")
        st.success(f"Levantamento conferido por {accepted_by}.")
        if accepted_at:
            st.caption(f"Liberação registrada em {accepted_at}")

        owners = ["Laisa", "Simeone", "César"]
        current_owner = safe_text((state or {}).get("budget_owner"), "")
        idx = owners.index(current_owner) if current_owner in owners else 0
        budget_owner = st.selectbox("Responsável pela elaboração", owners, index=idx, key=f"budget_{card_id}")
        if st.button("Atribuir elaboração", type="primary", use_container_width=True, key=f"assign_{card_id}"):
            ok, msg = assign_budget_owner(card_id, actor, budget_owner)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    else:
        st.info("Esta demanda está fora das três filas prioritárias do Radar.")

    with st.expander("Ver contexto do Trello"):
        st.write("**Próximo passo detectado:**", safe_text(row.get("Pendência / próxima ação")))
        st.write("**Possíveis lacunas detectadas:**", safe_text(row.get("Possíveis lacunas")))
        st.write("**Último comentário:**", safe_text(row.get("Último comentário")))
        st.write("**Autor / data:**", safe_text(row.get("Autor último comentário")), "•", safe_text(row.get("Último comentário em")))


# =============================================================================
# DADOS
# =============================================================================
nonce = int(st.session_state.get("trello_nonce", 0))
try:
    snapshot = cached_snapshot(nonce)
except TrelloError as exc:
    topbar(); st.error(str(exc)); st.stop()
except Exception as exc:
    topbar(); st.error(f"Não foi possível carregar o Trello: {exc}"); st.stop()

trust_ready = bool(secret("TRUST_TRELLO_READY_LIST", False))
result = analyze_snapshot(snapshot, trust_trello_ready_list=trust_ready)
df_all = result.rows.copy()
states = load_review_states()
df_all = apply_review_states(df_all, states)


# =============================================================================
# CABEÇALHO / CONTROLES
# =============================================================================
topbar()

head_l, head_r = st.columns([7, 2.2])
with head_l:
    st.markdown('<div class="ap-kicker">Orçamentos / Central de levantamentos</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="ap-title">Definir e cobrar levantamentos<span class="ap-dot">.</span></h1>', unsafe_allow_html=True)
    st.markdown('<div class="ap-sub">Prioridade: o que cobrar dos engenheiros, o que precisa ser revisado e o que já está pronto para elaborar.</div>', unsafe_allow_html=True)
with head_r:
    h1, h2 = st.columns([1.8, 1])
    with h1:
        actor = st.selectbox("Operador", ["Laisa", "Simeone", "César"], label_visibility="collapsed")
    with h2:
        st.toggle("Escuro", key="dark_mode", help="Alternar claro/escuro")

ctl1, ctl2, ctl3 = st.columns([1.2, 2, 6])
with ctl1:
    if st.button("↻ Atualizar", use_container_width=True):
        st.session_state.trello_nonce = int(st.session_state.get("trello_nonce", 0)) + 1
        cached_snapshot.clear()
        st.rerun()
with ctl2:
    modulo = st.selectbox(
        "Módulo",
        ["Radar de levantamentos", "Fluxo geral"],
        index=0 if st.session_state.modulo == "Radar de levantamentos" else 1,
        label_visibility="collapsed",
    )
    st.session_state.modulo = modulo
with ctl3:
    board_name = safe_text((snapshot.get("board") or {}).get("name"), "ORÇAMENTOS")
    db_status = "Neon conectado" if db_available() else "Neon indisponível"
    st.caption(f"Quadro: {board_name} • {db_status} • atualização manual ou a cada 5 minutos")


# =============================================================================
# MÓDULO 1 — RADAR DE LEVANTAMENTOS
# =============================================================================
if modulo == "Radar de levantamentos":
    # Este radar mostra somente as três filas operacionais prioritárias.
    radar_df = df_all[df_all["Fila"].isin(["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar"])].copy()

    f1, f2, f3, f4, f5 = st.columns([1.15, 1.2, 1.15, 1.0, 1.5])
    eng_opts = ["Todos"] + sorted([x for x in radar_df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    stage_opts = ["Todas"] + sorted([x for x in radar_df.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    with f1:
        filtro_eng = st.selectbox("Engenharia", eng_opts)
    with f2:
        filtro_stage = st.selectbox("Etapa Trello", stage_opts)
    with f3:
        filtro_prazo = st.selectbox("Prazo", ["Todos", "Atrasados", "Hoje", "Até 2 dias", "Sem prazo"])
    with f4:
        ordenacao = st.selectbox("Ordenar", ["Prazo", "Mais recentes"])
    with f5:
        busca = st.text_input("Buscar", placeholder="Obra, unidade, supervisor…")

    filtered = radar_df.copy()
    if not filtered.empty:
        if filtro_eng != "Todos":
            filtered = filtered[filtered["Engenharia"] == filtro_eng]
        if filtro_stage != "Todas":
            filtered = filtered[filtered["Etapa Trello"] == filtro_stage]
        dias = pd.to_numeric(filtered.get("Dias até prazo", pd.Series(index=filtered.index, dtype=float)), errors="coerce")
        if filtro_prazo == "Atrasados":
            filtered = filtered[dias < 0]
        elif filtro_prazo == "Hoje":
            filtered = filtered[dias == 0]
        elif filtro_prazo == "Até 2 dias":
            filtered = filtered[dias.between(0, 2, inclusive="both")]
        elif filtro_prazo == "Sem prazo":
            filtered = filtered[dias.isna()]
        if busca.strip():
            q = busca.strip().casefold()
            hay = (
                filtered["Demanda"].astype(str) + " " +
                filtered["Unidade"].astype(str) + " " +
                filtered["Engenharia"].astype(str)
            ).str.casefold()
            filtered = filtered[hay.str.contains(q, regex=False)]

        if ordenacao == "Prazo":
            filtered["_sort"] = pd.to_numeric(filtered.get("Dias até prazo"), errors="coerce").fillna(99999)
            filtered = filtered.sort_values("_sort", ascending=True)
        else:
            filtered = filtered.sort_values("Último comentário em", ascending=False, na_position="last")

    counts = filtered["Fila"].value_counts() if not filtered.empty else pd.Series(dtype=int)
    late = int((pd.to_numeric(filtered.get("Dias até prazo", pd.Series(dtype=float)), errors="coerce") < 0).sum()) if not filtered.empty else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cobrar Engenharia", int(counts.get("Cobrar Engenharia", 0)))
    m2.metric("Conferir retorno", int(counts.get("Conferir retorno", 0)))
    m3.metric("Pronto para elaborar", int(counts.get("Pronto para elaborar", 0)))
    m4.metric("Atrasadas", late)

    st.markdown(
        '<div class="ap-flow">'
        '<div class="ap-flow-step"><b>1 · Cobrar Engenharia</b><span>Definir exatamente o que falta e registrar a cobrança.</span></div>'
        '<div class="ap-flow-step"><b>2 · Conferir retorno</b><span>Validar item a item o que o supervisor respondeu.</span></div>'
        '<div class="ap-flow-step"><b>3 · Pronto para elaborar</b><span>Atribuir quem fará o orçamento e seguir para produção.</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    board_area, detail_area = st.columns([3.45, 1.45], gap="large")

    queues = ["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar"]
    visible_ids = set(filtered["Card ID"].astype(str).tolist()) if not filtered.empty else set()
    if st.session_state.selected_card_id not in visible_ids:
        st.session_state.selected_card_id = str(filtered.iloc[0]["Card ID"]) if not filtered.empty else ""

    with board_area:
        st.markdown('<div class="ap-section-title">Fila de trabalho</div>', unsafe_allow_html=True)
        st.caption(f"{len(filtered)} demandas nos filtros atuais")
        c1, c2, c3 = st.columns(3, gap="small")
        for col, queue in zip([c1, c2, c3], queues):
            with col:
                qdf = filtered[filtered["Fila"] == queue].copy() if not filtered.empty else pd.DataFrame()
                st.markdown(
                    f'<div class="ap-column-head"><div class="ap-column-title">{queue}</div>'
                    f'<div class="ap-count">{len(qdf)}</div></div>',
                    unsafe_allow_html=True,
                )
                with st.container(height=660, border=True):
                    if qdf.empty:
                        st.markdown('<div class="ap-empty">Nenhuma demanda aqui.</div>', unsafe_allow_html=True)
                    else:
                        for _, row in qdf.iterrows():
                            render_board_card(row, states.get(str(row.get("Card ID") or "")), queue)

    with detail_area:
        st.markdown('<div class="ap-section-title">Detalhes da demanda</div>', unsafe_allow_html=True)
        row = selected_row(filtered, st.session_state.selected_card_id)
        with st.container(border=True):
            if row is None:
                st.info("Selecione uma demanda no quadro para trabalhar nela.")
            else:
                render_detail(row, states.get(str(row.get("Card ID") or "")), actor, df_all)


# =============================================================================
# MÓDULO 2 — FLUXO GERAL
# =============================================================================
else:
    st.markdown('<div class="ap-section-title">Fluxo geral</div>', unsafe_allow_html=True)
    st.caption("Aqui ficam as demandas que não precisam ocupar o Radar principal: pendências de cliente, terceiros e demais etapas do processo.")

    fg1, fg2, fg3 = st.columns([1.4, 1.4, 2])
    stages = ["Todas"] + sorted([x for x in df_all.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    waits = ["Todos"] + sorted([x for x in df_all.get("Aguardando", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    with fg1:
        stage = st.selectbox("Etapa Trello", stages, key="flow_stage")
    with fg2:
        wait = st.selectbox("Aguardando", waits, key="flow_wait")
    with fg3:
        search_flow = st.text_input("Buscar demanda", key="flow_search")

    flow_df = df_all.copy()
    if stage != "Todas":
        flow_df = flow_df[flow_df["Etapa Trello"] == stage]
    if wait != "Todos":
        flow_df = flow_df[flow_df["Aguardando"] == wait]
    if search_flow.strip():
        q = search_flow.strip().casefold()
        hay = (flow_df["Demanda"].astype(str) + " " + flow_df["Unidade"].astype(str)).str.casefold()
        flow_df = flow_df[hay.str.contains(q, regex=False)]

    if flow_df.empty:
        st.info("Nenhuma demanda com estes filtros.")
    else:
        summary = (
            flow_df.groupby(["Etapa Trello", "Aguardando"], dropna=False)
            .size()
            .reset_index(name="Demandas")
            .sort_values("Demandas", ascending=False)
        )
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.markdown("#### Demandas")
        cols = [
            "Demanda", "Unidade", "Engenharia", "Etapa Trello", "Aguardando",
            "Situação do prazo", "Pendência / próxima ação", "URL",
        ]
        st.dataframe(flow_df[cols], use_container_width=True, hide_index=True)
