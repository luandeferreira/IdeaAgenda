"""Provedores de IA intercambiáveis: OpenAI e Google Gemini.

Ambos expõem a mesma interface ``generate_json(system, prompt) -> dict``, de modo
que o restante do sistema não precisa saber qual provedor o dono escolheu.
"""

import json
import logging
import re
from abc import ABC, abstractmethod

import httpx

from Config.settings import get_settings
from Dto.dto import AISettingsOut

logger = logging.getLogger("ideaagenda.ai")


class AIProviderError(Exception):
    pass


def extract_json(text: str) -> dict:
    """Converte a resposta do modelo em dict, tolerando cercas ```json."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIProviderError("A IA não retornou um JSON válido")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIProviderError("A IA não retornou um JSON válido") from exc
    if not isinstance(data, dict):
        raise AIProviderError("A IA retornou um formato inesperado")
    return data


class AIProvider(ABC):
    name: str

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float, http: httpx.AsyncClient | None = None):
        if not api_key:
            raise AIProviderError(f"Chave de API do provedor '{self.name}' não configurada")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http = http

    async def _post(self, url: str, **kwargs) -> dict:
        try:
            if self._http is not None:
                resp = await self._http.post(url, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, **kwargs)
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Falha de comunicação com {self.name}: {exc}") from exc
        if resp.status_code >= 400:
            logger.warning("Erro do provedor de IA", extra={"provider": self.name, "status": resp.status_code, "body": resp.text[:500]})
            raise AIProviderError(f"{self.name} respondeu com erro {resp.status_code}")
        return resp.json()

    @abstractmethod
    async def generate_json(self, system: str, prompt: str) -> dict: ...


class OpenAIProvider(AIProvider):
    name = "openai"

    async def generate_json(self, system: str, prompt: str) -> dict:
        data = await self._post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Resposta inesperada da OpenAI") from exc
        return extract_json(content)


class GeminiProvider(AIProvider):
    name = "gemini"

    async def generate_json(self, system: str, prompt: str) -> dict:
        data = await self._post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
            },
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            content = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Resposta inesperada do Gemini") from exc
        return extract_json(content)


def build_provider(ai_settings: AISettingsOut, http: httpx.AsyncClient | None = None) -> AIProvider:
    env = get_settings()
    if ai_settings.provider == "gemini":
        return GeminiProvider(env.gemini_api_key, ai_settings.gemini_model, env.gemini_base_url, env.ai_timeout_seconds, http)
    return OpenAIProvider(env.openai_api_key, ai_settings.openai_model, env.openai_base_url, env.ai_timeout_seconds, http)
