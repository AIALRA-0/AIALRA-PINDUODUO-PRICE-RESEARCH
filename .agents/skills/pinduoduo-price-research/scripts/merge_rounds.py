#!/usr/bin/env python3
"""Deduplicate 拼多多 rounds, calculate saturation, and build a detail shortlist."""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from domain_lib import canonical_item_url, normalized_text, parse_money, require_list, require_object


OBVIOUS_EXCLUSION_RE = re.compile(
    r"\b(?:box only|empty box|manual only|replacement|repair service|rental|"
    r"for parts|parts only|not working|broken|pre[- ]?order|deposit|case only|"
    r"hard case|carrying case|protective case|lens shade|cable only|adapter only|"
    r"lens only|mount only|wanted)\b|"
    r"空盒|仅包装|配件专用|维修服务|出租|求购|定金|预售|坏件|拆机件",
    re.IGNORECASE,
)


def contains_term(text: str, term: str) -> bool:
    if term in text:
        return True
    compact_text = re.sub(r"[\W_]+", "", text)
    compact_term = re.sub(r"[\W_]+", "", term)
    return bool(compact_term and compact_term in compact_text)


def build_shortlist(payload: dict[str, Any]) -> dict[str, Any]:
    plan = require_object(payload.get("plan"), "plan")
    product = require_object(plan.get("product"), "plan.product")
    collection = require_object(plan.get("collection"), "plan.collection")
    rounds = require_list(payload.get("rounds"), "rounds")
    candidates = require_list(payload.get("candidates"), "candidates")
    excluded_terms = {normalized_text(value) for value in product.get("excluded_terms", []) if normalized_text(value)}
    required_terms = {normalized_text(value) for value in product.get("required_terms", []) if normalized_text(value)}
    identity_phrases = {
        normalized_text(value)
        for value in product.get("identity_phrases", [])
        if normalized_text(value)
    }
    unique: dict[str, dict[str, Any]] = {}
    new_by_round: list[int] = []
    seen_before: set[str] = set()
    for round_data in rounds:
        round_id = round_data["round_id"]
        round_candidates = [candidate for candidate in candidates if candidate.get("round_id") == round_id]
        current_ids = {candidate["platform_item_id"] for candidate in round_candidates}
        new_by_round.append(len(current_ids - seen_before))
        seen_before.update(current_ids)
        for candidate in round_candidates:
            identifier = candidate["platform_item_id"]
            existing = unique.get(identifier)
            if existing is None:
                url = canonical_item_url(candidate["url"], identifier)
                if url is None:
                    continue
                unique[identifier] = {
                    "candidate_id": candidate["candidate_id"],
                    "platform_item_id": identifier,
                    "title": candidate["title"],
                    "displayed_price": candidate["displayed_price"],
                    "currency": candidate["currency"],
                    "buying_formats": list(dict.fromkeys(candidate["buying_formats"])),
                    "condition_summary": candidate["condition_summary"],
                    "seller_name": candidate["seller_name"],
                    "shipping_text": candidate["shipping_text"],
                    "image_url": candidate["image_url"],
                    "url": url,
                    "source_backends": [candidate["source_backend"]],
                    "seen_in_rounds": [round_id],
                    "matched_queries": [candidate["query"]],
                    "rank_history": [candidate["result_rank"]],
                    "price_observations": [candidate["displayed_price"]],
                    "first_seen_at": candidate["retrieved_at"],
                    "last_seen_at": candidate["retrieved_at"],
                }
                continue
            if candidate["source_backend"] not in existing["source_backends"]:
                existing["source_backends"].append(candidate["source_backend"])
            if round_id not in existing["seen_in_rounds"]:
                existing["seen_in_rounds"].append(round_id)
            if candidate["query"] not in existing["matched_queries"]:
                existing["matched_queries"].append(candidate["query"])
            for buying_format in candidate["buying_formats"]:
                if buying_format not in existing["buying_formats"]:
                    existing["buying_formats"].append(buying_format)
            existing["rank_history"].append(candidate["result_rank"])
            existing["price_observations"].append(candidate["displayed_price"])
            existing["last_seen_at"] = max(existing["last_seen_at"], candidate["retrieved_at"])
            price = parse_money(candidate["displayed_price"])
            old_price = parse_money(existing["displayed_price"])
            if candidate["currency"] == existing["currency"] and price is not None and (old_price is None or price < old_price):
                existing["displayed_price"] = candidate["displayed_price"]
                existing["shipping_text"] = candidate["shipping_text"]
    selected: list[dict[str, Any]] = []
    removed = 0
    for item in unique.values():
        title = normalized_text(item["title"])
        if OBVIOUS_EXCLUSION_RE.search(title) or any(contains_term(title, term) for term in excluded_terms):
            removed += 1
            continue
        if required_terms and not all(contains_term(title, term) for term in required_terms):
            removed += 1
            continue
        if identity_phrases and not any(
            contains_term(title, phrase) for phrase in identity_phrases
        ):
            removed += 1
            continue
        selected.append(item)
    comparison_currency = plan["purchase_context"]["comparison_currency"]

    def order_key(item: dict[str, Any]) -> tuple[bool, Decimal, int, int, str]:
        price = parse_money(item["displayed_price"])
        return (
            item["currency"] != comparison_currency,
            price if price is not None else Decimal("Infinity"),
            -len(item["seen_in_rounds"]),
            min(item["rank_history"]),
            item["platform_item_id"],
        )

    selected.sort(key=order_key)
    shortlist = selected[: collection["detail_limit"]]
    threshold = collection["saturation"]["min_new_unique_per_round"]
    saturated = len(rounds) >= collection["minimum_rounds"] and len(new_by_round) >= 2 and all(value <= threshold for value in new_by_round[-2:])
    return {
        "plan": plan,
        "access": payload["access"],
        "round_coverage": {
            "rounds_executed": len(rounds),
            "unique_candidates": len(unique),
            "new_unique_by_round": new_by_round,
            "duplicate_observations": len(candidates) - len(unique),
            "source_backends": list(dict.fromkeys(round_data["source_backend"] for round_data in rounds)),
            "saturated": saturated,
            "stop_reason": payload["collection_status"]["stop_reason"],
            "blocked_reasons": payload["collection_status"]["blocked_reasons"],
        },
        "filter_summary": {
            "input_observations": len(candidates),
            "obvious_mismatches_removed": removed,
            "selected_for_detail": len(shortlist),
        },
        "shortlist": shortlist,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        result = build_shortlist(payload)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
