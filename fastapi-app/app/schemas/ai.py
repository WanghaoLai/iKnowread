from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.services.ai_providers import get_provider, validate_base_url


ProviderId = Literal["deepseek", "glm", "mimo", "bailian"]
DEFAULT_SYSTEM_PROMPT = "你是 iKnowread 智能助手，请用清晰、准确的中文回答用户的问题。"


class AISettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: ProviderId = "deepseek"
    name: str = Field(default="", max_length=100)
    base_url: str = ""
    model: str = Field(default="", min_length=0, max_length=100, pattern=r"^[a-zA-Z0-9._:/-]*$")
    temperature: float = Field(default=1, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=32768)
    thinking: bool = False
    system_prompt: str = Field(default=DEFAULT_SYSTEM_PROMPT, max_length=8000)

    @model_validator(mode="after")
    def provider_settings(self):
        spec = get_provider(self.provider)
        self.base_url = validate_base_url(self.provider, self.base_url or spec.default_base_url)
        self.model = self.model or spec.models[0]
        self.name = self.name or f"{spec.name} · {self.model}"
        return self


class AIConfigSave(AISettings):
    # 空值表示保留已保存密钥，密钥不会通过读取接口回传。
    api_key: SecretStr | None = None
    activate: bool = False

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value):
        key = value.get_secret_value().strip() if value else ""
        if not key:
            return None
        if len(key) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("API Key 格式无效")
        return SecretStr(key)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=120000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(min_length=1, max_length=41)

    @model_validator(mode="after")
    def validate_conversation(self):
        if any(m.role != ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(self.messages)):
            raise ValueError("对话必须从用户消息开始并交替出现")
        if self.messages[-1].role != "user":
            raise ValueError("最后一条消息必须是用户问题")
        if sum(len(m.content) for m in self.messages) > 120000:
            raise ValueError("对话过长，请新建对话")
        return self


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=4000)
    document_title: str = Field(default="", max_length=255)
