# TransportOrder

A local shipping workspace for preparing transport orders between warehouses in the Netherlands. The interface uses ASML-inspired blue, larger Segoe UI text, stronger contrast, and light/dark themes, with the form in the centre and open pallets on the right.

## Run

Requires **Python 3.10 or later**. No pip packages, database download, Node installation or account setup is needed to run the app.

On Windows, double-click **`start.bat`**, or run from the repository folder:

```powershell
py -3 run.py
```

On macOS / Linux:

```bash
python3 run.py
```

Keep the terminal open. On Windows, the app opens in a dedicated Edge application window with its own browser profile. If Edge is unavailable, it opens the default browser. To explicitly use the default browser, including Firefox:

```powershell
py -3 run.py --browser default
```

If the browser does not open automatically, use the full local link printed in the terminal. The session portion of that link is required. Run `py -3 run.py --help` for the other options.

## First test

1. Open **Data infeed**.
2. Click an input cell and press **Ctrl+V** to paste the **Ship-to** and **Quantities** SAP tables. Headers are prefilled for data-only pastes; a paste containing headers replaces the input grid. File import (`.xlsx`, `.csv`, `.tsv`, `.txt`) is still available.
3. Preview, resolve any errors and apply each table. Pasted quantities can use a decimal point or comma; select the matching format before previewing. XLSX quantities use the workbook's numeric values.
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
- Consolidations omit individual form IDs and hide unused 12NC/description columns; final documents include a labelled QR placeholder.
- Destination choices show building and ship-to together; Building 05, Best II and Eindhoven 1 are removed from the destination picker. Origin choices are retained.
- Settings for appearance, origin, preparer, printer and copies. Optional receiver contact details, Emergency and Special Pick-up flags.

**Printing on Windows is direct.** Settings defaults to **Windows default**, resolved afresh for each job. You can choose a fixed installed printer without changing the Windows default. Open forms default to **1 copy** and finalised pallets to **2 copies**, with separate settings for each. The app submits an A4, one-sided job through Windows PowerShell/.NET and uses no external PDF-printing application. The bundled C# helper is compiled by Windows PowerShell; no separate compiler installation is needed. Organisation policies that disable PowerShell or `Add-Type` can prevent direct printing; the app reports the error and retains the saved document.

History → document revision opens an optional preview. **Print directly** uses the selected Windows printer; **Save PDF** explicitly opens the browser dialog. Microsoft Print to PDF/XPS jobs use a generated file under the workspace's `printouts` folder. Queue submission confirms the job was sent to Windows, not that paper was produced. A failed or timed-out submission is not automatically retried; check the print queue before using Retry.

Appearance can be changed in Settings (Light, Dark, Follow system), or toggled from the top bar. Existing workspaces keep their forms and pallets, and gain the new 1/2-copy defaults automatically.

## Data and current limits

Data is saved outside the repository in **`~/TransportOrderData`** (`%USERPROFILE%\TransportOrderData` on Windows). The main file is `transport-order.json`; the previous successful state is `transport-order.previous.json`. Closing the browser does not delete saved work. One application process can open a data folder at a time. Multiple browser windows share that process, with revision checks preventing overwrites.

**This version is a local, single-workstation prototype.** Supabase, driver pages, tracking QR codes, SharePoint PDF uploads and Spotfire automation are not connected. Finalisation currently means ready for pick-up in this local workspace. It does not notify drivers or another workstation. The preparer name is a local setting, not verified sign-in.

Part numbers and descriptions remain manual because the two current SAP exports do not contain them. One automatic row represents an HU's aggregate quantity; it does not invent item-level material details. A form supports up to 500 rows. Each input supports up to 50,000 source records.

The server binds only to `127.0.0.1`, uses a fresh session token at startup and rejects cross-origin API requests. It is intended to run locally, not to be exposed as a production web server. Application assets have no runtime CDN dependencies. The supplied SAP workbooks and transaction rows are not included in this repository.

## Code map

| Path | Responsibility |
|---|---|
| `run.py`, `start.bat` | Start the local workspace |
| `transport_order/server.py` | Local API, session checks and browser launcher |
| `transport_order/domain.py` | HU resolution, validation, forms, pallets and history |
| `transport_order/integrations/sap.py` | Paste, CSV and XLSX ingestion |
| `transport_order/integrations/spotfire.py` | Inactive provider boundary for the later report |
| `transport_order/locations.json` | Origin/destination directory and operational routing |
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
