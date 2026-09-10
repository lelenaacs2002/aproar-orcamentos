from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests


class TrelloError(RuntimeError):
    pass


def _norm(text: Any) -> str:
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", value).strip().upper()


def board_identifier(value: str) -> str:
    """Aceita shortLink, URL do board ou URL .json e devolve o shortLink."""
    value = str(value or "").strip()
    match = re.search(r"trello\.com/b/([^/?#\.]+)", value, flags=re.I)
    return match.group(1) if match else value.removesuffix(".json").strip("/")


def _board_slug(value: str) -> str:
    """Extrai o slug quando a URL vier como /b/SHORTLINK/slug."""
    try:
        path = urlparse(str(value or "")).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 3 and parts[0].lower() == "b":
            slug = parts[2].removesuffix(".json")
            return slug
    except Exception:
        pass
    return ""


class TrelloClient:
    """
    Leitura do quadro pelo export JSON do próprio link do Trello.

    Esta versão é somente leitura e NÃO exige API key/token. Para escrever no
    Trello (comentar, mover cartões etc.) será necessária autenticação em uma
    etapa posterior.
    """

    def __init__(self, board: str, timeout: int = 35):
        self.board_raw = str(board or "").strip()
        self.board = board_identifier(self.board_raw)
        self.slug = _board_slug(self.board_raw)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; AproarOrcamentos/1.0)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        })
        if not self.board:
            raise TrelloError("Configure TRELLO_BOARD_URL nos Secrets do Streamlit.")

    def _candidate_urls(self) -> list[str]:
        urls: list[str] = []
        # Se já vier um endereço .json completo, usa-o primeiro.
        if self.board_raw.lower().endswith(".json"):
            urls.append(self.board_raw)
        # A forma com slug é útil em alguns redirects do Trello.
        if self.slug:
            urls.append(f"https://trello.com/b/{self.board}/{self.slug}.json")
        urls.append(f"https://trello.com/b/{self.board}.json")
        # preserva ordem removendo duplicatas
        return list(dict.fromkeys(urls))

    def _public_payload(self) -> dict[str, Any]:
        errors: list[str] = []
        for url in self._candidate_urls():
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:160]}")
                continue

            if not response.ok:
                errors.append(f"{url}: HTTP {response.status_code}")
                continue

            try:
                payload = response.json()
            except ValueError:
                errors.append(f"{url}: resposta não era JSON")
                continue

            if isinstance(payload, dict) and ("cards" in payload or "lists" in payload):
                return payload
            errors.append(f"{url}: JSON sem cards/lists")

        detail = " | ".join(errors[-3:])
        raise TrelloError(
            "Não foi possível ler o quadro pelo link do Trello. "
            "Confirme se o link permite acesso ao quadro."
            + (f" Detalhe: {detail}" if detail else "")
        )

    def snapshot(self) -> dict[str, Any]:
        payload = self._public_payload()

        cards = [c for c in (payload.get("cards") or []) if not c.get("closed")]
        lists = [x for x in (payload.get("lists") or []) if not x.get("closed")]
        actions = list(payload.get("actions") or [])
        # Export do Trello costuma trazer ações em ordem decrescente; limitamos
        # para o radar não carregar dados desnecessários em memória.
        actions = actions[:1000]

        board = {
            "id": payload.get("id"),
            "name": payload.get("name"),
            "url": payload.get("url") or payload.get("shortUrl"),
            "shortLink": payload.get("shortLink") or self.board,
            "dateLastActivity": payload.get("dateLastActivity"),
        }

        return {
            "board": board,
            "lists": lists,
            "members": list(payload.get("members") or []),
            "custom_fields": list(payload.get("customFields") or []),
            "cards": cards,
            "actions": actions,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


def decode_custom_fields(card: dict[str, Any], custom_fields: list[dict[str, Any]]) -> dict[str, Any]:
    field_by_id = {str(field.get("id")): field for field in custom_fields}
    output: dict[str, Any] = {}

    for item in card.get("customFieldItems") or []:
        field = field_by_id.get(str(item.get("idCustomField")))
        if not field:
            continue
        name = str(field.get("name") or item.get("idCustomField") or "Campo")
        field_type = str(field.get("type") or "")
        value_obj = item.get("value") or {}
        value: Any = None

        if field_type == "list":
            option_id = str(item.get("idValue") or "")
            for option in (field.get("options") or []):
                if str(option.get("id")) == option_id:
                    value = (option.get("value") or {}).get("text")
                    break
        elif field_type == "checkbox":
            raw = value_obj.get("checked")
            value = str(raw).lower() == "true" if raw is not None else None
        elif field_type == "date":
            value = value_obj.get("date")
        elif field_type == "number":
            value = value_obj.get("number")
        else:
            value = value_obj.get("text")

        output[name] = value
    return output


def find_custom_value(fields: dict[str, Any], *needles: str) -> Any:
    normalized = {name: _norm(name) for name in fields}
    for needle in needles:
        target = _norm(needle)
        for name, normalized_name in normalized.items():
            if target and target in normalized_name:
                return fields.get(name)
    return None
