from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

import requests

BASE_URL = "https://api.trello.com/1"


class TrelloError(RuntimeError):
    pass


def _norm(text: Any) -> str:
    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", value).strip().upper()


def board_identifier(value: str) -> str:
    """Aceita shortLink, id ou URL do board e devolve um identificador aceito pela API."""
    value = str(value or "").strip()
    match = re.search(r"trello\.com/b/([^/?#]+)", value, flags=re.I)
    return match.group(1) if match else value


class TrelloClient:
    def __init__(self, api_key: str, token: str, board: str, timeout: int = 20):
        self.api_key = str(api_key or "").strip()
        self.token = str(token or "").strip()
        self.board = board_identifier(board)
        self.timeout = timeout
        self.session = requests.Session()
        if not self.api_key or not self.token or not self.board:
            raise TrelloError("Configure TRELLO_API_KEY, TRELLO_TOKEN e TRELLO_BOARD nos Secrets do Streamlit.")

    def _get(self, path: str, **params: Any) -> Any:
        query = {"key": self.api_key, "token": self.token, **params}
        try:
            response = self.session.get(f"{BASE_URL}{path}", params=query, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TrelloError(f"Falha de conexão com o Trello: {exc}") from exc
        if not response.ok:
            detail = response.text[:300].replace("\n", " ")
            raise TrelloError(f"Trello retornou HTTP {response.status_code}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise TrelloError("O Trello retornou uma resposta inválida.") from exc

    def board_info(self) -> dict[str, Any]:
        return self._get(f"/boards/{self.board}", fields="id,name,url,shortLink,dateLastActivity")

    def lists(self) -> list[dict[str, Any]]:
        return self._get(f"/boards/{self.board}/lists", fields="id,name,pos,closed", filter="open")

    def members(self) -> list[dict[str, Any]]:
        return self._get(f"/boards/{self.board}/members", fields="id,fullName,username,initials")

    def custom_fields(self) -> list[dict[str, Any]]:
        # Requer Power-Up de Custom Fields no board; se não houver, a API pode devolver [].
        try:
            return self._get(f"/boards/{self.board}/customFields")
        except TrelloError:
            return []

    def cards(self) -> list[dict[str, Any]]:
        fields = ",".join([
            "id", "name", "desc", "due", "dueComplete", "dateLastActivity",
            "idList", "idMembers", "labels", "url", "shortLink", "closed",
        ])
        return self._get(
            f"/boards/{self.board}/cards",
            filter="open",
            fields=fields,
            customFieldItems="true",
        )

    def recent_actions(self, limit: int = 1000) -> list[dict[str, Any]]:
        # Uma chamada para o board é muito mais rápida que uma chamada por cartão.
        # Se o filtro específico falhar por variação da API, usamos updateCard/commentCard amplo.
        filters = ["commentCard,updateCard:idList", "commentCard,updateCard"]
        for action_filter in filters:
            try:
                return self._get(
                    f"/boards/{self.board}/actions",
                    filter=action_filter,
                    limit=min(max(int(limit), 1), 1000),
                    fields="id,date,type,data,idMemberCreator,memberCreator",
                    memberCreator="true",
                    memberCreator_fields="id,fullName,username",
                )
            except TrelloError:
                continue
        return []

    def snapshot(self) -> dict[str, Any]:
        board = self.board_info()
        lists = self.lists()
        members = self.members()
        fields = self.custom_fields()
        cards = self.cards()
        actions = self.recent_actions()
        return {
            "board": board,
            "lists": lists,
            "members": members,
            "custom_fields": fields,
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
