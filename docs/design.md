# POC Address Application Design

Architecture, data flow, and technology stack for the intended production application,
as presented on the POC Design tab of the [reference page](C:/Source/Repos/poc-address/docs/index.html).

## Architecture

```mermaid
flowchart TB
    subgraph Client["Svelte SPA"]
        direction LR
        SB["Search Bar<br/>+ Country Selector"]
        MAP["Leaflet Map<br/>OpenStreetMap"]
        RL["Results List<br/>Clickable Items"]
        SB ~~~ MAP ~~~ RL
    end

    subgraph API["SvelteKit API Routes"]
        direction LR
        C["/api/countries<br/>GET"]
        S["/api/search<br/>GET"]
        R["/api/retrieve<br/>GET"]
        D["/api/docs<br/>GET"]
        C ~~~ S ~~~ R ~~~ D
    end

    subgraph External["External Services"]
        direction LR
        FIND["LOQATE Find<br/>Capture Interactive<br/>Find API v1.20"]
        VERIFY["LOQATE Verify<br/>Cleansing International<br/>Batch API v1.20"]
        CACHE[("SQLite Cache<br/>address_cache<br/>better-sqlite3")]

    end

    Client --> API
    API --> FIND
    API --> VERIFY
    API --> CACHE
```

## Component Diagram

```mermaid
graph LR
    subgraph Pages
        P[+page.svelte]
        DOCS[docs/+page.svelte]
    end

    subgraph Components
        MAP[Map.svelte]
    end

    subgraph Lib
        TYPES[types.ts]
        CACHE[cache.ts]
    end

    subgraph API
        COUNTRIES[api/countries]
        SEARCH[api/search]
        RETRIEVE[api/retrieve]
        DOCS_API[api/docs]
    end

    P --> MAP
    P --> TYPES
    MAP --> TYPES
    SEARCH --> TYPES
    RETRIEVE --> CACHE
    DOCS --> DOCS_API
```

## Data Flow

User Search → LOQATE Find → Map Markers → User Selects → Cache Check → LOQATE Verify → Formatted Address

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Svelte SPA
    participant API as API Routes
    participant L as LOQATE
    participant DB as SQLite Cache

    U->>UI: Select country + enter query
    UI->>API: GET /api/search?country=GB&query=tf26rf
    API->>L: Find API (recursive container drill-down)
    L-->>API: Address results
    API-->>UI: { results: [...] }
    UI->>UI: Plot markers on map

    U->>UI: Click address in list
    UI->>API: GET /api/retrieve?id=...&country=GB
    API->>DB: Check cache
    alt Cache hit
        DB-->>API: Cached response
    else Cache miss
        API->>L: Verify API (OutputAddressFormat=YES)
        L-->>API: Verified address + AddressFormat
        API->>DB: Store response
    end
    API-->>UI: { match: {...} }
    UI->>UI: Display formatted address using AddressFormat
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/countries` | GET | List of countries with flags |
| `/api/search` | GET | Search addresses via LOQATE Find |
| `/api/retrieve` | GET | Get verified address via LOQATE Verify |
| `/api/docs` | GET | OpenAPI 3.0 JSON spec |
| `/docs` | GET | Swagger UI |

## Database Schema (Cache)

```sql
CREATE TABLE address_cache (
    id TEXT PRIMARY KEY,      -- Address ID from LOQATE Find
    response TEXT NOT NULL,   -- JSON blob of LOQATE Verify response
    created_at INTEGER NOT NULL -- Unix timestamp
);
```

## Address Formatting

The `AddressFormat` field from LOQATE defines how to construct the formatted address. It's a string with field names separated by `<BR>` tags.

**Example (UK):**

```
Organisation<BR>DeliveryAddress<BR>Locality AdministrativeArea PostalCode
```

**Rendering Logic:**

1. Split `AddressFormat` by `<BR>` to get lines
2. For each line, split by whitespace to get field names
3. Look up each field name in the LOQATE response
4. Join non-empty values with spaces

## Standard

Uses **UPU S42** (not ISO 20022). UPU S42 is more flexible, covers more countries, and is designed for web application adaptation.

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Svelte 5 + SvelteKit 2 |
| Map | Leaflet + OpenStreetMap |
| API | SvelteKit server routes |
| Cache | SQLite (better-sqlite3) |
| API Docs | Swagger UI |
| External | LOQATE Find + Verify APIs |

## User Flow

```mermaid
flowchart TD
    A[Page Load] --> B[Fetch Countries]
    B --> C[Display World Map]
    C --> D[User Selects Country]
    D --> E[User Enters Search Query]
    E --> F[Search API Call]
    F --> G[Display Markers on Map]
    G --> H[User Clicks Marker or List Item]
    H --> I[Retrieve API Call]
    I --> J{Cache Hit?}
    J -->|Yes| K[Return Cached Data]
    J -->|No| L[LOQATE Verify Call]
    L --> M[Store in Cache]
    M --> K
    K --> N[Display Formatted Address]
    N --> O[Show Verification Badges]
    O --> P[Show All Fields]
```


Related: [[Loqate-api]].
