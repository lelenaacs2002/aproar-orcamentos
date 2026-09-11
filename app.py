from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from radar import ENGENHEIROS, analyze_snapshot, reconcile_review_states, LOCAL_TZ
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
    initial_sidebar_state="expanded",
)

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "selected_card_id" not in st.session_state:
    st.session_state.selected_card_id = ""
if "selected_queue" not in st.session_state:
    st.session_state.selected_queue = "Cobrar Engenharia"

DARK = bool(st.session_state.dark_mode)

if DARK:
    C = {
        "bg": "#0d1622",
        "surface": "#132131",
        "surface2": "#18293b",
        "text": "#f4f7fb",
        "muted": "#a7b5c5",
        "line": "#293c50",
        "sidebar": "#0b2037",
        "input": "#172638",
        "input_text": "#f4f7fb",
        "shadow": "rgba(0,0,0,.16)",
    }
else:
    C = {
        "bg": "#f4f6f9",
        "surface": "#ffffff",
        "surface2": "#f8fafc",
        "text": "#112d49",
        "muted": "#718399",
        "line": "#dbe3eb",
        "sidebar": "#0d2846",
        "input": "#ffffff",
        "input_text": "#17324f",
        "shadow": "rgba(30,55,80,.05)",
    }

st.markdown(
    f"""
<style>
:root {{
  color-scheme:{'dark' if DARK else 'light'};
  --bg:{C['bg']}; --surface:{C['surface']}; --surface2:{C['surface2']};
  --text:{C['text']}; --muted:{C['muted']}; --line:{C['line']};
  --sidebar:{C['sidebar']}; --input:{C['input']}; --input-text:{C['input_text']};
  --shadow:{C['shadow']}; --orange:#f36d34; --blue:#2f6ed1; --green:#16915b; --red:#dc5260;
}}

html,body,[data-testid="stAppViewContainer"] {{background:var(--bg)!important;color:var(--text)!important;}}
[data-testid="stHeader"] {{background:transparent!important;}}
#MainMenu,footer {{visibility:hidden;}}
.main .block-container {{max-width:1500px;padding-top:2rem;padding-bottom:3rem;padding-left:2.2rem;padding-right:2.2rem;}}
h1,h2,h3,h4,p,label {{color:var(--text);}}

/* SIDEBAR — inspirado no padrão das outras plataformas APROAR */
section[data-testid="stSidebar"] {{background:var(--sidebar)!important;border-right:none!important;}}
section[data-testid="stSidebar"] > div {{background:var(--sidebar)!important;}}
section[data-testid="stSidebar"] .block-container {{padding:1.6rem 1rem!important;}}
.ap-logo-wrap {{padding:1.25rem .65rem 1.5rem;text-align:center;}}
.ap-logo {{color:#fff;font-size:27px;font-weight:900;letter-spacing:.04em;line-height:1;}}
.ap-logo-sub {{color:#afc2d7;font-size:8px;letter-spacing:.26em;margin-top:4px;}}
.ap-side-section {{color:#6f91b4;font-size:9px;letter-spacing:.2em;font-weight:800;margin:1.1rem .45rem .35rem;text-transform:uppercase;}}
.ap-side-foot {{color:#88a2bc;font-size:11px;line-height:1.55;padding:.8rem .45rem;}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {{
  border-radius:10px!important;padding:10px 12px!important;margin:3px 0!important;background:transparent!important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label p,
section[data-testid="stSidebar"] [data-testid="stRadio"] label span {{color:#e8eef5!important;-webkit-text-fill-color:#e8eef5!important;font-size:14px!important;}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{background:#2d69dc!important;}}
section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"] > div:first-child {{display:none!important;}}
section[data-testid="stSidebar"] div[data-testid="stToggle"] label,
section[data-testid="stSidebar"] div[data-testid="stToggle"] label * {{color:#c6d4e2!important;-webkit-text-fill-color:#c6d4e2!important;font-size:12px!important;}}

/* CABEÇALHO */
.ap-page-head {{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:14px;}}
.ap-title {{font-size:34px;font-weight:900;letter-spacing:-.035em;line-height:1.1;color:var(--text);margin:0;}}
.ap-sub {{font-size:14px;color:var(--muted);margin-top:7px;}}
.ap-head-note {{text-align:right;color:var(--muted);font-size:11px;line-height:1.6;padding-top:4px;}}

/* CARDS */
.ap-panel {{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 24px var(--shadow);}}
.ap-kpis {{display:grid;grid-template-columns:repeat(3,1fr);background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin:16px 0 12px;box-shadow:0 8px 24px var(--shadow);}}
.ap-kpi {{padding:16px 20px;border-right:1px solid var(--line);min-height:92px;}}
.ap-kpi:last-child {{border-right:none;}}
.ap-kpi-label {{font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);font-weight:800;}}
.ap-kpi-row {{display:flex;align-items:baseline;gap:10px;margin-top:7px;}}
.ap-kpi-num {{font-size:29px;font-weight:900;line-height:1;}}
.ap-kpi-text {{font-size:12px;color:var(--muted);}}
.ap-orange {{color:var(--orange);}} .ap-blue {{color:var(--blue);}} .ap-green {{color:var(--green);}}

.ap-section-title {{font-size:18px;font-weight:900;color:var(--text);margin:0;}}
.ap-section-sub {{font-size:12px;color:var(--muted);margin-top:3px;}}
.ap-section-head {{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:18px 0 10px;}}
.ap-count {{font-size:11px;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:4px 9px;}}

.ap-row-card {{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:13px 14px;margin-bottom:8px;box-shadow:0 4px 14px var(--shadow);}}
.ap-row-top {{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;}}
.ap-row-title {{font-size:14px;font-weight:850;color:var(--text);line-height:1.35;}}
.ap-row-meta {{font-size:11px;color:var(--muted);margin-top:5px;line-height:1.5;}}
.ap-row-missing {{font-size:11px;color:var(--muted);margin-top:7px;}}
.ap-status {{font-size:10px;font-weight:800;border-radius:999px;padding:4px 8px;white-space:nowrap;}}
.ap-status-orange {{background:{'#3b241a' if DARK else '#fff0e8'};color:{'#ff9e79' if DARK else '#bf552b'};}}
.ap-status-blue {{background:{'#172d4b' if DARK else '#edf4ff'};color:{'#8fc0ff' if DARK else '#285f9f'};}}
.ap-status-green {{background:{'#173528' if DARK else '#edf9f2'};color:{'#7ed7a5' if DARK else '#167d4e'};}}
.ap-status-red {{background:{'#3a2025' if DARK else '#fff0f2'};color:{'#ff9ba4' if DARK else '#b9434f'};}}
.ap-status-gray {{background:var(--surface2);color:var(--muted);}}

.ap-detail-head {{padding-bottom:12px;border-bottom:1px solid var(--line);margin-bottom:12px;}}
.ap-detail-title {{font-size:18px;font-weight:900;line-height:1.35;color:var(--text);margin:6px 0;}}
.ap-detail-meta {{font-size:11px;color:var(--muted);line-height:1.55;}}
.ap-mini-title {{font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:800;margin:2px 0 8px;}}
.ap-context {{font-size:12px;color:var(--muted);line-height:1.55;background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:9px 10px;margin:8px 0;}}
.ap-message {{font-size:12px;line-height:1.55;color:var(--text);background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:10px 11px;white-space:pre-wrap;}}
.ap-help {{font-size:11px;line-height:1.5;color:var(--muted);}}
.ap-empty {{font-size:12px;color:var(--muted);padding:18px;text-align:center;}}

/* Native containers */
div[data-testid="stVerticalBlockBorderWrapper"] {{background:var(--surface)!important;border:1px solid var(--line)!important;border-radius:14px!important;box-shadow:0 8px 24px var(--shadow)!important;}}
div[data-testid="stVerticalBlockBorderWrapper"] > div {{background:transparent!important;}}

/* Inputs/selects — força contraste correto nos dois temas */
div[data-baseweb="select"] > div {{background:var(--input)!important;color:var(--input-text)!important;border:1px solid var(--line)!important;border-radius:10px!important;}}
div[data-baseweb="select"] span,div[data-baseweb="select"] p,div[data-baseweb="select"] input {{color:var(--input-text)!important;-webkit-text-fill-color:var(--input-text)!important;opacity:1!important;}}
div[data-baseweb="select"] svg {{fill:var(--input-text)!important;color:var(--input-text)!important;}}
ul[role="listbox"] {{background:var(--surface)!important;border:1px solid var(--line)!important;}}
li[role="option"],li[role="option"] * {{background:var(--surface)!important;color:var(--text)!important;-webkit-text-fill-color:var(--text)!important;}}
li[role="option"]:hover,li[role="option"]:hover * {{background:var(--surface2)!important;}}
.stTextInput input,.stTextArea textarea,[data-testid="stDateInput"] input {{background:var(--input)!important;color:var(--input-text)!important;-webkit-text-fill-color:var(--input-text)!important;border-color:var(--line)!important;}}
.stTextInput input::placeholder,.stTextArea textarea::placeholder {{color:var(--muted)!important;}}

/* Botões */
div[data-testid="stButton"] > button {{background:var(--surface)!important;color:var(--text)!important;border:1px solid var(--line)!important;border-radius:10px!important;font-weight:750!important;box-shadow:none!important;}}
div[data-testid="stButton"] > button *,div[data-testid="stButton"] > button p,div[data-testid="stButton"] > button span {{color:var(--text)!important;-webkit-text-fill-color:var(--text)!important;opacity:1!important;}}
div[data-testid="stButton"] > button:hover {{background:var(--surface2)!important;border-color:#a8b8c8!important;}}
div[data-testid="stButton"] > button[kind="primary"] {{background:#2d69dc!important;color:#fff!important;border-color:#2d69dc!important;}}
div[data-testid="stButton"] > button[kind="primary"] *,div[data-testid="stButton"] > button[kind="primary"] p {{color:#fff!important;-webkit-text-fill-color:#fff!important;}}

/* Segmented control */
[data-testid="stSegmentedControl"] button {{background:var(--surface)!important;border-color:var(--line)!important;color:var(--text)!important;}}
[data-testid="stSegmentedControl"] button[aria-pressed="true"] {{background:var(--sidebar)!important;color:#fff!important;}}
[data-testid="stSegmentedControl"] button[aria-pressed="true"] * {{color:#fff!important;}}
/* Contraste definitivo: os botões escuros da fila sempre usam texto branco. */
[data-testid="stSegmentedControl"] button {{
  background:#10243a!important;
  border-color:#31475d!important;
  color:#fff!important;
  -webkit-text-fill-color:#fff!important;
}}
[data-testid="stSegmentedControl"] button *,
[data-testid="stSegmentedControl"] button p,
[data-testid="stSegmentedControl"] button span {{
  color:#fff!important;
  -webkit-text-fill-color:#fff!important;
  opacity:1!important;
}}
[data-testid="stSegmentedControl"] button[aria-pressed="true"] {{
  background:#2d69dc!important;
  border-color:#2d69dc!important;
}}

/* Checkboxes / expanders */
div[data-testid="stCheckbox"] label span {{color:var(--text)!important;}}
div[data-testid="stExpander"] {{background:transparent!important;border:none!important;}}
div[data-testid="stExpander"] details {{background:var(--surface)!important;border:1px solid var(--line)!important;border-radius:10px!important;overflow:hidden;}}
/* Cabeçalho do expander é um botão escuro: texto sempre branco. */
div[data-testid="stExpander"] summary {{background:#10243a!important;color:#fff!important;-webkit-text-fill-color:#fff!important;}}
div[data-testid="stExpander"] summary *,
div[data-testid="stExpander"] summary p,
div[data-testid="stExpander"] summary span,
div[data-testid="stExpander"] summary svg {{color:#fff!important;-webkit-text-fill-color:#fff!important;fill:#fff!important;opacity:1!important;}}

/* Link buttons do Streamlit também usam uma árvore diferente de st.button. */
[data-testid="stLinkButton"] a,
a[data-testid^="stBaseLinkButton"] {{background:#10243a!important;border:1px solid #31475d!important;color:#fff!important;-webkit-text-fill-color:#fff!important;border-radius:10px!important;font-weight:750!important;}}
[data-testid="stLinkButton"] a *,
a[data-testid^="stBaseLinkButton"] *,
[data-testid="stLinkButton"] a p,
[data-testid="stLinkButton"] a span {{color:#fff!important;-webkit-text-fill-color:#fff!important;opacity:1!important;}}

/* Reforço específico para a fila: selecionado escuro = texto branco. */
.st-key-queue_selector button[aria-pressed="true"],
.st-key-queue_selector button[aria-pressed="true"] *,
.st-key-queue_selector button[aria-pressed="true"] p,
.st-key-queue_selector button[aria-pressed="true"] span {{color:#fff!important;-webkit-text-fill-color:#fff!important;opacity:1!important;}}

@media(max-width:1000px) {{
  .main .block-container{{padding-left:1rem;padding-right:1rem;}}
  .ap-page-head{{display:block;}}
  .ap-head-note{{text-align:left;margin-top:8px;}}
  .ap-kpis{{grid-template-columns:1fr;}}
  .ap-kpi{{border-right:none;border-bottom:1px solid var(--line);}}
  .ap-kpi:last-child{{border-bottom:none;}}
}}
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# DADOS / HELPERS
# =============================================================================
def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)


def safe_text(value: Any, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else fallback


def trim(value: Any, size: int = 120) -> str:
    text = safe_text(value, "")
    return text if len(text) <= size else text[: size - 1].rstrip() + "…"


def load_snapshot(force_nonce: int = 0) -> dict[str, Any]:
    board = secret("TRELLO_BOARD_URL", secret("TRELLO_BOARD", "https://trello.com/b/TX8hGvmI"))
    snapshot = TrelloClient(board=board).snapshot()
    snapshot["_fetched_at"] = datetime.now(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")
    return snapshot


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
    if not raw or raw in {"—", "-", "Nenhuma"}:
        return []
    items = [x.strip() for x in raw.replace(" • ", ";").split(";") if x.strip()]
    return list(dict.fromkeys(items))


def engineer_options(df: pd.DataFrame) -> list[str]:
    standard = [x for x in ENGENHEIROS if x != "Gabriel"] + ["Gabriel"]
    actual = [
        x for x in df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique()
        if x and x != "Não identificado"
    ]
    return list(dict.fromkeys(["Não identificado"] + standard + sorted(actual)))


def card_items(row: pd.Series, state: dict[str, Any] | None) -> list[str]:
    payload = parse_payload((state or {}).get("pending_reason"))
    saved = [str(x).strip() for x in (payload.get("items") or []) if str(x).strip()]
    return saved or gaps_to_items(row.get("Possíveis lacunas"))


def due_label(row: pd.Series) -> str:
    return safe_text(row.get("Situação do prazo"), "Sem prazo")


def queue_status_class(queue: str) -> str:
    return {
        "Cobrar Engenharia": "ap-status-orange",
        "Conferir retorno": "ap-status-blue",
        "Pronto para elaborar": "ap-status-green",
    }.get(queue, "ap-status-gray")


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
        st.error("Não foi possível carregar as decisões salvas. Verifique a conexão e as tabelas do banco antes de continuar.")
        st.stop()


def save_definition(
    card_id: str,
    items: list[str],
    supervisor: str,
    actor: str,
    note: str,
    response_due: date | None,
) -> tuple[bool, str]:
    if not db_available():
        return False, "Neon não está disponível."
    if not items:
        return False, "Defina pelo menos um item que precisa ser respondido."
    if supervisor not in ENGENHEIROS:
        return False, "Selecione o engenheiro responsável antes de salvar."

    payload = {
        "items": items,
        "supervisor": supervisor,
        "note": note.strip(),
        "response_due": response_due.isoformat() if response_due else None,
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
                    values (%s, 'waiting_engineering', 'engineering', %s, null, null, now())
                    on conflict (card_id) do update set
                        review_status='waiting_engineering',
                        pending_owner_type='engineering',
                        pending_reason=excluded.pending_reason,
                        accepted_at=null,
                        accepted_by=null,
                        updated_at=now()
                    """,
                    (card_id, raw),
                )
                cur.execute(
                    """
                    insert into orcamento_event_log(card_id,event_type,actor,owner_type,details,occurred_at)
                    values (%s,'definition_saved',%s,'engineering',%s,now())
                    """,
                    (card_id, actor, raw),
                )
            conn.commit()
        return True, "Pendências salvas."
    except Exception as exc:
        return False, f"Não foi possível salvar: {str(exc)[:180]}"


def register_chase(card_id: str, actor: str, details: str) -> tuple[bool, str]:
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
                    (card_id, actor, details),
                )
            conn.commit()
        return True, "Cobrança registrada."
    except Exception as exc:
        return False, f"Não foi possível registrar: {str(exc)[:180]}"


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
                        review_status='accepted', pending_owner_type='budget',
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
        return True, "Levantamento liberado para elaboração."
    except Exception as exc:
        return False, f"Não foi possível liberar: {str(exc)[:180]}"


def return_unresolved(
    card_id: str,
    items: list[str],
    supervisor: str,
    actor: str,
    note: str,
) -> tuple[bool, str]:
    return save_definition(card_id, items, supervisor, actor, note, None)


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
        return True, f"Responsável pela elaboração: {owner}."
    except Exception as exc:
        return False, f"Não foi possível atribuir: {str(exc)[:180]}"


def apply_review_states(df: pd.DataFrame, states: dict[str, dict[str, Any]]) -> pd.DataFrame:
    return reconcile_review_states(df, states)


def selected_row(df: pd.DataFrame, card_id: str) -> pd.Series | None:
    if df.empty or not card_id:
        return None
    rows = df[df["Card ID"].astype(str) == str(card_id)]
    return None if rows.empty else rows.iloc[0]


def render_compact_row(row: pd.Series, state: dict[str, Any] | None) -> None:
    card_id = str(row.get("Card ID") or "")
    queue = safe_text(row.get("Fila"))
    title = trim(row.get("Demanda"), 72)
    unit = safe_text(row.get("Unidade"), "Unidade não mapeada")
    engineer = safe_text(row.get("Engenharia"), "Não identificado")
    due = due_label(row)
    items = card_items(row, state)
    missing = (" · ".join(items[:3]) if items else "Definir o que precisa ser solicitado") if queue == "Cobrar Engenharia" else safe_text(row.get("Pendência / próxima ação"))

    st.markdown(
        f"""
        <div class="ap-row-card">
          <div class="ap-row-top">
            <div>
              <div class="ap-row-title">{escape(title)}</div>
              <div class="ap-row-meta">{escape(unit)} &nbsp;•&nbsp; {escape(engineer)}</div>
            </div>
            <span class="ap-status {queue_status_class(queue)}">{escape(due)}</span>
          </div>
          <div class="ap-row-missing"><b>{'Falta' if queue == 'Cobrar Engenharia' else 'Resumo'}:</b> {escape(trim(missing, 115))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir", key=f"open_{queue}_{card_id}", use_container_width=True):
        st.session_state.selected_card_id = card_id
        st.rerun()


def render_detail(row: pd.Series, state: dict[str, Any] | None, actor: str, all_df: pd.DataFrame) -> None:
    card_id = str(row.get("Card ID") or "")
    queue = safe_text(row.get("Fila"))
    payload = parse_payload((state or {}).get("pending_reason"))
    items = card_items(row, state)
    supervisor_saved = str(payload.get("supervisor") or safe_text(row.get("Engenharia"), "Não identificado"))
    url = safe_text(row.get("URL"), "")
    revision = str(row.get("_Atualização Engenharia") or "") + str((state or {}).get("updated_at") or "")

    st.markdown(
        f"""
        <div class="ap-detail-head">
          <span class="ap-status {queue_status_class(queue)}">{escape(queue)}</span>
          <div class="ap-detail-title">{escape(safe_text(row.get('Demanda')))}</div>
          <div class="ap-detail-meta">
            <b>{escape(safe_text(row.get('Unidade')))}</b> &nbsp;•&nbsp;
            {escape(safe_text(row.get('Engenharia')))} &nbsp;•&nbsp;
            {escape(safe_text(row.get('Etapa Trello')))} &nbsp;•&nbsp;
            {escape(due_label(row))}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if queue == "Cobrar Engenharia":
        st.markdown('<div class="ap-mini-title">Definir o que cobrar</div>', unsafe_allow_html=True)
        initial = "\n".join(f"- {x}" for x in items)
        pending_text = st.text_area(
            "Itens que o engenheiro precisa responder",
            value=initial,
            height=150,
            key=f"items_{card_id}",
            placeholder="- Altura da pintura\n- Acabamento da tinta\n- Área total em m²",
        )
        current_items = split_items(pending_text)

        engs = engineer_options(all_df)
        current_idx = engs.index(supervisor_saved) if supervisor_saved in engs else 0
        supervisor = st.selectbox("Quem responde?", engs, index=current_idx, key=f"sup_{card_id}")

        c1, c2 = st.columns(2)
        with c1:
            response_due = st.date_input(
                "Prazo para resposta",
                value=date.fromisoformat(payload["response_due"][:10]) if payload.get("response_due") else None,
                key=f"due_{card_id}",
            )
        with c2:
            note = st.text_input(
                "Observação interna",
                value=str(payload.get("note") or ""),
                key=f"note_{card_id}",
                placeholder="Opcional",
            )

        st.markdown(
            '<div class="ap-help">Sugestões detectadas no texto precisam ser conferidas. Salvar registra as pendências no painel. A cobrança deve ser enviada pelo operador.</div>',
            unsafe_allow_html=True,
        )

        message = f"{supervisor}, para elaborar o orçamento {row.get('Demanda')}, precisamos:\n" + "\n".join(f"• {item}" for item in current_items)
        if response_due:
            message += f"\nPrazo de resposta: {response_due:%d/%m/%Y}."
        message += f"\nRegistre as informações no cartão: {url}"
        with st.expander("Texto para copiar e cobrar"):
            st.code(message, language=None)
        st.caption("Registrar cobrança apenas anota um contato já realizado; não envia mensagens.")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Salvar pendências", type="primary", use_container_width=True, key=f"save_{card_id}"):
                ok, msg = save_definition(card_id, current_items, supervisor, actor, note, response_due)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
        with b2:
            if st.button("Registrar cobrança", use_container_width=True, key=f"chase_{card_id}"):
                ok, msg = save_definition(card_id, current_items, supervisor, actor, note, response_due)
                if ok:
                    ok, msg = register_chase(card_id, actor, " | ".join(current_items))
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

    elif queue == "Conferir retorno":
        st.markdown('<div class="ap-mini-title">Retorno recebido</div>', unsafe_allow_html=True)
        last_reply = safe_text(row.get("Último retorno Engenharia"), "Nenhum texto de retorno identificado.")
        st.markdown(f'<div class="ap-message">{escape(last_reply)}</div>', unsafe_allow_html=True)

        st.markdown('<div class="ap-mini-title" style="margin-top:14px;">Conferir item a item</div>', unsafe_allow_html=True)
        if not items:
            items = gaps_to_items(row.get("Possíveis lacunas"))
        resolved: list[str] = []
        for i, item in enumerate(items):
            if st.checkbox(item + " — atendido ou não se aplica", key=f"review_{card_id}_{revision}_{i}"):
                resolved.append(item)
        unresolved = [x for x in items if x not in resolved]
        st.caption(f"{len(resolved)} atendidos • {len(unresolved)} ainda pendentes")
        note = st.text_input("Observação da revisão", key=f"review_note_{card_id}", placeholder="Opcional")

        confirmed = st.checkbox("Conferi o levantamento e todos os itens estão atendidos ou não se aplicam.", key=f"confirm_{card_id}_{revision}")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Devolver o que falta", use_container_width=True, key=f"return_{card_id}"):
                if not unresolved:
                    st.warning("Todos os itens estão marcados. Use “Marcar pronto”.")
                else:
                    ok, msg = return_unresolved(card_id, unresolved, supervisor_saved, actor, note)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
        with b2:
            if st.button("Marcar pronto", type="primary", use_container_width=True, key=f"ready_{card_id}", disabled=not confirmed or bool(unresolved)):
                ok, msg = mark_ready(card_id, actor)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

    elif queue == "Pronto para elaborar":
        st.success("Levantamento conferido. Já pode seguir para elaboração.")
        owners = ["Laisa", "Simeone", "César"]
        current_owner = safe_text((state or {}).get("budget_owner"), "")
        idx = owners.index(current_owner) if current_owner in owners else 0
        owner = st.selectbox("Responsável pela elaboração", owners, index=idx, key=f"owner_{card_id}")
        if st.button("Atribuir elaboração", type="primary", use_container_width=True, key=f"assign_{card_id}"):
            ok, msg = assign_budget_owner(card_id, actor, owner)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    st.caption(f"Resposta: {safe_text(row.get('Prazo resposta'))} • Última cobrança: {safe_text(row.get('Última cobrança'))}")
    st.caption(f"Responsável identificado por: {safe_text(row.get('Fonte responsável'))}")
    with st.expander("Descrição, anexos e comentários recebidos do Trello"):
        st.text(safe_text(row.get("_Descrição"), "Sem descrição."))
        for attachment in row.get("_Anexos", []) or []:
            if str(attachment.get("url", "")).startswith("https://"):
                st.link_button(attachment.get("nome") or "Anexo", attachment["url"])
        for comment in row.get("_Comentários", []) or []:
            st.caption(f"{comment['autor']} • {comment['data']}")
            st.text(comment["texto"])
        st.caption("Exibimos o histórico entregue pelo cliente Trello. O conteúdo dos anexos não é analisado automaticamente.")
        st.write("**Próximo passo detectado:**", safe_text(row.get("Pendência / próxima ação")))
        st.write("**Último comentário:**", safe_text(row.get("Último comentário")))
        st.write("**Autor/data:**", safe_text(row.get("Autor último comentário")), "•", safe_text(row.get("Último comentário em")))
        if url and url != "—":
            st.link_button("Abrir card no Trello ↗", url, type="primary", use_container_width=True)


# =============================================================================
# CARREGAMENTO
# =============================================================================
nonce = int(st.session_state.get("trello_nonce", 0))
try:
    snapshot = cached_snapshot(nonce)
except TrelloError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(f"Não foi possível carregar o Trello: {exc}")
    st.stop()

# A etapa do Trello é contexto, mas não decide sozinha a fila operacional.
# Comentários/atividades mais recentes podem mostrar que ainda falta informação.
# Ex.: um card em PARA ELABORAR ORÇAMENTO com "no aguardo das informações
# @gustavo" continua em Cobrar Engenharia.
trust_ready = False
result = analyze_snapshot(snapshot, trust_trello_ready_list=False)
df_all = result.rows.copy()
states = load_review_states()
df_all = apply_review_states(df_all, states)


# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.markdown(
        '<div class="ap-logo-wrap"><div class="ap-logo">APROAR</div><div class="ap-logo-sub">ENGENHARIA</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ap-side-section">Orçamentos</div>', unsafe_allow_html=True)
    module = st.radio(
        "Navegação",
        ["🏠  Radar", "📋  Fluxo geral"],
        label_visibility="collapsed",
    )
    st.markdown('<div class="ap-side-section">Sistema</div>', unsafe_allow_html=True)
    st.toggle("🌙 Modo escuro", key="dark_mode")
    db_status = "conectado" if db_available() else "indisponível"
    st.markdown(
        f'<div class="ap-side-foot">Trello lido em {escape(str(snapshot.get("_fetched_at", "—")))}<br>Neon {db_status}<br><br>Central de Orçamentos</div>',
        unsafe_allow_html=True,
    )


# =============================================================================
# RADAR PRINCIPAL
# =============================================================================
if module.startswith("🏠"):
    title_col, actor_col = st.columns([5.5, 1.6])
    with title_col:
        st.markdown(
            '<div class="ap-page-head"><div><h1 class="ap-title">Radar de levantamentos</h1>'
            '<div class="ap-sub">O que precisa ser cobrado, o que voltou para revisão e o que já pode ser elaborado.</div></div></div>',
            unsafe_allow_html=True,
        )
    with actor_col:
        actor = st.selectbox("Operador", ["Laisa", "Simeone", "César"], label_visibility="visible")

    # filtros em um único bloco, como no padrão visual de referência
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns([1.5, 1.45, 1.15, .9])
        radar_df = df_all[df_all["Fila"].isin(["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar"])].copy()
        eng_opts = ["Todos"] + sorted([x for x in radar_df.get("Engenharia", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
        stage_opts = ["Todas"] + sorted([x for x in radar_df.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
        with f1:
            filtro_eng = st.selectbox("Engenharia", eng_opts)
        with f2:
            filtro_stage = st.selectbox("Etapa Trello", stage_opts)
        with f3:
            filtro_prazo = st.selectbox("Prazo", ["Todos", "Atrasados", "Hoje", "Até 2 dias", "Sem prazo"])
        with f4:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Atualizar", type="primary", use_container_width=True):
                st.session_state.trello_nonce = int(st.session_state.get("trello_nonce", 0)) + 1
                cached_snapshot.clear()
                st.rerun()

    search_radar = st.text_input("Buscar demanda ou unidade", key="radar_search")
    st.caption("Atualize para buscar retornos novos. Prazo do orçamento vem do Trello; prazo de resposta é definido na pendência.")
    filtered = radar_df.copy()
    if search_radar.strip():
        hay = filtered["Demanda"].astype(str) + " " + filtered["Unidade"].astype(str)
        filtered = filtered[hay.str.contains(search_radar.strip(), case=False, regex=False)]
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

    counts = filtered["Fila"].value_counts() if not filtered.empty else pd.Series(dtype=int)
    st.markdown(
        f"""
        <div class="ap-kpis">
          <div class="ap-kpi"><div class="ap-kpi-label">Cobrar Engenharia</div><div class="ap-kpi-row"><div class="ap-kpi-num ap-blue">{int(counts.get('Cobrar Engenharia',0))}</div><div class="ap-kpi-text">pendências dos supervisores</div></div></div>
          <div class="ap-kpi"><div class="ap-kpi-label">Conferir retorno</div><div class="ap-kpi-row"><div class="ap-kpi-num ap-orange">{int(counts.get('Conferir retorno',0))}</div><div class="ap-kpi-text">retornos aguardando revisão</div></div></div>
          <div class="ap-kpi"><div class="ap-kpi-label">Pronto para elaborar</div><div class="ap-kpi-row"><div class="ap-kpi-num ap-green">{int(counts.get('Pronto para elaborar',0))}</div><div class="ap-kpi-text">levantamentos liberados</div></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Carga por engenheiro e pendências de resposta"):
        if not filtered.empty:
            summary = pd.crosstab(filtered["Engenharia"], filtered["Fila"])
            st.dataframe(summary, use_container_width=True)
            cols = ["Demanda", "Engenharia", "Fila", "Pendência / próxima ação", "Prazo resposta", "Situação resposta", "Última cobrança", "Responsável elaboração"]
            st.dataframe(filtered[cols], hide_index=True, use_container_width=True)
    main_col, detail_col = st.columns([1.7, 1], gap="large")

    with main_col:
        st.markdown(
            f'<div class="ap-section-head"><div><div class="ap-section-title">Precisa de atenção</div>'
            f'<div class="ap-section-sub">Escolha uma fila e trabalhe somente nela.</div></div>'
            f'<div class="ap-count">{len(filtered)} demandas</div></div>',
            unsafe_allow_html=True,
        )

        queue_options = ["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar"]
        current = st.session_state.selected_queue if st.session_state.selected_queue in queue_options else queue_options[0]
        selected_queue = st.segmented_control(
            "Fila",
            queue_options,
            default=current,
            selection_mode="single",
            label_visibility="collapsed",
            key="queue_selector",
        ) or current
        st.session_state.selected_queue = selected_queue

        qdf = filtered[filtered["Fila"] == selected_queue].copy() if not filtered.empty else pd.DataFrame()
        if not qdf.empty:
            qdf["_sort"] = pd.to_numeric(qdf.get("Dias até prazo"), errors="coerce").fillna(99999)
            qdf = qdf.sort_values("_sort", ascending=True)

        visible_ids = set(qdf["Card ID"].astype(str).tolist()) if not qdf.empty else set()
        if st.session_state.selected_card_id not in visible_ids:
            st.session_state.selected_card_id = str(qdf.iloc[0]["Card ID"]) if not qdf.empty else ""

        with st.container(height=610, border=False):
            if qdf.empty:
                st.markdown('<div class="ap-empty">Nenhuma demanda nesta fila com os filtros atuais.</div>', unsafe_allow_html=True)
            else:
                for _, row in qdf.iterrows():
                    render_compact_row(row, states.get(str(row.get("Card ID") or "")))

    with detail_col:
        st.markdown(
            '<div class="ap-section-head"><div><div class="ap-section-title">Ação da demanda</div>'
            '<div class="ap-section-sub">Confira as evidências e registre a próxima ação.</div></div></div>',
            unsafe_allow_html=True,
        )
        row = selected_row(qdf if 'qdf' in locals() else filtered, st.session_state.selected_card_id)
        with st.container(border=True):
            if row is None:
                st.markdown('<div class="ap-empty">Abra uma demanda da lista para trabalhar nela.</div>', unsafe_allow_html=True)
            else:
                render_detail(row, states.get(str(row.get("Card ID") or "")), actor, df_all)


# =============================================================================
# FLUXO GERAL — MÓDULO SECUNDÁRIO
# =============================================================================
else:
    actor = "Laisa"
    st.markdown(
        '<div class="ap-page-head"><div><h1 class="ap-title">Fluxo geral</h1>'
        '<div class="ap-sub">Solicitados, pendências de cliente, terceiros e demais etapas ficam aqui — sem poluir o Radar principal.</div></div></div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        f1, f2, f3 = st.columns([1.2, 1.2, 2])
        stages = ["Todas"] + sorted([x for x in df_all.get("Etapa Trello", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
        waits = ["Todos"] + sorted([x for x in df_all.get("Aguardando", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
        with f1:
            stage = st.selectbox("Etapa Trello", stages)
        with f2:
            wait = st.selectbox("Aguardando", waits)
        with f3:
            search = st.text_input("Buscar", placeholder="Demanda, unidade, supervisor…")

    flow_df = df_all.copy()
    if stage != "Todas":
        flow_df = flow_df[flow_df["Etapa Trello"] == stage]
    if wait != "Todos":
        flow_df = flow_df[flow_df["Aguardando"] == wait]
    if search.strip():
        q = search.strip().casefold()
        hay = (
            flow_df["Demanda"].astype(str) + " " +
            flow_df["Unidade"].astype(str) + " " +
            flow_df["Engenharia"].astype(str)
        ).str.casefold()
        flow_df = flow_df[hay.str.contains(q, regex=False)]

    st.markdown(
        f'<div class="ap-section-head"><div><div class="ap-section-title">Demandas</div>'
        f'<div class="ap-section-sub">Visão secundária do processo completo.</div></div><div class="ap-count">{len(flow_df)}</div></div>',
        unsafe_allow_html=True,
    )

    if flow_df.empty:
        st.info("Nenhuma demanda com estes filtros.")
    else:
        cols = [
            "Demanda", "Unidade", "Engenharia", "Etapa Trello",
            "Aguardando", "Situação do prazo", "Pendência / próxima ação", "URL",
        ]
        st.dataframe(flow_df[cols], use_container_width=True, hide_index=True, height=620)
