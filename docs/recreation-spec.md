# POC Address Recreation Specification

This document is the implementation specification for recreating the Address
Explorer POC if the source application is unavailable. It complements
[design.md](./design.md), which explains the architecture and research context.

## Product purpose

Build a static browser application that:

1. Searches international addresses through Loqate.
2. Verifies a selected address and requests geocoding.
3. Displays formatted and raw verified address fields.
4. Shows search-result and verified-address locations on an interactive map.
5. Provides a catalogue of recently verified addresses with local search and
   country filtering.

This is a proof of concept. It is not an address database, an identity system,
or a deliverability/legal verification service.

## Runtime shape

The application has no frontend build step or framework:

```text
src/
  poc-address-app.html   Complete browser application and inline UI logic
  loqate-client.js       Browser API client and catalogue filtering helper
  config.js              ADDRESS_API_BASE_URL configuration
api/
  main.py                FastAPI Loqate proxy
  requirements.txt       FastAPI, httpx, and uvicorn
  Containerfile          Python container image
  start.py               Local/container server entry point
scripts/
  run-local.ps1          Starts the API and static client locally
  serve-client.js        Static file server
docs/
  index.html              Published copy of the application
  loqate-client.js        Published copy of the browser client
  config.js               Published API configuration
```

Leaflet 1.9.4 is loaded from unpkg.com. OpenStreetMap tiles are used for the
map. Both services require browser network access.

## UI specification

The page contains:

- A dark/light theme toggle. Persist the theme as
  `poc-address.theme.v1` in `localStorage`.
- Country selector with GB, US, DE, FR, ES, IT, NL, BE, IE, PT, AU, and CA.
- Address/postcode query input.
- Loqate API key password input and save button. Persist it as
  `loqate_api_key`.
- Search button and status/error messages.
- Search-results catalogue showing result text and description.
- A compact map preview and an expandable full-size map dialog.
- A verified-address detail panel.
- A verified address catalogue with:
  - refresh button;
  - free-text local filtering;
  - country filtering;
  - record count;
  - selectable records.

Selecting a search result or catalogue record must:

1. Show the detail panel.
2. Render the verified address.
3. Center the map on valid latitude/longitude values.
4. Create or update the marker.
5. Open the marker popup.

Catalogue selection uses its cached `details` object and must not issue another
verification request.

## Address rendering

If `AddressFormat` is present, split it on `<BR>` tags. For each line, resolve
the field names against the verification response and display non-empty values.
If it is absent, display the `Address` field.

The raw field table excludes formatted/redundant fields including `Address`,
`Address1`-`Address5`, `AddressFormat`, delivery-format fields, quality/status
fields, `Sequence`, `MatchRuleLabel`, `HyphenClass`, `ID`, and `Country`.

Latitude and longitude are accepted only when numeric and within normal
geographic bounds.

## Demo mode

Without an API key, use built-in fixtures:

- `tf26rf` → `93 Teagues Crescent`, Trench Telford TF2 6RF
- `EC2M 7NH` → `1 Liverpool Street`, London EC2M 7NH

Demo verification data must include address lines, `AddressFormat`, country,
postcode, latitude, longitude, `AVC`, and `AQI`. Demo mode does not populate
the server-side catalogue.

## Client behavior

`LoqateClient` must expose:

```javascript
search(apiKey, country, query)       // Promise<SearchItem[]>
retrieve(apiKey, result, country)     // Promise<VerifiedAddress>
catalog(apiKey, country = "")        // Promise<CatalogItem[]>
filterCatalog(items, query, country) // CatalogItem[]
```

`filterCatalog` performs case-insensitive local matching against the serialized
catalogue record and applies an optional exact country filter.

## API and server behavior

The API contract is documented separately in [api-contract.md](./api-contract.md).
The proxy must:

- forward the caller's Loqate API key only to Loqate;
- never include the key in an error response;
- recursively follow Loqate Find containers up to five levels;
- cache successful search and verification results;
- add successful verified addresses to the in-memory catalogue;
- isolate cache and catalogue entries by an SHA-256 API-key fingerprint;
- deep-copy cached values before returning them;
- expire entries after five minutes by default;
- cap each cache at 256 entries;
- allow `ADDRESS_CACHE_TTL_SECONDS=0` to disable caching.

The cache and catalogue are intentionally process-local and non-durable.

## Configuration and operations

Required environment variables:

```text
CORS_ORIGINS=*
ADDRESS_CACHE_TTL_SECONDS=300
```

Optional:

```text
LOQATE_CA_BUNDLE=C:\path\company-root.cer
```

The API listens on port 8001. The local static client is served on port 5174.
Run the local environment with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

## Acceptance checklist

- Search sends `q`, `country`, and `X-Loqate-Api-Key`.
- Repeated identical searches do not call Loqate while the cache is valid.
- Verification returns the first verified match and caches it.
- `GET /api/addresses/catalog` returns verified records for the caller's key.
- Catalogue query and country filters work without another API request.
- Catalogue selection displays details and updates the map.
- Invalid upstream JSON, timeouts, network errors, and upstream errors produce
  explicit user-visible failures.
- API keys never appear in logs, response bodies, or error details.
- API tests cover forwarding, caching, catalogue retrieval, filtering, and
  upstream failure handling.
