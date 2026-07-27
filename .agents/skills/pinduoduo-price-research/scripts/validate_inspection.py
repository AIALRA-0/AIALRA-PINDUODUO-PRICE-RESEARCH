#!/usr/bin/env python3
"""Validate that 拼多多 detail evidence belongs to the requested shortlist."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from domain_lib import canonical_item_url, parse_money, require_list, require_object, time_is_fresh


def validate(shortlist: dict[str, Any], inspection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if inspection.get("plan") != shortlist.get("plan"):
        errors.append("inspection must preserve the complete plan")
    if inspection.get("access") != shortlist.get("access"):
        errors.append("inspection must preserve the access preflight")
    if inspection.get("round_coverage") != shortlist.get("round_coverage"):
        errors.append("inspection must preserve round coverage")
    expected = {item["platform_item_id"]: item for item in require_list(shortlist.get("shortlist"), "shortlist")}
    offers = require_list(inspection.get("offers"), "offers")
    seen: set[str] = set()
    verified = 0
    reviews_inspected = 0
    for offer in offers:
        identifier = offer.get("platform_item_id")
        if identifier in seen:
            errors.append(f"duplicate inspected item: {identifier}")
        seen.add(identifier)
        source = expected.get(identifier)
        if source is None:
            errors.append(f"inspection contains item outside shortlist: {identifier}")
            continue
        if offer.get("offer_id") != source["candidate_id"]:
            errors.append(f"offer_id must preserve candidate_id: {identifier}")
        if canonical_item_url(offer.get("url"), identifier) != source["url"]:
            errors.append(f"inspection URL does not match shortlist: {identifier}")
        if offer.get("seen_in_rounds") != source["seen_in_rounds"]:
            errors.append(f"inspection changed seen_in_rounds: {identifier}")
        if offer.get("rank_history") != source["rank_history"]:
            errors.append(f"inspection changed rank_history: {identifier}")
        if offer.get("search_backends") != source["source_backends"]:
            errors.append(f"inspection changed search backends: {identifier}")
        if offer.get("detail_backend") != shortlist.get("access", {}).get("source_backend"):
            errors.append(f"inspection changed backend after preflight: {identifier}")
        if not time_is_fresh(offer.get("retrieved_at")):
            errors.append(f"inspection time is missing, invalid, or stale: {identifier}")
        if offer.get("evidence_level") == "A":
            verified += 1
            if parse_money(offer.get("price")) is None:
                errors.append(f"A-level evidence requires a direct price: {identifier}")
            if offer.get("currency") == "unknown":
                errors.append(f"A-level evidence requires a currency: {identifier}")
            if not offer.get("image_urls"):
                errors.append(f"A-level evidence requires at least one direct image: {identifier}")
        if offer.get("discount_verified") and parse_money(offer.get("discount")) is None:
            errors.append(f"verified discount requires a numeric amount: {identifier}")
        if offer.get("reviews", {}).get("inspected"):
            reviews_inspected += 1
    coverage = require_object(inspection.get("inspection_coverage"), "inspection_coverage")
    failed_urls = require_list(coverage.get("failed_urls"), "failed_urls")
    if coverage.get("details_attempted") != len(offers) + len(failed_urls):
        errors.append("details_attempted must equal offers plus failed URLs")
    if coverage.get("details_attempted", 0) > len(expected):
        errors.append("details_attempted exceeds the shortlist")
    if coverage.get("details_verified") != verified:
        errors.append("details_verified must equal A-level offers")
    if coverage.get("reviews_inspected") != reviews_inspected:
        errors.append("reviews_inspected must equal offers with inspected reviews")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        shortlist = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        inspection = require_object(json.loads(args.output.read_text(encoding="utf-8")), "output")
        errors = validate(shortlist, inspection)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
