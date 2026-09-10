"""Raw response archive with credential redaction.

Redaction happens BEFORE the bytes reach storage, never as a display filter. An
archive that has ever held a live API key is a credential-disclosure incident,
and immutable storage means it cannot be cleaned up afterwards.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

#: Matched case-insensitively against header names.
SECRET_HEADERS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "api-key", "x-api-key", "x-auth-token", "x-access-token", "apikey",
    "x-client-secret", "client-secret", "token", "x-subscription-key",
})

#: Matched case-insensitively against query-string and JSON body keys.
SECRET_PARAMS = frozenset({
    "api_key", "apikey", "key", "token", "access_token", "auth", "secret",
    "client_secret", "password", "signature", "subscription_key",
})

_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]+")


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        k: (REDACTED if k.lower() in SECRET_HEADERS else _BEARER.sub(rf"\1 {REDACTED}", v))
        for k, v in headers.items()
    }


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    cleaned = [
        (k, REDACTED if k.lower() in SECRET_PARAMS else v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(cleaned)))


def redact_body(body: str | None) -> str | None:
    """JSON bodies are redacted key-wise; anything else has bearer-style tokens
    stripped. A body we cannot parse is still archived -- unparseable is not a
    reason to discard evidence -- but it is scrubbed conservatively."""
    if body is None:
        return None
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return _BEARER.sub(rf"\1 {REDACTED}", body)
    return json.dumps(_redact_tree(parsed), sort_keys=True, separators=(",", ":"))


def _redact_tree(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: (REDACTED if k.lower() in SECRET_PARAMS else _redact_tree(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_redact_tree(x) for x in node]
    return node


def archive(
    conn,
    *,
    adapter_id: str,
    adapter_version: str,
    capability_id: str,
    observed_at: datetime,
    method: str,
    url: str,
    request_headers: Mapping[str, str],
    request_body: str | None,
    response_status: int | None,
    response_headers: Mapping[str, str] | None,
    response_body: str | None,
    lawful_basis,
) -> str:
    """Store one exchange verbatim and return its content hash.

    Called on failure as well as success. A 500 body is the evidence that the
    authority was down.
    """
    safe_url = redact_url(url)
    safe_req_headers = redact_headers(request_headers)
    safe_req_body = redact_body(request_body)

    digest = hashlib.sha256(
        json.dumps(
            {
                "adapter_id": adapter_id, "capability_id": capability_id,
                "observed_at": observed_at.isoformat(), "method": method,
                "url": safe_url, "request_headers": safe_req_headers,
                "request_body": safe_req_body, "response_status": response_status,
                "response_body": response_body,
            },
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_responses (content_sha256,adapter_id,adapter_version,
                   capability_id,observed_at,request_method,request_url,
                   request_headers,request_body,response_status,response_headers,
                   response_body,lawful_basis,consent_reference,requested_by,purpose)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (content_sha256) DO NOTHING""",
            (digest, adapter_id, adapter_version, capability_id, observed_at,
             method, safe_url, json.dumps(safe_req_headers), safe_req_body,
             response_status,
             json.dumps(dict(response_headers or {})),
             response_body,
             lawful_basis.basis.value, lawful_basis.consent_reference,
             lawful_basis.requested_by, lawful_basis.purpose),
        )
    return digest
