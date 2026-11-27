import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ProviderError(Exception):
    """Raised when a configured answer provider cannot return a usable response."""


class MalformedProviderResponse(ProviderError):
    """Raised when the provider's response is not the required structured JSON."""


class OpenAICompatibleProvider:
    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 30):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            self.api_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("The configured AI provider request failed.") from error

        try:
            content = payload["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                lines = [ln for ln in content.splitlines() if not ln.strip().startswith("```")]
                content = "\n".join(lines).strip()
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as error:
            raise MalformedProviderResponse("The AI provider returned malformed structured output.") from error
        if not isinstance(parsed, dict) or not isinstance(parsed.get("claims"), list):
            raise MalformedProviderResponse("The AI provider response must contain a claims list.")
        return parsed["claims"]


def _is_local_endpoint(parsed_url) -> bool:
    host = (parsed_url.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def get_provider(config: Any) -> OpenAICompatibleProvider | None:
    provider_name = str(config.get("AI_PROVIDER", "none")).strip().lower()
    if provider_name in {"", "none"}:
        return None
    if provider_name != "openai_compatible":
        raise ProviderError("AI_PROVIDER must be 'none' or 'openai_compatible'.")

    api_key = str(config.get("AI_API_KEY", "")).strip()
    api_url = str(config.get("AI_API_URL", "")).strip()
    model = str(config.get("AI_MODEL", "")).strip()
    parsed_url = urlsplit(api_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ProviderError("AI_API_URL must be an HTTP or HTTPS endpoint.")
    if not model or (not api_key and not _is_local_endpoint(parsed_url)):
        raise ProviderError(
            "AI_PROVIDER is enabled but AI_API_KEY, AI_API_URL, or AI_MODEL is missing."
        )
    try:
        timeout = int(config.get("AI_TIMEOUT_SECONDS", 30))
    except (TypeError, ValueError) as error:
        raise ProviderError("AI_TIMEOUT_SECONDS must be a positive integer.") from error
    if timeout < 1 or timeout > 120:
        raise ProviderError("AI_TIMEOUT_SECONDS must be between 1 and 120.")
    return OpenAICompatibleProvider(
        api_url=api_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
