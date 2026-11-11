> Spotfire is temporarily disabled because the current report omits deliveries. SAP paste/import is the active source for new and existing workspaces. The integration code is retained for a future complete report.

# TransportOrder

A local shipping workspace for preparing transport orders between warehouses in the Netherlands. The interface uses ASML-inspired blue, larger Segoe UI text, stronger contrast, and light/dark themes, with the form in the centre and open pallets on the right.

## Changes in 0.9.2

- Department receiving uses the connected QR scanner, without camera controls. Scanner letter-case changes in the handover URL and token are accepted. Complete scans are checked automatically, with Enter/manual submission also supported.
- Published department transport orders appear under Pallets as **Awaiting receipt**. The receiving button shows their count. Authorized workstations refresh incoming orders every 15 seconds; a failed refresh retains the last known list and shows an error.
- Open Orders is combined with FIFO tracker. **Not counted** lists material outside the FIFO rules, including DN, HU, ship-to, storage bin and SAP change time. S4/I2 orders in INTER-IN still raise emergency alerts.

## Changes in 0.9.0

- The tracking website opens with global search and ten building tabs. Each building separates **In process**, **Ready for Pick-up**, **Collected** and **Delivered**. Building names lead the cards. The current search, category and expanded document survive reloads; sign-in remains saved until sign-out or session revocation.
- Tracking shows actual collected contents after a partial pickup. The driver comment stays visible; uncollected pallets appear separately until assigned to another manifest. Delivery records show the receiver's name. The desktop checks online status every 15 seconds and makes released pallets available automatically.
- **FIFO tracker** monitors `PS_READY-INT`: S1/I1 after four hours, S2/I8 after two hours, S4/I2 immediately. S4/I2 also alert in `INTER-IN`. Age uses SAP **Changed On / Changed At**, interpreted in Europe/Amsterdam. Missing timestamps are listed for correction. Refresh SAP regularly; this is not an automatic SAP connection.
- **Settings → Department workspace** defaults to Delivery Operations. Another department supplies its name and location and gets a manual **Print transport order form** workflow. Sign in under Online shipments before printing its QR document. Tracking starts at **At [department]**.
- Delivery Operations uses **Create order → Receive transport order** to scan a department QR, check the original contents and receive an **Open Pallet** or **Finalised Pallet**. A finalised receipt prints the normal pallet QR for loading. The original department form remains an immutable revision; retries do not create another pallet.
- All displayed operational times use Europe/Amsterdam and 24-hour time. Dock-slot inputs use `HH:MM`. Version 0.9.1 includes the approved Monday–Friday schedule below, including existing workspaces. Custom windows are retained; later edits or removals are preserved.

### Weekday dock slots (Europe/Amsterdam)

| Destination | Arrival windows, Monday–Friday |
|---|---|
| Weert 1A | 06:30–07:00; 11:30–12:00; 14:30–15:00 |
| Weert 1B | 08:00–08:30; 15:00–15:30; 18:30–19:00; 20:00–20:30; 22:00–22:30 |
| Weert 2 | 08:30–09:00; 12:00–12:30; 20:30–21:00 |
| Building 21 | 09:00–09:30; 13:30–14:00; 22:30–23:00 |
| Building 9 and Building 17 | 07:00–07:30; 12:30–13:00 |
| Building 30 | 07:30–08:00; 14:00–14:30 |

Building 9 and Building 17 use the same windows and retain separate building-specific reminders. No slots are assigned to other buildings. Reminders begin 20 minutes before each window when there is work to dispatch.

The website remains on [GitHub Pages](https://molntam.github.io/TransportOrder/). Apply the new Supabase migration before deploying the new clients. Spotfire remains disabled and SharePoint is not used.

## Run

Requires **Python 3.10 or later**. SAP paste/import runs without pip packages. For automatic Spotfire collection, run **`setup_spotfire.bat`** once to install the optional browser dependency; see [Spotfire setup](docs/SPOTFIRE.md). Node is not needed to run the app.

On Windows, double-click **`start.bat`**, or run from the repository folder:

```powershell
py -3 run.py
```

On macOS / Linux:

```bash
python3 run.py
```

Keep the terminal open. With Spotfire enabled, the app opens in a visible Edge window with a separate report tab for your corporate sign-in. Without the optional dependency it opens the existing local workspace and shows the setup instructions. SAP mode uses the dedicated Edge application window. To explicitly use your default browser for the workspace, including Firefox:

```powershell
py -3 run.py --browser default
```

If the browser does not open automatically, use the full local link printed in the terminal. The session portion of that link is required. Run `py -3 run.py --help` for the other options.

## First test

SAP paste/import is the active source while Spotfire is disabled.

To test the SAP workflow:

1. Open **Data infeed** and choose **Use SAP paste/import**.
2. Click an input cell and press **Ctrl+V** to paste the **Ship-to** and **Quantities** SAP tables. Headers are prefilled for data-only pastes; a paste containing headers replaces the input grid. File import (`.xlsx`, `.csv`, `.tsv`, `.txt`) is still available.
3. Click **Validate & apply**, resolving any errors. Leaving Data infeed also applies changed valid cells. Pasted quantities can use a decimal point or comma; select the matching format before validating. XLSX quantities use the workbook's numeric values.
4. Open **Create order**. Enter HUs one by one or use **Paste HUs**. Destination, DN, quantity and Emergency fill from the imports.
5. Enter optional part numbers, descriptions and remarks.
6. Use **Print & keep open** to save the form and print **one copy** directly. Select that pallet on the right to add another form.
7. Use **Finalise pallet** when ready. It saves the consolidation and prints **two copies** directly, without a browser print screen.
8. Use **History** to resume drafts, inspect revisions, reprint or reopen a pallet for correction.

For fictional examples, choose **Load fictional demo** in Data infeed. `DEMO-HU-001` and `DEMO-HU-002` share a destination; the first sums to 25 and the second triggers Emergency. `DEMO-HU-003` demonstrates a conflicting destination. `DEMO-HU-004` and `DEMO-HU-005` demonstrate the Weert scrap/re-use split. `DEMO-HU-006` requires an explicit NL05 destination.

## Included in this phase

- Automatic and manual entry, building presets and searchable/free-text destinations.
- HU-level quantity totals, ERP delivery numbers, route lookup and Emergency from S4 or I2.
- Specific errors for missing HUs, duplicate assignments, document mismatches, missing quantities and incompatible destinations.
- Separate Weert 1A scrap and re-use routes; explicit Weert / Eindhoven selection for NL05C.
- Drafts, multiple open pallets, several forms per pallet and consolidated delivery summaries.
- Local persistence, a previous-state backup, an export-backup button and protection against stale-window saves.
- Versioned completed forms and pallet documents; reopening retains the old consolidation and marks it superseded.
- A4 portrait direct Windows printing, separate copy defaults for open forms/final pallets and optional previews from History.
- Consolidations omit individual form IDs and hide unused 12NC/description columns; final documents include a scannable revision-specific pallet QR.
- Destination choices show building and ship-to together; Building 05, Best II and Eindhoven 1 are removed from the destination picker. Origin choices are retained.
- Settings for appearance, origin, preparer, printer and copies. Optional receiver contact details, Emergency and Special Pick-up flags.

**Printing on Windows is direct.** Settings defaults to **Windows default**, resolved afresh for each job. You can choose a fixed installed printer without changing the Windows default. Open forms default to **1 copy** and finalised pallets to **2 copies**, with separate settings for each. The app submits an A4, one-sided job through Windows PowerShell/.NET and uses no external PDF-printing application. The bundled C# helper is compiled by Windows PowerShell; no separate compiler installation is needed. Organisation policies that disable PowerShell or `Add-Type` can prevent direct printing; the app reports the error and retains the saved document.

History → document revision opens an optional preview. **Print directly** uses the selected Windows printer; **Save PDF** explicitly opens the browser dialog. Microsoft Print to PDF/XPS jobs use a generated file under the workspace's `printouts` folder. Queue submission confirms the job was sent to Windows, not that paper was produced. A failed or timed-out submission is not automatically retried; check the print queue before using Retry.

Appearance can be changed in Settings (Light, Dark, Follow system), or toggled from the top bar. Existing workspaces keep their forms and pallets, and gain the new 1/2-copy defaults automatically.

## Data and current limits

Data is saved outside the repository in **`~/TransportOrderData`** (`%USERPROFILE%\TransportOrderData` on Windows). The main file is `transport-order.json`; the previous successful state is `transport-order.previous.json`. Closing the browser does not delete saved work. One application process can open a data folder at a time. Multiple browser windows share that process, with revision checks preventing overwrites.

**The preparation app is a local workstation application with shared online tracking.** Loading manifests, pallet QRs and the driver loading screen work in this local workspace. A separate public driver website is available in `driver-site`; see [Driver website](docs/DRIVER_SITE.md). Fresh revision-1 loading manifests can be explicitly published from Truck loading after one-time workstation pairing in Settings; reprint the manifest to use its online QR. Desktop progress updates through Refresh online status. Shared desktop storage and SharePoint PDF uploads are not connected. Spotfire collection runs locally through the signed-in report tab; see [Spotfire setup and limits](docs/SPOTFIRE.md). The app does not notify another workstation. Preparer and driver names are self-reported labels. Tracking viewers sign in on the website. The active app resets daily after archiving; see the driver website documentation.

Part numbers and descriptions remain manual because the two current SAP exports do not contain them. One automatic row represents an HU's aggregate quantity; it does not invent item-level material details. A form supports up to 500 rows. Each input supports up to 50,000 source records.

The server binds only to `127.0.0.1`, uses a fresh session token at startup and rejects cross-origin API requests. It is intended to run locally, not to be exposed as a production web server. Application assets have no runtime CDN dependencies. The supplied SAP workbooks and transaction rows are not included in this repository.

## Code map

| Path | Responsibility |
|---|---|
| `run.py`, `start.bat` | Start the local workspace |
| `transport_order/server.py` | Local API, session checks and browser launcher |
| `transport_order/domain.py` | HU resolution, validation, forms, pallets and history |
| `transport_order/integrations/sap.py` | Paste, CSV and XLSX ingestion |
| `transport_order/integrations/spotfire.py`, `spotfire_browser.py` | Spotfire CSV validation, destination aliases and signed-in browser collection |
| `transport_order/locations.json` | Origin/destination directory and operational routing |
| `transport_order/loads.py` | Loading manifests, reservations, scan validation, pickups and weekday dock slots |
| `transport_order/qr.py` | Offline QR encoding shared by HTML and native printing |
| `transport_order/storage.py` | Atomic JSON persistence and concurrency protection |
| `transport_order/printing.py` | Shared document model and printable HTML |
| `transport_order/native_print.py`, `transport_order/native/NativePrinter.cs` | Windows printer discovery, direct spool submission and paginated native rendering |
| `transport_order/web/` | Browser interface, styles and interactions |
| `tests/` | Import, routing, workflow, persistence and API tests |
| `docs/` | Extracted workbook rules, architecture and test guide |

## Validation

```bash
python -m unittest discover -s tests -v
node --check transport_order/web/app.js
node tests/ui-smoke.cjs
```

Node is only needed for the optional JavaScript syntax check and developer UI checks; it is not needed to run the app. See [the test guide](docs/TESTING.md) for the Windows and printer acceptance checks.

The UI layout takes inspiration from [Cargix TMS](https://dribbble.com/shots/26814297-Cargix-TMS-Logistics-Web-Dashboard). Implementation, icons and styles are original; this is a prototype, not an official ASML product.

## Changes in 0.3.0

- Queue-print helper responses use a separate JSON result file so driver stdout cannot corrupt acknowledgement parsing. Queue submission still requires local verification with the installed print manager.
- Validate immediately applies SAP data. Leaving Data infeed automatically validates and applies changed inputs, blocking navigation on errors.
- Open orders lists imported DN/HU, storage bin, ship-to and SAP change date/time, excluding HUs assigned to active pallets (including pallet drafts). Refresh SAP inputs to see current bins; this is not live SAP polling.
- Pallet details immediately shows DN/HU/quantity rows.
- QR placeholders are top-right in the header; building names are larger and bold. Single-delivery final documents are titled Transport order.
- WH21-MPSC is grouped under Building 21; Weert 2 includes Key sight.

## Changes in 0.4.0

Summary cards are in History, keeping order processing focused. Open pallets display building and ship-to together and can be searched by destination, DN or HU. Completing a form parks its pallet without automatically selecting it; select a parked pallet explicitly to add more forms.

Before completing/printing, free-text remarks require Keep/Cancel confirmation. Exact Emergency notes are exempt when Emergency applies, and exact Keysight notes only when the current destination is Keysight. Cancelling retains the editor for correction. Empty optional part/description columns are omitted from individual orders as well as consolidations.

Data infeed presents Internals and Quantities side by side, with an Expand/Collapse control on each. Narrow screens stack the tables.


## Changes in 0.5.0 — truck loading

1. Review or adjust the approved weekday arrival windows in **Dock slots**. Times use Europe/Amsterdam; an in-app reminder starts 20 minutes before the slot when that building has open or unassigned ready pallets. The app must stay running. Manifest copies default to one and can be changed here.
2. In **Truck loading**, choose **Create manifest** for a building. It includes every unassigned finalised pallet for that building, including different ship-to departments, and excludes open/collected pallets. Pallets from different origins cannot be combined. The immutable manifest lists pallet/consolidation IDs and revisions, form IDs, ship-to, DNs, HUs and quantities. Preview and print the driver copy explicitly.
3. Included pallets are reserved against other manifests and cannot be reopened. Cancel the manifest with a reason before correcting an uncollected pallet. A cancelled manifest is retained and its print marked superseded.
4. Open **Continue loading**, or scan the manifest QR in the authenticated local workspace. Start the camera once and scan pallet QRs continuously. A USB scanner or QR text input also works. The bundled reader works offline; camera permission is requested only on Start camera.
5. Progress counts pallets, such as 1/20. Wrong-building, unrelated and superseded QRs are rejected. Duplicate scans leave progress unchanged. **Remove from truck** reverses a scan with an audit reason before confirmation.
6. Enter driver name and vehicle registration, then **Confirm pickup**. Partial pickup requires a reason and marks only scanned pallets collected. Unscanned pallets become available for the next truck. Cancel with a reason if no pallets leave. Collected pallets cannot be reopened.
7. Manifests retain their planned contents. The loading record separately records actual scans, timestamps, driver, vehicle and partial-pickup reason. Pallet views distinguish reserved and collected pallets; the activity log records all loading actions. These labels do not prove a physical scan or authenticate the driver.

Existing saved forms and pallets migrate automatically. Old printed placeholder QRs must be replaced by reprinting the current pallet revision to use scanning.

Manifest QRs currently point to the running local app address and contain no session token. They require an already authenticated workspace on that same computer. **They will not open the shipment on a driver's phone.** Production driver use needs a shared HTTPS service, scoped driver links, authentication/authorisation and concurrent shared storage. Delivery-at-destination confirmation is a later step. See [third-party notices](docs/THIRD_PARTY.md) for the bundled QR libraries.


## Supabase backend setup

The `supabase/` directory contains the shared shipment database migration, destination presets and a first-administrator bootstrap script. It adds workspace access rules, versioned documents, controlled operator actions, scoped driver links, loading scans and pickup/delivery records. See [Supabase setup](docs/SUPABASE.md) for deployment, operator provisioning, API payloads and testing.

Applying the migration alone does not upload existing forms or change printing. Database regression tests use the pinned PGlite development dependency. The desktop uses the optional Playwright dependency only for automatic Spotfire collection.
