import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field


FIND_URL = "https://api.addressy.com/Capture/Interactive/Find/v1.20/json6.ws"
VERIFY_URL = "https://api.addressy.com/Cleansing/International/Batch/v1.20/json6.ws"


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
    return items


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
    return item.get("Matches", [item])[0] if item.get("Matches") else item
