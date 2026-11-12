# POC Address API Contract

The API is a FastAPI proxy for Loqate. The default local base URL is
`http://127.0.0.1:8001`.

All address endpoints require:

```http
X-Loqate-Api-Key: <caller Loqate key>
Accept: application/json
```

The proxy does not persist or expose the API key.

## `GET /health`

Response:

```json
{"status": "ok"}
```

## `GET /heartbeat`

Response:

```json
{"status": "awake"}
```

## `GET /api/addresses/search`

Query parameters:

| Parameter | Required | Rules |
|---|---:|---|
| `q` | yes | 1-160 characters; address or postcode |
| `country` | yes | Two alphabetic characters; normalized uppercase |

Example:

```http
GET /api/addresses/search?q=tf26rf&country=GB
X-Loqate-Api-Key: caller-key
```

Response:

```json
{
  "items": [
    {
      "id": "GB|RM|B|24490784|ENG",
      "text": "93 Teagues Crescent",
      "description": "Trench Telford TF2 6RF"
    }
  ]
}
```

The proxy calls Loqate Find with `Limit=100`. If the first response is a
container rather than an address, it follows the first container's `Id` using
`Container`, up to five levels.

## `POST /api/addresses/retrieve`

Request:

```json
{
  "id": "GB|RM|B|24490784|ENG",
  "text": "93 Teagues Crescent",
  "description": "Trench Telford TF2 6RF",
  "country": "GB"
}
```

Rules:

- `id` and `text` are required non-empty strings.
- `description` defaults to an empty string.
- `country` is exactly two characters and is normalized uppercase.
- Unknown request fields are rejected.

The proxy calls Loqate International Batch Verify with geocoding enabled and
returns the first item in `Matches`, or the item itself when `Matches` is
absent.

Example response:

```json
{
  "Address": "93 Teagues Crescent<br>Trench<br>Telford<br>TF2 6RF",
  "Address1": "93 Teagues Crescent",
  "Address2": "Trench",
  "Locality": "Telford",
  "DependentLocality": "Trench",
  "PostalCode": "TF2 6RF",
  "CountryName": "United Kingdom",
  "ISO3166_2": "GB",
  "Latitude": "52.707846",
  "Longitude": "-2.460302",
  "AVC": "V44-I44-P6-100",
  "AQI": "A"
}
```

Successful verification adds a record to the process-local catalogue.

## `GET /api/addresses/catalog`

Optional query parameter:

| Parameter | Rules |
|---|---|
| `country` | Optional two-letter country code |

Example:

```http
GET /api/addresses/catalog?country=GB
X-Loqate-Api-Key: caller-key
```

Response:

```json
{
  "items": [
    {
      "id": "GB|RM|B|24490784|ENG",
      "text": "93 Teagues Crescent",
      "description": "Trench Telford TF2 6RF",
      "country": "GB",
      "details": {
        "Address": "93 Teagues Crescent<br>Trench<br>Telford<br>TF2 6RF",
        "Latitude": "52.707846",
        "Longitude": "-2.460302"
      }
    }
  ]
}
```

The catalogue contains only successfully verified addresses. It is scoped by
the caller's API-key fingerprint and is not durable. An empty catalogue returns
`{"items":[]}`.

## Errors

The proxy uses FastAPI validation responses (`422`) for invalid requests and:

| Status | Meaning |
|---:|---|
| `502` | Loqate network failure, rejected response, invalid JSON, or unexpected payload |
| `504` | Loqate request timed out |

Error bodies use:

```json
{"detail": "A human-readable message"}
```

Messages must not echo the API key.

## Cache behavior

Successful search and retrieve requests are cached in process memory for five
minutes by default. Configure the duration with
`ADDRESS_CACHE_TTL_SECONDS`. Setting it to `0` disables storage and causes
catalogue records to expire immediately. Each cache is capped at 256 entries.
Cache keys include an SHA-256 API-key fingerprint, so callers cannot see another
caller's cached results.
