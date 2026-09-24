"""Optional structured LLM boundaries. Core ONLINE does not require them."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from .errors import LLMProviderError


class BaseProvider(ABC):
    @abstractmethod
    def structured(self, system: str, user: str, schema: dict) -> dict: ...

    def readiness(self) -> dict:
        return {"status": "UNKNOWN"}


def _request_json(url: str, *, headers: dict | None = None, timeout: float = 5) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


class HttpJsonProvider(BaseProvider):
    def __init__(self, url: str, model: str, api_key: str | None = None,
                 timeout: float = 60, health_url: str | None = None):
        self.url = url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.health_url = health_url

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "ngrok-skip-browser-warning": "true",
        }
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def structured(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "result", "schema": schema}},
        }
        try:
            request = urllib.request.Request(
                self.url, data=json.dumps(payload).encode(), headers=self._headers(), method="POST"
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read())
            content = raw["choices"][0]["message"]["content"]
            return json.loads(content) if isinstance(content, str) else content
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

    def readiness(self) -> dict:
        if not self.health_url:
            return {"status": "UNKNOWN", "provider": "http", "model": self.model}
        try:
            raw = _request_json(self.health_url, headers=self._headers(), timeout=min(self.timeout, 10))
            ready = raw.get("ready", raw.get("status") in {"ok", "ready"})
            return {"status": "READY" if ready else "DEGRADED", "provider": "http", "model": self.model}
        except Exception as exc:
            return {"status": "DEGRADED", "provider": "http", "model": self.model,
                    "error": type(exc).__name__}


class OllamaProvider(BaseProvider):
    def __init__(self, url: str = "http://127.0.0.1:11434/api/chat", model: str = "qwen3:4b",
                 timeout: float = 120, health_url: str | None = None):
        self.url = url
        self.model = model
        self.timeout = timeout
        self.health_url = health_url or urllib.parse.urljoin(url, "/api/tags")

    def structured(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "think": False,
            "options": {"temperature": 0, "seed": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            request = urllib.request.Request(
                self.url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read())
            return json.loads(raw["message"]["content"])
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

    def readiness(self) -> dict:
        try:
            raw = _request_json(self.health_url, timeout=min(self.timeout, 10))
            models = {row.get("name", "").split(":")[0] for row in raw.get("models", [])}
            requested = self.model.split(":")[0]
            return {"status": "READY" if requested in models else "DEGRADED",
                    "provider": "ollama", "model": self.model, "model_loaded": requested in models}
        except Exception as exc:
            return {"status": "DEGRADED", "provider": "ollama", "model": self.model,
                    "error": type(exc).__name__}
