from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = ROOT.name
SKILL = ROOT / ".agents" / "skills" / SKILL_NAME
sys.path.insert(0, str(SKILL / "scripts"))

from domain_lib import canonical_item_url, official_search_url  # noqa: E402
from merge_rounds import build_shortlist  # noqa: E402
from rank_offers import ranked_output  # noqa: E402
from validate_access import validate as validate_access  # noqa: E402
from validate_final import validate as validate_final  # noqa: E402
from validate_inspection import validate as validate_inspection  # noqa: E402
from validate_plan import validate as validate_plan  # noqa: E402
from validate_round_results import validate as validate_round_results  # noqa: E402


CASES = {
    "jd-price-research": {
        "marketplace": "jd.com",
        "country": "中国",
        "region": "上海",
        "currency": "CNY",
        "ids": ["100000000001", "100000000002", "100000000003", "100000000004"],
        "urls": [
            "https://item.jd.com/100000000001.html?utm_source=test",
            "https://item.jd.com/100000000002.html",
            "https://item.jd.com/100000000003.html",
            "https://item.jd.com/100000000004.html",
        ],
    },
    "pinduoduo-price-research": {
        "marketplace": "pinduoduo.com",
        "country": "中国",
        "region": "上海",
        "currency": "CNY",
        "ids": ["200000000001", "200000000002", "200000000003", "200000000004"],
        "urls": [
            "https://mobile.yangkeduo.com/goods.html?goods_id=200000000001&utm_source=test",
            "https://mobile.yangkeduo.com/goods.html?goods_id=200000000002",
            "https://mobile.yangkeduo.com/goods.html?goods_id=200000000003",
            "https://mobile.yangkeduo.com/goods.html?goods_id=200000000004",
        ],
    },
    "amazon-price-research": {
        "marketplace": "amazon.com",
        "country": "United States",
        "region": "California",
        "currency": "USD",
        "ids": ["B0ABCDEF01", "B0ABCDEF02", "B0ABCDEF03", "B0ABCDEF04"],
        "urls": [
            "https://www.amazon.com/example-product/dp/B0ABCDEF01?ref_=test",
            "https://www.amazon.com/dp/B0ABCDEF02",
            "https://www.amazon.com/gp/product/B0ABCDEF03",
            "https://www.amazon.com/dp/B0ABCDEF04",
        ],
    },
    "walmart-price-research": {
        "marketplace": "walmart.com",
        "country": "United States",
        "region": "California",
        "currency": "USD",
        "ids": ["300000001", "300000002", "300000003", "300000004"],
        "urls": [
            "https://www.walmart.com/ip/example-product/300000001?athbdg=test",
            "https://www.walmart.com/ip/300000002",
            "https://www.walmart.com/ip/example-product/300000003",
            "https://www.walmart.com/ip/300000004",
        ],
    },
}
CASE = CASES[SKILL_NAME]


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat()


def source() -> dict:
    return {
        "request_text": "搜索 RTX 5070 Ti 16GB 最便宜可行商品",
        "marketplace": CASE["marketplace"],
        "destination_country": CASE["country"],
        "destination_region": CASE["region"],
        "comparison_currency": CASE["currency"],
        "desired_condition": "new",
        "buying_formats": ["fixed-price"],
        "detail_limit": 6,
    }


def plan() -> dict:
    return {
        "request_text": source()["request_text"],
        "product": {
            "canonical_query": "RTX 5070 Ti 16GB",
            "category": "graphics card",
            "condition": "new",
            "required_terms": ["5070 Ti", "16GB"],
            "excluded_terms": ["box only", "cooler only", "wanted"],
        },
        "purchase_context": {
            "marketplace": CASE["marketplace"],
            "destination_country": CASE["country"],
            "destination_region": CASE["region"],
            "comparison_currency": CASE["currency"],
        },
        "constraints": {
            "maximum_budget": "unknown",
            "allowed_buying_formats": ["fixed-price"],
            "allow_unknown_shipping": True,
            "require_returns": False,
        },
        "collection": {
            "query_variants": [
                "RTX 5070 Ti 16GB",
                "GeForce 5070Ti 16G graphics card",
                "RTX5070Ti 16GB new",
            ],
            "sort_modes": ["relevance", "price-ascending", "newest"],
            "minimum_rounds": 3,
            "maximum_rounds": 5,
            "pages_per_round": 1,
            "candidate_limit": 80,
            "detail_limit": 6,
            "saturation": {
                "min_new_unique_per_round": 1,
                "consecutive_rounds": 2,
            },
            "pacing": {
                "maximum_parallel_pages": 1,
                "minimum_action_interval_seconds": 3,
                "risk_event_retries": 0,
                "reuse_observation_cache_seconds": 900,
            },
        },
        "assumptions": ["只比较完整显卡"],
    }


def access() -> dict:
    return {
        "plan": plan(),
        "access": {
            "source_backend": "aialra-shopping-browser",
            "marketplace": CASE["marketplace"],
            "search_transition_verified": True,
            "visible_state": "results-visible",
            "login_state": "signed-in",
            "checked_at": now_iso(),
        },
    }


def card(
    candidate_id: str,
    item_index: int,
    round_id: str,
    query: str,
    title: str,
    price: str,
    rank: int,
    sort_mode: str,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "platform_item_id": CASE["ids"][item_index],
        "round_id": round_id,
        "query": query,
        "sort_mode": sort_mode,
        "source_backend": "aialra-shopping-browser",
        "page_number": 1,
        "result_rank": rank,
        "title": title,
        "displayed_price": price,
        "currency": CASE["currency"],
        "buying_formats": ["fixed-price"],
        "condition_summary": "new",
        "seller_name": f"seller-{item_index}",
        "shipping_text": "free shipping",
        "image_url": "https://images.invalid/product.webp",
        "url": CASE["urls"][item_index],
        "retrieved_at": now_iso(),
    }


def rounds(access_payload: dict | None = None) -> dict:
    access_payload = access_payload or access()
    queries = access_payload["plan"]["collection"]["query_variants"]
    round_rows = [
        {
            "round_id": "round-1",
            "query": queries[0],
            "sort_mode": "relevance",
            "source_backend": "aialra-shopping-browser",
            "page_numbers": [1],
            "retrieved_at": now_iso(),
            "result_count": 3,
        },
        {
            "round_id": "round-2",
            "query": queries[1],
            "sort_mode": "price-ascending",
            "source_backend": "aialra-shopping-browser",
            "page_numbers": [1],
            "retrieved_at": now_iso(),
            "result_count": 2,
        },
        {
            "round_id": "round-3",
            "query": queries[2],
            "sort_mode": "newest",
            "source_backend": "aialra-shopping-browser",
            "page_numbers": [1],
            "retrieved_at": now_iso(),
            "result_count": 2,
        },
    ]
    candidates = [
        card("c1", 0, "round-1", queries[0], "RTX 5070 Ti 16GB Graphics Card", "799.00", 1, "relevance"),
        card("c2", 1, "round-1", queries[0], "GeForce RTX 5070Ti 16GB New", "829.00", 2, "relevance"),
        card("c3", 2, "round-1", queries[0], "RTX 5070 Ti box only", "20.00", 3, "relevance"),
        card("c4", 0, "round-2", queries[1], "RTX 5070 Ti 16GB Graphics Card", "799.00", 2, "price-ascending"),
        card("c5", 3, "round-2", queries[1], "RTX5070Ti 16GB OC Graphics Card", "849.00", 1, "price-ascending"),
        card("c6", 0, "round-3", queries[2], "RTX 5070 Ti 16GB Graphics Card", "799.00", 3, "newest"),
        card("c7", 3, "round-3", queries[2], "RTX5070Ti 16GB OC Graphics Card", "849.00", 2, "newest"),
    ]
    return {
        "plan": access_payload["plan"],
        "access": access_payload["access"],
        "collection_status": {
            "stop_reason": "saturated",
            "blocked_reasons": [],
        },
        "rounds": round_rows,
        "candidates": candidates,
    }


def offer(item: dict, price: str, *, risk: bool = False) -> dict:
    return {
        "offer_id": item["candidate_id"],
        "platform_item_id": item["platform_item_id"],
        "title": item["title"],
        "url": item["url"],
        "image_urls": [item["image_url"]],
        "search_backends": item["source_backends"],
        "detail_backend": "aialra-shopping-browser",
        "listing_type": "product",
        "listing_state": "active",
        "buying_formats": ["fixed-price"],
        "match_confidence": "high",
        "match_reasons": ["型号和显存一致"],
        "condition": "new",
        "selected_variant": "RTX 5070 Ti 16GB",
        "availability": "in-stock",
        "price": price,
        "shipping": "0",
        "import_charges": "0",
        "tax": "0",
        "discount": "0",
        "discount_verified": False,
        "currency": CASE["currency"],
        "price_scope": "public",
        "seller": {
            "name": item["seller_name"],
            "feedback_percent": "95.0" if risk else "99.5",
            "feedback_count": "20" if risk else "12000",
            "top_rated": not risk,
        },
        "policy": {
            "returns": "not-accepted" if risk else "accepted",
            "returns_window": "30 days",
            "warranty": "manufacturer warranty",
        },
        "reviews": {
            "inspected": True,
            "rating": "4.0" if risk else "4.8",
            "rating_count": "100",
            "negative_themes": ["包装破损"] if risk else [],
        },
        "signals": {
            "quantity_available": "3",
            "sold_count": "47",
            "negative_signals": [],
            "contradictions": ["运费信息冲突"] if risk else [],
        },
        "evidence_level": "A",
        "retrieved_at": now_iso(),
        "seen_in_rounds": item["seen_in_rounds"],
        "rank_history": item["rank_history"],
    }


def inspection(shortlist: dict, offers: list[dict]) -> dict:
    return {
        "plan": shortlist["plan"],
        "access": shortlist["access"],
        "round_coverage": shortlist["round_coverage"],
        "inspection_coverage": {
            "details_attempted": len(offers),
            "details_verified": len(offers),
            "reviews_inspected": len(offers),
            "failed_urls": [],
        },
        "offers": offers,
    }


class PlatformDomainTests(unittest.TestCase):
    def test_url_contract_and_direct_search_urls(self) -> None:
        self.assertEqual(
            canonical_item_url(CASE["urls"][0], CASE["ids"][0]),
            canonical_item_url(CASE["urls"][0]),
        )
        for sort_mode in ("relevance", "price-ascending", "newest"):
            self.assertTrue(
                official_search_url(CASE["marketplace"], "RTX 5070 Ti", sort_mode).startswith("https://")
            )

    def test_plan_access_and_schema_invariants(self) -> None:
        self.assertEqual([], validate_plan(source(), plan()))
        duplicate = plan()
        duplicate["collection"]["query_variants"][1] = duplicate["collection"]["query_variants"][0]
        self.assertTrue(validate_plan(source(), duplicate))
        access_payload = access()
        self.assertEqual([], validate_access(access_payload["plan"], access_payload))
        access_payload["access"]["search_transition_verified"] = False
        self.assertTrue(validate_access(access_payload["plan"], access_payload))

    def test_round_merge_deduplicates_and_filters_accessories(self) -> None:
        payload = rounds()
        access_payload = {"plan": payload["plan"], "access": payload["access"]}
        self.assertEqual([], validate_round_results(access_payload, payload))
        shortlist = build_shortlist(payload)
        self.assertEqual([3, 1, 0], shortlist["round_coverage"]["new_unique_by_round"])
        self.assertEqual(3, shortlist["round_coverage"]["duplicate_observations"])
        self.assertNotIn(
            CASE["ids"][2],
            {item["platform_item_id"] for item in shortlist["shortlist"]},
        )
        self.assertEqual(
            ["round-1", "round-2", "round-3"],
            shortlist["shortlist"][0]["seen_in_rounds"],
        )

    def test_ranking_selects_lowest_complete_low_risk_offer(self) -> None:
        shortlist = build_shortlist(rounds())
        offers = [
            offer(shortlist["shortlist"][0], "799.00"),
            offer(shortlist["shortlist"][1], "829.00", risk=True),
        ]
        payload = inspection(shortlist, offers)
        self.assertEqual([], validate_inspection(shortlist, payload))
        final = ranked_output(payload)
        self.assertEqual(offers[0]["offer_id"], final["recommendation"]["winner_id"])
        self.assertEqual([], validate_final(final))

    def test_workflow_is_read_only_bounded_and_classified(self) -> None:
        workflow = json.loads((SKILL / "workflow.yaml").read_text(encoding="utf-8"))
        nodes = {item["id"]: item for item in workflow["execution"]["graph"]["nodes"]}
        self.assertLessEqual(
            {item["side_effect"] for item in nodes.values()},
            {"none", "read"},
        )
        routing = nodes["preflight-access"]["action"]["arguments"]["source_routing"]
        self.assertEqual(["aialra-shopping-browser"], routing["provider_order"])
        self.assertEqual(
            {"provider_order", "providers", "selection_policy"},
            set(routing),
        )
        provider = routing["providers"]["aialra-shopping-browser"]
        self.assertIn("account-write", provider["prohibited_operation_classes"])
        self.assertIn("credential-read", provider["prohibited_operation_classes"])
        self.assertIn("policy-blocked", routing["selection_policy"]["hard_stop_kinds"])
        for node_id in ("preflight-access", "collect-search-rounds", "inspect-details"):
            node_data = nodes[node_id]
            arguments = node_data["action"]["arguments"]
            self.assertEqual(1, arguments["maximum_parallel_pages"])
            self.assertGreaterEqual(arguments["minimum_action_interval_seconds"], 3)
            self.assertEqual(0, arguments["risk_event_retries"])
            self.assertGreaterEqual(arguments["reuse_observation_cache_seconds"], 900)
            self.assertEqual(0, node_data["max_retries"])
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("至少准备三个不同查询词", skill_text)
        self.assertIn("禁止使用代理轮换", skill_text)
        self.assertIn("验证码", skill_text)


class PlatformRunnerEndToEndTests(unittest.TestCase):
    def run_runner(self, *arguments: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(SKILL / "scripts" / "runner.py"), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        return json.loads(completed.stdout)

    def test_runner_completes_full_graph(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)

            def write(name: str, value: dict) -> str:
                target = directory / name
                target.write_text(
                    json.dumps(value, ensure_ascii=False),
                    encoding="utf-8",
                )
                return str(target)

            started = self.run_runner("start", "--input", write("input.json", source()))
            state_id = started["state_id"]
            self.run_runner("advance", "--state-id", state_id)
            self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "plan-research",
                "--output",
                write("plan.json", plan()),
            )
            self.run_runner("advance", "--state-id", state_id)
            access_payload = access()
            self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "preflight-access",
                "--output",
                write("access.json", access_payload),
            )
            self.run_runner("advance", "--state-id", state_id)
            round_payload = rounds(access_payload)
            self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "collect-search-rounds",
                "--output",
                write("rounds.json", round_payload),
            )
            directive = self.run_runner("advance", "--state-id", state_id)
            self.assertEqual("inspect-details", directive["node"]["id"])
            shortlist = build_shortlist(round_payload)
            offers = [
                offer(shortlist["shortlist"][0], "799.00"),
                offer(shortlist["shortlist"][1], "829.00", risk=True),
            ]
            detail_payload = inspection(shortlist, offers)
            self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "inspect-details",
                "--output",
                write("inspection.json", detail_payload),
            )
            completed = self.run_runner("advance", "--state-id", state_id)
            self.assertEqual("completed", completed["status"])
            self.assertEqual(
                offers[0]["offer_id"],
                completed["final_output"]["recommendation"]["winner_id"],
            )


if __name__ == "__main__":
    unittest.main()
