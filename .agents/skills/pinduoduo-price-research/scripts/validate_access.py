#!/usr/bin/env python3
"""Validate that an 拼多多 backend passed a real search-transition preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from domain_lib import require_object, time_is_fresh


def validate(plan: dict, result: dict) -> list[str]:
    errors: list[str] = []
    if result.get("plan") != plan:
        errors.append("access preflight must preserve the complete plan")
    access = require_object(result.get("access"), "access")
    if access.get("marketplace") != plan.get("purchase_context", {}).get("marketplace"):
        errors.append("access marketplace must match the research plan")
    if access.get("search_transition_verified") is not True:
        errors.append("access preflight must verify an actual search transition")
    if not time_is_fresh(access.get("checked_at")):
        errors.append("access preflight time is missing, invalid, or stale")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        plan = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        result = require_object(json.loads(args.output.read_text(encoding="utf-8")), "output")
        errors = validate(plan, result)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
