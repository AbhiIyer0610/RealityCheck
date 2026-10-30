"""Check Nebius Token Factory authentication, visible models, and a tiny inference call.

Run from the repository root after setting NEBIUS_API_KEY in .env.
Never prints the API key. The inference probe uses the configured claim model and
a tiny prompt; it may consume a small amount of the project's credits.
"""
from __future__ import annotations

import sys

import httpx
from app.core.config import settings


def main() -> int:
    key = settings.nebius_api_key.get_secret_value().strip() if settings.nebius_api_key else ""
    if not key:
        print("ERROR: NEBIUS_API_KEY is empty. Add it to the project-root .env file.")
        return 2

    base = settings.nebius_base_url.rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(10.0, read=45.0, write=15.0, pool=5.0)
    try:
        with httpx.Client(base_url=base, headers=headers, timeout=timeout) as client:
            response = client.get("models")
            if response.status_code in {401, 403}:
                print(f"AUTHENTICATION/ACCESS ERROR: HTTP {response.status_code}. Confirm this is a Token Factory API key and that the selected project is accessible.")
                return 1
            response.raise_for_status()
            body = response.json()
            models = body.get("data", []) if isinstance(body, dict) else []
            ids = [str(item.get("id")) for item in models if isinstance(item, dict) and item.get("id")]
            print(f"PASS: API key authenticated; {len(ids)} model IDs returned.")
            configured = [settings.nebius_claim_model, settings.nebius_reasoning_model]
            for model in configured:
                print(f"{'AVAILABLE' if model in ids else 'NOT LISTED'}: {model}")
            if not ids:
                print("The API returned no model IDs. Check the selected project and Token Factory dashboard.")
                return 1

            model = settings.nebius_claim_model
            if model not in ids:
                print("Skipping inference probe because the configured claim model is not listed. Select an available model in .env first.")
                return 1
            print(f"Sending a tiny inference probe to {model} (this may use a small amount of credits)...")
            completion = client.post("chat/completions", json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: RealityCheck connection successful"}],
                "max_tokens": 20,
                "temperature": 0,
            })
            if completion.status_code in {402, 403}:
                print(f"BILLING/ACCESS ERROR: HTTP {completion.status_code}. Authentication may work, but the project may lack usable inference credits or model access.")
                print(completion.text[:600])
                return 1
            if completion.status_code == 429:
                print("RATE LIMIT: authentication succeeded, but the request was rate limited. Retry later.")
                return 1
            completion.raise_for_status()
            data = completion.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            print("PASS: inference request completed.")
            print(f"Model response: {str(content)[:200]}")
            if usage:
                print(f"Token usage: prompt={usage.get('prompt_tokens', '?')}, completion={usage.get('completion_tokens', '?')}, total={usage.get('total_tokens', '?')}")
            print("Check the Token Factory project's usage/balance page to confirm the request is reflected there.")
            return 0
    except httpx.HTTPStatusError as exc:
        print(f"HTTP ERROR: {exc.response.status_code}: {exc.response.text[:600]}")
        return 1
    except httpx.HTTPError as exc:
        print(f"NETWORK ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
