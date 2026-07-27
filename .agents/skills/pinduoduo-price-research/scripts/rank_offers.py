#!/usr/bin/env python3
"""Compute comparable 拼多多 totals, eligibility, risk, and recommendation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from domain_lib import canonical_item_url, format_money, official_search_url, parse_money, require_list, require_object


def condition_matches(requested: str, actual: str) -> bool:
    if requested == "any":
        return actual not in {"parts-only", "unknown"}
    if requested == "refurbished":
        return actual in {"certified-refurbished", "seller-refurbished"}
    return requested == actual


def risk_for(offer: dict[str, Any], median_price: Decimal | None) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if offer["match_confidence"] == "medium":
        add(12, "商品身份只有中等置信匹配")
    elif offer["match_confidence"] == "low":
        add(30, "商品身份匹配度低")
    if offer["listing_type"] != "product":
        add(35, f"详情类型为 {offer['listing_type']}")
    if offer["listing_state"] != "active":
        add(30, f"商品状态为 {offer['listing_state']}")
    if offer["condition"] == "seller-refurbished":
        add(6, "翻新标准由卖家自行声明")
    if offer["condition"] in {"parts-only", "unknown"}:
        add(20, "成色无法作为正常商品核验")
    feedback = parse_money(offer["seller"]["feedback_percent"])
    feedback_count = parse_money(offer["seller"]["feedback_count"])
    if feedback is None:
        add(8, "卖家好评率未知")
    elif feedback < Decimal("98"):
        add(15, "卖家好评率低于 98%")
    if feedback_count is None:
        add(6, "卖家反馈数量未知")
    elif feedback_count < Decimal("50"):
        add(10, "卖家反馈数量少于 50")
    if offer["policy"]["returns"] == "not-accepted":
        add(14, "卖家不接受退货")
    elif offer["policy"]["returns"] == "unknown":
        add(8, "退货政策未知")
    if offer["policy"]["warranty"] in {"unknown", "未知", "不详"}:
        add(5, "保修信息未知")
    if offer["price_scope"] in {"coupon", "account-personalized"}:
        add(5, "价格带有优惠码或账户条件")
    if offer["price_scope"] == "current-bid":
        add(18, "当前出价不是最终成交价")
    for signal in offer["signals"]["negative_signals"]:
        add(6, f"风险信号 {signal}")
    for contradiction in offer["signals"]["contradictions"]:
        add(9, f"页面信息矛盾 {contradiction}")
    for theme in offer["reviews"]["negative_themes"]:
        add(5, f"评价负面主题 {theme}")
    price = parse_money(offer["price"])
    if median_price is not None and price is not None and price < median_price * Decimal("0.60"):
        add(25, "价格低于可比商品中位数的 60%")
    return min(score, 100), reasons


def review_summary(offer: dict[str, Any]) -> str:
    reviews = offer["reviews"]
    if not reviews["inspected"]:
        return "未读取商品评价"
    if reviews["negative_themes"]:
        return f"商品评分 {reviews['rating']} 负面主题 {'、'.join(reviews['negative_themes'])}"
    return f"商品评分 {reviews['rating']} 评价数 {reviews['rating_count']}"


def ranked_output(payload: dict[str, Any]) -> dict[str, Any]:
    plan = require_object(payload.get("plan"), "plan")
    product = require_object(plan.get("product"), "plan.product")
    constraints = require_object(plan.get("constraints"), "plan.constraints")
    context = require_object(plan.get("purchase_context"), "plan.purchase_context")
    offers = require_list(payload.get("offers"), "offers")
    comparison_currency = context["comparison_currency"]
    prices = [
        price
        for offer in offers
        for price in [parse_money(offer.get("price"))]
        if price is not None
        and offer.get("currency") == comparison_currency
        and offer.get("listing_type") == "product"
        and offer.get("match_confidence") != "low"
    ]
    median_price = Decimal(str(statistics.median(prices))) if prices else None
    budget = parse_money(constraints["maximum_budget"])
    allowed_formats = set(constraints["allowed_buying_formats"])
    evaluated: list[dict[str, Any]] = []
    for offer in offers:
        price = parse_money(offer["price"])
        shipping = parse_money(offer["shipping"])
        import_charges = parse_money(offer["import_charges"])
        tax = parse_money(offer["tax"])
        discount = parse_money(offer["discount"]) if offer["discount_verified"] else Decimal("0")
        if price is None:
            known_total = None
        else:
            known_total = max(
                price + (shipping or 0) + (import_charges or 0) + (tax or 0) - (discount or 0),
                Decimal("0"),
            )
        if None not in {shipping, import_charges, tax}:
            completeness = "complete"
        elif shipping is not None and import_charges is not None:
            completeness = "pre-tax-only"
        else:
            completeness = "display-only"
        exclusions: list[str] = []
        if offer["listing_type"] != "product":
            exclusions.append("不是完整目标商品")
        if offer["listing_state"] != "active":
            exclusions.append("商品当前不是在售状态")
        if offer["match_confidence"] == "low":
            exclusions.append("商品身份匹配度低")
        if not condition_matches(product["condition"], offer["condition"]):
            exclusions.append("商品成色不符合请求")
        if not allowed_formats.intersection(offer["buying_formats"]):
            exclusions.append("购买形式不符合请求")
        if offer["price_scope"] == "current-bid" or (
            "auction" in offer["buying_formats"]
            and not {"fixed-price", "best-offer"}.intersection(offer["buying_formats"])
        ):
            exclusions.append("拍卖当前价不是最终可购买总价")
        if offer["availability"] not in {"in-stock", "limited"}:
            exclusions.append("商品当前无法确认有货")
        if offer["evidence_level"] != "A":
            exclusions.append("缺少 A 级详情证据")
        if price is None:
            exclusions.append("详情价格无法核验")
        if offer["currency"] != comparison_currency:
            exclusions.append("币种不同且未使用实时汇率换算")
        if constraints["require_returns"] and offer["policy"]["returns"] != "accepted":
            exclusions.append("退货政策不符合请求")
        if shipping is None and not constraints["allow_unknown_shipping"]:
            exclusions.append("运费未知且用户不接受未知运费")
        if budget is not None and known_total is not None and known_total > budget:
            exclusions.append("超过用户预算")
        risk_score, risk_reasons = risk_for(offer, median_price)
        risk_level = "low" if risk_score <= 19 else "medium" if risk_score <= 39 else "high"
        if risk_level == "high":
            exclusions.append("综合风险为高")
        canonical_url = canonical_item_url(offer["url"], offer["platform_item_id"])
        if canonical_url is None:
            exclusions.append("商品链接不属于受支持的 拼多多 市场")
            canonical_url = offer["url"]
        evaluated.append(
            {
                "rank": 1,
                "offer_id": offer["offer_id"],
                "title": offer["title"],
                "seller_name": offer["seller"]["name"],
                "url": canonical_url,
                "image_urls": offer["image_urls"],
                "search_backends": offer["search_backends"],
                "detail_backend": offer["detail_backend"],
                "condition": offer["condition"],
                "buying_formats": offer["buying_formats"],
                "currency": offer["currency"],
                "price": format_money(price),
                "known_total": format_money(known_total),
                "cost_completeness": completeness,
                "price_scope": offer["price_scope"],
                "eligible": not exclusions,
                "exclusion_reasons": exclusions,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "risk_reasons": risk_reasons,
                "review_summary": review_summary(offer),
                "evidence_level": offer["evidence_level"],
                "seen_in_rounds": offer["seen_in_rounds"],
                "rank_history": offer["rank_history"],
                "retrieved_at": offer["retrieved_at"],
            }
        )

    def order_key(item: dict[str, Any]) -> tuple[bool, int, Decimal, int, str]:
        completeness_order = {"complete": 0, "pre-tax-only": 1, "display-only": 2}
        amount = parse_money(item["known_total"])
        return (
            not item["eligible"],
            completeness_order[item["cost_completeness"]],
            amount if amount is not None else Decimal("Infinity"),
            item["risk_score"],
            item["offer_id"],
        )

    evaluated.sort(key=order_key)
    for index, offer in enumerate(evaluated, start=1):
        offer["rank"] = index
    eligible = [offer for offer in evaluated if offer["eligible"]]
    complete = [offer for offer in eligible if offer["cost_completeness"] == "complete"]
    if complete:
        winner = complete[0]
        status = "complete"
        decision = "lowest-complete-total"
        summary = f"{winner['seller_name']} 的已核验含税已知总额最低 币种为 {winner['currency']} 风险等级为 {winner['risk_level']}"
    elif eligible:
        winner = eligible[0]
        status = "partial"
        decision = "lowest-known-pre-tax-total"
        summary = f"{winner['seller_name']} 的当前可比已知金额最低 税费或其他到手成本仍不完整"
    else:
        winner = None
        status = "no-result"
        decision = "no-viable-offer"
        summary = "没有同时满足商品身份 在售状态 成色 币种 详情证据和风险要求的候选"
    warnings = list(payload["round_coverage"]["blocked_reasons"])
    if any(item["cost_completeness"] != "complete" for item in eligible):
        warnings.append("部分可行商品缺少税费 运费或进口费用")
    if any(item["price_scope"] != "public" for item in eligible):
        warnings.append("部分价格带有优惠码 账户条件或其他价格范围")
    if not payload["round_coverage"]["saturated"]:
        warnings.append("多轮结果尚未达到连续两轮低新增的饱和条件")
    if any("auction" in item["buying_formats"] for item in evaluated):
        warnings.append("拍卖当前价仅作证据展示 不参与最低可购买总价结论")
    return {
        "status": status,
        "query_snapshot": {
            "request_text": plan["request_text"],
            "product": product["canonical_query"],
            "marketplace": context["marketplace"],
            "destination_country": context["destination_country"],
            "destination_region": context["destination_region"],
            "condition": product["condition"],
            "comparison_currency": comparison_currency,
            "retrieved_at": dt.datetime.now().astimezone().isoformat(),
        },
        "recommendation": {
            "decision_type": decision,
            "winner_id": winner["offer_id"] if winner else "",
            "summary": summary,
        },
        "offers": evaluated,
        "round_coverage": payload["round_coverage"],
        "inspection_coverage": payload["inspection_coverage"],
        "manual_search_urls": [official_search_url(context["marketplace"], query) for query in plan["collection"]["query_variants"]],
        "warnings": list(dict.fromkeys(warnings)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        result = ranked_output(payload)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
