from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from dateutil import parser as dtparser

from trello_client import decode_custom_fields, find_custom_value

ENGENHEIROS = ["Gabriel", "Eduardo", "Joel", "Victor", "Neto", "Soares", "Gustavo"]
ORCAMENTOS = ["César", "Cesar", "Simeone", "Laisa"]

LISTA_PEND_CLIENTE = "SOLICITADOS PENDENCIAS CLIENTE"
LISTA_SOLICITADOS = "SOLICITADOS"
LISTA_PARA_ELABORAR = "PARA ELABORAR ORCAMENTO"
LISTA_EM_ELABORACAO = "EM ELABORACAO"
LISTA_REVISAO = "REVISAO"


@dataclass
class RadarResult:
    rows: pd.DataFrame
    queues: dict[str, pd.DataFrame]


def norm(text: Any) -> str:
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
    return re.sub(r"\s+", " ", value)


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.isoparse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fmt_date(value: Any) -> str:
    dt = parse_dt(value)
    return dt.astimezone().strftime("%d/%m/%Y") if dt else "—"


def yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return norm(value) in {"SIM", "YES", "TRUE", "1", "OK", "CONCLUIDO", "PREENCHIDO"}


def member_name_map(members: list[dict[str, Any]]) -> dict[str, str]:
    return {str(member.get("id")): str(member.get("fullName") or member.get("username") or "") for member in members}


def identify_engineer(card: dict[str, Any], custom: dict[str, Any], members_by_id: dict[str, str]) -> str:
    custom_owner = find_custom_value(custom, "engenheiro", "supervisor de obra", "responsavel levantamento", "responsável levantamento")
    if custom_owner:
        custom_text = str(custom_owner)
        for engineer in ENGENHEIROS:
            if norm(engineer) in norm(custom_text):
                return engineer
        return custom_text

    names = [members_by_id.get(str(mid), "") for mid in card.get("idMembers") or []]
    for engineer in ENGENHEIROS:
        if any(norm(engineer) in norm(name) for name in names):
            return engineer
    return ", ".join(name for name in names if name) or "Não identificado"


def identify_budget_owner(custom: dict[str, Any], card: dict[str, Any], members_by_id: dict[str, str]) -> str:
    value = find_custom_value(custom, "responsavel pela elaboracao", "responsável pela elaboração", "elaborador", "orcamentista", "orçamentista")
    if value:
        return str(value)
    names = [members_by_id.get(str(mid), "") for mid in card.get("idMembers") or []]
    selected = [name for name in names if any(norm(person) in norm(name) for person in ORCAMENTOS)]
    return ", ".join(selected) or "Não definido"


def action_card_id(action: dict[str, Any]) -> str:
    return str(((action.get("data") or {}).get("card") or {}).get("id") or "")


def index_actions(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in actions:
        cid = action_card_id(action)
        if cid:
            indexed[cid].append(action)
    for cid in indexed:
        indexed[cid].sort(key=lambda a: parse_dt(a.get("date")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return indexed


def current_list_entry(card: dict[str, Any], card_actions: list[dict[str, Any]], list_by_id: dict[str, str]) -> datetime | None:
    current_id = str(card.get("idList") or "")
    for action in card_actions:
        data = action.get("data") or {}
        after = data.get("listAfter") or {}
        if str(after.get("id") or "") == current_id:
            dt = parse_dt(action.get("date"))
            if dt:
                return dt
    return None


def latest_comment(card_actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((a for a in card_actions if str(a.get("type")) == "commentCard"), None)


def comment_author(action: dict[str, Any] | None) -> str:
    if not action:
        return ""
    creator = action.get("memberCreator") or {}
    return str(creator.get("fullName") or creator.get("username") or "")


def comment_text(action: dict[str, Any] | None) -> str:
    if not action:
        return ""
    return str(((action.get("data") or {}).get("text")) or "")


def waiting_owner(list_name: str, description: str, labels: list[dict[str, Any]], custom: dict[str, Any]) -> str:
    haystack = " ".join([list_name, description] + [str(label.get("name") or "") for label in labels] + [f"{k} {v}" for k, v in custom.items()])
    text = norm(haystack)
    if "PENDENCIA CLIENTE" in text or norm(list_name) == LISTA_PEND_CLIENTE:
        return "Cliente"
    if "FORNECEDOR" in text or "PRESTADOR" in text:
        return "Fornecedor"
    if "ESPECIALISTA" in text:
        return "Especialista"
    return "Engenharia"


def due_status(due: Any, now: datetime) -> tuple[str, int | None]:
    dt = parse_dt(due)
    if not dt:
        return "Sem prazo", None
    delta_days = (dt.astimezone().date() - now.astimezone().date()).days
    if delta_days < 0:
        return f"Atrasado {abs(delta_days)}d", delta_days
    if delta_days == 0:
        return "Vence hoje", 0
    if delta_days == 1:
        return "Vence amanhã", 1
    return f"Em {delta_days}d", delta_days


def missing_reasons(list_name: str, custom: dict[str, Any], engineer: str) -> list[str]:
    reasons: list[str] = []
    visit = find_custom_value(custom, "data da visita", "visita realizada", "data visita")
    info = find_custom_value(custom, "informacoes preenchidas", "informações preenchidas", "levantamento preenchido")

    if engineer == "Não identificado":
        reasons.append("Responsável da Engenharia não identificado")
    if not visit:
        reasons.append("Visita realizada não registrada")
    if info is not None and not yes(info):
        reasons.append("Informações ainda não marcadas como preenchidas")
    if norm(list_name) == LISTA_SOLICITADOS and info is None:
        reasons.append("Levantamento ainda sem confirmação de preenchimento")
    return reasons


def manual_review_signal(custom: dict[str, Any]) -> bool:
    # Se o board ganhar um campo específico no futuro, o painel passa a entendê-lo sem alterar IDs.
    value = find_custom_value(
        custom,
        "conferido por orcamentos",
        "conferido por orçamentos",
        "levantamento conferido",
        "aprovado orcamentos",
        "aprovado orçamentos",
        "liberado para elaborar",
    )
    return yes(value)


def analyze_snapshot(snapshot: dict[str, Any], trust_trello_ready_list: bool = False) -> RadarResult:
    now = datetime.now(timezone.utc)
    lists = snapshot.get("lists") or []
    cards = snapshot.get("cards") or []
    members = snapshot.get("members") or []
    custom_fields = snapshot.get("custom_fields") or []
    actions = snapshot.get("actions") or []

    list_by_id = {str(item.get("id")): str(item.get("name") or "") for item in lists}
    members_by_id = member_name_map(members)
    actions_by_card = index_actions(actions)

    rows: list[dict[str, Any]] = []
    for card in cards:
        list_name = list_by_id.get(str(card.get("idList")), "Lista não identificada")
        list_norm = norm(list_name)
        # O radar operacional não precisa poluir a tela com execução/concluído/medições.
        if any(term in list_norm for term in ["CONCLUID", "EM EXECUCAO", "APROVADO AGUARDANDO EXECUCAO", "MEDICAO"]):
            continue

        custom = decode_custom_fields(card, custom_fields)
        card_actions = actions_by_card.get(str(card.get("id")), [])
        engineer = identify_engineer(card, custom, members_by_id)
        budget_owner = identify_budget_owner(custom, card, members_by_id)
        owner = waiting_owner(list_name, str(card.get("desc") or ""), card.get("labels") or [], custom)
        reasons = missing_reasons(list_name, custom, engineer)
        info_value = find_custom_value(custom, "informacoes preenchidas", "informações preenchidas", "levantamento preenchido")
        info_yes = yes(info_value)
        reviewed = manual_review_signal(custom)
        latest = latest_comment(card_actions)
        latest_author = comment_author(latest)
        latest_text = comment_text(latest)
        latest_dt = parse_dt(latest.get("date")) if latest else None
        engineer_replied = bool(latest and any(norm(e) in norm(latest_author) for e in ENGENHEIROS))
        entered = current_list_entry(card, card_actions, list_by_id)
        age_days = max(0, (now - entered).days) if entered else None
        status_due, delta_due = due_status(card.get("due"), now)

        queue = "Acompanhar"
        pending = ""

        if owner != "Engenharia":
            queue = "Aguardar terceiros"
            pending = f"Aguardando {owner.lower()}"
        elif reviewed and list_norm == LISTA_PARA_ELABORAR:
            queue = "Pronto para elaborar"
            pending = "Levantamento conferido"
        elif trust_trello_ready_list and list_norm == LISTA_PARA_ELABORAR:
            queue = "Pronto para elaborar"
            pending = "Lista do Trello considerada como liberação"
        elif list_norm == LISTA_PARA_ELABORAR or info_yes or engineer_replied:
            queue = "Conferir retorno"
            pending = "Validar se o retorno/levantamento está suficiente"
        elif list_norm == LISTA_SOLICITADOS or reasons:
            queue = "Cobrar Engenharia"
            pending = "; ".join(reasons) if reasons else "Levantamento pendente"
        elif list_norm in {LISTA_EM_ELABORACAO, LISTA_REVISAO}:
            queue = "Em produção"
            pending = "Orçamento em elaboração/revisão"

        rows.append({
            "Fila": queue,
            "Demanda": str(card.get("name") or "Sem título"),
            "Etapa Trello": list_name,
            "Engenharia": engineer,
            "Pendência / próxima ação": pending,
            "Aguardando": owner,
            "Prazo": fmt_date(card.get("due")),
            "Situação do prazo": status_due,
            "Dias até prazo": delta_due,
            "Tempo na etapa (dias)": age_days,
            "Último comentário": latest_text[:180] if latest_text else "—",
            "Autor último comentário": latest_author or "—",
            "Último comentário em": latest_dt.astimezone().strftime("%d/%m %H:%M") if latest_dt else "—",
            "Responsável elaboração": budget_owner,
            "Informações preenchidas": "Sim" if info_yes else "Não/sem informação",
            "Revisão manual": "Sim" if reviewed else "Não",
            "URL": str(card.get("url") or ""),
            "Card ID": str(card.get("id") or ""),
        })

    columns = [
        "Fila", "Demanda", "Etapa Trello", "Engenharia", "Pendência / próxima ação", "Aguardando",
        "Prazo", "Situação do prazo", "Dias até prazo", "Tempo na etapa (dias)", "Último comentário",
        "Autor último comentário", "Último comentário em", "Responsável elaboração", "Informações preenchidas",
        "Revisão manual", "URL", "Card ID",
    ]
    df = pd.DataFrame(rows, columns=columns)
    if not df.empty:
        df["_prioridade_prazo"] = df["Dias até prazo"].fillna(9999)
        df = df.sort_values(["_prioridade_prazo", "Tempo na etapa (dias)"], ascending=[True, False], na_position="last").drop(columns="_prioridade_prazo")

    queues = {
        name: df[df["Fila"] == name].copy() if not df.empty else pd.DataFrame(columns=columns)
        for name in ["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar", "Aguardar terceiros", "Em produção"]
    }
    return RadarResult(rows=df, queues=queues)
