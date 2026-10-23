"""Validate the rendered Compose crawler trust boundary.

The script consumes ``docker compose config --format json`` on stdin. Keeping
the assertions against rendered Compose catches accidental changes introduced
by overrides as well as edits to the base file.
"""
from __future__ import annotations

import json
import sys


CRAWLER_IMAGE_PREFIX = "iknowread-crawler:"


def _networks(service: dict) -> set[str]:
    value = service.get("networks", {})
    return set(value if isinstance(value, dict) else value)


def verify(config: dict) -> None:
    services = config.get("services", {})
    backend = services["backend"]
    crawler = services["crawler"]
    gateway = services["crawler-gateway"]

    crawler_image = crawler.get("image", "")
    if not crawler_image.startswith(CRAWLER_IMAGE_PREFIX) or crawler_image.endswith(":latest"):
        raise AssertionError("crawler image must use an immutable iKnowread release tag")
    crawler_environment = crawler.get("environment", {})
    if str(crawler_environment.get("CRAWL4AI_ALLOW_INTERNAL_URLS", "")).lower() != "false":
        raise AssertionError("crawler must fail closed for internal destinations")
    backend_environment = backend.get("environment", {})
    if backend_environment.get("CRAWLER_BASE_URL") != "http://crawler-gateway:8080":
        raise AssertionError("backend must call the fixed crawler gateway")
    backend_dependencies = set(backend.get("depends_on", {}))
    if backend_dependencies & {"crawler", "crawler-gateway"}:
        raise AssertionError("optional crawler services must not gate backend startup")

    backend_networks = _networks(backend)
    crawler_networks = _networks(crawler)
    gateway_networks = _networks(gateway)
    if "crawler_api" not in backend_networks or backend_networks & {"crawl_control", "crawl_egress"}:
        raise AssertionError("backend must be isolated from crawler execution networks")
    if crawler_networks != {"crawl_control", "crawl_egress"}:
        raise AssertionError("crawler may only use its control and egress networks")
    if gateway_networks != {"crawler_api", "crawl_control"}:
        raise AssertionError("crawler gateway must be the only bridge between API and control networks")
    if crawler_networks & backend_networks:
        raise AssertionError("crawler must not share any network with backend")


def main() -> None:
    try:
        verify(json.load(sys.stdin))
    except (AssertionError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"crawler isolation check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print("crawler isolation check: PASS")


if __name__ == "__main__":
    main()
