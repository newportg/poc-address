import asyncio
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from httpx import AsyncClient as HttpxAsyncClient

import main


class FakeResponse:
    def __init__(self, status_code: int, data: object) -> None:
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self.data = data

    def json(self) -> object:
        return self.data


class FakeAsyncClient:
    response = FakeResponse(200, {"Items": [{"Type": "Address", "Id": "GB|1", "Text": "1 High Street", "Description": "London"}]})
    requests: list[dict[str, object]] = []

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        type(self).requests.append({"method": "GET", "url": url, **kwargs})
        return type(self).response

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        type(self).requests.append({"method": "POST", "url": url, **kwargs})
        return type(self).response


class LoqateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        main._search_cache.clear()
        main._retrieve_cache.clear()
        main._catalog.clear()
        FakeAsyncClient.response = FakeResponse(200, {"Items": [{
            "Type": "Address",
            "Id": "GB|1",
            "Text": "1 High Street",
            "Description": "London",
        }]})
        FakeAsyncClient.requests = []
        self.client_patch = patch.object(main.httpx, "AsyncClient", FakeAsyncClient)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def test_search_forwards_key_query_and_country(self) -> None:
        result = asyncio.run(main.search_addresses(" tf26rf ", "gb", " client-key "))
        self.assertEqual(result.model_dump(), {
            "items": [{"id": "GB|1", "text": "1 High Street", "description": "London"}]
        })
        request = FakeAsyncClient.requests[0]
        self.assertEqual(request["url"], main.FIND_URL)
        self.assertEqual(request["params"], {
            "Key": "client-key", "Text": "tf26rf", "Countries": "GB", "Limit": "100"
        })

    def test_retrieve_returns_the_verified_match(self) -> None:
        FakeAsyncClient.response = FakeResponse(200, {"Items": [{"Matches": [{"Address": "1 High Street"}]}]})
        result = asyncio.run(main.retrieve_address(
            main.AddressRetrieveRequest(id="GB|1", text="1 High Street", country="gb"),
            " client-key ",
        ))
        self.assertEqual(result, {"Address": "1 High Street"})
        self.assertEqual(FakeAsyncClient.requests[0]["json"]["Key"], "client-key")

    def test_repeated_search_uses_cache(self) -> None:
        asyncio.run(main.search_addresses("ACME", "GB", "client-key"))
        asyncio.run(main.search_addresses("ACME", "GB", "client-key"))
        self.assertEqual(len(FakeAsyncClient.requests), 1)

    def test_catalog_contains_verified_addresses_and_can_filter_by_country(self) -> None:
        FakeAsyncClient.response = FakeResponse(200, {"Items": [{"Matches": [{"Address": "1 High Street"}]}]})
        asyncio.run(main.retrieve_address(
            main.AddressRetrieveRequest(id="GB|1", text="1 High Street", country="gb"),
            "client-key",
        ))
        result = asyncio.run(main.retrieve_catalog("client-key", "GB"))
        self.assertEqual(result.model_dump(), {
            "items": [{
                "id": "GB|1",
                "text": "1 High Street",
                "description": "",
                "country": "GB",
                "details": {"Address": "1 High Street"},
            }]
        })
        self.assertEqual(asyncio.run(main.retrieve_catalog("client-key", "US")).items, [])

    def test_openapi_exposes_key_header_and_both_endpoints(self) -> None:
        schema = main.app.openapi()
        self.assertIn("/api/addresses/search", schema["paths"])
        self.assertIn("/api/addresses/retrieve", schema["paths"])
        self.assertIn("/api/addresses/catalog", schema["paths"])
        headers = schema["paths"]["/api/addresses/search"]["get"]["parameters"]
        self.assertEqual(
            [parameter["name"] for parameter in headers if parameter["in"] == "header"],
            ["X-Loqate-Api-Key"],
        )

    def test_http_endpoint_returns_typed_search_response(self) -> None:
        async def make_request() -> httpx.Response:
            transport = httpx.ASGITransport(app=main.app)
            async with HttpxAsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.get(
                    "/api/addresses/search?q=ACME&country=GB",
                    headers={"X-Loqate-Api-Key": "client-key"},
                )

        response = asyncio.run(make_request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], "GB|1")

    def test_upstream_error_does_not_echo_key(self) -> None:
        FakeAsyncClient.response = FakeResponse(200, {"Items": [{"Error": "INVALID", "Description": "Invalid key"}]})
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.search_addresses("ACME", "GB", "secret-key"))
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("secret-key", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
