# Driver website

The login-free driver interface lives in `driver-site/dist`. The desktop operator app stays local for now. Connecting the GitHub repository to Supabase is optional; the website calls the existing Supabase RPC directly.

Production: https://transportorder-driver.chicaron.chatgpt.site

Demonstration: https://transportorder-driver.chicaron.chatgpt.site/?demo=1

The demonstration uses 20 fictional pallets, resets on reload and never writes to Supabase. A valid shipment capability always takes precedence over demo mode.

## Driver flow

1. Open the loading manifest QR, formatted as `https://transportorder-driver.chicaron.chatgpt.site/#<64-character random hex capability>`.
2. Scan pallet QRs continuously, or enter codes with a handheld scanner. Correct pallets count once; wrong-building, foreign and outdated pallet codes are rejected.
3. Confirm pickup with driver name and vehicle registration. Partial pickup requires a reason. Uncollected pallets remain available for a later truck.
4. At the destination, confirm the building, receiver and physical arrival.

The page shows shipment progress, pallet contents, DNs, HUs and quantities. Search accepts pallet IDs, DNs and HUs. Scans can be removed before pickup with a reason. The interface refreshes while visible and asks for another review if it detects a shipment change during confirmation.

## Access and deployment

The capability grants access to one manifest; treat the QR like a private shipment document. The backend checks expiry, revocation and document revisions. Default capability lifetime is seven days. No driver account is required. The token is kept in the URL fragment and request body, never a request URL or browser storage. Driver names and registrations are sent only when confirming the shipment.

`config.mjs` contains only the Supabase URL and public publishable key. It must never contain a service-role key. The UI calls only `transport_driver`; anonymous users have no direct table access. See [Supabase setup](SUPABASE.md).

All assets are self-hosted. Camera access starts only after the driver presses Start camera and requires HTTPS or localhost. Permission denial leaves manual scanning available. Camera streams stop when the dialog closes, the page hides or the link becomes unavailable. Real phone camera capture still needs device acceptance testing.

`.openai/hosting.json` identifies the existing public Sites project. Deploy `dist` as static assets. Preserve fragment URLs. `_headers` supplies additional privacy/security headers where supported; the HTML also supplies CSP and no-referrer metadata.

## Remaining operator integration

The local app does not yet publish its loading manifests to Supabase or print these online capability links. Existing local QR documents keep their current behavior. Next: add operator authentication and a protected publisher, upload finalized manifests, print the returned capability URL, then display shared pickup/delivery status in the desktop workspace. Do not place an operator credential or service-role key in this public website. No real shipment records have been created for this interface.

## Checks

Run `npm run test:driver`, `npm run test:database`, `node tests/ui-smoke.cjs`, and `python -m unittest discover -s tests`. Browser checks cover the demonstration workflow and responsive phone layout; database tests exercise the real RPC permissions and transitions.
