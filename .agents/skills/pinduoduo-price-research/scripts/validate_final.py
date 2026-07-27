#!/usr/bin/env python3
"""Validate 拼多多 recommendation and ranking invariants."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from domain_lib import canonical_item_url, parse_money, require_list, require_object, time_is_fresh


def validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    offers = require_list(payload.get("offers"), "offers")
    if [offer.get("rank") for offer in offers] != list(range(1, len(offers) + 1)):
        errors.append("offer ranks must be consecutive and ordered")
    recommendation = require_object(payload.get("recommendation"), "recommendation")
    winner_id = recommendation.get("winner_id")
    decision = recommendation.get("decision_type")
    eligible = [offer for offer in offers if offer.get("eligible")]
    winners = [offer for offer in eligible if offer.get("offer_id") == winner_id]
    for offer in offers:
        if canonical_item_url(offer.get("url")) != offer.get("url"):
            errors.append(f"offer URL is not canonical: {offer.get('offer_id')}")
        if offer.get("eligible") and offer.get("exclusion_reasons"):
            errors.append(f"eligible offer contains exclusion reasons: {offer.get('offer_id')}")
        if offer.get("eligible") and offer.get("risk_level") == "high":
            errors.append(f"high-risk offer cannot be eligible: {offer.get('offer_id')}")
        if offer.get("eligible") and offer.get("price_scope") == "current-bid":
            errors.append(f"auction current bid cannot be an eligible winner: {offer.get('offer_id')}")
        if not time_is_fresh(offer.get("retrieved_at")):
            errors.append(f"offer time is missing, invalid, or stale: {offer.get('offer_id')}")
    if payload.get("status") == "no-result":
        if winner_id or eligible:
            errors.append("no-result must not contain an eligible winner")
    else:
        if len(winners) != 1:
            errors.append("complete or partial result must name exactly one eligible winner")
        elif winners[0] is not eligible[0]:
            errors.append("winner must be the first eligible ranked offer")
    if decision == "lowest-complete-total" and winners:
        if winners[0].get("cost_completeness") != "complete":
            errors.append("lowest-complete-total requires complete cost")
        candidates = [offer for offer in eligible if offer.get("cost_completeness") == "complete"]
    elif decision == "lowest-known-pre-tax-total" and winners:
        if any(offer.get("cost_completeness") == "complete" for offer in eligible):
            errors.append("pre-tax decision is invalid while a complete offer exists")
        candidates = eligible
    else:
        candidates = []
    if winners and candidates:
        winner_total = parse_money(winners[0].get("known_total"))
        minimum = min(parse_money(offer.get("known_total")) or Decimal("Infinity") for offer in candidates)
        if winner_total != minimum:
            errors.append("winner is not the lowest comparable eligible offer")
    if len(payload.get("manual_search_urls", [])) < 3:
        errors.append("at least three direct search URLs are required")
    if decision == "no-viable-offer" and eligible:
        errors.append("no-viable-offer is invalid while eligible offers exist")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = require_object(json.loads(args.output.read_text(encoding="utf-8")), "output")
        errors = validate(payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
