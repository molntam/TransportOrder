# Tracking and driver website

Website: https://molntam.github.io/TransportOrder/

The static website is deployed by `.github/workflows/pages.yml` from `driver-site/dist` to GitHub Pages. Repository Settings → Pages uses **GitHub Actions**. GitHub hosts the interface; Supabase stores private shipment records. No shipment data, credentials or workstation keys are committed to GitHub.

## Website login and tracking

Open the website without a QR to log in with an existing Supabase Auth account. Membership of the Delivery Operations workspace is required; creating an account alone does not grant access. Authorized viewers, operators and administrators can search DN, HU, form, pallet and manifest references, including archived records. Results show the latest 200 matches; narrow a search to find older documents. Expand a result for DN/HU quantities and its recorded events. Status and timestamps come from the linked online loading manifest when available.

The browser saves the tracking session and renews it when needed. Use **Sign out** on a shared browser. Search keeps the highest matching document for each shipment and leaves unrelated matches visible.

## Authorize a workstation

Sign in with an operator account in desktop **Settings → Online shipments**. The app exchanges the sign-in for a revocable workstation credential and saves it using the existing workstation storage. The password stays out of local storage.

The driver site remembers up to 20 recently opened manifests for seven days. **Return to your shipment** lists saved stops. Drivers can scan another manifest and switch between stops. A pallet from another saved manifest is recorded against that manifest. Dispatch must assign loose pallets before drivers can scan them.

## Publish and scan

Finalise fresh pallets, create a loading manifest, select it and choose **Publish online**. Then print/reprint the manifest. Its QR uses `https://molntam.github.io/TransportOrder/#<64-character random capability>`.

Drivers do not log in. The capability grants access to one manifest, expires after seven days and is checked for revocation and revision changes. Scan pallet QRs continuously, or use manual/scanner input. Duplicate scans count once; wrong destinations and outdated pallet revisions are rejected. Partial pickup requires a reason. Uncollected pallets remain ready for another truck. Confirm arrival and receiver at delivery. Desktop **Refresh online status** retrieves phone progress.

Camera capture requires HTTPS and a user click on Start camera. Permission denial leaves manual entry available. The scanner does not focus a text field automatically; form inputs are at least 16px to avoid iOS focus zoom. Physical iOS/Opera GX camera testing remains a device acceptance check.

Old paper copies keep their original URL and must be reprinted. Previously saved online manifests are migrated to the GitHub URL on app restart, preserving their existing capability token. Reprint paper copies to use the new address. Existing local scans are not merged. The first publishing integration supports fresh revision-1 pallets and explicit selected-pallet membership. Published pallet reopening, older revision migration and online cancellation remain deferred.

## Daily desktop workspace and archive

The active desktop resets at the start of a new Europe/Amsterdam calendar day, on the next state read/action. A running UI checks once a minute. Settings and the workstation pairing remain; the previous day's forms, pallets, manifests, events and SAP infeed leave the active workspace. A complete JSON copy is written successfully under `TransportOrderData/archive/workspaces` before the reset. If archiving fails, the old workspace is retained.

Print-and-keep-open, finalisation and manifest creation generate local printable HTML copies under `archive/documents` and immutable revision snapshots under `archive/outbox`. A paired running desktop uploads queued snapshots to Supabase every ten seconds, then moves successful entries to `archive/uploaded`. Failed uploads stay queued. Settings displays pending count and errors. Publishing also archives the online manifest mapping. Reprinting retries local archiving. SharePoint is out of scope.

The desktop front page counts distinct infeed HUs not yet assigned to a non-removed pallet form. The count uses the current SAP infeed, not an inferred count from old shipments.

## Checks

Run `python -m unittest discover -s tests -q`, `node tests/ui-smoke.cjs`, `npm run test:driver` and `npm run test:database`. PostgreSQL tests cover membership isolation, device restrictions/revocation, immutable archives, search, token redaction and driver flows. Local tests cover archive retry and rollover preservation. Live user password sign-in and physical camera capture require user/device testing.
