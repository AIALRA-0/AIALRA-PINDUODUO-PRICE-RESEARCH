#!/usr/bin/env python3
"""Validate direct 拼多多 search observations and multi-round coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from domain_lib import canonical_item_url, item_id_from_url, parse_money, require_list, require_object, time_is_fresh


def new_unique_counts(rounds: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[int]:
    seen: set[str] = set()
    counts: list[int] = []
    for round_data in rounds:
        current = {candidate["platform_item_id"] for candidate in candidates if candidate.get("round_id") == round_data.get("round_id")}
        counts.append(len(current - seen))
        seen.update(current)
    return counts


def validate(access_result: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    plan = require_object(access_result.get("plan"), "input.plan")
    if payload.get("plan") != plan:
        errors.append("round results must preserve the complete plan")
    if payload.get("access") != access_result.get("access"):
        errors.append("round results must preserve the access preflight")
    rounds = require_list(payload.get("rounds"), "rounds")
    candidates = require_list(payload.get("candidates"), "candidates")
    collection = require_object(plan.get("collection"), "plan.collection")
    if not collection["minimum_rounds"] <= len(rounds) <= collection["maximum_rounds"]:
        errors.append("executed round count is outside the planned limits")
    if len(candidates) > collection["candidate_limit"]:
        errors.append("candidate observations exceed candidate_limit")
    expected_backend = access_result.get("access", {}).get("source_backend")
    round_map: dict[str, dict[str, Any]] = {}
    for round_data in rounds:
        if not isinstance(round_data, dict):
            errors.append("every round must be an object")
            continue
        identifier = round_data.get("round_id")
        if identifier in round_map:
            errors.append(f"duplicate round_id: {identifier}")
        round_map[identifier] = round_data
        if round_data.get("query") not in collection["query_variants"]:
            errors.append(f"round query was not planned: {round_data.get('query')}")
        if round_data.get("sort_mode") not in collection["sort_modes"]:
            errors.append(f"round sort mode was not planned: {round_data.get('sort_mode')}")
        if round_data.get("source_backend") != expected_backend:
            errors.append(f"round changed backend after preflight: {identifier}")
        if not time_is_fresh(round_data.get("retrieved_at")):
            errors.append(f"round time is missing, invalid, or stale: {identifier}")
    candidate_ids: set[str] = set()
    observed_counts = {identifier: 0 for identifier in round_map}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append("every candidate must be an object")
            continue
        candidate_id = candidate.get("candidate_id")
        if candidate_id in candidate_ids:
            errors.append(f"duplicate candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)
        round_id = candidate.get("round_id")
        round_data = round_map.get(round_id)
        if round_data is None:
            errors.append(f"candidate references unknown round: {round_id}")
            continue
        observed_counts[round_id] += 1
        if candidate.get("query") != round_data.get("query") or candidate.get("sort_mode") != round_data.get("sort_mode"):
            errors.append(f"candidate round metadata mismatch: {candidate_id}")
        if candidate.get("source_backend") != round_data.get("source_backend"):
            errors.append(f"candidate source backend mismatch: {candidate_id}")
        item_id = candidate.get("platform_item_id")
        if canonical_item_url(candidate.get("url"), item_id) is None or item_id_from_url(candidate.get("url")) != item_id:
            errors.append(f"candidate URL and item ID do not match: {candidate_id}")
        if candidate.get("displayed_price") != "unknown" and parse_money(candidate.get("displayed_price")) is None:
            errors.append(f"candidate displayed price is invalid: {candidate_id}")
        if not time_is_fresh(candidate.get("retrieved_at")):
            errors.append(f"candidate time is missing, invalid, or stale: {candidate_id}")
    for round_id, count in observed_counts.items():
        if round_map[round_id].get("result_count") != count:
            errors.append(f"round result_count does not match candidates: {round_id}")
    counts = new_unique_counts([value for value in rounds if isinstance(value, dict)], [value for value in candidates if isinstance(value, dict)])
    status = require_object(payload.get("collection_status"), "collection_status")
    if status.get("stop_reason") == "saturated":
        threshold = collection["saturation"]["min_new_unique_per_round"]
        if len(counts) < collection["minimum_rounds"] or len(counts) < 2 or not all(value <= threshold for value in counts[-2:]):
            errors.append("saturated stop requires two consecutive low-yield rounds after the minimum")
    if not candidates and access_result.get("access", {}).get("visible_state") != "no-results-visible":
        errors.append("empty candidates require a visible no-results state from preflight")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        access_result = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        payload = require_object(json.loads(args.output.read_text(encoding="utf-8")), "output")
        errors = validate(access_result, payload)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
