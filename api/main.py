import os
import hashlib
import time
from copy import deepcopy
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field


FIND_URL = "https://api.addressy.com/Capture/Interactive/Find/v1.20/json6.ws"
VERIFY_URL = "https://api.addressy.com/Cleansing/International/Batch/v1.20/json6.ws"
CACHE_TTL_SECONDS = max(0, float(os.getenv("ADDRESS_CACHE_TTL_SECONDS", "300")))
MAX_CACHE_ENTRIES = 256
_search_cache: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, list[dict[str, Any]]]] = {}
_retrieve_cache: dict[tuple[str, str, str, str, str], tuple[float, dict[str, Any]]] = {}
_catalog: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


def loqate_client_options() -> dict[str, object]:
    options: dict[str, object] = {"timeout": 15.0}
    ca_bundle = os.getenv("LOQATE_CA_BUNDLE")
    if ca_bundle:
        options["verify"] = ca_bundle
    return options


class AddressSearchItem(BaseModel):
    id: str
    text: str
    description: str


class AddressSearchResponse(BaseModel):
    items: list[AddressSearchItem]


class AddressRetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    description: str = ""
    country: str = Field(min_length=2, max_length=2)


class AddressCatalogResponse(BaseModel):
    items: list[dict[str, Any]]


app = FastAPI(
    title="Loqate Address Proxy API",
    description=(
        "A small proxy for Loqate address search and verification. The caller "
        "supplies their Loqate API key with each request."
    ),
    version="1.0.0",
)

configured_origins = os.getenv("CORS_ORIGINS", "*").strip()
allowed_origins = (
    ["*"]
    if configured_origins == "*"
    else [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type", "X-Loqate-Api-Key"],
)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "Loqate Address Proxy API", "docs": "/docs"}


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/heartbeat", tags=["service"])
async def heartbeat() -> dict[str, str]:
    return {"status": "awake"}


def api_error(items: list[dict[str, Any]]) -> None:
    error = next((item for item in items if item.get("Error")), None)
    if error:
        raise HTTPException(
            status_code=502,
            detail=f"Loqate rejected the request: {error.get('Description') or error.get('Error')}",
        )


def response_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("Items"), list):
        return [item for item in data["Items"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    raise HTTPException(status_code=502, detail="Loqate returned an unexpected response.")


async def loqate_get(params: dict[str, str]) -> list[dict[str, Any]]:
    cache_key = (
        _api_key_cache_key(params["Key"]),
        tuple(sorted((key, value) for key, value in params.items() if key != "Key")),
    )
    cached = _search_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return deepcopy(cached[1])

    try:
        async with httpx.AsyncClient(**loqate_client_options()) as client:
            response = await client.get(
                FIND_URL,
                params=params,
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Loqate request timed out.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Loqate.") from exc

    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"Loqate request failed (HTTP {response.status_code}).",
        )
    try:
        items = response_items(response.json())
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Loqate returned invalid JSON.") from exc
    api_error(items)
    _cache_put(_search_cache, cache_key, items)
    return items


def _cache_put(cache: dict[Any, tuple[float, Any]], key: Any, value: Any) -> None:
    if CACHE_TTL_SECONDS <= 0:
        return
    if len(cache) >= MAX_CACHE_ENTRIES:
        cache.pop(next(iter(cache)))
    cache[key] = (time.monotonic(), deepcopy(value))


def _api_key_cache_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _catalog_items(api_key: str, country: str = "") -> list[dict[str, Any]]:
    now = time.monotonic()
    key_hash = _api_key_cache_key(api_key)
    items = []
    for (cached_key_hash, item_country, _), (created, item) in _catalog.items():
        if cached_key_hash != key_hash or now - created >= CACHE_TTL_SECONDS:
            continue
        if country and item_country != country:
            continue
        items.append(deepcopy(item))
    return items


def _store_catalog_item(
    api_key: str,
    request: AddressRetrieveRequest,
    verified: dict[str, Any],
) -> None:
    country = request.country.upper()
    catalog_item = {
        "id": request.id,
        "text": request.text,
        "description": request.description,
        "country": country,
        "details": verified,
    }
    _cache_put(
        _catalog,
        (_api_key_cache_key(api_key), country, request.id),
        catalog_item,
    )


@app.get(
    "/api/addresses/search",
    response_model=AddressSearchResponse,
    response_model_exclude_none=True,
    tags=["addresses"],
)
async def search_addresses(
    q: str = Query(..., min_length=1, max_length=160, description="Address or postcode"),
    country: str = Query(..., min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    api_key: str = Header(..., alias="X-Loqate-Api-Key", min_length=1),
) -> AddressSearchResponse:
    query = q.strip()
    country_code = country.strip().upper()
    client_api_key = api_key.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Enter an address or postcode to search.")
    if not client_api_key:
        raise HTTPException(status_code=422, detail="A Loqate API key is required.")

    params = {
        "Key": client_api_key,
        "Text": query,
        "Countries": country_code,
        "Limit": "100",
    }
    items = await loqate_get(params)
    remaining_depth = 5
    while (
        remaining_depth > 0
        and items
        and items[0].get("Type") != "Address"
    ):
        params["Container"] = str(items[0].get("Id", ""))
        items = await loqate_get(params)
        remaining_depth -= 1

    return AddressSearchResponse(
        items=[
            AddressSearchItem(
                id=str(item["Id"]),
                text=str(item.get("Text", "")),
                description=str(item.get("Description", "")),
            )
            for item in items
            if item.get("Type") == "Address" and item.get("Id")
        ]
    )


@app.get(
    "/api/addresses/catalog",
    response_model=AddressCatalogResponse,
    response_model_exclude_none=True,
    tags=["addresses"],
)
async def retrieve_catalog(
    api_key: str = Header(..., alias="X-Loqate-Api-Key", min_length=1),
    country: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
) -> AddressCatalogResponse:
    client_api_key = api_key.strip()
    if not client_api_key:
        raise HTTPException(status_code=422, detail="A Loqate API key is required.")
    country_code = country.strip().upper() if country else ""
    return AddressCatalogResponse(items=_catalog_items(client_api_key, country_code))


@app.post(
    "/api/addresses/retrieve",
    response_model=dict[str, Any],
    response_model_exclude_none=True,
    tags=["addresses"],
)
async def retrieve_address(
    request: AddressRetrieveRequest,
    api_key: str = Header(..., alias="X-Loqate-Api-Key", min_length=1),
) -> dict[str, Any]:
    client_api_key = api_key.strip()
    if not client_api_key:
        raise HTTPException(status_code=422, detail="A Loqate API key is required.")

    retrieve_cache_key = (
        _api_key_cache_key(client_api_key),
        request.id,
        request.text,
        request.description,
        request.country.upper(),
    )
    cached = _retrieve_cache.get(retrieve_cache_key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        verified = deepcopy(cached[1])
        _store_catalog_item(client_api_key, request, verified)
        return verified

    payload = {
        "Key": client_api_key,
        "GeoCode": True,
        "Addresses": [{
            "Id": request.id,
            "Address": request.text,
            "Address1": request.text,
            "Locality": request.description,
            "Country": request.country.upper(),
        }],
        "Options": {
            "Process": "Verify",
            "Enhance": False,
            "ServerOptions": {"OutputAddressFormat": "YES"},
        },
    }
    try:
        async with httpx.AsyncClient(**loqate_client_options()) as client:
            response = await client.post(
                VERIFY_URL,
                json=payload,
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Loqate verification timed out.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Loqate.") from exc

    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"Loqate verification failed (HTTP {response.status_code}).",
        )
    try:
        items = response_items(response.json())
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Loqate returned invalid JSON.") from exc
    api_error(items)
    item = items[0] if items else None
    if not item:
        raise HTTPException(status_code=502, detail="Loqate returned no address details.")
    verified = item.get("Matches", [item])[0] if item.get("Matches") else item
    _cache_put(_retrieve_cache, retrieve_cache_key, verified)
    _store_catalog_item(client_api_key, request, verified)
    return deepcopy(verified)
