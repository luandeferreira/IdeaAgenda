"""Provedores de IA intercambiáveis: OpenAI e Google Gemini.

Ambos expõem a mesma interface ``generate_json(system, prompt) -> dict``, de modo
que o restante do sistema não precisa saber qual provedor o dono escolheu.
"""

import asyncio
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
        max_attempts = 3
        last_resp = None
        for attempt in range(max_attempts):
            try:
                if self._http is not None:
                    resp = await self._http.post(url, **kwargs)
                else:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.post(url, **kwargs)
            except httpx.HTTPError as exc:
                if attempt == max_attempts - 1:
                    raise AIProviderError(f"Falha de comunicação com {self.name}: {exc}") from exc
                await asyncio.sleep(0.5 * (attempt + 1) if self._http is None else 0.01)
                continue

            last_resp = resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                logger.warning(
                    f"Tentativa {attempt + 1} de {max_attempts} para {self.name} retornou status {resp.status_code}. Tentando novamente...",
                    extra={"provider": self.name, "status": resp.status_code},
                )
                await asyncio.sleep(1.0 * (attempt + 1) if self._http is None else 0.01)
                continue
            break

        if last_resp is None:
            raise AIProviderError(f"Falha de comunicação com {self.name}")

        if last_resp.status_code >= 400:
            logger.warning(
                "Erro do provedor de IA",
                extra={"provider": self.name, "status": last_resp.status_code, "body": last_resp.text[:500]},
            )
            raise AIProviderError(f"{self.name} respondeu com erro {last_resp.status_code}")
        return last_resp.json()

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

    # Modelos alternativos caso o selecionado sofra com picos de tráfego (503) ou 404
    FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.8-flash"]

    async def generate_json(self, system: str, prompt: str) -> dict:
        models_to_try = [self.model]
        for m in self.FALLBACK_MODELS:
            if m != self.model and m not in models_to_try:
                models_to_try.append(m)

        last_exc: Exception | None = None
        for model_name in models_to_try:
            try:
                data = await self._post(
                    f"{self.base_url}/models/{model_name}:generateContent",
                    headers={"x-goog-api-key": self.api_key},
                    json={
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
                    },
                )
                parts = data["candidates"][0]["content"]["parts"]
                content = "".join(p.get("text", "") for p in parts)
                return extract_json(content)
            except (KeyError, IndexError, TypeError) as exc:
                last_exc = AIProviderError("Resposta inesperada do Gemini")
                break
            except AIProviderError as exc:
                last_exc = exc
                logger.warning(
                    f"Modelo {model_name} falhou ({exc}). Tentando modelo alternativo...",
                    extra={"provider": self.name, "model": model_name, "error": str(exc)},
                )
                continue

        if last_exc:
            raise last_exc
        raise AIProviderError("Não foi possível obter resposta do Gemini")


def build_provider(ai_settings: AISettingsOut, http: httpx.AsyncClient | None = None) -> AIProvider:
    env = get_settings()
    if ai_settings.provider == "gemini":
        return GeminiProvider(env.gemini_api_key, ai_settings.gemini_model, env.gemini_base_url, env.ai_timeout_seconds, http)
    return OpenAIProvider(env.openai_api_key, ai_settings.openai_model, env.openai_base_url, env.ai_timeout_seconds, http)
