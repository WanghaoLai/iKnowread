"""隔离 SQLite + 模拟各模型服务商，测试不读取真实密钥、不调用付费 API。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, AIConfig, Document
from app.services import ai_service


class KeyPersistenceTests(unittest.TestCase):
    def test_generated_key_survives_restart_and_has_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(ai_service, "BASE_DIR", Path(directory)), patch.object(ai_service.settings, "AI_CONFIG_KEY", ""):
                ai_service.key_cipher.cache_clear()
                encrypted = ai_service.key_cipher().encrypt(b"test-secret")
                path = Path(directory) / "data" / ".ai-config-key"
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                ai_service.key_cipher.cache_clear()
                self.assertEqual(ai_service.key_cipher().decrypt(encrypted), b"test-secret")
                ai_service.key_cipher.cache_clear()


class AITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.user = await Account.create(username="ai-test", name="测试", password="unused", role="user")
        self.admin = await Account.create(username="ai-admin", name="管理员", password="unused", role="admin")
        self.document = await Document.create(
            name="示例文档.pdf", ext="pdf", size=100,
            path="files/download/user/1/example.pdf", account_id=self.user.id,
        )
        self.app = create_app()
        self.as_account(self.user)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        self.cipher = Fernet(Fernet.generate_key())
        self.key_patch = patch.object(ai_service, "key_cipher", return_value=self.cipher)
        self.key_patch.start()
        self.payload = {"api_key": "sk-test-private-key", "model": "deepseek-flash"}

    def as_account(self, account):
        self.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(account.id, account.role, account)

    async def asyncTearDown(self):
        await self.client.aclose()
        self.key_patch.stop()
        await Tortoise.close_connections()

    async def save(self):
        response = await self.client.put("/ai/config", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def source_anchor(self, text="第一性原理", *, version=None, source_format="pdf"):
        return {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": self.document.id,
            "document_version": version or self.document.content_version,
            "source_format": source_format,
            "scope": "page" if source_format == "pdf" else "document",
            "page": 2 if source_format == "pdf" else None,
            "progression": 0.2,
            "selector": {
                "position": {"start": 10, "end": 10 + len(text)},
                "quote": {"exact": text, "prefix": "理解", "suffix": "方法"},
            },
        }

    def upstream(self, handler):
        upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return patch.object(ai_service, "AsyncClient", return_value=upstream_client)

    async def test_defaults_and_missing_key(self):
        response = await self.client.get("/ai/config")
        self.assertFalse(response.json()["data"]["has_api_key"])
        self.assertEqual((await self.client.put("/ai/config", json={})).status_code, 400)
        self.assertEqual((await self.client.post("/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})).status_code, 400)

    async def test_secret_encryption_preservation_and_replacement(self):
        response = await self.save()
        self.assertNotIn(self.payload["api_key"], response.text)
        config = await AIConfig.get(account_id=self.user.id)
        self.assertNotIn(self.payload["api_key"], config.encrypted_api_key)
        self.assertEqual(self.cipher.decrypt(config.encrypted_api_key.encode()).decode(), self.payload["api_key"])
        await self.client.put("/ai/config", json={"model": "deepseek-v4-pro", "api_key": ""})
        updated = await AIConfig.get(account_id=self.user.id)
        self.assertEqual(updated.encrypted_api_key, config.encrypted_api_key)
        self.assertEqual(updated.model, "deepseek-v4-pro")
        await self.client.put("/ai/config", json={"api_key": "sk-replaced"})
        updated = await AIConfig.get(account_id=self.user.id)
        self.assertEqual(self.cipher.decrypt(updated.encrypted_api_key.encode()).decode(), "sk-replaced")
        self.assertNotIn("sk-replaced", (await self.client.get("/ai/config")).text)

    async def test_account_isolation_including_admin(self):
        await self.save()
        self.as_account(self.admin)
        self.assertFalse((await self.client.get("/ai/config")).json()["data"]["has_api_key"])
        self.assertEqual((await self.client.post("/ai/test")).status_code, 400)
        await self.client.put("/ai/config", json={"api_key": "admin-private", "model": "deepseek-v4-pro"})
        self.assertEqual(await AIConfig.all().count(), 2)
        self.as_account(self.user)
        self.assertEqual((await self.client.get("/ai/config")).json()["data"]["model"], "deepseek-flash")

    async def test_authentication_required(self):
        self.app.dependency_overrides.clear()
        for method, path, body in [
            ("GET", "/ai/config", None), ("GET", "/ai/configs", None),
            ("GET", "/ai/providers", None), ("POST", "/ai/configs", {}),
            ("GET", "/ai/configs/1/models", None),
            ("PUT", "/ai/config", {}), ("POST", "/ai/test", None),
            ("POST", "/ai/chat", {"messages": [{"role": "user", "content": "hi"}]}),
            ("POST", "/ai/explain", {"content": "word"}),
        ]:
            self.assertEqual((await self.client.request(method, path, json=body)).status_code, 401)

    async def test_multiple_configs_activation_deletion_and_isolation(self):
        await self.save()
        response = await self.client.post("/ai/configs", json={
            "name": "工作 GLM",
            "provider": "glm",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4.7",
            "api_key": "glm-private-key",
        })
        self.assertEqual(response.status_code, 200, response.text)
        glm = response.json()["data"]
        self.assertFalse(glm["is_active"])
        self.assertNotIn("glm-private-key", response.text)

        configs = (await self.client.get("/ai/configs")).json()["data"]
        self.assertEqual(len(configs), 2)
        self.assertEqual(sum(item["is_active"] for item in configs), 1)
        self.assertEqual({item["provider"] for item in configs}, {"deepseek", "glm"})

        activated = await self.client.post(f"/ai/configs/{glm['id']}/activate")
        self.assertEqual(activated.status_code, 200)
        self.assertEqual((await self.client.get("/ai/config")).json()["data"]["provider"], "glm")
        self.assertEqual(await AIConfig.filter(account_id=self.user.id, is_active=True).count(), 1)

        self.as_account(self.admin)
        self.assertEqual((await self.client.post(f"/ai/configs/{glm['id']}/activate")).status_code, 404)
        self.assertEqual((await self.client.delete(f"/ai/configs/{glm['id']}")).status_code, 404)
        self.as_account(self.user)

        deleted = await self.client.delete(f"/ai/configs/{glm['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["data"]["active_config"]["provider"], "deepseek")
        self.assertEqual((await self.client.get("/ai/config")).json()["data"]["provider"], "deepseek")

    async def test_provider_catalog_validation_and_duplicate_names(self):
        catalog = (await self.client.get("/ai/providers")).json()["data"]
        self.assertEqual([item["id"] for item in catalog], ["deepseek", "glm", "mimo", "bailian"])
        payloads = [
            ("GLM", "glm", "https://open.bigmodel.cn/api/paas/v4", "glm-4.7"),
            ("MiMo", "mimo", "https://api.xiaomimimo.com/v1", "mimo-v2.6-flash"),
            ("百炼", "bailian", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
            ("百炼工作空间", "bailian", "https://workspace-1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
        ]
        for name, provider, base_url, model in payloads:
            response = await self.client.post("/ai/configs", json={
                "name": name, "provider": provider, "base_url": base_url,
                "model": model, "api_key": f"{provider}-key",
            })
            self.assertEqual(response.status_code, 200, response.text)
        duplicate = await self.client.post("/ai/configs", json={
            "name": "GLM", "provider": "glm", "api_key": "another-key",
        })
        self.assertEqual(duplicate.status_code, 409)
        for provider, base_url in [
            ("glm", "https://api.deepseek.com"),
            ("mimo", "https://api.xiaomimimo.com.evil.test/v1"),
            ("bailian", "http://dashscope.aliyuncs.com/compatible-mode/v1"),
            ("bailian", "https://127.0.0.1/compatible-mode/v1"),
        ]:
            response = await self.client.post("/ai/configs", json={
                "name": f"bad-{provider}-{base_url}", "provider": provider,
                "base_url": base_url, "model": "valid-model", "api_key": "private-key",
            })
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("private-key", response.text)

    async def test_each_provider_uses_its_request_adapter(self):
        cases = [
            ("deepseek", "https://api.deepseek.com", "deepseek-flash", "max_tokens", "thinking", {"type": "disabled"}),
            ("glm", "https://open.bigmodel.cn/api/paas/v4", "glm-4.7", "max_tokens", None, None),
            ("mimo", "https://api.xiaomimimo.com/v1", "mimo-v2.6-flash", "max_completion_tokens", "thinking", {"type": "disabled"}),
            ("bailian", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "max_tokens", "enable_thinking", False),
        ]
        for provider, base_url, model, token_field, thinking_field, thinking_value in cases:
            response = await self.client.post("/ai/configs", json={
                "name": f"test-{provider}", "provider": provider, "base_url": base_url,
                "model": model, "api_key": f"{provider}-secret", "thinking": True,
            })
            self.assertEqual(response.status_code, 200, response.text)
            config_id = response.json()["data"]["id"]

            def handler(request, *, p=provider, u=base_url, tf=token_field, thf=thinking_field, thv=thinking_value):
                self.assertEqual(str(request.url), f"{u}/chat/completions")
                self.assertEqual(request.headers["Authorization"], f"Bearer {p}-secret")
                body = json.loads(request.content)
                self.assertEqual(body[tf], 32)
                self.assertEqual(body["temperature"], 1)
                if thf:
                    self.assertEqual(body[thf], thv)
                else:
                    self.assertNotIn("thinking", body)
                return httpx.Response(200, json={"choices": [{"message": {"content": "连接成功"}}]})

            with self.upstream(handler):
                tested = await self.client.post(f"/ai/configs/{config_id}/test")
            self.assertEqual(tested.status_code, 200, tested.text)

    async def test_model_discovery_normalizes_provider_catalogs(self):
        cases = [
            (
                "deepseek", "https://api.deepseek.com", "deepseek-flash",
                "https://api.deepseek.com/models",
                {"data": [{"id": "deepseek-flash", "name": "DeepSeek Flash", "context_window": 1000}]},
                ["deepseek-flash"], "provider",
            ),
            (
                "mimo", "https://api.xiaomimimo.com/v1", "mimo-v2.6-flash",
                "https://api.xiaomimimo.com/v1/models",
                {"data": [{"id": "mimo-v2.6-flash"}, {"id": "mimo-v2.5-asr"}, {"id": "mimo-v2.5-tts"}]},
                ["mimo-v2.6-flash"], "provider",
            ),
            (
                "bailian", "https://workspace-1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", "qwen-plus",
                "https://workspace-1.cn-beijing.maas.aliyuncs.com/api/v1/models",
                {"output": {"models": [{"model": "qwen-plus", "name": "Qwen Plus", "model_info": {"context_window": 128000}}]}},
                ["qwen-plus"], "provider",
            ),
            (
                "glm", "https://open.bigmodel.cn/api/paas/v4", "glm-4.7",
                "https://open.bigmodel.cn/api/paas/v4/models",
                None, ["glm-4.7", "glm-4.6", "glm-4.5-air"], "preset",
            ),
        ]
        for provider, base_url, model, expected_url, upstream_json, expected_ids, source in cases:
            created = await self.client.post("/ai/configs", json={
                "name": f"discover-{provider}", "provider": provider,
                "base_url": base_url, "model": model, "api_key": f"{provider}-catalog-key",
            })
            self.assertEqual(created.status_code, 200, created.text)
            config_id = created.json()["data"]["id"]

            def handler(request, *, p=provider, url=expected_url, payload=upstream_json):
                self.assertEqual(f"{request.url.scheme}://{request.url.host}{request.url.path}", url)
                self.assertEqual(request.headers["Authorization"], f"Bearer {p}-catalog-key")
                if p == "bailian":
                    self.assertIn("page_size=100", str(request.url))
                    self.assertIn("capabilities=TG", str(request.url))
                if payload is None:
                    return httpx.Response(404)
                return httpx.Response(200, json=payload)

            with self.upstream(handler):
                response = await self.client.get(f"/ai/configs/{config_id}/models")
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()["data"]
            self.assertEqual([item["id"] for item in data["models"]], expected_ids)
            self.assertEqual(data["source"], source)
            self.assertNotIn(f"{provider}-catalog-key", response.text)

        with self.upstream(lambda request: httpx.Response(401, text="private-upstream-error")):
            unauthorized = await self.client.get(f"/ai/configs/{config_id}/models")
        self.assertEqual(unauthorized.status_code, 502)
        self.assertIn("API Key", unauthorized.text)
        self.assertNotIn("private-upstream-error", unauthorized.text)

        with (
            patch.object(settings, "AI_MAX_RESPONSE_BYTES", 16),
            self.upstream(lambda request: httpx.Response(200, content=b"{" + b"x" * 100)),
        ):
            oversized = await self.client.get(f"/ai/configs/{config_id}/models")
        self.assertEqual(oversized.status_code, 502)
        self.assertIn("过大", oversized.text)

        self.as_account(self.admin)
        self.assertEqual((await self.client.get(f"/ai/configs/{config_id}/models")).status_code, 404)

    async def test_validation_does_not_echo_secrets(self):
        for payload in [
            {**self.payload, "base_url": "http://127.0.0.1"},
            {**self.payload, "base_url": "https://api.deepseek.com.evil.test"},
            {**self.payload, "max_tokens": 0},
            {**self.payload, "temperature": 3},
            {**self.payload, "account_id": self.admin.id},
            {"api_key": "private\ninvalid-key"},
        ]:
            response = await self.client.put("/ai/config", json=payload)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("private", response.text)

    async def test_chat_uses_saved_config_and_context(self):
        self.payload.update(system_prompt="测试系统提示", temperature=0.4, max_tokens=1024, base_url="https://api.deepseek.com/v1/")
        await self.save()
        messages = [{"role": "user", "content": "第一问"}, {"role": "assistant", "content": "第一答"}, {"role": "user", "content": "继续"}]

        def handler(request):
            self.assertEqual(str(request.url), "https://api.deepseek.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test-private-key")
            body = json.loads(request.content)
            self.assertEqual(body["messages"], [{"role": "system", "content": "测试系统提示"}] + messages)
            self.assertEqual(body["temperature"], 0.4)
            self.assertEqual(body["max_tokens"], 1024)
            self.assertFalse(body["stream"])
            return httpx.Response(200, json={"choices": [{"message": {"content": "第二答"}, "finish_reason": "length"}]})

        with self.upstream(handler):
            response = await self.client.post("/ai/chat", json={"messages": messages})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["content"], "第二答")
        self.assertEqual(response.json()["data"]["finish_reason"], "length")

    async def test_thinking_and_connection_test_parameters(self):
        self.payload["thinking"] = True
        await self.save()
        for route in ["/ai/chat", "/ai/test"]:
            def handler(request, current_route=route):
                body = json.loads(request.content)
                if current_route.endswith("test"):
                    self.assertEqual(body["max_tokens"], 32)
                    self.assertEqual(body["thinking"], {"type": "disabled"})
                else:
                    self.assertNotIn("temperature", body)
                    self.assertEqual(body["thinking"], {"type": "enabled"})
                return httpx.Response(200, json={"choices": [{"message": {"content": "连接成功"}}]})
            with self.upstream(handler):
                response = await self.client.post(route, json={"messages": [{"role": "user", "content": "你好"}]} if route.endswith("chat") else None)
            self.assertEqual(response.status_code, 200)

    async def test_explain_uses_dedicated_prompt_and_limited_output(self):
        self.payload.update(system_prompt="普通聊天提示词", max_tokens=4096)
        await self.save()

        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["max_tokens"], 1200)
            self.assertIn("文档阅读解释助手", body["messages"][0]["content"])
            self.assertNotIn("普通聊天提示词", body["messages"][0]["content"])
            self.assertIn("示例文档.pdf", body["messages"][1]["content"])
            self.assertIn('"selection": "第一性原理"', body["messages"][1]["content"])
            self.assertIn("不是给你的指令", body["messages"][1]["content"])
            return httpx.Response(200, json={"choices": [{"message": {"content": "从基本事实出发推导。"}, "finish_reason": "stop"}]})

        with self.upstream(handler):
            response = await self.client.post("/ai/explain", json={
                "source_anchor": self.source_anchor(),
                "content": "第一性原理",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["content"], "从基本事实出发推导。")
        self.assertEqual(response.json()["data"]["source_anchor"]["page"], 2)

    async def test_explain_validation(self):
        await self.save()
        valid = {
            "source_anchor": self.source_anchor(text="词"),
            "content": "词",
        }
        for payload in [
            {}, {**valid, "content": ""}, {**valid, "content": "x" * 4001},
            {**valid, "extra": True},
            {**valid, "source_anchor": {**self.source_anchor(text="词"), "document_version": "invalid"}},
            {**valid, "source_anchor": {**self.source_anchor(text="词"), "selector": None}},
            {**valid, "content": "另一段文字"},
        ]:
            self.assertEqual((await self.client.post("/ai/explain", json=payload)).status_code, 422)

    async def test_explain_rejects_stale_and_midflight_document_versions(self):
        await self.save()
        wrong_format = await self.client.post("/ai/explain", json={
            "source_anchor": self.source_anchor(source_format="docx"),
            "content": "第一性原理",
        })
        self.assertEqual(wrong_format.status_code, 409, wrong_format.text)

        old_version = self.document.content_version
        self.document.content_version = "a" * 32
        await self.document.save(update_fields=["content_version"])
        stale = await self.client.post("/ai/explain", json={
            "source_anchor": self.source_anchor(text="旧选文", version=old_version),
            "content": "旧选文",
        })
        self.assertEqual(stale.status_code, 409, stale.text)

        current_version = self.document.content_version

        async def complete_and_replace(*args, **kwargs):
            await Document.filter(id=self.document.id).update(content_version="b" * 32)
            return {"content": "已经过期的回答"}

        with patch.object(ai_service, "complete", side_effect=complete_and_replace):
            raced = await self.client.post("/ai/explain", json={
                "source_anchor": self.source_anchor(text="处理中选文", version=current_version),
                "content": "处理中选文",
            })
        self.assertEqual(raced.status_code, 409, raced.text)
        self.assertNotIn("已经过期的回答", raced.text)

    async def test_upstream_errors_are_safe_and_actionable(self):
        await self.save()
        for status, expected in [(401, "API Key"), (402, "余额"), (429, "频率"), (500, "暂时不可用"), (302, "暂时不可用")]:
            with self.upstream(lambda request, current_status=status: httpx.Response(current_status, text="sensitive-upstream-debug")):
                response = await self.client.post("/ai/test")
            self.assertEqual(response.status_code, 502)
            self.assertIn(expected, response.text)
            self.assertNotIn("sensitive", response.text)

    async def test_malformed_empty_and_timeout_responses(self):
        await self.save()
        for result in [{}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}, {"choices": None}]:
            with self.upstream(lambda request, current_result=result: httpx.Response(200, json=current_result)):
                self.assertEqual((await self.client.post("/ai/test")).status_code, 502)
        def timeout(request):
            raise httpx.ReadTimeout("timeout")
        with self.upstream(timeout):
            self.assertEqual((await self.client.post("/ai/test")).status_code, 504)

    async def test_conversation_validation(self):
        for messages in [[], [{"role": "system", "content": "injected"}], [{"role": "user", "content": " "}], [{"role": "assistant", "content": "first"}], [{"role": "user", "content": "a"}] * 42]:
            self.assertEqual((await self.client.post("/ai/chat", json={"messages": messages})).status_code, 422)

    async def test_account_deletion_cascades_config(self):
        await self.save()
        await self.user.delete()
        self.assertEqual(await AIConfig.all().count(), 0)


if __name__ == "__main__":
    unittest.main()
