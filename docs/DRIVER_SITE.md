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

## Publish a real test manifest

1. Update the desktop app from GitHub and restart Python.
2. In Supabase Authentication → Users, create your operator email/password account and confirm it. Run `supabase/bootstrap_operator.sql` after replacing its email placeholder. This creates workspace membership; a dashboard login alone is not an application operator account.
3. In desktop Settings → Online shipments, sign in with that account. Credentials are sent to Supabase Auth over HTTPS through the local server. The password is not saved; the access token lives only in Python memory until expiry, sign-out or app restart.
4. Finalise fresh pallets, then create a loading manifest under Truck loading. Select it and choose **Publish online**. Confirm the upload of this manifest's pallet/form contents.
5. Print/reprint the manifest. Its QR now contains the hosted capability URL. Old paper copies still point to the local app and must be replaced. Pallet QRs remain revision-specific identifiers for the scanner.
6. Open the new manifest QR on the phone. Scan the associated pallet QRs and confirm pickup/delivery. Use **Refresh online status** on the desktop to retrieve progress and release uncollected pallets after a partial pickup.

This first integration supports fresh revision-1 pallets and unscanned ready manifests. Local scans are not merged. Reopening published pallets, online cancellation and migration of older local revisions are blocked pending the shared editing workflow. Publish only when the online unassigned pallets for that building match the selected manifest exactly. Existing online records are checked before retrying an uncertain publish; writes are not automatically retried. The operator app remains a local workspace with explicit publishing and refresh, rather than general multi-workstation synchronization.

The capability URL is saved in the local workspace so manifest reprints preserve the same QR. Workspace backups therefore contain shipment access links; share backups only with authorized operators. Publishing does not upload the SAP import tables. Only the chosen manifest's pallet/form data is uploaded. Driver responses contain the limited shipment DTO.

## Checks

Run `npm run test:driver`, `npm run test:database`, `node tests/ui-smoke.cjs`, and `python -m unittest discover -s tests`. Browser checks cover the demonstration workflow and responsive phone layout; database tests exercise the real RPC permissions and transitions.
