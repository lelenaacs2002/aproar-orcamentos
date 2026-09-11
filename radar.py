from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
from dateutil import parser as dtparser

from trello_client import decode_custom_fields, find_custom_value


LOCAL_TZ = ZoneInfo("America/Fortaleza")

ENGENHEIROS = [
    "Eduardo",
    "Joel",
    "Victor",
    "Neto",
    "Soares",
    "Gustavo",
    "Gabriel",
]

ORCAMENTOS = [
    "César",
    "Cesar",
    "Simeone",
    "Laisa",
    "Helena",
    "Ariana",
]

# Mapeamentos preservados do código existente.
# São sugestões de responsabilidade e devem ser conferidos pela operação.
RESPONSAVEL_POR_UNIDADE = [
    (("UNIFOR",), "UNIFOR", "Joel"),
    (("HORIZONTE",), "HORIZONTE", "Soares"),
    (("COLISEU",), "COLISEU", "Joel"),
    (("MARACANAU",), "MARACANAÚ", "Neto"),
    (("BARRA DO CEARA",), "BARRA DO CEARÁ", "Eduardo"),
    (("MUSEU",), "MUSEU", "Victor"),
    (
        ("CASA DA INDUSTRIA", "FIEC"),
        "FIEC / CASA DA INDÚSTRIA",
        "Gustavo",
    ),
    (("SENAI CENTRO", "SESI CENTRO"), "CENTRO", "Victor"),
]

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


# =============================================================================
# TEXTO E DATAS
# =============================================================================

def norm(text: Any) -> str:
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(
        char for char in value
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
    return re.sub(r"\s+", " ", value)


def flat(text: Any) -> str:
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(
        char for char in value
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", value.upper()).strip()


def parse_dt(value: Any) -> datetime | None:
    if value is None or value is pd.NaT:
        return None

    if isinstance(value, str) and not value.strip():
        return None

    try:
        dt = (
            value
            if isinstance(value, datetime)
            else dtparser.isoparse(str(value))
        )

        if pd.isna(dt):
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except (ValueError, TypeError, OverflowError):
        return None


def fmt_date(value: Any) -> str:
    dt = parse_dt(value)
    if dt is None:
        return "—"
    return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y")


def yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    return norm(value) in {
        "SIM",
        "YES",
        "TRUE",
        "1",
        "OK",
        "CONCLUIDO",
        "PREENCHIDO",
    }


def member_name_map(members):
    return {
        str(member.get("id")): str(
            member.get("fullName")
            or member.get("username")
            or ""
        )
        for member in members
    }


def alias_to_engineer(value):
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


# =============================================================================
# AÇÕES E COMENTÁRIOS
# =============================================================================

def action_card_id(action):
    data = action.get("data") or {}
    card = data.get("card") or {}
    return str(card.get("id") or "")


def index_actions(actions):
    indexed = defaultdict(list)

    for action in actions:
        card_id = action_card_id(action)
        if card_id:
            indexed[card_id].append(action)

    minimum = datetime.min.replace(tzinfo=timezone.utc)

    for card_id in indexed:
        indexed[card_id].sort(
            key=lambda action: parse_dt(action.get("date")) or minimum,
            reverse=True,
        )

    return indexed


def comment_actions(card_actions):
    return [
        action
        for action in card_actions
        if str(action.get("type")) == "commentCard"
    ]


def comment_author(action):
    if not action:
        return ""

    creator = action.get("memberCreator") or {}
    return str(
        creator.get("fullName")
        or creator.get("username")
        or ""
    )


def comment_text(action):
    if not action:
        return ""

    return str((action.get("data") or {}).get("text") or "")


def comment_date(action):
    return parse_dt(action.get("date")) if action else None


def current_list_entry(card, card_actions):
    current_id = str(card.get("idList") or "")

    for action in card_actions:
        after = (action.get("data") or {}).get("listAfter") or {}

        if str(after.get("id") or "") == current_id:
            dt = parse_dt(action.get("date"))
            if dt is not None:
                return dt

    return None


def engineer_from_comment_author(action):
    creator = action.get("memberCreator") or {}
    full_name = str(creator.get("fullName") or "")
    username = str(creator.get("username") or "")
    return alias_to_engineer(f"{full_name} {username}")


def is_office_author(action):
    author = norm(comment_author(action))
    return any(norm(person) in author for person in ORCAMENTOS)


def mentioned_engineers(text):
    found = []
    source = norm(text)

    for alias, engineer in PESSOA_ALIASES.items():
        position = source.find(norm(alias))
        if position >= 0:
            found.append((position, engineer))

    for engineer in ENGENHEIROS:
        position = source.find(norm(engineer))
        if position >= 0:
            found.append((position, engineer))

    result = []
    for _, name in sorted(found, key=lambda item: item[0]):
        if name not in result:
            result.append(name)

    return result


ASSIGNMENT_WORDS = {
    "MARCAR",
    "VISITA",
    "LEVANTAMENTO",
    "ORCAR",
    "ORCAMENTO",
    "VERIFICAR",
    "EXPLICAR",
    "INFORMAR",
    "ENVIAR",
    "COBRAR",
    "REALIZAR",
    "CONFERIR",
    "COMPLEMENTAR",
    "ACRESCENTAR",
    "CORRIGIR",
    "ANEXAR",
    "COTACAO",
    "SOLICITADO",
    "SOLICITADA",
    "SOLICITAR",
    "AGUARDO",
    "AGUARDANDO",
    "PENDENTE",
    "PENDENCIA",
    "ADEQUACAO",
    "AJUSTE",
    "AJUSTAR",
}

REQUEST_SIGNAL_WORDS = ASSIGNMENT_WORDS | {
    "PRECISO",
    "PRECISAMOS",
    "FALTA",
    "FALTAM",
    "INFORMACOES",
}


def explicit_assignment(card_actions):
    for action in comment_actions(card_actions):
        if not is_office_author(action):
            continue

        text = comment_text(action)
        normalized = norm(text)
        mentions = mentioned_engineers(text)

        if mentions and any(
            word in normalized for word in ASSIGNMENT_WORDS
        ):
            return mentions[0], text

    return None, None


# =============================================================================
# UNIDADE E RESPONSÁVEIS
# =============================================================================

def identify_unit(card):
    haystack = f" {norm(card.get('name'))} {norm(card.get('desc'))} "

    for aliases, display, engineer in RESPONSAVEL_POR_UNIDADE:
        for alias in aliases:
            if f" {norm(alias)} " in haystack:
                return display, engineer

    return "NÃO MAPEADA", None


def identify_engineer(card, custom, card_actions, members_by_id):
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

    assigned, _ = explicit_assignment(card_actions)
    if assigned:
        return assigned, "Atribuição explícita"

    _, unit_owner = identify_unit(card)
    if unit_owner:
        return unit_owner, "Responsável da unidade"

    for action in comment_actions(card_actions):
        engineer = engineer_from_comment_author(action)
        if engineer and engineer != "Gabriel":
            return engineer, "Autor de retorno"

    names = [
        members_by_id.get(str(member_id), "")
        for member_id in card.get("idMembers") or []
    ]

    for name in names:
        engineer = alias_to_engineer(name)
        if engineer and engineer != "Gabriel":
            return engineer, "Membro do card (fallback)"

    return "Não identificado", "Sem responsável detectável"


def identify_budget_owner(custom, card, members_by_id):
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

    names = [
        members_by_id.get(str(member_id), "")
        for member_id in card.get("idMembers") or []
    ]

    selected = [
        name
        for name in names
        if any(
            norm(person) in norm(name)
            for person in ["César", "Simeone", "Laisa"]
        )
    ]

    return ", ".join(selected) or "Não definido"


# =============================================================================
# SINAIS DE RETORNO E COBRANÇA
# =============================================================================

ATTACHMENT_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def strip_attachment_markup(text):
    text = ATTACHMENT_RE.sub("", str(text or ""))
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def is_generic_visit_request(text):
    normalized = norm(text)
    return (
        "MARCAR O DIA E REALIZAR A VISITA" in normalized
        and "LEVANTAMENTO DO ESCOPO" in normalized
    )


def engineer_comments(card_actions):
    return [
        action
        for action in comment_actions(card_actions)
        if engineer_from_comment_author(action)
    ]


def office_requests_to_engineer(card_actions, engineer):
    output = []

    for action in comment_actions(card_actions):
        if (
            not is_office_author(action)
            and "GABRIEL" not in norm(comment_author(action))
        ):
            continue

        text = comment_text(action)
        mentions = mentioned_engineers(text)

        if (
            engineer != "Não identificado"
            and mentions
            and engineer not in mentions
        ):
            continue

        normalized = norm(text)
        has_request_signal = any(
            word in normalized for word in REQUEST_SIGNAL_WORDS
        )

        waiting_for_engineering = (
            any(
                phrase in normalized
                for phrase in [
                    "NO AGUARDO DAS INFORMACOES",
                    "AGUARDANDO INFORMACOES",
                    "AGUARDANDO AS INFORMACOES",
                    "AGUARDO DAS INFORMACOES",
                    "ADEQUACAO DO ESCOPO",
                    "AJUSTE DO ESCOPO",
                ]
            )
            and (bool(mentions) or engineer != "Não identificado")
        )

        looks_like_request = (
            (bool(mentions) and has_request_signal)
            or waiting_for_engineering
            or "?" in text
        )

        if looks_like_request:
            output.append(action)

    return output


def comments_after(actions, moment):
    if moment is None:
        return actions

    minimum = datetime.min.replace(tzinfo=timezone.utc)
    return [
        action
        for action in actions
        if (comment_date(action) or minimum) > moment
    ]


def latest_engineer_response(card_actions, engineer):
    for action in engineer_comments(card_actions):
        author = engineer_from_comment_author(action)
        if engineer == "Não identificado" or author == engineer:
            return action

    return None


def office_ready_signal(card_actions):
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
        normalized = norm(text)

        if re.search(
            r"\b(NAO|AINDA|SE|QUANDO|APOS|FALTA|PENDENTE)\b",
            normalized,
        ):
            continue

        if any(phrase in normalized for phrase in ready_phrases):
            return text[:280], comment_date(action)

    return None, None


# =============================================================================
# VERIFICAÇÕES TÉCNICAS
# As verificações geram sugestões; não substituem a conferência humana.
# =============================================================================

def has_number_with_unit(text):
    return bool(
        re.search(
            r"\b\d+(?:[\.,]\d+)?\s*"
            r"(?:M2|M²|M\b|CM\b|MM\b|METROS?|CENTIMETROS?|MILIMETROS?)",
            flat(text),
        )
    )


def has_area(text):
    value = flat(text)
    return bool(
        re.search(
            r"\b\d+(?:[\.,]\d+)?\s*(?:M2|M²|METROS? QUADRADOS?)\b",
            value,
        )
        or re.search(r"\bAREA\b.{0,30}\d", value)
        or re.search(
            r"\d+(?:[\.,]\d+)?\s*[Xx]\s*\d+(?:[\.,]\d+)?",
            value,
        )
    )


def has_height(text):
    value = flat(text)
    return bool(
        re.search(
            r"ALTURA.{0,25}\d+(?:[\.,]\d+)?\s*(?:M|CM|MM|METRO)",
            value,
        )
        or re.search(
            r"\bH\s*[=:]?\s*\d+(?:[\.,]\d+)?\s*M\b",
            value,
        )
        or (
            ("ANDAIME" in value or "PLATAFORMA" in value)
            and has_number_with_unit(value)
        )
    )


def has_quantity(text):
    value = flat(text)
    return bool(
        re.search(r"\b(?:TOTAL|QTD|QUANTIDADE)\b.{0,20}\d+", value)
        or re.search(
            r"\b\d+\s*(?:UN|UND|UNID|UNIDADE|UNIDADES|PECAS?|PORTAS?|"
            r"POSTES?|LUMINARIAS?|PLACAS?|TAMPAS?|PONTOS?|SENSORES?|"
            r"REGISTROS?|JANELAS?)\b",
            value,
        )
    )


def has_finish(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "FOSCO", "ACETINADO", "SEMI BRILHO", "SEMIBRILHO",
            "BRILHANTE", "ALTO BRILHO", "TEXTURIZADO",
        ]
    )


def has_paint_type_or_color(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "TINTA", "ACRILICA", "PVA", "EPOXI", "ESMALTE",
            "COR ", "BRANCO", "BRANCA", "AZUL", "CINZA",
            "PRETO", "PRETA", "VERDE", "AMARELO", "BEGE", "OCEANO",
        ]
    )


def has_preparation(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "LIX", "EMASS", "RASP", "ESCARIFIC", "SELADOR",
            "FUNDO PREPARADOR", "LIMPEZA", "REMOCAO", "DEMOL",
            "REBOCO", "REGULARIZ", "PREPARACAO", "TRATAMENTO",
        ]
    )


def has_material(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "ALUMINIO", "ACO", "FERRO", "INOX", "VIDRO",
            "GRANITO", "MARMORE", "ACRILICO", "CERAMIC",
            "PORCELANATO", "DRYWALL", "GESSO", "CONCRETO",
            "ARGAMASSA", "TINTA", "TELHA", "MADEIRA", "PVC",
            "BORRACHA", "RESINA", "PERFIL", "CHAPA", "PASTILHA",
        ]
    )


def has_model_spec(text):
    value = norm(text)
    return has_material(value) or any(
        word in value
        for word in [
            "MODELO", "MARCA", "REFERENCIA", "ESPECIFICACAO",
            "DIAMETRO", "BITOLA", "ESPESSURA", "POTENCIA",
            "TENSAO", "VOLTAGEM", "COR ", "TIPO ", "DIMENSAO",
        ]
    )


def has_shutdown(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "DESATIV", "DESLIG", "ENERGIA", "QUADRO",
            "INTERDICAO", "BLOQUEIO ELETRICO",
        ]
    )


def has_access(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "ANDAIME", "PLATAFORMA", "ESCADA", "ACESSO",
            "ALTURA", "NR 35", "TRABALHO EM ALTURA",
        ]
    )


def has_dimensions(text):
    value = flat(text)
    return has_number_with_unit(value) or bool(
        re.search(
            r"\d+(?:[\.,]\d+)?\s*[Xx]\s*\d+(?:[\.,]\d+)?",
            value,
        )
    )


def has_thickness(text):
    value = flat(text)
    return bool(
        re.search(
            r"ESPESSURA.{0,20}\d+(?:[\.,]\d+)?\s*(?:MM|CM|M)",
            value,
        )
        or re.search(
            r"CAMADA.{0,20}\d+(?:[\.,]\d+)?\s*(?:MM|CM)",
            value,
        )
        or re.search(
            r"\b\d+(?:[\.,]\d+)?\s*(?:MM|CM)\b",
            value,
        )
    )


def has_diagnosis(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "ORIGEM", "CAUSA", "DIAGNOST", "INFILTR",
            "VAZAMENTO", "UMIDADE", "TRINCA", "FISSURA",
            "CORROSAO", "AFUND", "SOLT", "DANIFIC",
            "OXID", "DESPLAC",
        ]
    )


def has_solution(text):
    value = norm(text)
    return any(
        word in value
        for word in [
            "RETIR", "REMOV", "SUBSTIT", "INSTAL",
            "RECOMP", "EXECUT", "APLIC", "PINT",
            "IMPERMEABIL", "REGULARIZ", "TRAT", "FIX",
            "SOLD", "REPAR", "COMPACT", "ATERRO",
            "DESATIV", "REINSTAL", "CONFECC",
            "FORNEC", "MONT",
        ]
    )


def explicit_unknown(text):
    value = norm(text)
    return any(
        phrase in value
        for phrase in [
            "A CONFIRMAR",
            "NAO DEFINIDO",
            "NAO DEFINIDA",
            "AGUARDANDO INFORMACAO",
            "DEPENDE DO CLIENTE",
            "PRECISA CONFIRMAR",
        ]
    )


REQUEST_CHECKS = [
    (
        ("ACABAMENTO",),
        "Acabamento",
        lambda text: has_finish(text) or explicit_unknown(text),
    ),
    (
        ("ALTURA",),
        "Altura",
        lambda text: has_height(text) or explicit_unknown(text),
    ),
    (
        ("AREA", "METROS QUADRADOS"),
        "Área",
        lambda text: has_area(text) or explicit_unknown(text),
    ),
    (
        ("MEDIDA", "DIMENSAO", "DIMENSOES", "COMPRIMENTO", "LARGURA"),
        "Medidas/dimensões",
        lambda text: has_dimensions(text) or explicit_unknown(text),
    ),
    (
        ("QUANTIDADE", "QTD", "QUANTOS", "QUANTAS"),
        "Quantidade",
        lambda text: has_quantity(text) or explicit_unknown(text),
    ),
    (
        ("ESPESSURA",),
        "Espessura",
        lambda text: has_thickness(text) or explicit_unknown(text),
    ),
    (
        ("QUAL COR", "COR DA TINTA", "COR DO MATERIAL"),
        "Cor",
        lambda text: has_paint_type_or_color(text) or explicit_unknown(text),
    ),
    (
        ("TIPO DE TINTA", "QUAL TINTA", "ESPECIFICACAO DA TINTA"),
        "Tipo de tinta",
        lambda text: has_paint_type_or_color(text) or explicit_unknown(text),
    ),
    (
        ("MATERIAL", "ESPECIFICACAO", "MODELO", "REFERENCIA"),
        "Material/especificação",
        lambda text: has_model_spec(text) or explicit_unknown(text),
    ),
    (
        ("ANDAIME", "ACESSO", "PLATAFORMA"),
        "Condição de acesso",
        lambda text: has_access(text) or explicit_unknown(text),
    ),
]


def requested_fields(question):
    normalized = f" {norm(question)} "
    found = []

    for needles, label, check in REQUEST_CHECKS:
        if any(norm(needle) in normalized for needle in needles):
            if label not in [item[0] for item in found]:
                found.append((label, check))

    return found


def unresolved_specific_request(card_actions, engineer):
    requests = office_requests_to_engineer(card_actions, engineer)
    eng_comments = engineer_comments(card_actions)

    for request in requests:
        question = strip_attachment_markup(comment_text(request))
        request_dt = comment_date(request)
        fields = requested_fields(question)
        subsequent = comments_after(eng_comments, request_dt)

        if engineer != "Não identificado":
            subsequent = [
                action for action in subsequent
                if engineer_from_comment_author(action) == engineer
            ]

        if not subsequent:
            if is_generic_visit_request(question):
                return (
                    "Agendar/realizar a visita e preencher o levantamento",
                    ["Visita/levantamento ainda sem retorno"],
                    request_dt,
                )

            normalized = norm(question)

            if (
                "ADEQUACAO DO ESCOPO" in normalized
                or "AJUSTE DO ESCOPO" in normalized
            ):
                return (
                    "Informar a adequação/ajuste de escopo solicitado",
                    ["Adequação do escopo"],
                    request_dt,
                )

            if any(
                phrase in normalized
                for phrase in [
                    "NO AGUARDO DAS INFORMACOES",
                    "AGUARDANDO INFORMACOES",
                    "AGUARDO DAS INFORMACOES",
                ]
            ):
                return (
                    "Enviar as informações solicitadas pelo setor de Orçamentos",
                    ["Informações solicitadas"],
                    request_dt,
                )

            return (
                question[:280] or "Responder à solicitação de Orçamentos",
                [],
                request_dt,
            )

        answer = "\n".join(comment_text(action) for action in subsequent)
        missing = [
            label for label, check in fields
            if not check(answer)
        ]

        if fields and missing:
            return (
                "Resposta recebida, mas ainda não informa: "
                + ", ".join(missing),
                missing,
                request_dt,
            )

        if fields:
            return None, [], request_dt

    return None, [], None


# =============================================================================
# DEPENDÊNCIAS DE TERCEIROS
# =============================================================================

def third_party_signal(card_actions):
    for action in comment_actions(card_actions):
        text = norm(comment_text(action))
        author_eng = engineer_from_comment_author(action)

        supplier_wait = any(
            phrase in text
            for phrase in [
                "AGUARDANDO ORCAMENTO DO FORNECEDOR",
                "AGUARDANDO ORCAMENTO FORNECEDOR",
                "AGUARDANDO COTACAO",
                "AGUARDANDO RETORNO DO FORNECEDOR",
                "AGUARDANDO FORNECEDOR",
                "VISITA DO FORNECEDOR",
                "FORNECEDOR FOI VERIFICAR",
                "FORNECEDOR JA FOI",
            ]
        )

        if supplier_wait and author_eng:
            return (
                "Fornecedor",
                strip_attachment_markup(comment_text(action))[:260],
                comment_date(action),
            )

        client_wait = any(
            phrase in text
            for phrase in [
                "AGUARDANDO CLIENTE",
                "AGUARDANDO RETORNO DO CLIENTE",
                "PENDENTE CLIENTE",
                "CLIENTE VAI CONFIRMAR",
                "CLIENTE IRA CONFIRMAR",
            ]
        )

        if client_wait:
            return (
                "Cliente",
                strip_attachment_markup(comment_text(action))[:260],
                comment_date(action),
            )

        specialist_wait = any(
            phrase in text
            for phrase in [
                "AGUARDANDO ESPECIALISTA",
                "AGUARDANDO PROJETO",
                "AGUARDANDO PROJETISTA",
                "AGUARDANDO ENGENHEIRO ELETRICO",
                "AGUARDANDO ESTRUTURAL",
            ]
        )

        if specialist_wait:
            return (
                "Especialista",
                strip_attachment_markup(comment_text(action))[:260],
                comment_date(action),
            )

    return None, None, None


# =============================================================================
# REGRAS POR SERVIÇO
# =============================================================================

def detect_service_type(card, technical_text):
    full = norm(
        f"{card.get('name', '')} "
        f"{card.get('desc', '')} "
        f"{technical_text}"
    )

    def has_word(word):
        return bool(re.search(rf"\b{re.escape(norm(word))}\b", full))

    if has_word("GARANTIA"):
        return "Garantia"

    if any(word in full for word in ["INFILTR", "VAZAMENTO", "IMPERMEABIL"]):
        return "Infiltração / impermeabilização"

    if any(
        word in full
        for word in ["PINTURA", "PINTAR", "EMASSAMENTO", "LIXAMENTO"]
    ):
        return "Pintura"

    if any(word in full for word in ["SOLEIRA", "RODAPE"]):
        return "Soleira / rodapé"

    if any(
        word in full
        for word in ["CERAMIC", "PISO", "REVESTIMENTO", "PORCELANATO"]
    ):
        return "Piso / revestimento"

    if (
        has_word("PORTA")
        or has_word("PORTAS")
        or any(
            word in full
            for word in ["VIDRO", "JANELA", "ESQUADRIA", "CILINDRO"]
        )
    ):
        return "Porta / vidro / esquadria"

    if any(
        word in full
        for word in ["GRADIL", "PORTAO", "GRADE METAL", "ESTRUTURA METAL", "SOLD"]
    ):
        return "Serralheria / gradil / portão"

    if any(
        word in full
        for word in ["POSTE", "LUMINARIA", "ELETRIC", "ILUMINACAO", "FIBRA", "CABEAMENTO"]
    ):
        return "Elétrica / iluminação"

    if any(word in full for word in ["DRYWALL", "DRY WALL", "FORRO", "GESSO"]):
        return "Drywall / forro"

    if any(
        word in full
        for word in ["ARMADURA", "REBOCO", "CONCRETO", "ARGAMASSA ESTRUTURAL", "LAJE"]
    ):
        return "Concreto / reboco / armadura"

    if any(word in full for word in ["COBERTURA", "COBERTA", "TELHA"]):
        return "Cobertura"

    if "ACRILICO" in full:
        return "Acrílico"

    if any(
        word in full
        for word in ["MARMORE", "MARMORARIA", "GRANITO", "BANCADA"]
    ):
        return "Marmoraria"

    if any(word in full for word in ["SENSOR", "BEBEDOURO", "EQUIPAMENTO"]):
        return "Equipamento"

    return "Outros"


def attachment_names(card):
    return " ".join(
        str(attachment.get("name") or attachment.get("fileName") or "")
        for attachment in card.get("attachments") or []
    )


def tech_rules(service, card):
    def checked(check):
        return lambda text, current_card: check(text) or explicit_unknown(text)

    def contains(*words):
        return lambda text, current_card: (
            any(word in norm(text) for word in words)
            or explicit_unknown(text)
        )

    def any_check(*checks):
        return lambda text, current_card: (
            any(check(text) for check in checks)
            or explicit_unknown(text)
        )

    if service == "Pintura":
        return [
            TechRule("Área/dimensões da pintura", checked(has_area)),
            TechRule(
                "Altura/condição de acesso",
                any_check(has_height, has_access),
            ),
            TechRule("Preparação da superfície", checked(has_preparation)),
            TechRule("Tipo/cor da tinta", checked(has_paint_type_or_color)),
            TechRule("Acabamento da tinta", checked(has_finish)),
        ]

    if service == "Infiltração / impermeabilização":
        return [
            TechRule("Origem/diagnóstico do problema", checked(has_diagnosis)),
            TechRule(
                "Área/dimensões afetadas",
                any_check(has_area, has_dimensions),
            ),
            TechRule("Solução/sistema previsto", checked(has_solution)),
            TechRule(
                "Remoções e recomposições necessárias",
                lambda text, current_card: (
                    has_preparation(text)
                    or "RECOMP" in norm(text)
                    or explicit_unknown(text)
                ),
            ),
        ]

    if service == "Soleira / rodapé":
        return [
            TechRule(
                "Comprimento/quantidade",
                any_check(has_dimensions, has_quantity),
            ),
            TechRule("Material/padrão", checked(has_material)),
            TechRule("Dimensões/seção da peça", checked(has_dimensions)),
            TechRule(
                "Condição da base/remoção existente",
                lambda text, current_card: (
                    has_preparation(text)
                    or "BASE" in norm(text)
                    or explicit_unknown(text)
                ),
            ),
        ]

    if service == "Piso / revestimento":
        return [
            TechRule("Área/quantidade", any_check(has_area, has_quantity)),
            TechRule(
                "Tipo/dimensão do revestimento",
                lambda text, current_card: (
                    (
                        has_material(text)
                        and (
                            has_dimensions(text)
                            or "TIPO" in norm(text)
                        )
                    )
                    or explicit_unknown(text)
                ),
            ),
            TechRule(
                "Base/preparo",
                lambda text, current_card: (
                    has_preparation(text)
                    or "CONTRAPISO" in norm(text)
                    or "BASE" in norm(text)
                    or explicit_unknown(text)
                ),
            ),
            TechRule(
                "Remoção/recomposição",
                contains(
                    "REMOV", "RETIR", "RECOMP",
                    "MANTER EXISTENTE", "SEM REMOCAO",
                ),
            ),
        ]

    if service == "Porta / vidro / esquadria":
        return [
            TechRule("Quantidade de peças", checked(has_quantity)),
            TechRule("Medidas", checked(has_dimensions)),
            TechRule("Material/modelo/especificação", checked(has_model_spec)),
            TechRule(
                "Ferragens/acessórios/reaproveitamento",
                contains(
                    "FERRAGEM", "DOBRAD", "PUXADOR", "FECHADURA",
                    "CILINDRO", "ROLDANA", "TRILHO",
                    "REAPROVEIT", "ACESSORIO",
                ),
            ),
        ]

    if service == "Serralheria / gradil / portão":
        return [
            TechRule(
                "Comprimento/quantidade",
                any_check(has_dimensions, has_quantity),
            ),
            TechRule("Altura/dimensões", checked(has_dimensions)),
            TechRule("Material/perfil", checked(has_model_spec)),
            TechRule(
                "Fixação/remoção/reinstalação",
                contains("FIX", "REMOV", "RETIR", "REINSTAL", "SOLD", "CHUMB", "PARAFUS"),
            ),
            TechRule(
                "Acabamento/proteção",
                lambda text, current_card: (
                    has_finish(text)
                    or any(
                        word in norm(text)
                        for word in ["PINT", "GALVAN", "ANTICORROS", "FUNDO"]
                    )
                    or explicit_unknown(text)
                ),
            ),
        ]

    if service == "Elétrica / iluminação":
        rules = [
            TechRule("Quantidade", checked(has_quantity)),
            TechRule(
                "Especificação dos equipamentos/materiais",
                checked(has_model_spec),
            ),
            TechRule("Desligamento/desativação", checked(has_shutdown)),
            TechRule(
                "Interferências/dependências",
                contains("FIBRA", "INTERFER", "DEPEND", "OUTRA REDE", "ENERGIA", "ALIMENTA"),
            ),
        ]

        if any(
            word in norm(card.get("name"))
            for word in ["POSTE", "LUMINARIA"]
        ):
            rules.insert(
                2,
                TechRule(
                    "Altura/condição de acesso",
                    any_check(has_height, has_access),
                ),
            )

        if (
            "POSTE" in norm(f"{card.get('name')} {card.get('desc')}")
            and any(
                word in norm(f"{card.get('desc')} {attachment_names(card)}")
                for word in ["SUBSTIT", "NOVO POSTE"]
            )
        ):
            rules.append(
                TechRule(
                    "Especificação do poste substituto",
                    lambda text, current_card: (
                        (
                            "POSTE" in norm(text)
                            and has_model_spec(text)
                            and has_dimensions(text)
                        )
                        or explicit_unknown(text)
                    ),
                )
            )

        return rules

    if service == "Drywall / forro":
        return [
            TechRule("Área/dimensões", any_check(has_area, has_dimensions)),
            TechRule("Tipo/material da placa", checked(has_model_spec)),
            TechRule(
                "Estrutura/perfis",
                contains("PERFIL", "MONTANTE", "GUIA", "ESTRUTURA"),
            ),
            TechRule(
                "Acabamento",
                contains("MASSA", "FITA", "PINT", "ACABAMENTO"),
            ),
            TechRule(
                "Interferências",
                contains(
                    "ELETR", "AR COND", "SPRINKLER", "LUMINARIA",
                    "INTERFER", "SEM INTERFERENCIA",
                ),
            ),
        ]

    if service == "Concreto / reboco / armadura":
        return [
            TechRule("Área/dimensões", any_check(has_area, has_dimensions)),
            TechRule("Espessura/profundidade", checked(has_thickness)),
            TechRule("Remoção/preparo", checked(has_preparation)),
            TechRule(
                "Tratamento/material de recomposição",
                lambda text, current_card: (
                    has_material(text)
                    or "TRAT" in norm(text)
                    or "RECOMP" in norm(text)
                    or explicit_unknown(text)
                ),
            ),
            TechRule(
                "Acabamento final",
                lambda text, current_card: (
                    has_finish(text)
                    or any(
                        word in norm(text)
                        for word in ["PINT", "CERAMIC", "REVEST", "ACABAMENTO"]
                    )
                    or explicit_unknown(text)
                ),
            ),
        ]

    if service == "Cobertura":
        return [
            TechRule("Área/dimensões", any_check(has_area, has_dimensions)),
            TechRule("Sistema/material", checked(has_model_spec)),
            TechRule(
                "Estrutura/fixação",
                contains("ESTRUTURA", "PERFIL", "VIGA", "PILAR", "FIX", "CHUMB", "PARAFUS"),
            ),
            TechRule(
                "Projeto/anexo de referência",
                lambda text, current_card: (
                    bool(current_card.get("attachments"))
                    or "ANEX" in norm(text)
                ),
            ),
        ]

    if service == "Acrílico":
        return [
            TechRule("Quantidade", checked(has_quantity)),
            TechRule("Medidas", checked(has_dimensions)),
            TechRule("Espessura", checked(has_thickness)),
            TechRule(
                "Tipo/cor/transparência",
                contains("TRANSPAREN", "CRISTAL", "FUME", "LEITOSO", "COLORIDO", "COR "),
            ),
        ]

    if service == "Marmoraria":
        return [
            TechRule("Quantidade/peças", checked(has_quantity)),
            TechRule("Medidas", checked(has_dimensions)),
            TechRule("Material/padrão", checked(has_material)),
            TechRule(
                "Acabamento",
                contains("POLID", "LEVIG", "BOLEAD", "ACABAMENTO", "BRILHO"),
            ),
            TechRule(
                "Instalação/remoção",
                contains("INSTAL", "REMOV", "RETIR", "FIX", "COLA"),
            ),
        ]

    if service == "Equipamento":
        return [
            TechRule("Quantidade", checked(has_quantity)),
            TechRule("Modelo/especificação", checked(has_model_spec)),
            TechRule(
                "Local/ponto de instalação",
                contains("LOCAL", "TERREO", "SALA", "PORTARIA", "PONTO", "ACADEMIA"),
            ),
            TechRule(
                "Condição de instalação/alimentação",
                contains("INSTAL", "ALIMENT", "TOMADA", "TENSAO", "ENERGIA", "FIX"),
            ),
        ]

    if service == "Garantia":
        return [
            TechRule(
                "Referência do serviço/orçamento anterior",
                contains("OBRA ", "PIPE", "ORCAMENTO ANTERIOR", "SERVICO ANTERIOR"),
            ),
            TechRule(
                "Fornecedor/responsável pela garantia",
                contains("FORNECEDOR", "PRESTADOR", "GARANTIA COM", "RESPONSAVEL"),
            ),
            TechRule(
                "Defeito/diagnóstico",
                lambda text, current_card: (
                    has_diagnosis(text)
                    or any(
                        word in norm(text)
                        for word in ["NAO GEL", "MOTOR", "DEFEITO", "NAO FUNCIONA"]
                    )
                    or explicit_unknown(text)
                ),
            ),
            TechRule(
                "Providência/acionamento",
                contains("ACION", "AGEND", "VISITA FORNECEDOR", "TROCA", "REPARO"),
            ),
        ]

    return [
        TechRule("Escopo/solução do serviço", checked(has_solution)),
        TechRule(
            "Medidas/quantidades",
            any_check(has_dimensions, has_quantity),
        ),
        TechRule("Materiais/especificações", checked(has_model_spec)),
        TechRule(
            "Condições de execução/dependências",
            contains(
                "ACESSO", "INTERFER", "RESTRICAO", "DESLIG",
                "ANDAIME", "FORNECEDOR", "CLIENTE", "DEPEND",
            ),
        ),
    ]


def technical_assessment(card, card_actions):
    eng = engineer_comments(card_actions)

    engineer_text = "\n".join(
        strip_attachment_markup(comment_text(action))
        for action in reversed(eng)
    )

    source_text = "\n".join([
        str(card.get("desc") or ""),
        attachment_names(card),
        engineer_text,
    ])

    service = detect_service_type(card, engineer_text)
    rules = tech_rules(service, card)

    informed = []
    missing = []

    for rule in rules:
        try:
            ok = bool(rule.check(source_text, card))
        except Exception:
            ok = False

        (informed if ok else missing).append(rule.label)

    substantive_reply = False

    for action in eng:
        text = strip_attachment_markup(comment_text(action))
        normalized = norm(text)

        if not text:
            continue

        if any(
            phrase in normalized
            for phrase in [
                "AGUARDANDO",
                "FOI SOLICITADO",
                "VOU COBRAR",
                "VISITA MARCADA",
            ]
        ):
            if (
                has_dimensions(text)
                or has_quantity(text)
                or has_model_spec(text)
                or has_solution(text)
            ):
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

    summary = (
        ", ".join(informed[:4])
        if informed
        else "Nenhuma informação técnica objetiva identificada"
    )

    return service, informed, missing, substantive_reply, summary


# =============================================================================
# PRAZOS E STATUS
# =============================================================================

def due_status(due, now):
    dt = parse_dt(due)

    if dt is None:
        return "Sem prazo", None

    delta_days = (
        dt.astimezone(LOCAL_TZ).date()
        - now.astimezone(LOCAL_TZ).date()
    ).days

    if delta_days < 0:
        return f"Atrasado {abs(delta_days)}d", delta_days
    if delta_days == 0:
        return "Vence hoje", 0
    if delta_days == 1:
        return "Vence amanhã", 1

    return f"Em {delta_days}d", delta_days


def manual_review_signal(custom):
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


def status_marks_incomplete(custom):
    value = find_custom_value(custom, "status")
    normalized = norm(value)

    return any(
        phrase in normalized
        for phrase in [
            "INFORMACAO AUSENTE",
            "INCOMPLETO",
            "NECESSIDADE DE AJUSTES",
        ]
    )


# =============================================================================
# MOTOR PRINCIPAL
# =============================================================================

def analyze_snapshot(snapshot, trust_trello_ready_list=False):
    now = datetime.now(timezone.utc)

    lists = snapshot.get("lists") or []
    cards = snapshot.get("cards") or []
    members = snapshot.get("members") or []
    custom_fields = (
        snapshot.get("custom_fields")
        or snapshot.get("customFields")
        or []
    )
    actions = snapshot.get("actions") or []

    list_by_id = {
        str(item.get("id")): str(item.get("name") or "")
        for item in lists
    }

    members_by_id = member_name_map(members)
    actions_by_card = index_actions(actions)
    rows = []

    for card in cards:
        if card.get("closed"):
            continue

        list_name = list_by_id.get(str(card.get("idList")), "")
        list_norm = norm(list_name)

        if list_norm not in LISTAS_RADAR:
            continue

        custom = decode_custom_fields(card, custom_fields)
        card_actions = actions_by_card.get(str(card.get("id")), [])
        comments = comment_actions(card_actions)
        latest = comments[0] if comments else None

        unit, _ = identify_unit(card)
        engineer, engineer_source = identify_engineer(
            card,
            custom,
            card_actions,
            members_by_id,
        )
        budget_owner = identify_budget_owner(
            custom,
            card,
            members_by_id,
        )

        info_value = find_custom_value(
            custom,
            "informacoes preenchidas",
            "informações preenchidas",
            "levantamento preenchido",
        )
        info_yes = yes(info_value)

        visit_value = find_custom_value(
            custom,
            "data visita",
            "data da visita",
            "visita realizada",
        )
        status_value = find_custom_value(custom, "status")
        reviewed = manual_review_signal(custom)

        (
            service,
            informed,
            missing,
            substantive_reply,
            technical_summary,
        ) = technical_assessment(card, card_actions)

        (
            specific_pending,
            specific_missing,
            specific_request_dt,
        ) = unresolved_specific_request(card_actions, engineer)

        third_owner, third_note, third_dt = third_party_signal(card_actions)
        ready_note, ready_dt = office_ready_signal(card_actions)

        latest_eng = latest_engineer_response(card_actions, engineer)
        latest_eng_dt = comment_date(latest_eng)

        requests = office_requests_to_engineer(card_actions, engineer)
        latest_request_dt = (
            comment_date(requests[0]) if requests else None
        )

        entered = current_list_entry(card, card_actions)
        age_days = max(0, (now - entered).days) if entered else None

        due_value = find_custom_value(custom, "prazo") or card.get("due")
        received_value = (
            find_custom_value(custom, "recebido em")
            or card.get("start")
        )
        status_due, delta_due = due_status(due_value, now)

        queue = "Acompanhar"
        waiting = "—"
        pending = ""

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
            request_is_newer = bool(
                specific_pending
                and specific_request_dt
                and (
                    not third_dt
                    or specific_request_dt > third_dt
                )
            )

            third_is_current = bool(
                third_owner
                and third_dt
                and (
                    not specific_request_dt
                    or third_dt >= specific_request_dt
                )
            )

            engineer_replied_after_request = bool(
                latest_eng_dt
                and (
                    not specific_request_dt
                    or latest_eng_dt > specific_request_dt
                )
            )

            if request_is_newer or specific_pending:
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = (
                    specific_pending
                    or "Responder à solicitação de Orçamentos"
                )

            elif third_is_current:
                queue = "Aguardar terceiros"
                waiting = third_owner or "Terceiro"
                pending = (
                    third_note
                    or f"Aguardando {(third_owner or 'terceiro').lower()}"
                )

            elif (
                ready_dt
                and (
                    not specific_request_dt
                    or ready_dt > specific_request_dt
                )
                and (not third_dt or ready_dt >= third_dt)
            ):
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = "Confirmar a liberação indicada no Trello"

            elif reviewed:
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = "Confirmar a conferência indicada no Trello"

            elif (
                engineer_replied_after_request
                or substantive_reply
                or info_yes
            ):
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = "Conferir retorno recebido"

                if missing:
                    pending += (
                        " • possíveis lacunas: "
                        + ", ".join(missing[:5])
                    )

            else:
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = "Conferir levantamento antes de liberar"

                if missing:
                    pending += (
                        " • possíveis lacunas: "
                        + ", ".join(missing[:4])
                    )

        elif list_norm == LISTA_SOLICITADOS:
            request_is_newer = bool(
                specific_pending
                and specific_request_dt
                and (
                    not third_dt
                    or specific_request_dt > third_dt
                )
            )

            third_is_current = bool(
                third_owner
                and third_dt
                and (
                    not specific_request_dt
                    or third_dt >= specific_request_dt
                )
            )

            if request_is_newer:
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = (
                    specific_pending
                    or "Responder à solicitação de Orçamentos"
                )

            elif third_is_current:
                queue = "Aguardar terceiros"
                waiting = third_owner or "Terceiro"
                pending = (
                    third_note
                    or f"Aguardando {(third_owner or 'terceiro').lower()}"
                )

            elif status_marks_incomplete(custom):
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                gaps = specific_missing or missing

                pending = specific_pending or (
                    "Complementar levantamento: " + ", ".join(gaps[:5])
                    if gaps
                    else f"Status do Trello: {status_value}"
                )

            elif specific_pending:
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = specific_pending

            elif substantive_reply or info_yes:
                queue = "Conferir retorno"
                waiting = "Orçamentos"
                pending = "Conferir retorno recebido"

                if missing:
                    pending += (
                        " • possíveis lacunas: "
                        + ", ".join(missing[:5])
                    )

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
                    pending += " • cobrar: " + ", ".join(missing[:4])

        eng_updates = [
            action
            for action in card_actions
            if str(action.get("type")) in {
                "commentCard",
                "addAttachmentToCard",
                "updateCustomFieldItem",
            }
            and engineer_from_comment_author(action) == engineer
        ]

        latest_update = (
            comment_date(eng_updates[0])
            if eng_updates
            else latest_eng_dt
        )

        if list_norm in {LISTA_SOLICITADOS, LISTA_PARA_ELABORAR}:
            if latest_update and (
                not latest_request_dt
                or latest_update > latest_request_dt
            ):
                if third_dt and third_dt == latest_update:
                    queue = "Aguardar terceiros"
                    waiting = third_owner or "Terceiro"
                    pending = third_note or "Conferir dependência"
                else:
                    queue = "Conferir retorno"
                    waiting = "Orçamentos"
                    pending = (
                        "Novo retorno/anexo recebido. "
                        "Conferir antes de cobrar novamente."
                    )

            elif latest_request_dt and (
                not ready_dt or latest_request_dt > ready_dt
            ):
                queue = "Cobrar Engenharia"
                waiting = "Engenharia"
                pending = (
                    specific_pending
                    or "Responder à última solicitação de Orçamentos"
                )

        latest_date = comment_date(latest)
        gaps = specific_missing or missing

        rows.append({
            "Fila": queue,
            "Demanda": str(card.get("name") or "Sem título"),
            "Etapa Trello": list_name,
            "Unidade": unit,
            "Engenharia": engineer,
            "Fonte responsável": engineer_source,
            "Tipo de serviço": service,
            "Pendência / próxima ação": pending,
            "Possíveis lacunas": "; ".join(gaps[:8]) if gaps else "—",
            "Já identificado": "; ".join(informed[:8]) if informed else "—",
            "Aguardando": waiting,
            "Prazo": fmt_date(due_value),
            "Situação do prazo": status_due,
            "Dias até prazo": delta_due,
            "Recebido em": fmt_date(received_value),
            "Data visita": fmt_date(visit_value),
            "Tempo na etapa (dias)": age_days,
            "Último comentário": (
                strip_attachment_markup(comment_text(latest))[:300]
                if latest else "—"
            ),
            "Autor último comentário": comment_author(latest) or "—",
            "Último comentário em": (
                latest_date.astimezone(LOCAL_TZ).strftime("%d/%m %H:%M")
                if latest_date else "—"
            ),
            "Último retorno Engenharia": (
                comment_text(latest_eng) if latest_eng else "—"
            ),
            "_Atualização Engenharia": latest_update,
            "_Atualização relevante": (
                comment_date(card_actions[0]) if card_actions else None
            ),
            "_Comentários": [
                {
                    "autor": comment_author(action),
                    "data": str(action.get("date") or ""),
                    "texto": comment_text(action),
                }
                for action in comments
            ],
            "_Descrição": str(card.get("desc") or ""),
            "_Anexos": [
                {
                    "nome": str(attachment.get("name") or "Anexo"),
                    "url": str(attachment.get("url") or ""),
                }
                for attachment in card.get("attachments") or []
            ],
            "Responsável elaboração": budget_owner,
            "Informações preenchidas": (
                "Sim" if info_yes else "Não/sem informação"
            ),
            "Status Trello": str(status_value or "—"),
            "Revisão manual": "Sim" if reviewed else "Não",
            "Resumo técnico": technical_summary,
            "URL": str(card.get("url") or card.get("shortUrl") or ""),
            "Card ID": str(card.get("id") or ""),
            "_Última solicitação": latest_request_dt,
            "_Último retorno": latest_eng_dt,
        })

    columns = [
        "_Atualização Engenharia",
        "_Atualização relevante",
        "_Comentários",
        "_Descrição",
        "_Anexos",
        "Fila",
        "Demanda",
        "Etapa Trello",
        "Unidade",
        "Engenharia",
        "Fonte responsável",
        "Tipo de serviço",
        "Pendência / próxima ação",
        "Possíveis lacunas",
        "Já identificado",
        "Aguardando",
        "Prazo",
        "Situação do prazo",
        "Dias até prazo",
        "Recebido em",
        "Data visita",
        "Tempo na etapa (dias)",
        "Último comentário",
        "Autor último comentário",
        "Último comentário em",
        "Último retorno Engenharia",
        "Responsável elaboração",
        "Informações preenchidas",
        "Status Trello",
        "Revisão manual",
        "Resumo técnico",
        "URL",
        "Card ID",
        "_Última solicitação",
        "_Último retorno",
    ]

    df = pd.DataFrame(rows, columns=columns)

    if not df.empty:
        df["_prioridade_prazo"] = pd.to_numeric(
            df["Dias até prazo"],
            errors="coerce",
        ).fillna(9999)

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
            [
                "_ord_fila",
                "_prioridade_prazo",
                "Tempo na etapa (dias)",
            ],
            ascending=[True, True, False],
            na_position="last",
        ).drop(columns=["_prioridade_prazo", "_ord_fila"])

    queue_names = [
        "Cobrar Engenharia",
        "Conferir retorno",
        "Pronto para elaborar",
        "Aguardar terceiros",
        "Em produção",
    ]

    queues = {
        name: df[df["Fila"] == name].copy()
        for name in queue_names
    }

    return RadarResult(rows=df, queues=queues)


# =============================================================================
# DECISÕES SALVAS NO PAINEL
# =============================================================================

def reconcile_review_states(df, states):
    """Combina decisões de Orçamentos com as evidências do Trello."""
    out = df.copy()

    for column in [
        "Última cobrança",
        "Prazo resposta",
        "Situação resposta",
        "Aceito por",
    ]:
        out[column] = "—"

    out["Dias resposta"] = float("nan")

    def timestamp(value):
        return pd.to_datetime(value, utc=True, errors="coerce")

    for idx, row in out.iterrows():
        card_id = str(row.get("Card ID") or "")
        state = (states or {}).get(card_id) or {}

        raw = state.get("pending_reason")

        try:
            payload = (
                raw if isinstance(raw, dict)
                else json.loads(raw or "{}")
            )
            if not isinstance(payload, dict):
                payload = {}
        except (ValueError, TypeError):
            payload = {"items": [str(raw)]} if raw else {}

        items = payload.get("items") or []
        if isinstance(items, str):
            items = [items]

        supervisor = payload.get("supervisor")
        if supervisor:
            out.at[idx, "Engenharia"] = supervisor
            out.at[idx, "Fonte responsável"] = "Definido por Orçamentos"

        if state.get("budget_owner"):
            out.at[idx, "Responsável elaboração"] = state["budget_owner"]

        out.at[idx, "Última cobrança"] = fmt_date(
            state.get("last_chase_at")
        )
        out.at[idx, "Aceito por"] = state.get("accepted_by") or "—"

        response_due = payload.get("response_due")

        # Evita que uma data de calendário recue um dia por causa do fuso.
        if response_due and len(str(response_due)) == 10:
            response_due = str(response_due) + "T12:00:00-03:00"

        out.at[idx, "Prazo resposta"] = fmt_date(response_due)

        status_due, days = due_status(
            response_due,
            datetime.now(timezone.utc),
        )
        out.at[idx, "Situação resposta"] = status_due
        out.at[idx, "Dias resposta"] = (
            float(days) if days is not None else float("nan")
        )

        # Um aceite antigo não deve retroceder etapas avançadas.
        if norm(row.get("Etapa Trello")) not in {
            LISTA_SOLICITADOS,
            LISTA_PARA_ELABORAR,
        }:
            continue

        request = timestamp(row.get("_Última solicitação"))
        response = timestamp(row.get("_Atualização Engenharia"))

        if pd.isna(response):
            response = timestamp(row.get("_Último retorno"))

        accepted = timestamp(state.get("accepted_at"))
        definition = timestamp(payload.get("saved_at"))
        chase = timestamp(state.get("last_chase_at"))

        reference_dates = [
            value
            for value in [definition, chase, request]
            if pd.notna(value)
        ]
        reference = (
            max(reference_dates) if reference_dates else pd.NaT
        )

        status = state.get("review_status")

        if status == "waiting_engineering":
            has_new_response = (
                pd.notna(response)
                and (
                    pd.isna(reference)
                    or response > reference
                )
            )

            if pd.isna(reference) or has_new_response:
                out.at[idx, "Fila"] = "Conferir retorno"
                out.at[idx, "Aguardando"] = "Orçamentos"
                out.at[idx, "Pendência / próxima ação"] = (
                    "Conferir retorno frente aos itens solicitados"
                )
            else:
                out.at[idx, "Fila"] = "Cobrar Engenharia"
                out.at[idx, "Aguardando"] = "Engenharia"
                out.at[idx, "Pendência / próxima ação"] = (
                    "Solicitar: " + "; ".join(map(str, items))
                    if items
                    else "Definir os itens que o engenheiro precisa responder"
                )

        elif status == "accepted":
            newer_request = (
                pd.notna(request)
                and (
                    pd.isna(accepted)
                    or request > accepted
                )
            )
            newer_response = (
                pd.notna(response)
                and (
                    pd.isna(accepted)
                    or response > accepted
                )
            )

            if newer_request:
                if pd.notna(response) and response > request:
                    out.at[idx, "Fila"] = "Conferir retorno"
                    out.at[idx, "Aguardando"] = "Orçamentos"
                    out.at[idx, "Pendência / próxima ação"] = (
                        "Conferir retorno à solicitação posterior ao aceite"
                    )
                else:
                    out.at[idx, "Fila"] = "Cobrar Engenharia"
                    out.at[idx, "Aguardando"] = "Engenharia"
                    out.at[idx, "Pendência / próxima ação"] = (
                        "Cobrar a solicitação registrada após o aceite"
                    )

            elif pd.isna(accepted) or newer_response:
                out.at[idx, "Fila"] = "Conferir retorno"
                out.at[idx, "Aguardando"] = "Orçamentos"
                out.at[idx, "Pendência / próxima ação"] = (
                    "Conferir atualização ou confirmar aceite sem data"
                )

            else:
                out.at[idx, "Fila"] = "Pronto para elaborar"
                out.at[idx, "Aguardando"] = "Orçamentos"
                out.at[idx, "Pendência / próxima ação"] = (
                    "Levantamento aceito por "
                    + str(state.get("accepted_by") or "Orçamentos")
                )

    return out
