# POC Address

A browser-based proof of concept for address search and verification, with a
companion international-addressing reference page. The app uses static HTML, CSS,
and browser-native JavaScript, matching the POC Asset app's no-framework approach.
Loqate requests are proxied through a small FastAPI service, which can run in a
local Podman container.

The research and discovery notes live in the Address project folder in the
knowledge vault: `C:\Source\Obsidian\Projects\POC-Documentation\POC-Documentation-Vault\projects\Address`.

## Run

Open the standalone app in a browser:

```powershell
Start-Process src\poc-address-app.html
```

No build step or dependency installation is required to run the app. Leaflet is
loaded from unpkg.com and map tiles from OpenStreetMap, so those services must be
reachable in the browser. The app's Documentation button opens the
international-addressing guide. The current implementation is also described in
`docs/design.md`.

## Run the local API with Podman

Install Podman Desktop and Node.js, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

The script builds and starts the FastAPI container, serves the generated client,
and opens the app. The API's interactive OpenAPI page is at
`http://127.0.0.1:8001/docs`.

The runner carries a trusted Windows Zscaler root certificate into the container
when one is installed. For another corporate certificate, provide it explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1 -CaCertificatePath C:\path\company-root.cer
```

## Publish the app and documentation

From the repository root, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish.ps1
```

The script reads the Address vault notes and sources under `src\`, then
generates the GitHub Pages site under `docs\`:

- `docs\index.html` — primary Address Explorer app with a Documentation button
- `docs\documentation.html` — international-addressing guide
- `docs\documentation.css` — guide styles matching the Asset documentation page
- `docs\loqate-client.js` — browser-side Loqate client for the home page
- `docs\config.js` — API base URL configuration for the published client
- `docs\design.md` — copy of the current POC design note in the Address vault project

The default vault location is the sibling `C:\Source\Obsidian\...` checkout shown
above. Pass `-VaultProjectPath` if the vault is checked out elsewhere.

## Publish to GitHub Pages

The `Publish GitHub Pages` workflow deploys the committed `docs\` site whenever
files in that folder change on `master`. Before pushing app or standards changes,
run the publish script above and include the regenerated `docs\` files in your
commit. You can also start a deployment manually from the repository's Actions tab.

For the first deployment, set the repository's Pages source to **GitHub Actions**
under **Settings → Pages**.

## Project layout

- `src\` — standalone browser app, API client, configuration, and documentation sources.
- `api\` — FastAPI Loqate proxy, tests, and Podman Containerfile.
- `scripts\` — publishing and local Podman runner scripts.
- `docs\` — generated app, documentation, and published design note.

The Loqate API key is entered in the app and stored in browser `localStorage`,
then sent to the API in the `X-Loqate-Api-Key` header. The key is not stored by
the proxy and this remains a proof-of-concept, not a production secret store.
The browser client is in `src\loqate-client.js`; the Loqate calls are in
`api\main.py`.
