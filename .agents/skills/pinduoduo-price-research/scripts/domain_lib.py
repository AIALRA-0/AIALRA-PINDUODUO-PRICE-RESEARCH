#!/usr/bin/env python3
"""Shared deterministic helpers for one configured retail platform"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlsplit, urlunsplit


CONFIG = json.loads(
    (Path(__file__).resolve().parents[1] / "platform.json").read_text(encoding="utf-8")
)
MARKETPLACE_HOSTS = CONFIG["marketplace_hosts"]
ALLOWED_ITEM_HOSTS = set(CONFIG["item_hosts"])
UNKNOWN_VALUES = {"", "unknown", "未知", "不详", "null", "none", "-"}
MONEY_RE = re.compile(r"^\d+(?:\.\d{1,2})?$")


def normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def parse_money(value: Any) -> Decimal | None:
    if not isinstance(value, str):
        return None
    cleaned = unicodedata.normalize("NFKC", value).strip().replace(",", "")
    if normalized_text(cleaned) in UNKNOWN_VALUES:
        return None
    cleaned = re.sub(
        r"^(?:US|C|AU|JP|CA)?[$£€¥￥]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not MONEY_RE.fullmatch(cleaned):
        return None
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    return number if number >= 0 else None


def format_money(value: Decimal | None) -> str:
    if value is None:
        return "unknown"
    return format(value.quantize(Decimal("0.01")), "f")


def _configured_id(raw: Any) -> tuple[str, str] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = urlsplit(raw.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_ITEM_HOSTS:
        return None
    for key in CONFIG.get("id_query_keys", []):
        values = parse_qs(parsed.query).get(key, [])
        if values and re.fullmatch(CONFIG["item_id_pattern"], values[0]):
            return host, values[0]
    normalized_path = re.sub(r"/+", "/", parsed.path or "/")
    for pattern in CONFIG.get("id_path_patterns", []):
        match = re.search(pattern, normalized_path, re.IGNORECASE)
        if match and re.fullmatch(CONFIG["item_id_pattern"], match.group(1)):
            return host, match.group(1)
    return None


def item_id_from_url(raw: Any) -> str | None:
    configured = _configured_id(raw)
    return configured[1] if configured else None


def canonical_item_url(raw: Any, item_id: Any = None) -> str | None:
    configured = _configured_id(raw)
    identifier = str(item_id) if item_id is not None else (
        configured[1] if configured else ""
    )
    if not re.fullmatch(CONFIG["item_id_pattern"], identifier):
        return None
    if configured is None:
        return None
    host = CONFIG.get("canonical_host") or configured[0]
    path = CONFIG["canonical_path_template"].format(item_id=identifier)
    query = CONFIG.get("canonical_query_template", "").format(item_id=identifier)
    return urlunsplit(("https", host, path, query, ""))


def official_search_url(
    marketplace: str,
    query: str,
    sort_mode: str = "relevance",
) -> str:
    host = MARKETPLACE_HOSTS.get(marketplace)
    if host is None:
        raise ValueError("unsupported marketplace")
    templates = CONFIG["search_url_templates"]
    template = templates.get(sort_mode, templates["relevance"])
    return template.format(host=host, query=quote_plus(query))


def parse_aware_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def time_is_fresh(value: Any, *, hours: int = 24) -> bool:
    parsed = parse_aware_time(value)
    if parsed is None:
        return False
    age = dt.datetime.now(dt.timezone.utc) - parsed.astimezone(dt.timezone.utc)
    return -dt.timedelta(minutes=5) <= age <= dt.timedelta(hours=hours)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value
