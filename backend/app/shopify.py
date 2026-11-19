import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-07")


_cached_token: str | None = None
_token_expires_at: float = 0


def get_shopify_access_token() -> str:
    global _cached_token
    global _token_expires_at

    # Keep a five-minute safety margin before expiration.
    if _cached_token and time.time() < (_token_expires_at - 300):
        return _cached_token

    if not SHOPIFY_SHOP:
        raise RuntimeError("SHOPIFY_SHOP is not configured")

    if not SHOPIFY_CLIENT_ID:
        raise RuntimeError("SHOPIFY_CLIENT_ID is not configured")

    if not SHOPIFY_CLIENT_SECRET:
        raise RuntimeError("SHOPIFY_CLIENT_SECRET is not configured")

    url = f"https://{SHOPIFY_SHOP}/admin/oauth/access_token"

    form_data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": SHOPIFY_CLIENT_ID,
            "client_secret": SHOPIFY_CLIENT_SECRET,
        }
    ).encode()

    request = urllib.request.Request(
        url,
        data=form_data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode())

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")

        raise RuntimeError(
            f"Shopify authentication failed with HTTP {exc.code}: {body}"
        ) from exc

    access_token = result.get("access_token")

    if not access_token:
        raise RuntimeError("Shopify did not return an access token")

    expires_in = int(result.get("expires_in", 86400))

    _cached_token = access_token
    _token_expires_at = time.time() + expires_in

    return access_token


def shopify_graphql(
    query: str,
    variables: dict | None = None,
):
    token = get_shopify_access_token()

    url = (
        f"https://{SHOPIFY_SHOP}/admin/api/"
        f"{SHOPIFY_API_VERSION}/graphql.json"
    )

    payload = json.dumps(
        {
            "query": query,
            "variables": variables or {},
        }
    ).encode()

    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode())

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")

        raise RuntimeError(
            f"Shopify GraphQL request failed with HTTP {exc.code}: {body}"
        ) from exc

    if result.get("errors"):
        raise RuntimeError(
            f"Shopify GraphQL errors: {result['errors']}"
        )

    return result["data"]
