import unittest

from scripts.verify_crawler_isolation import verify


CRAWLER_IMAGE = "iknowread-crawler:release-20261022"


def secure_config() -> dict:
    return {
        "services": {
            "backend": {
                "environment": {"CRAWLER_BASE_URL": "http://crawler-gateway:8080"},
                "networks": {"proxy": None, "data": None, "crawler_api": None},
            },
            "crawler": {
                "image": CRAWLER_IMAGE,
                "environment": {"CRAWL4AI_ALLOW_INTERNAL_URLS": "false"},
                "networks": {"crawl_control": None, "crawl_egress": None},
            },
            "crawler-gateway": {
                "networks": {"crawler_api": None, "crawl_control": None},
            },
        }
    }


class CrawlerIsolationTests(unittest.TestCase):
    def test_secure_topology_is_accepted(self):
        verify(secure_config())

    def test_mutable_or_different_image_is_rejected(self):
        config = secure_config()
        config["services"]["crawler"]["image"] = "iknowread-crawler:latest"
        with self.assertRaisesRegex(AssertionError, "immutable"):
            verify(config)

    def test_internal_url_escape_hatch_is_rejected(self):
        config = secure_config()
        config["services"]["crawler"]["environment"]["CRAWL4AI_ALLOW_INTERNAL_URLS"] = "true"
        with self.assertRaisesRegex(AssertionError, "fail closed"):
            verify(config)

    def test_shared_backend_and_crawler_network_is_rejected(self):
        config = secure_config()
        config["services"]["backend"]["networks"]["crawl_control"] = None
        with self.assertRaisesRegex(AssertionError, "isolated"):
            verify(config)

    def test_gateway_cannot_be_bypassed(self):
        config = secure_config()
        config["services"]["backend"]["environment"]["CRAWLER_BASE_URL"] = "http://crawler:11235"
        with self.assertRaisesRegex(AssertionError, "fixed crawler gateway"):
            verify(config)

    def test_optional_crawler_does_not_gate_backend_startup(self):
        config = secure_config()
        config["services"]["backend"]["depends_on"] = {"crawler": {}}
        with self.assertRaisesRegex(AssertionError, "must not gate"):
            verify(config)


if __name__ == "__main__":
    unittest.main()
