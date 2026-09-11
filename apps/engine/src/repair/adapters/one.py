"""One adapter — prefers CLI (`one --agent actions execute`) which is known-working;
falls back to HTTP passthrough when action ids are known.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from repair.config import Settings, get_settings
from repair.models import ToolResponse

# Discovered via `one actions search` during M0
STRIPE_ACTIONS = {
    "balance": "conn_mod_def::GJ7K5s4tHw8::rzDJMzETSLytlu-8gCLGfQ",
    "create_refund": "conn_mod_def::GJ7KpkTA_dc::Od_rWeH9TVOLKMbBMtEJYA",
    "list_refunds": None,  # resolve lazily
    "create_payment_intent": None,
}

LINEAR_ACTIONS = {
    "graphql": None,  # use passthrough/CLI knowledge
}


class OneAdapter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._call_log: list[dict[str, Any]] = []
        self._action_cache: dict[str, str] = {k: v for k, v in STRIPE_ACTIONS.items() if v}
        self._use_cli = shutil.which("one") is not None
        self._connection_cache: dict[str, str] = {}

    def list_connections(self) -> list[dict[str, Any]]:
        """Authoritative live inventory from One CLI (never trust stale IDs)."""
        if not self._use_cli:
            return []
        proc = subprocess.run(
            ["one", "--agent", "list"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**__import__("os").environ, "ONE_NO_TELEMETRY": "1"},
        )
        if proc.returncode != 0:
            return []
        try:
            data = json.loads(proc.stdout)
            return list(data.get("connections") or [])
        except json.JSONDecodeError:
            return []

    def connection_key(self, platform: str, *, refresh: bool = False) -> str:
        """Resolve operational connection dynamically from One; env is fallback only."""
        if not refresh and platform in self._connection_cache:
            return self._connection_cache[platform]

        for c in self.list_connections():
            if c.get("platform") == platform and c.get("state") == "operational" and c.get("key"):
                self._connection_cache[platform] = c["key"]
                if platform == "stripe":
                    self.settings.one_stripe_connection_key = c["key"]
                elif platform == "linear":
                    self.settings.one_linear_connection_key = c["key"]
                return c["key"]

        if platform == "stripe":
            key = self.settings.one_stripe_connection_key
        elif platform == "linear":
            key = self.settings.one_linear_connection_key
        else:
            raise ValueError(f"Unknown platform: {platform}")
        if not key:
            raise RuntimeError(
                f"No operational One connection for {platform}. "
                f"Run `one add {platform}` and ensure `one --agent list` shows it."
            )
        self._connection_cache[platform] = key
        return key

    def search_action(self, platform: str, query: str) -> list[dict[str, Any]]:
        if not self._use_cli:
            return []
        proc = subprocess.run(
            ["one", "--agent", "actions", "search", platform, query, "-t", "execute"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return []
        try:
            data = json.loads(proc.stdout)
            return data.get("actions") or []
        except json.JSONDecodeError:
            return []

    def resolve_action(self, platform: str, query: str, cache_key: str) -> str:
        if self._action_cache.get(cache_key):
            return self._action_cache[cache_key]  # type: ignore[return-value]
        actions = self.search_action(platform, query)
        if not actions:
            raise RuntimeError(f"No One action found for {platform}: {query}")
        action_id = actions[0]["actionId"]
        self._action_cache[cache_key] = action_id
        return action_id

    def execute_action(
        self,
        platform: str,
        action_id: str,
        *,
        data: dict[str, Any] | None = None,
        path_vars: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        form_url_encoded: bool = False,
        timeout: float = 90.0,
    ) -> ToolResponse:
        """Execute via One CLI (reliable auth path)."""
        conn = self.connection_key(platform)
        cmd = [
            "one",
            "--agent",
            "actions",
            "execute",
            platform,
            action_id,
            conn,
        ]
        if data is not None:
            cmd.extend(["-d", json.dumps(data)])
        if path_vars:
            cmd.extend(["--path-vars", json.dumps(path_vars)])
        if query_params:
            cmd.extend(["--query-params", json.dumps({k: str(v) for k, v in query_params.items()})])
        if headers:
            cmd.extend(["--headers", json.dumps(headers)])
        if form_url_encoded:
            cmd.append("--form-url-encoded")

        self._call_log.append(
            {
                "platform": platform,
                "method": "CLI",
                "path": action_id,
                "headers_keys": sorted((headers or {}).keys()),
            }
        )
        started = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        duration = (time.perf_counter() - started) * 1000
        raw = proc.stdout.strip() or proc.stderr.strip()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return ToolResponse(
                ok=False,
                status_code=None,
                body={"raw": raw},
                error=f"CLI non-JSON (code={proc.returncode})",
                duration_ms=duration,
            )

        # CLI wraps response
        response = parsed.get("response", parsed)
        # Detect errors
        err = None
        ok = proc.returncode == 0
        if isinstance(response, dict):
            if response.get("error") or response.get("type") in {
                "invalid_request_error",
                "secret_middleware_error",
                "api_error",
            }:
                ok = False
                err = response.get("message") or response.get("error") or "action failed"
            # Stripe error shape
            if "error" in response and isinstance(response["error"], dict):
                ok = False
                err = response["error"].get("message")
        return ToolResponse(
            ok=ok,
            status_code=200 if ok else 400,
            body=response,
            error=err,
            duration_ms=duration,
        )

    def execute(
        self,
        platform: str,
        method: str,
        path: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
        query: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> ToolResponse:
        """HTTP passthrough fallback (may fail depending on secret middleware)."""
        if not self.settings.one_secret:
            raise RuntimeError("ONE_SECRET is not set")

        path = path.lstrip("/")
        url = f"{self.settings.one_api_base.rstrip('/')}/v1/passthrough/{path}"
        if query:
            url = f"{url}?{urlencode({k: str(v) for k, v in query.items()})}"

        req_headers = {
            "x-one-secret": self.settings.one_secret,
            "x-one-connection-key": self.connection_key(platform),
        }
        if headers:
            req_headers.update(headers)

        content: bytes | None = None
        json_body = None
        if body is not None:
            if content_type == "application/x-www-form-urlencoded":
                req_headers["Content-Type"] = content_type
                if isinstance(body, dict):
                    content = urlencode({k: str(v) for k, v in body.items() if v is not None}).encode()
                else:
                    content = str(body).encode()
            else:
                req_headers["Content-Type"] = "application/json"
                json_body = body

        started = time.perf_counter()
        self._call_log.append(
            {
                "platform": platform,
                "method": method,
                "path": path,
                "headers_keys": sorted((headers or {}).keys()),
            }
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.request(
                    method.upper(),
                    url,
                    headers=req_headers,
                    content=content,
                    json=json_body,
                )
            duration = (time.perf_counter() - started) * 1000
            try:
                parsed = resp.json()
            except Exception:
                parsed = {"raw": resp.text}
            return ToolResponse(
                ok=resp.is_success,
                status_code=resp.status_code,
                body=parsed,
                error=None if resp.is_success else f"HTTP {resp.status_code}",
                headers={k: v for k, v in resp.headers.items()},
                duration_ms=duration,
            )
        except httpx.HTTPError as exc:
            duration = (time.perf_counter() - started) * 1000
            return ToolResponse(ok=False, error=str(exc), duration_ms=duration)

    def call_count(self, platform: str | None = None, path_contains: str | None = None) -> int:
        n = 0
        for c in self._call_log:
            if platform and c["platform"] != platform:
                continue
            if path_contains and path_contains not in c["path"]:
                continue
            n += 1
        return n

    def reset_log(self) -> None:
        self._call_log.clear()
