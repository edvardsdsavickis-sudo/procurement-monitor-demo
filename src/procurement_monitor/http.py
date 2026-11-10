from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)


class HttpError(RuntimeError):
    def __init__(self, status: int | None, url: str, message: str):
        super().__init__(f"HTTP error ({status or 'connection'}) {url}: {message}")
        self.status = status
        self.url = url


class JsonHttpClient:
    def __init__(
        self,
        *,
        timeout: int = 45,
        retries: int = 3,
        user_agent: str = "Procurement-Monitor-Demo/0.1",
    ):
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent

    def get_json(self, url: str, *, allow_not_found: bool = False) -> Any:
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
            method="GET",
        )
        return self._execute(request, allow_not_found=allow_not_found)

    def get_text(self, url: str) -> str:
        request = Request(
            url,
            headers={"Accept": "text/html", "User-Agent": self.user_agent},
            method="GET",
        )
        result = self._execute(request, allow_not_found=False, parse_json=False)
        return str(result)

    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        return self._execute(request, allow_not_found=False)

    def _execute(
        self,
        request: Request,
        *,
        allow_not_found: bool,
        parse_json: bool = True,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                    charset = response.headers.get_content_charset() or "utf-8"
                    text = response.read().decode(charset)
                    if not parse_json:
                        return text
                    content_type = response.headers.get_content_type()
                    is_json = content_type == "application/json" or content_type.endswith("+json")
                    if allow_not_found and not is_json:
                        LOGGER.info(
                            "JSON resource unavailable (%s returned %s)",
                            request.full_url,
                            content_type,
                        )
                        return None
                    return json.loads(text)
            except HTTPError as exc:
                if exc.code == 404 and allow_not_found:
                    return None
                details = exc.read().decode("utf-8", errors="replace")[:1000]
                if exc.code < 500 and exc.code != 429:
                    raise HttpError(exc.code, request.full_url, details) from exc
                last_error = HttpError(exc.code, request.full_url, details)
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc

            if attempt < self.retries:
                delay = 2 ** (attempt - 1)
                LOGGER.warning(
                    "Request to %s failed (attempt %s/%s); retrying in %ss",
                    request.full_url,
                    attempt,
                    self.retries,
                    delay,
                )
                time.sleep(delay)

        raise HttpError(None, request.full_url, str(last_error or "unknown error"))
