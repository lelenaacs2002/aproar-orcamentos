from __future__ import annotations

import re
import json
from zoneinfo import ZoneInfo
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd
from dateutil import parser as dtparser

from trello_client import decode_custom_fields, find_custom_value

LOCAL_TZ = ZoneInfo('America/Fortaleza')

# -----------------------------------------------------------------------------
# REGRAS OPERACIONAIS APROAR
# -----------------------------------------------------------------------------
# Gabriel acompanha a operação como supervisor geral. Ele NÃO é usado como
# responsável padrão só porque está como membro do card.
ENGENHEIROS = ["Eduardo", "Joel", "Victor", "Neto", "Soares", "Gustavo", "Gabriel"]
ORCAMENTOS = ["César", "Cesar", "Simeone", "Laisa", "Helena", "Ariana"]

RESPONSAVEL_POR_UNIDADE: list[tuple[tuple[str, ...], str, str]] = [
    (("UNIFOR",), "UNIFOR", "Joel"),
    (("HORIZONTE",), "HORIZONTE", "Soares"),
    (("COLISEU",), "COLISEU", "Joel"),
    (("MARACANAU",), "MARACANAÚ", "Neto"),
    (("BARRA DO CEARA", "BARRA DO CEARÁ"), "BARRA DO CEARÁ", "Eduardo"),
    (("MUSEU",), "MUSEU", "Victor"),
    (("CASA DA INDUSTRIA", "CASA DA INDÚSTRIA", "FIEC"), "FIEC / CASA DA INDÚSTRIA", "Gustavo"),
    # CENTRO fica depois de UNIFOR para não confundir "Centro de Convivência UNIFOR".
    (("SENAI CENTRO", "SESI CENTRO"), "CENTRO", "Victor"),
]

# Handles/nome reais vistos no quadro. Ambos os "Neto" ficam normalizados para
# o nome operacional usado pela equipe; a unidade continua sendo o principal
# critério quando não há atribuição explícita.
PESSOA_ALIASES = {
    "EDUARDOROCHA APROAR": "Eduardo",
    "EDUARDO ROCHA": "Eduardo",
    "JOELLIMA43": "Joel",
    "JOEL LIMA": "Joel",
    "VICTORBEZERRA27": "Victor",
    "VICTOR BEZERRA": "Victor",
    "SOARES JUNIOR": "Soares",
    "FRANCISCO SOARES": "Soares",
    "GUSTAVODEHOLANDASOUZA": "Gustavo",
    "GUSTAVO HOLANDA": "Gustavo",
    "FRANCISCOASSISOLIVEIRANETO": "Neto",
    "FRANCISCO ASSIS OLIVEIRA NETO": "Neto",
    "RUPERTOCAVALCANTEPORTONETO1": "Neto",
    "RUPERTO CAVALCANTE PORTO NETO": "Neto",
    "GABRIELMONTEIRO340": "Gabriel",
    "GABRIEL MONTEIRO": "Gabriel",
}

LISTA_PEND_CLIENTE = "SOLICITADOS PENDENCIAS CLIENTE"
LISTA_SOLICITADOS = "SOLICITADOS"
LISTA_PARA_ELABORAR = "PARA ELABORAR ORCAMENTO"
LISTA_EM_ELABORACAO = "EM ELABORACAO DE ORCAMENTO"
LISTA_REVISAO = "REVISAO"
LISTA_ENVIADO = "ENVIADO AO CLIENTE"
LISTA_REVISAO_CLIENTE = "REVISAO CLIENTE"

LISTAS_RADAR = {
    LISTA_PEND_CLIENTE,
    LISTA_SOLICITADOS,
    LISTA_PARA_ELABORAR,
    LISTA_EM_ELABORACAO,
    LISTA_REVISAO,
    LISTA_ENVIADO,
    LISTA_REVISAO_CLIENTE,
}


@dataclass
class RadarResult:
    rows: pd.DataFrame
    queues: dict[str, pd.DataFrame]


@dataclass
class TechRule:
    label: str
    check: Callable[[str, dict[str, Any]], bool]


# -----------------------------------------------------------------------------
# TEXTO / DATAS
# -----------------------------------------------------------------------------
def norm(text: Any) -> str:
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
    return re.sub(r"\s+", " ", value)


def flat(text: Any) -> str:
    """Maiúsculo, sem acento, mas preserva pontuação/unidades para regex."""
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", value.upper()).strip()


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = value if isinstance(value, datetime) else dtparser.isoparse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fmt_date(value: Any) -> str:
    dt = parse_dt(value)
    return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y") if dt else "—"


def yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return norm(value) in {"SIM", "YES", "TRUE", "1", "OK", "CONCLUIDO", "PREENCHIDO"}


def member_name_map(members: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(member.get("id")): str(member.get("fullName") or member.get("username") or "")
        for member in members
    }


def alias_to_engineer(value: Any) -> str | None:
    text = norm(value)
    if not text:
        return None
    for alias, engineer in PESSOA_ALIASES.items():
        if norm(alias) in text:
            return engineer
    for engineer in ENGENHEIROS:
        if norm(engineer) in text:
            return engineer
    return None


# -----------------------------------------------------------------------------
# AÇÕES / COMENTÁRIOS
# -----------------------------------------------------------------------------
def action_card_id(action: dict[str, Any]) -> str:
    return str(((action.get("data") or {}).get("card") or {}).get("id") or "")


def index_actions(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in actions:
        cid = action_card_id(action)
        if cid:
            indexed[cid].append(action)
    for cid in indexed:
        indexed[cid].sort(
            key=lambda a: parse_dt(a.get("date")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
    return indexed


def comment_actions(card_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in card_actions if str(a.get("type")) == "commentCard"]


def comment_author(action: dict[str, Any] | None) -> str:
    if not action:
        return ""
    creator = action.get("memberCreator") or {}
    return str(creator.get("fullName") or creator.get("username") or "")


def comment_text(action: dict[str, Any] | None) -> str:
    if not action:
        return ""
    return str(((action.get("data") or {}).get("text")) or "")


def comment_date(action: dict[str, Any] | None) -> datetime | None:
    return parse_dt(action.get("date")) if action else None


def current_list_entry(card: dict[str, Any], card_actions: list[dict[str, Any]]) -> datetime | None:
    current_id = str(card.get("idList") or "")
    for action in card_actions:
        after = (action.get("data") or {}).get("listAfter") or {}
        if str(after.get("id") or "") == current_id:
            dt = parse_dt(action.get("date"))
            if dt:
                return dt
    return None


def engineer_from_comment_author(action: dict[str, Any]) -> str | None:
    creator = action.get("memberCreator") or {}
    full = str(creator.get("fullName") or "")
    username = str(creator.get("username") or "")
    return alias_to_engineer(f"{full} {username}")


def is_office_author(action: dict[str, Any]) -> bool:
    author = norm(comment_author(action))
    return any(norm(person) in author for person in ORCAMENTOS)


def mentioned_engineers(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    source = norm(text)
    for alias, engineer in PESSOA_ALIASES.items():
        pos = source.find(norm(alias))
        if pos >= 0:
            found.append((pos, engineer))
    # também cobre @victor, @eduardo etc.
    for engineer in ENGENHEIROS:
        pos = source.find(norm(engineer))
        if pos >= 0:
            found.append((pos, engineer))
    result: list[str] = []
    for _, name in sorted(found, key=lambda x: x[0]):
        if name not in result:
            result.append(name)
    return result


ASSIGNMENT_WORDS = {
    "MARCAR", "VISITA", "LEVANTAMENTO", "ORCAR", "ORCAMENTO", "VERIFICAR",
    "EXPLICAR", "INFORMAR", "ENVIAR", "COBRAR", "REALIZAR", "CONFERIR",
    "COMPLEMENTAR", "ACRESCENTAR", "CORRIGIR", "ANEXAR", "COTACAO",
    # Palavras muito usadas nos comentários reais quando Orçamentos devolve um
    # card para o supervisor. Elas também ajudam a detectar a atribuição correta.
    "SOLICITADO", "SOLICITADA", "SOLICITAR", "AGUARDO", "AGUARDANDO",
    "PENDENTE", "PENDENCIA", "ADEQUACAO", "AJUSTE", "AJUSTAR",
}

REQUEST_SIGNAL_WORDS = ASSIGNMENT_WORDS | {
    "PRECISO", "PRECISAMOS", "FALTA", "FALTAM", "INFORMACOES",
}


def explicit_assignment(card_actions: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Atribuição explícita em comentário vence a regra da unidade."""
    for action in comment_actions(card_actions):
        if not is_office_author(action):
            continue
        text = comment_text(action)
        text_norm = norm(text)
        mentions = mentioned_engineers(text)
        if not mentions:
            continue
        if any(word in text_norm for word in ASSIGNMENT_WORDS):
            return mentions[0], text
    return None, None


# -----------------------------------------------------------------------------
# UNIDADE / RESPONSABILIDADE
# -----------------------------------------------------------------------------
def identify_unit(card: dict[str, Any]) -> tuple[str, str | None]:
    haystack = f" {norm(card.get('name'))} {norm(card.get('desc'))} "
    for aliases, display, engineer in RESPONSAVEL_POR_UNIDADE:
        for alias in aliases:
            needle = f" {norm(alias)} "
            if needle in haystack:
                return display, engineer
    return "NÃO MAPEADA", None


def identify_engineer(
    card: dict[str, Any],
    custom: dict[str, Any],
    card_actions: list[dict[str, Any]],
    members_by_id: dict[str, str],
) -> tuple[str, str]:
    # 1) Campo dedicado, se um dia for criado no board.
    custom_owner = find_custom_value(
        custom,
        "engenheiro",
        "supervisor de obra",
        "responsavel levantamento",
        "responsável levantamento",
    )
    if custom_owner:
        identified = alias_to_engineer(custom_owner)
        if identified:
            return identified, "Campo do Trello"

    # 2) Atribuição explícita em comentário.
    assigned, _ = explicit_assignment(card_actions)
    if assigned:
        return assigned, "Atribuição explícita"

    # 3) Regra fixa da unidade informada pela operação.
    _, unit_owner = identify_unit(card)
    if unit_owner:
        return unit_owner, "Responsável da unidade"

    # 4) Se unidade não estiver mapeada, usa autor de retorno técnico recente.
    for action in comment_actions(card_actions):
        engineer = engineer_from_comment_author(action)
        if engineer and engineer != "Gabriel":
            return engineer, "Autor de retorno"

    # 5) Fallback de membros, MAS nunca transforma Gabriel em responsável só
    # porque ele acompanha praticamente todo o quadro.
    names = [members_by_id.get(str(mid), "") for mid in card.get("idMembers") or []]
    for name in names:
        engineer = alias_to_engineer(name)
        if engineer and engineer != "Gabriel":
            return engineer, "Membro do card (fallback)"

    return "Não identificado", "Sem responsável detectável"


def identify_budget_owner(custom: dict[str, Any], card: dict[str, Any], members_by_id: dict[str, str]) -> str:
    value = find_custom_value(
        custom,
        "responsavel pela elaboracao",
        "responsável pela elaboração",
        "resp elaboracao",
        "resp. elaboracao",
        "elaborador",
        "orcamentista",
        "orçamentista",
    )
    if value:
        return str(value)
    names = [members_by_id.get(str(mid), "") for mid in card.get("idMembers") or []]
    selected = [name for name in names if any(norm(person) in norm(name) for person in ["César", "Simeone", "Laisa"])]
    return ", ".join(selected) or "Não definido"


# -----------------------------------------------------------------------------
# SINAIS DE RETORNO / COBRANÇA
# -----------------------------------------------------------------------------
ATTACHMENT_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def strip_attachment_markup(text: str) -> str:
    text = ATTACHMENT_RE.sub("", str(text or ""))
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def is_generic_visit_request(text: str) -> bool:
    t = norm(text)
    return "MARCAR O DIA E REALIZAR A VISITA" in t and "LEVANTAMENTO DO ESCOPO" in t


def engineer_comments(card_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in comment_actions(card_actions) if engineer_from_comment_author(a)]


def office_requests_to_engineer(card_actions: list[dict[str, Any]], engineer: str) -> list[dict[str, Any]]:
    """
    Retorna cobranças/devoluções feitas por Orçamentos para Engenharia.

    Importante: no quadro real nem toda cobrança vem em forma de pergunta.
    Comentários como "No aguardo das informações @gustavo" ou
    "foi solicitada uma adequação do escopo" também deixam a demanda
    pendente, mesmo se o card estiver em PARA ELABORAR ORÇAMENTO.
    """
    output: list[dict[str, Any]] = []
    for action in comment_actions(card_actions):
        if not is_office_author(action) and "GABRIEL" not in norm(comment_author(action)):
            continue
        text = comment_text(action)
        mentions = mentioned_engineers(text)
        if engineer != "Não identificado" and mentions and engineer not in mentions:
            continue
        t = norm(text)
        has_request_signal = any(word in t for word in REQUEST_SIGNAL_WORDS)
        waiting_for_engineering = (
            any(x in t for x in [
                "NO AGUARDO DAS INFORMACOES",
                "AGUARDANDO INFORMACOES",
                "AGUARDANDO AS INFORMACOES",
                "AGUARDO DAS INFORMACOES",
                "ADEQUACAO DO ESCOPO",
                "AJUSTE DO ESCOPO",
            ])
            and (bool(mentions) or engineer != "Não identificado")
        )
        looks_like_request = (bool(mentions) and has_request_signal) or waiting_for_engineering or "?" in text
        if looks_like_request:
            output.append(action)
    return output


def comments_after(actions: list[dict[str, Any]], moment: datetime | None) -> list[dict[str, Any]]:
    if not moment:
        return actions
    return [a for a in actions if (comment_date(a) or datetime.min.replace(tzinfo=timezone.utc)) > moment]


def latest_engineer_response(card_actions: list[dict[str, Any]], engineer: str) -> dict[str, Any] | None:
    for action in engineer_comments(card_actions):
        who = engineer_from_comment_author(action)
        if engineer == "Não identificado" or who == engineer:
            return action
    return None


def office_ready_signal(card_actions: list[dict[str, Any]]) -> tuple[str | None, datetime | None]:
    """Detecta uma liberação explícita feita pelo setor de Orçamentos."""
    ready_phrases = [
        "LEVANTAMENTO CONFERIDO",
        "INFORMACOES SUFICIENTES",
        "INFORMACAO SUFICIENTE",
        "LIBERADO PARA ELABORACAO",
        "LIBERADA PARA ELABORACAO",
        "PODE ELABORAR",
        "PODE SEGUIR PARA ELABORACAO",
        "PODE PROSSEGUIR COM O ORCAMENTO",
        "OK PARA ELABORAR",
    ]
    for action in comment_actions(card_actions):
        if not is_office_author(action):
            continue
        text = strip_attachment_markup(comment_text(action))
        t = norm(text)
        if re.search(r'\b(NAO|AINDA|SE|QUANDO|APOS|FALTA|PENDENTE)\b', t):
            continue
        if any(phrase in t for phrase in ready_phrases):
            return text[:280], comment_date(action)
    return None, None


# -----------------------------------------------------------------------------
# CONFERÊNCIA DE PERGUNTAS OBJETIVAS
# -----------------------------------------------------------------------------
def has_number_with_unit(text: str) -> bool:
    t = flat(text)
    return bool(re.search(r"\b\d+(?:[\.,]\d+)?\s*(?:M2|M²|M\b|CM\b|MM\b|METROS?|CENTIMETROS?|MILIMETROS?)", t))


def has_area(text: str) -> bool:
    t = flat(text)
    return bool(
        re.search(r"\b\d+(?:[\.,]\d+)?\s*(?:M2|M²|METROS? QUADRADOS?)\b", t)
        or re.search(r"\b(?:AREA|ÁREA)\b.{0,30}\d", t)
        or re.search(r"\d+(?:[\.,]\d+)?\s*[Xx]\s*\d+(?:[\.,]\d+)?", t)
    )


def has_height(text: str) -> bool:
    t = flat(text)
    return bool(
        re.search(r"ALTURA.{0,25}\d+(?:[\.,]\d+)?\s*(?:M|CM|MM|METRO)", t)
        or re.search(r"\bH\s*[=:]?\s*\d+(?:[\.,]\d+)?\s*M\b", t)
        or ("ANDAIME" in t or "PLATAFORMA" in t) and has_number_with_unit(t)
    )


def has_quantity(text: str) -> bool:
    t = flat(text)
    return bool(
        re.search(r"\b(?:TOTAL|QTD|QUANTIDADE)\b.{0,20}\d+", t)
        or re.search(
            r"\b\d+\s*(?:UN|UND|UNID|UNIDADE|UNIDADES|PECAS?|PORTAS?|POSTES?|LUMINARIAS?|PLACAS?|TAMPAS?|PONTOS?|SENSORES?|REGISTROS?|JANELAS?)\b",
            t,
        )
    )


def has_finish(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in ["FOSCO", "ACETINADO", "SEMI BRILHO", "SEMIBRILHO", "BRILHANTE", "ALTO BRILHO", "TEXTURIZADO"])


def has_paint_type_or_color(text: str) -> bool:
    t = norm(text)
    words = [
        "TINTA", "ACRILICA", "PVA", "EPOXI", "ESMALTE", "COR ", "BRANCO", "BRANCA",
        "AZUL", "CINZA", "PRETO", "PRETA", "VERDE", "AMARELO", "BEGE", "OCEANO",
    ]
    return any(x in t for x in words)


def has_preparation(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in [
        "LIX", "EMASS", "RASP", "ESCARIFIC", "SELADOR", "FUNDO PREPARADOR", "LIMPEZA",
        "REMOCAO", "DEMOL", "REBOCO", "REGULARIZ", "PREPARACAO", "TRATAMENTO",
    ])


def has_material(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in [
        "ALUMINIO", "ACO", "FERRO", "INOX", "VIDRO", "GRANITO", "MARMORE", "ACRILICO",
        "CERAMIC", "PORCELANATO", "DRYWALL", "GESSO", "CONCRETO", "ARGAMASSA", "TINTA",
        "TELHA", "MADEIRA", "PVC", "BORRACHA", "RESINA", "PERFIL", "CHAPA", "PASTILHA",
    ])


def has_model_spec(text: str) -> bool:
    t = norm(text)
    return has_material(t) or any(x in t for x in [
        "MODELO", "MARCA", "REFERENCIA", "ESPECIFICACAO", "DIAMETRO", "BITOLA", "ESPESSURA",
        "POTENCIA", "TENSAO", "VOLTAGEM", "COR ", "TIPO ", "DIMENSAO",
    ])


def has_shutdown(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in ["DESATIV", "DESLIG", "ENERGIA", "QUADRO", "INTERDICAO", "BLOQUEIO ELETRICO"])


def has_access(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in ["ANDAIME", "PLATAFORMA", "ESCADA", "ACESSO", "ALTURA", "NR 35", "TRABALHO EM ALTURA"])


def has_dimensions(text: str) -> bool:
    t = flat(text)
    return has_number_with_unit(t) or bool(re.search(r"\d+(?:[\.,]\d+)?\s*[Xx]\s*\d+(?:[\.,]\d+)?", t))


def has_thickness(text: str) -> bool:
    t = flat(text)
    return bool(
        re.search(r"ESPESSURA.{0,20}\d+(?:[\.,]\d+)?\s*(?:MM|CM|M)", t)
        or re.search(r"CAMADA.{0,20}\d+(?:[\.,]\d+)?\s*(?:MM|CM)", t)
        or re.search(r"\b\d+(?:[\.,]\d+)?\s*(?:MM|CM)\b", t)
    )


def has_diagnosis(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in [
        "ORIGEM", "CAUSA", "DIAGNOST", "INFILTR", "VAZAMENTO", "UMIDADE", "TRINCA", "FISSURA",
        "CORROSAO", "AFUND", "SOLT", "DANIFIC", "OXID", "DESPLAC",
    ])


def has_solution(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in [
        "RETIR", "REMOV", "SUBSTIT", "INSTAL", "RECOMP", "EXECUT", "APLIC", "PINT",
        "IMPERMEABIL", "REGULARIZ", "TRAT", "FIX", "SOLD", "REPAR", "COMPACT", "ATERRO",
        "DESATIV", "REINSTAL", "CONFECC", "FORNEC", "MONT",
    ])


def explicit_unknown(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in ["A CONFIRMAR", "NAO DEFINIDO", "NAO DEFINIDA", "AGUARDANDO INFORMACAO", "DEPENDE DO CLIENTE", "PRECISA CONFIRMAR"])


REQUEST_CHECKS: list[tuple[tuple[str, ...], str, Callable[[str], bool]]] = [
    (("ACABAMENTO",), "Acabamento", lambda x: has_finish(x) or explicit_unknown(x)),
    (("ALTURA",), "Altura", lambda x: has_height(x) or explicit_unknown(x)),
    (("AREA", "METROS QUADRADOS"), "Área", lambda x: has_area(x) or explicit_unknown(x)),
    (("MEDIDA", "DIMENSAO", "DIMENSOES", "COMPRIMENTO", "LARGURA"), "Medidas/dimensões", lambda x: has_dimensions(x) or explicit_unknown(x)),
    (("QUANTIDADE", "QTD", "QUANTOS", "QUANTAS"), "Quantidade", lambda x: has_quantity(x) or explicit_unknown(x)),
    (("ESPESSURA",), "Espessura", lambda x: has_thickness(x) or explicit_unknown(x)),
    (("QUAL COR", "COR DA TINTA", "COR DO MATERIAL"), "Cor", lambda x: has_paint_type_or_color(x) or explicit_unknown(x)),
    (("TIPO DE TINTA", "QUAL TINTA", "ESPECIFICACAO DA TINTA"), "Tipo de tinta", lambda x: has_paint_type_or_color(x) or explicit_unknown(x)),
    (("MATERIAL", "ESPECIFICACAO", "MODELO", "REFERENCIA"), "Material/especificação", lambda x: has_model_spec(x) or explicit_unknown(x)),
    (("ANDAIME", "ACESSO", "PLATAFORMA"), "Condição de acesso", lambda x: has_access(x) or explicit_unknown(x)),
]


def requested_fields(question: str) -> list[tuple[str, Callable[[str], bool]]]:
    q = f" {norm(question)} "
    found: list[tuple[str, Callable[[str], bool]]] = []
    for needles, label, check in REQUEST_CHECKS:
        if any(norm(n) in q for n in needles):
            if label not in [x[0] for x in found]:
                found.append((label, check))
    return found


def unresolved_specific_request(card_actions: list[dict[str, Any]], engineer: str) -> tuple[str | None, list[str], datetime | None]:
    """
    Procura a cobrança objetiva mais recente e confere se a resposta posterior
    realmente contém o dado perguntado. Ex.: pergunta 'qual o acabamento?' e
    resposta 'emassamento, lixamento e pintura' continua pendente.
    """
    requests = office_requests_to_engineer(card_actions, engineer)
    eng_comments = engineer_comments(card_actions)
    for request in requests:
        q_text = strip_attachment_markup(comment_text(request))
        q_dt = comment_date(request)
        fields = requested_fields(q_text)
        subsequent = comments_after(eng_comments, q_dt)
        if engineer != "Não identificado":
            subsequent = [a for a in subsequent if engineer_from_comment_author(a) == engineer]

        if not subsequent:
            if is_generic_visit_request(q_text):
                return "Agendar/realizar a visita e preencher o levantamento", ["Visita/levantamento ainda sem retorno"], q_dt
            qt = norm(q_text)
            if "ADEQUACAO DO ESCOPO" in qt or "AJUSTE DO ESCOPO" in qt:
                return "Informar a adequação/ajuste de escopo solicitado", ["Adequação do escopo"], q_dt
            if any(x in qt for x in ["NO AGUARDO DAS INFORMACOES", "AGUARDANDO INFORMACOES", "AGUARDO DAS INFORMACOES"]):
                return "Enviar as informações solicitadas pelo setor de Orçamentos", ["Informações solicitadas"], q_dt
            return q_text[:280] or "Responder a solicitação do setor de Orçamentos", [], q_dt

        answer_text = " \n ".join(comment_text(a) for a in subsequent)
        missing = [label for label, check in fields if not check(answer_text)]
        if fields and missing:
            return f"Resposta recebida, mas ainda não informa: {', '.join(missing)}", missing, q_dt
        # Se era cobrança genérica e houve retorno, deixa a avaliação técnica geral decidir.
        if fields:
            return None, [], q_dt
    return None, [], None


# -----------------------------------------------------------------------------
# SINAIS DE TERCEIROS
# -----------------------------------------------------------------------------
def third_party_signal(card_actions: list[dict[str, Any]]) -> tuple[str | None, str | None, datetime | None]:
    """Só considera 'aguardando terceiro' quando já existe sinal de que a ação foi disparada."""
    for action in comment_actions(card_actions):
        text = norm(comment_text(action))
        author_eng = engineer_from_comment_author(action)

        supplier_wait = any(x in text for x in [
            "AGUARDANDO ORCAMENTO DO FORNECEDOR", "AGUARDANDO ORCAMENTO FORNECEDOR",
            "AGUARDANDO COTACAO", "AGUARDANDO RETORNO DO FORNECEDOR", "AGUARDANDO FORNECEDOR",
            "VISITA DO FORNECEDOR", "FORNECEDOR FOI VERIFICAR", "FORNECEDOR JA FOI",
        ])
        if supplier_wait and author_eng:
            return "Fornecedor", strip_attachment_markup(comment_text(action))[:260], comment_date(action)

        client_wait = any(x in text for x in [
            "AGUARDANDO CLIENTE", "AGUARDANDO RETORNO DO CLIENTE", "PENDENTE CLIENTE",
            "CLIENTE VAI CONFIRMAR", "CLIENTE IRA CONFIRMAR",
        ])
        if client_wait:
            return "Cliente", strip_attachment_markup(comment_text(action))[:260], comment_date(action)

        specialist_wait = any(x in text for x in [
            "AGUARDANDO ESPECIALISTA", "AGUARDANDO PROJETO", "AGUARDANDO PROJETISTA",
            "AGUARDANDO ENGENHEIRO ELETRICO", "AGUARDANDO ESTRUTURAL",
        ])
        if specialist_wait:
            return "Especialista", strip_attachment_markup(comment_text(action))[:260], comment_date(action)
    return None, None, None


# -----------------------------------------------------------------------------
# REGRAS TÉCNICAS POR SERVIÇO
# -----------------------------------------------------------------------------
def detect_service_type(card: dict[str, Any], technical_text: str) -> str:
    title = norm(card.get("name"))
    full = norm(f"{card.get('name','')} {card.get('desc','')} {technical_text}")

    def has_word(word: str) -> bool:
        return bool(re.search(rf"\b{re.escape(norm(word))}\b", full))

    if has_word("GARANTIA"):
        return "Garantia"
    if any(x in full for x in ["INFILTR", "VAZAMENTO", "IMPERMEABIL"]):
        return "Infiltração / impermeabilização"
    if any(x in full for x in ["PINTURA", "PINTAR", "EMASSAMENTO", "LIXAMENTO"]):
        return "Pintura"
    if any(x in full for x in ["SOLEIRA", "RODAPE"]):
        return "Soleira / rodapé"
    if any(x in full for x in ["CERAMIC", "PISO", "REVESTIMENTO", "PORCELANATO"]):
        return "Piso / revestimento"
    if has_word("PORTA") or has_word("PORTAS") or any(x in full for x in ["VIDRO", "JANELA", "ESQUADRIA", "CILINDRO"]):
        return "Porta / vidro / esquadria"
    if any(x in full for x in ["GRADIL", "PORTAO", "GRADE METAL", "ESTRUTURA METAL", "SOLD"]):
        return "Serralheria / gradil / portão"
    if any(x in full for x in ["POSTE", "LUMINARIA", "ELETRIC", "ILUMINACAO", "FIBRA", "CABEAMENTO"]):
        return "Elétrica / iluminação"
    if any(x in full for x in ["DRYWALL", "DRY WALL", "FORRO", "GESSO"]):
        return "Drywall / forro"
    if any(x in full for x in ["ARMADURA", "REBOCO", "CONCRETO", "ARGAMASSA ESTRUTURAL", "LAJE"]):
        return "Concreto / reboco / armadura"
    if any(x in full for x in ["COBERTURA", "COBERTA", "TELHA"]):
        return "Cobertura"
    if "ACRILICO" in full:
        return "Acrílico"
    if any(x in full for x in ["MARMORE", "MARMORARIA", "GRANITO", "BANCADA"]):
        return "Marmoraria"
    if any(x in full for x in ["SENSOR", "BEBEDOURO", "EQUIPAMENTO"]):
        return "Equipamento"
    return "Outros"


def attachment_names(card: dict[str, Any]) -> str:
    return " ".join(str(a.get("name") or a.get("fileName") or "") for a in card.get("attachments") or [])


def tech_rules(service: str, card: dict[str, Any]) -> list[TechRule]:
    always_unknown_ok = lambda check: (lambda text, c: check(text) or explicit_unknown(text))
    has_attachment = lambda text, c: bool(c.get("attachments")) or "ANEX" in norm(text)

    if service == "Pintura":
        return [
            TechRule("Área/dimensões da pintura", always_unknown_ok(has_area)),
            TechRule("Altura/condição de acesso", lambda t, c: has_height(t) or has_access(t) or explicit_unknown(t)),
            TechRule("Preparação da superfície", always_unknown_ok(has_preparation)),
            TechRule("Tipo/cor da tinta", always_unknown_ok(has_paint_type_or_color)),
            TechRule("Acabamento da tinta", always_unknown_ok(has_finish)),
        ]
    if service == "Infiltração / impermeabilização":
        return [
            TechRule("Origem/diagnóstico do problema", always_unknown_ok(has_diagnosis)),
            TechRule("Área/dimensões afetadas", lambda t, c: has_area(t) or has_dimensions(t) or explicit_unknown(t)),
            TechRule("Solução/sistema previsto", always_unknown_ok(has_solution)),
            TechRule("Remoções e recomposições necessárias", lambda t, c: has_preparation(t) or "RECOMP" in norm(t) or explicit_unknown(t)),
        ]
    if service == "Soleira / rodapé":
        return [
            TechRule("Comprimento/quantidade", lambda t, c: has_dimensions(t) or has_quantity(t) or explicit_unknown(t)),
            TechRule("Material/padrão", always_unknown_ok(has_material)),
            TechRule("Dimensões/seção da peça", always_unknown_ok(has_dimensions)),
            TechRule("Condição da base/remoção existente", lambda t, c: has_preparation(t) or "BASE" in norm(t) or explicit_unknown(t)),
        ]
    if service == "Piso / revestimento":
        return [
            TechRule("Área/quantidade", lambda t, c: has_area(t) or has_quantity(t) or explicit_unknown(t)),
            TechRule("Tipo/dimensão do revestimento", lambda t, c: has_material(t) and (has_dimensions(t) or "TIPO" in norm(t)) or explicit_unknown(t)),
            TechRule("Base/preparo", lambda t, c: has_preparation(t) or "CONTRAPISO" in norm(t) or "BASE" in norm(t) or explicit_unknown(t)),
            TechRule("Remoção/recomposição", lambda t, c: any(x in norm(t) for x in ["REMOV", "RETIR", "RECOMP", "MANTER EXISTENTE", "SEM REMOCAO"]) or explicit_unknown(t)),
        ]
    if service == "Porta / vidro / esquadria":
        return [
            TechRule("Quantidade de peças", lambda t, c: has_quantity(t) or explicit_unknown(t)),
            TechRule("Medidas", always_unknown_ok(has_dimensions)),
            TechRule("Material/modelo/especificação", always_unknown_ok(has_model_spec)),
            TechRule("Ferragens/acessórios/reaproveitamento", lambda t, c: any(x in norm(t) for x in ["FERRAGEM", "DOBRAD", "PUXADOR", "FECHADURA", "CILINDRO", "ROLDANA", "TRILHO", "REAPROVEIT", "ACESSORIO"]) or explicit_unknown(t)),
        ]
    if service == "Serralheria / gradil / portão":
        return [
            TechRule("Comprimento/quantidade", lambda t, c: has_dimensions(t) or has_quantity(t) or explicit_unknown(t)),
            TechRule("Altura/dimensões", always_unknown_ok(has_dimensions)),
            TechRule("Material/perfil", always_unknown_ok(has_model_spec)),
            TechRule("Fixação/remoção/reinstalação", lambda t, c: any(x in norm(t) for x in ["FIX", "REMOV", "RETIR", "REINSTAL", "SOLD", "CHUMB", "PARAFUS"]) or explicit_unknown(t)),
            TechRule("Acabamento/proteção", lambda t, c: has_finish(t) or any(x in norm(t) for x in ["PINT", "GALVAN", "ANTICORROS", "FUNDO"]) or explicit_unknown(t)),
        ]
    if service == "Elétrica / iluminação":
        rules = [
            TechRule("Quantidade", lambda t, c: has_quantity(t) or explicit_unknown(t)),
            TechRule("Especificação dos equipamentos/materiais", always_unknown_ok(has_model_spec)),
            TechRule("Desligamento/desativação", always_unknown_ok(has_shutdown)),
            TechRule("Interferências/dependências", lambda t, c: any(x in norm(t) for x in ["FIBRA", "INTERFER", "DEPEND", "OUTRA REDE", "ENERGIA", "ALIMENTA"]) or explicit_unknown(t)),
        ]
        if any(x in norm(card.get("name")) for x in ["POSTE", "LUMINARIA"]):
            rules.insert(2, TechRule("Altura/condição de acesso", lambda t, c: has_height(t) or has_access(t) or explicit_unknown(t)))
        if "POSTE" in norm(f"{card.get('name')} {card.get('desc')}") and any(x in norm(f"{card.get('desc')} {attachment_names(card)}") for x in ["SUBSTIT", "NOVO POSTE"]):
            rules.append(TechRule("Especificação do poste substituto", lambda t, c: "POSTE" in norm(t) and has_model_spec(t) and has_dimensions(t) or explicit_unknown(t)))
        return rules
    if service == "Drywall / forro":
        return [
            TechRule("Área/dimensões", lambda t, c: has_area(t) or has_dimensions(t) or explicit_unknown(t)),
            TechRule("Tipo/material da placa", always_unknown_ok(has_model_spec)),
            TechRule("Estrutura/perfis", lambda t, c: any(x in norm(t) for x in ["PERFIL", "MONTANTE", "GUIA", "ESTRUTURA"]) or explicit_unknown(t)),
            TechRule("Acabamento", lambda t, c: any(x in norm(t) for x in ["MASSA", "FITA", "PINT", "ACABAMENTO"]) or explicit_unknown(t)),
            TechRule("Interferências", lambda t, c: any(x in norm(t) for x in ["ELETR", "AR COND", "SPRINKLER", "LUMINARIA", "INTERFER", "SEM INTERFERENCIA"]) or explicit_unknown(t)),
        ]
    if service == "Concreto / reboco / armadura":
        return [
            TechRule("Área/dimensões", lambda t, c: has_area(t) or has_dimensions(t) or explicit_unknown(t)),
            TechRule("Espessura/profundidade", always_unknown_ok(has_thickness)),
            TechRule("Remoção/preparo", always_unknown_ok(has_preparation)),
            TechRule("Tratamento/material de recomposição", lambda t, c: has_material(t) or "TRAT" in norm(t) or "RECOMP" in norm(t) or explicit_unknown(t)),
            TechRule("Acabamento final", lambda t, c: has_finish(t) or any(x in norm(t) for x in ["PINT", "CERAMIC", "REVEST", "ACABAMENTO"]) or explicit_unknown(t)),
        ]
    if service == "Cobertura":
        return [
            TechRule("Área/dimensões", lambda t, c: has_area(t) or has_dimensions(t) or explicit_unknown(t)),
            TechRule("Sistema/material", always_unknown_ok(has_model_spec)),
            TechRule("Estrutura/fixação", lambda t, c: any(x in norm(t) for x in ["ESTRUTURA", "PERFIL", "VIGA", "PILAR", "FIX", "CHUMB", "PARAFUS"]) or explicit_unknown(t)),
            TechRule("Projeto/anexo de referência", has_attachment),
        ]
    if service == "Acrílico":
        return [
            TechRule("Quantidade", lambda t, c: has_quantity(t) or explicit_unknown(t)),
            TechRule("Medidas", always_unknown_ok(has_dimensions)),
            TechRule("Espessura", always_unknown_ok(has_thickness)),
            TechRule("Tipo/cor/transparência", lambda t, c: any(x in norm(t) for x in ["TRANSPAREN", "CRISTAL", "FUME", "LEITOSO", "COLORIDO", "COR "]) or explicit_unknown(t)),
        ]
    if service == "Marmoraria":
        return [
            TechRule("Quantidade/peças", lambda t, c: has_quantity(t) or explicit_unknown(t)),
            TechRule("Medidas", always_unknown_ok(has_dimensions)),
            TechRule("Material/padrão", always_unknown_ok(has_material)),
            TechRule("Acabamento", lambda t, c: any(x in norm(t) for x in ["POLID", "LEVIG", "BOLEAD", "ACABAMENTO", "BRILHO"]) or explicit_unknown(t)),
            TechRule("Instalação/remoção", lambda t, c: any(x in norm(t) for x in ["INSTAL", "REMOV", "RETIR", "FIX", "COLA"]) or explicit_unknown(t)),
        ]
    if service == "Equipamento":
        return [
            TechRule("Quantidade", lambda t, c: has_quantity(t) or explicit_unknown(t)),
            TechRule("Modelo/especificação", always_unknown_ok(has_model_spec)),
            TechRule("Local/ponto de instalação", lambda t, c: any(x in norm(t) for x in ["LOCAL", "TERREO", "SALA", "PORTARIA", "PONTO", "ACADEMIA"]) or explicit_unknown(t)),
            TechRule("Condição de instalação/alimentação", lambda t, c: any(x in norm(t) for x in ["INSTAL", "ALIMENT", "TOMADA", "TENSAO", "ENERGIA", "FIX"]) or explicit_unknown(t)),
        ]
    if service == "Garantia":
        return [
            TechRule("Referência do serviço/orçamento anterior", lambda t, c: any(x in norm(t) for x in ["OBRA ", "PIPE", "ORCAMENTO ANTERIOR", "SERVICO ANTERIOR"]) or explicit_unknown(t)),
            TechRule("Fornecedor/responsável pela garantia", lambda t, c: any(x in norm(t) for x in ["FORNECEDOR", "PRESTADOR", "GARANTIA COM", "RESPONSAVEL"]) or explicit_unknown(t)),
            TechRule("Defeito/diagnóstico", lambda t, c: has_diagnosis(t) or any(x in norm(t) for x in ["NAO GEL", "MOTOR", "DEFEITO", "NAO FUNCIONA"]) or explicit_unknown(t)),
            TechRule("Providência/acionamento", lambda t, c: any(x in norm(t) for x in ["ACION", "AGEND", "VISITA FORNECEDOR", "TROCA", "REPARO"]) or explicit_unknown(t)),
        ]
    return [
        TechRule("Escopo/solução do serviço", always_unknown_ok(has_solution)),
        TechRule("Medidas/quantidades", lambda t, c: has_dimensions(t) or has_quantity(t) or explicit_unknown(t)),
        TechRule("Materiais/especificações", always_unknown_ok(has_model_spec)),
        TechRule("Condições de execução/dependências", lambda t, c: any(x in norm(t) for x in ["ACESSO", "INTERFER", "RESTRICAO", "DESLIG", "ANDAIME", "FORNECEDOR", "CLIENTE", "DEPEND"]) or explicit_unknown(t)),
    ]


def technical_assessment(card: dict[str, Any], card_actions: list[dict[str, Any]]) -> tuple[str, list[str], list[str], bool, str]:
    eng = engineer_comments(card_actions)
    engineer_text = " \n ".join(strip_attachment_markup(comment_text(a)) for a in reversed(eng))
    source_text = " \n ".join([str(card.get("desc") or ""), attachment_names(card), engineer_text])
    service = detect_service_type(card, engineer_text)
    rules = tech_rules(service, card)
    informed: list[str] = []
    missing: list[str] = []
    for rule in rules:
        try:
            ok = bool(rule.check(source_text, card))
        except Exception:
            ok = False
        (informed if ok else missing).append(rule.label)

    substantive_reply = False
    for action in eng:
        text = strip_attachment_markup(comment_text(action))
        t = norm(text)
        if not text:
            continue
        if any(x in t for x in ["AGUARDANDO", "FOI SOLICITADO", "VOU COBRAR", "VISITA MARCADA"]):
            # é retorno operacional, mas não necessariamente levantamento técnico
            if has_dimensions(text) or has_quantity(text) or has_model_spec(text) or has_solution(text):
                substantive_reply = True
                break
            continue
        if len(text) >= 25 and (
            has_dimensions(text)
            or has_quantity(text)
            or has_model_spec(text)
            or has_solution(text)
            or has_diagnosis(text)
            or has_preparation(text)
        ):
            substantive_reply = True
            break

    summary = ", ".join(informed[:4]) if informed else "Nenhuma informação técnica objetiva identificada"
    return service, informed, missing, substantive_reply, summary


# -----------------------------------------------------------------------------
# PRAZOS / STATUS
# -----------------------------------------------------------------------------
def due_status(due: Any, now: datetime) -> tuple[str, int | None]:
    dt = parse_dt(due)
    if not dt:
        return "Sem prazo", None
    delta_days = (dt.astimezone(LOCAL_TZ).date() - now.astimezone(LOCAL_TZ).date()).days
    if delta_days < 0:
        return f"Atrasado {abs(delta_days)}d", delta_days
    if delta_days == 0:
        return "Vence hoje", 0
    if delta_days == 1:
        return "Vence amanhã", 1
    return f"Em {delta_days}d", delta_days


def manual_review_signal(custom: dict[str, Any]) -> bool:
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


def status_marks_incomplete(custom: dict[str, Any]) -> bool:
    value = find_custom_value(custom, "status")
    t = norm(value)
    return any(x in t for x in ["INFORMACAO AUSENTE", "INCOMPLETO", "NECESSIDADE DE AJUSTES"])


# -----------------------------------------------------------------------------
# MOTOR PRINCIPAL
# -----------------------------------------------------------------------------
def analyze_snapshot(snapshot: dict[str, Any], trust_trello_ready_list: bool = False) -> RadarResult:
    now = datetime.now(timezone.utc)
    lists = snapshot.get("lists") or []
    cards = snapshot.get("cards") or []
    members = snapshot.get("members") or []
    custom_fields = snapshot.get("custom_fields") or snapshot.get("customFields") or []
    actions = snapshot.get("actions") or []

    list_by_id = {str(item.get("id")): str(item.get("name") or "") for item in lists}
    members_by_id = member_name_map(members)
    actions_by_card = index_actions(actions)

    rows: list[dict[str, Any]] = []
    for card in cards:
        if card.get('closed'):
            continue
        list_name = list_by_id.get(str(card.get("idList")), "")
        list_norm = norm(list_name)

        # Evita reproduzir o Trello inteiro: somente as etapas do funil de orçamento.
        if list_norm not in LISTAS_RADAR:
            continue

        custom = decode_custom_fields(card, custom_fields)
        card_actions = actions_by_card.get(str(card.get("id")), [])
        comments = comment_actions(card_actions)
        latest = comments[0] if comments else None

        unit, _ = identify_unit(card)
        engineer, engineer_source = identify_engineer(card, custom, card_actions, members_by_id)
        budget_owner = identify_budget_owner(custom, card, members_by_id)

        info_value = find_custom_value(custom, "informacoes preenchidas", "informações preenchidas", "levantamento preenchido")
        info_yes = yes(info_value)
        visit_value = find_custom_value(custom, "data visita", "data da visita", "visita realizada")
        status_value = find_custom_value(custom, "status")
        reviewed = manual_review_signal(custom)

        service, informed, missing, substantive_reply, technical_summary = technical_assessment(card, card_actions)
        specific_pending, specific_missing, specific_request_dt = unresolved_specific_request(card_actions, engineer)
        third_owner, third_note, third_dt = third_party_signal(card_actions)
        ready_note, ready_dt = office_ready_signal(card_actions)

        latest_eng = latest_engineer_response(card_actions, engineer)
        latest_eng_dt = comment_date(latest_eng)
        latest_request = office_requests_to_engineer(card_actions, engineer)
        latest_request_dt = comment_date(latest_request[0]) if latest_request else None

        entered = current_list_entry(card, card_actions)
        age_days = max(0, (now - entered).days) if entered else None

        # O campo customizado "Prazo:" é usado como prazo original quando existe.
        due_value = find_custom_value(custom, "prazo") or card.get("due")
        received_value = find_custom_value(custom, "recebido em") or card.get("start")
        status_due, delta_due = due_status(due_value, now)

        queue = "Acompanhar"
        waiting = "—"
        pending = ""

        # 1) A etapa do Trello é a primeira verdade. Isso impede que cards enviados
        # ao cliente caiam em "Cobrar Engenharia" só por terem campos vazios.
        if list_norm == LISTA_PEND_CLIENTE:
            queue = "Aguardar terceiros"
            waiting = "Cliente"
            pending = "Aguardando informação/definição do cliente"
        elif list_norm in {LISTA_ENVIADO, LISTA_REVISAO_CLIENTE}:
            queue = "Aguardar terceiros"
            waiting = "Cliente"
            pending = "Acompanhar retorno/revisão do cliente"
        elif list_norm in {LISTA_EM_ELABORACAO, LISTA_REVISAO}:
            queue = "Em produção"
            waiting = "Orçamentos"
            pending = "Orçamento em elaboração/revisão interna"
        elif list_norm == LISTA_PARA_ELABORAR:
            # A lista, sozinha, NÃO significa que o levantamento está liberado.
            # Primeiro prevalece o sinal mais recente dos comentários/atividades.
            # Exemplo real: o card voltou para PARA ELABORAR, mas César escreveu
            # "No aguardo das informações @gustavo". Nesse caso é cobrança.
            request_is_newer = bool(
                specific_pending and specific_request_dt and (not third_dt or specific_request_dt > third_dt)
            )
            third_is_current = bool(
                third_owner and third_dt and (not specific_request_dt or third_dt >= specific_request_dt)
            )
            engineer_replied_after_request = bool(
                latest_eng_dt and (not specific_request_dt or latest_eng_dt > specific_request_dt)
            )

            if request_is_newer or specific_pending:
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = specific_pending or "Responder à solicitação de Orçamentos"
            elif third_is_current:
                queue = "Aguardar terceiros"
                waiting = third_owner or "Terceiro"
                pending = third_note or f"Aguardando {(third_owner or 'terceiro').lower()}"
            elif ready_dt and (not specific_request_dt or ready_dt > specific_request_dt) and (not third_dt or ready_dt >= third_dt):
                queue = "Pronto para elaborar"
                waiting = "Orçamentos"
                pending = ready_note or "Levantamento explicitamente liberado para elaboração"
            elif reviewed:
                queue = "Pronto para elaborar"
                waiting = "Orçamentos"
                pending = "Levantamento conferido e liberado para elaboração"
            elif engineer_replied_after_request or substantive_reply or info_yes:
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = "Conferir retorno recebido"
                if missing:
                    pending += f" • possíveis lacunas: {', '.join(missing[:5])}"
            else:
                # Fallback seguro: entrar nessa lista do Trello pede conferência,
                # não uma liberação automática. O parâmetro legado de confiança
                # é mantido na assinatura apenas por compatibilidade.
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = (
                    "Conferir levantamento antes de liberar"
                    + (f" • possíveis lacunas: {', '.join(missing[:4])}" if missing else "")
                )
        elif list_norm == LISTA_SOLICITADOS:
            # 2) Resolve a ordem temporal entre uma cobrança interna e uma espera
            # externa. Se o supervisor respondeu depois dizendo que já acionou o
            # fornecedor, a demanda passa a aguardar fornecedor. Se Orçamentos
            # cobrou algo depois disso, volta para Engenharia.
            request_is_newer = bool(
                specific_pending and specific_request_dt and (not third_dt or specific_request_dt > third_dt)
            )
            third_is_current = bool(
                third_owner and third_dt and (not specific_request_dt or third_dt >= specific_request_dt)
            )

            if request_is_newer:
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = specific_pending or "Responder à solicitação de Orçamentos"
            elif third_is_current:
                queue = "Aguardar terceiros"
                waiting = third_owner or "Terceiro"
                pending = third_note or f"Aguardando {(third_owner or 'terceiro').lower()}"
            # 3) Se o próprio Trello já marcou incompleto/ajustes, volta para cobrança.
            elif status_marks_incomplete(custom):
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = specific_pending or (
                    f"Complementar levantamento: {', '.join((specific_missing or missing)[:5])}"
                    if (specific_missing or missing)
                    else f"Status do Trello: {status_value}"
                )
            # 4) Uma pergunta objetiva ainda não respondida (ou respondida sem o dado)
            # permanece em cobrança. Este é o caso 'acabamento da tinta' / 'altura'.
            elif specific_pending:
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = specific_pending
            # 5) Houve levantamento/resposta técnica: passa para conferência humana,
            # exibindo lacunas prováveis em vez de liberar automaticamente.
            elif substantive_reply or info_yes:
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = "Conferir retorno recebido"
                if missing:
                    pending += f" • possíveis lacunas: {', '.join(missing[:5])}"
            else:
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                if engineer == "Não identificado":
                    pending = "Definir responsável pelo levantamento"
                elif not visit_value:
                    pending = "Agendar/realizar visita e enviar levantamento"
                else:
                    pending = "Enviar informações técnicas do levantamento"
                if missing:
                    pending += f" • cobrar: {', '.join(missing[:4])}"

        # O retorno precisa ser visto por uma pessoa, inclusive quando a heurística
        # acha que ele não respondeu tudo. Nomes de anexos não provam seu conteúdo.
        eng_updates = [a for a in card_actions if
                       str(a.get('type')) in {'commentCard', 'addAttachmentToCard', 'updateCustomFieldItem'}
                       and engineer_from_comment_author(a) == engineer]
        latest_update = comment_date(eng_updates[0]) if eng_updates else latest_eng_dt
        if list_norm in {LISTA_SOLICITADOS, LISTA_PARA_ELABORAR}:
            if latest_update and (not latest_request_dt or latest_update > latest_request_dt):
                if third_dt and third_dt == latest_update:
                    queue, waiting, pending = 'Aguardar terceiros', third_owner or 'Terceiro', third_note or 'Conferir dependência'
                else:
                    queue, waiting = 'Conferir retorno', 'Orçamentos'
                    pending = 'Novo retorno/anexo recebido. Conferir antes de cobrar novamente.'
            elif latest_request_dt and (not ready_dt or latest_request_dt > ready_dt):
                queue, waiting = 'Cobrar Engenharia', 'Engenharia'
                pending = specific_pending or 'Responder à última solicitação de Orçamentos'
            # Campo preenchido e frases livres são indícios, não aceite rastreável.
            if queue == 'Pronto para elaborar':
                queue, waiting, pending = 'Conferir retorno', 'Orçamentos', 'Confirmar a liberação indicada no Trello'

        rows.append({
            "Fila": queue,
            "Demanda": str(card.get("name") or "Sem título"),
            "Etapa Trello": list_name,
            "Unidade": unit,
            "Engenharia": engineer,
            "Fonte responsável": engineer_source,
            "Tipo de serviço": service,
            "Pendência / próxima ação": pending,
            "Possíveis lacunas": "; ".join((specific_missing or missing)[:8]) if (specific_missing or missing) else "—",
            "Já identificado": "; ".join(informed[:8]) if informed else "—",
            "Aguardando": waiting,
            "Prazo": fmt_date(due_value),
            "Situação do prazo": status_due,
            "Dias até prazo": delta_due,
            "Recebido em": fmt_date(received_value),
            "Data visita": fmt_date(visit_value),
            "Tempo na etapa (dias)": age_days,
            "Último comentário": strip_attachment_markup(comment_text(latest))[:300] if latest else "—",
            "Autor último comentário": comment_author(latest) or "—",
            "Último comentário em": comment_date(latest).astimezone().strftime("%d/%m %H:%M") if comment_date(latest) else "—",
            "Último retorno Engenharia": comment_text(latest_eng) if latest_eng else "—",
            "_Atualização Engenharia": latest_update,
            "_Atualização relevante": comment_date(card_actions[0]) if card_actions else None,
            "_Comentários": [{"autor": comment_author(a), "data": str(a.get('date') or ''), "texto": comment_text(a)} for a in comments],
            "_Descrição": str(card.get('desc') or ''),
            "_Anexos": [{"nome": str(a.get('name') or 'Anexo'), "url": str(a.get('url') or '')} for a in card.get('attachments') or []],
            "Responsável elaboração": budget_owner,
            "Informações preenchidas": "Sim" if info_yes else "Não/sem informação",
            "Status Trello": str(status_value or "—"),
            "Revisão manual": "Sim" if reviewed else "Não",
            "Resumo técnico": technical_summary,
            "URL": str(card.get("url") or card.get("shortUrl") or ""),
            "Card ID": str(card.get("id") or ""),
            "_Última solicitação": latest_request_dt,
            "_Último retorno": latest_eng_dt,
        })

    columns = [
        "_Atualização Engenharia", "_Atualização relevante", "_Comentários", "_Descrição", "_Anexos",
        "Fila", "Demanda", "Etapa Trello", "Unidade", "Engenharia", "Fonte responsável",
        "Tipo de serviço", "Pendência / próxima ação", "Possíveis lacunas", "Já identificado",
        "Aguardando", "Prazo", "Situação do prazo", "Dias até prazo", "Recebido em", "Data visita",
        "Tempo na etapa (dias)", "Último comentário", "Autor último comentário", "Último comentário em",
        "Último retorno Engenharia", "Responsável elaboração", "Informações preenchidas", "Status Trello",
        "Revisão manual", "Resumo técnico", "URL", "Card ID", "_Última solicitação", "_Último retorno",
    ]
    df = pd.DataFrame(rows, columns=columns)
    if not df.empty:
        df["_prioridade_prazo"] = df["Dias até prazo"].fillna(9999)
        queue_order = {
            "Cobrar Engenharia": 0,
            "Conferir retorno": 1,
            "Pronto para elaborar": 2,
            "Aguardar terceiros": 3,
            "Em produção": 4,
            "Acompanhar": 5,
        }
        df["_ord_fila"] = df["Fila"].map(queue_order).fillna(9)
        df = df.sort_values(
            ["_ord_fila", "_prioridade_prazo", "Tempo na etapa (dias)"],
            ascending=[True, True, False],
            na_position="last",
        ).drop(columns=["_prioridade_prazo", "_ord_fila"])

    queue_names = ["Cobrar Engenharia", "Conferir retorno", "Pronto para elaborar", "Aguardar terceiros", "Em produção"]
    queues = {
        name: df[df["Fila"] == name].copy() if not df.empty else pd.DataFrame(columns=columns)
        for name in queue_names
    }
    return RadarResult(rows=df, queues=queues)


def reconcile_review_states(df: pd.DataFrame, states: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Decisões do painel + evidências do Trello, sem retroceder etapas avançadas."""
    out = df.copy()
    for name in ['Última cobrança', 'Prazo resposta', 'Situação resposta', 'Aceito por']:
        out[name] = '—'
    out['Dias resposta'] = float('nan')
    for idx, row in out.iterrows():
        state = states.get(str(row.get('Card ID')), {})
        try:
            payload = json.loads(state.get('pending_reason') or '{}')
            if not isinstance(payload, dict):
                payload = {}
        except (ValueError, TypeError):
            payload = {}
        if payload.get('supervisor'):
            out.at[idx, 'Engenharia'] = payload['supervisor']
            out.at[idx, 'Fonte responsável'] = 'Definido por Orçamentos'
        if state.get('budget_owner'):
            out.at[idx, 'Responsável elaboração'] = state['budget_owner']
        out.at[idx, 'Última cobrança'] = fmt_date(state.get('last_chase_at'))
        response_due = payload.get('response_due')
        # Prazo escolhido no calendário é uma data civil, não meia-noite UTC.
        if response_due and len(str(response_due)) == 10:
            response_due = str(response_due) + 'T12:00:00-03:00'
        out.at[idx, 'Prazo resposta'] = fmt_date(response_due)
        out.at[idx, 'Aceito por'] = state.get('accepted_by') or '—'
        status, days = due_status(response_due, datetime.now(timezone.utc))
        out.at[idx, 'Situação resposta'], out.at[idx, 'Dias resposta'] = status, days
        if norm(row.get('Etapa Trello')) not in {LISTA_SOLICITADOS, LISTA_PARA_ELABORAR}:
            continue
        def timestamp(value):
            return pd.to_datetime(value, utc=True, errors='coerce')
        request = timestamp(row.get('_Última solicitação'))
        response = timestamp(row.get('_Atualização Engenharia', row.get('_Último retorno')))
        accepted = timestamp(state.get('accepted_at'))
        definition = timestamp(payload.get('saved_at'))
        chase = timestamp(state.get('last_chase_at'))
        base = max([x for x in [definition, chase, request] if pd.notna(x)], default=pd.NaT)
        if state.get('review_status') == 'waiting_engineering':
            # Sem data confiável, pedir conferência em vez de manter uma cobrança indefinida.
            if pd.isna(base) or (pd.notna(response) and response > base):
                out.at[idx, 'Fila'] = 'Conferir retorno'
                out.at[idx, 'Aguardando'] = 'Orçamentos'
                out.at[idx, 'Pendência / próxima ação'] = 'Conferir retorno frente aos itens solicitados'
            else:
                out.at[idx, 'Fila'] = 'Cobrar Engenharia'
                out.at[idx, 'Aguardando'] = 'Engenharia'
                out.at[idx, 'Pendência / próxima ação'] = 'Solicitar: ' + '; '.join(map(str, payload.get('items') or []))
        elif state.get('review_status') == 'accepted':
            # updated_at pode mudar só ao atribuir elaborador: nunca equivale a novo aceite.
            newer_request = pd.notna(request) and (pd.isna(accepted) or request > accepted)
            changed = timestamp(row.get('_Atualização Engenharia'))
            if newer_request:
                continue
            if pd.isna(accepted) or (pd.notna(changed) and changed > accepted):
                out.at[idx, 'Fila'] = 'Conferir retorno'
                out.at[idx, 'Aguardando'] = 'Orçamentos'
                out.at[idx, 'Pendência / próxima ação'] = 'Conferir atualização posterior ao aceite'
            else:
                out.at[idx, 'Fila'] = 'Pronto para elaborar'
                out.at[idx, 'Aguardando'] = 'Orçamentos'
                out.at[idx, 'Pendência / próxima ação'] = 'Levantamento aceito por ' + str(state.get('accepted_by') or 'Orçamentos')
    return out
