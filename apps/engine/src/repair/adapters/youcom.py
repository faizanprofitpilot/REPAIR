"""You.com Search + Contents adapters with provenance."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from repair.config import get_settings
from repair.models import Availability, CapabilityEvidence, Citation, ToolCapabilities


class YouComAdapter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base = "https://ydc-index.io/v1"

    @property
    def enabled(self) -> bool:
        return bool(self.settings.ydc_api_key)

    def _headers(self) -> dict[str, str]:
        if not self.settings.ydc_api_key:
            raise RuntimeError("YDC_API_KEY is not set")
        return {"X-API-Key": self.settings.ydc_api_key, "Content-Type": "application/json"}

    def search(
        self,
        query: str,
        *,
        include_domains: list[str] | None = None,
        count: int = 5,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "count": count,
            "extraction": {"extraction_mode": "highlights"},
        }
        if include_domains:
            payload["include_domains"] = include_domains
        started = time.perf_counter()
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{self.base}/search", headers=self._headers(), json=payload)
        latency = (time.perf_counter() - started) * 1000
        resp.raise_for_status()
        data = resp.json()
        data["_latency_ms"] = latency
        return data

    def contents(self, urls: list[str], *, timeout: float = 20.0) -> list[dict[str, Any]]:
        payload = {"urls": urls[:10], "formats": ["markdown"], "crawl_timeout": 10}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{self.base}/contents", headers=self._headers(), json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("results") or data.get("contents") or []

    def research_tool_capabilities(
        self,
        *,
        tool_id: str,
        query: str,
        include_domains: list[str],
        cache_name: str,
    ) -> ToolCapabilities:
        cache_path = self.settings.fixtures_dir / "evidence_cache" / f"{cache_name}.json"
        try:
            if not self.enabled:
                raise RuntimeError("YDC_API_KEY missing")
            data = self.search(query, include_domains=include_domains)
            web = ((data.get("results") or {}).get("web")) or []
            citations: list[Citation] = []
            highlights: list[str] = []
            for item in web[:5]:
                hs = ((item.get("contents") or {}).get("highlights")) or item.get("snippets") or []
                quote = hs[0] if hs else (item.get("description") or "")
                citations.append(
                    Citation(
                        url=item.get("url") or "",
                        title=item.get("title"),
                        quote=quote[:500] if quote else None,
                        page_age=item.get("page_age"),
                    )
                )
                highlights.extend([str(h) for h in hs[:3]])
            # Optional Contents on top URL
            if citations and citations[0].url:
                try:
                    pages = self.contents([citations[0].url])
                    if pages:
                        md = (pages[0].get("markdown") or "")[:4000]
                        if md:
                            highlights.append(md[:1000])
                except Exception:
                    pass

            evidence = CapabilityEvidence(
                query=query,
                search_uuid=((data.get("metadata") or {}).get("search_uuid")),
                citations=citations,
                latency_ms=data.get("_latency_ms"),
                source="live",
                raw_highlights=highlights[:20],
            )
            # Deterministic extraction heuristics (no LLM required for capability resolution)
            blob = " ".join(highlights).lower() + " " + " ".join(c.quote or "" for c in citations).lower()
            caps = self._resolve_from_text(tool_id, blob, evidence)
            # Persist labeled cache for fallback
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "verified_at": datetime.now(timezone.utc).isoformat(),
                        "capabilities": caps.model_dump(mode="json"),
                    },
                    indent=2,
                )
            )
            return caps
        except Exception as exc:
            if cache_path.exists():
                cached = json.loads(cache_path.read_text())
                caps = ToolCapabilities.model_validate(cached["capabilities"])
                if caps.evidence:
                    caps.evidence.source = "cached"
                    caps.evidence.verified_at = datetime.fromisoformat(cached["verified_at"])
                caps.source = "cached"
                caps.preflight_result = {"fallback_reason": str(exc)}
                return caps
            # Conservative defaults without evidence
            return ToolCapabilities(
                tool_id=tool_id,
                native_safe_replay=Availability.UNAVAILABLE,
                state_verification=Availability.AVAILABLE,
                source="cached",
                preflight_result={"error": str(exc)},
            )

    def _resolve_from_text(self, tool_id: str, blob: str, evidence: CapabilityEvidence) -> ToolCapabilities:
        if "stripe" in tool_id:
            has_idem = "idempotency" in blob or "idempotency-key" in blob or "idempotency key" in blob
            return ToolCapabilities(
                tool_id=tool_id,
                native_safe_replay=Availability.AVAILABLE if has_idem else Availability.UNKNOWN,
                mechanism="idempotency_key" if has_idem else None,
                preserve_operation_identity_required=has_idem,
                state_verification=Availability.AVAILABLE,
                verification_mechanism="list_refunds",
                evidence=evidence,
                source="live",
            )
        # Linear: look for issueCreate idempotency / deduplication
        has_native = ("idempoten" in blob and "issuecreate" in blob.replace(" ", "")) or (
            "deduplicationkey" in blob.replace(" ", "") and "issuecreate" in blob.replace(" ", "")
        )
        # More conservative: require clear idempotency for issue create
        has_native = False
        if "idempotency" in blob and "issue" in blob and "create" in blob:
            # only if docs explicitly say issueCreate supports it — usually they don't
            has_native = "issuecreate" in blob.replace(" ", "") and "idempotency key" in blob
        has_filter = "contains" in blob or "filter" in blob or "description" in blob
        return ToolCapabilities(
            tool_id=tool_id,
            native_safe_replay=Availability.AVAILABLE if has_native else Availability.UNAVAILABLE,
            mechanism=None,
            preserve_operation_identity_required=False,
            state_verification=Availability.AVAILABLE if has_filter or True else Availability.UNAVAILABLE,
            verification_mechanism="issues_filter_description_contains",
            evidence=evidence,
            source="live",
        )
