# TransportOrder

A local shipping workspace for preparing transport orders between warehouses in the Netherlands. The interface uses ASML-inspired blue and a compact logistics dashboard layout, with the form in the centre and open pallets on the right.

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
2. Paste the **Ship-to** and **Quantities** SAP tables, including their header rows, or import their `.xlsx`, `.csv`, `.tsv` or `.txt` exports.
3. Preview, resolve any errors and apply each table. Pasted quantities can use a decimal point or comma; select the matching format before previewing. XLSX quantities use the workbook's numeric values.
4. Open **Create order**. Enter HUs one by one or use **Paste HUs**. Destination, DN, quantity and Emergency fill from the imports.
5. Enter optional part numbers, descriptions and remarks.
6. Use **Print & keep open** to save the form and open its printable preview. Select that pallet on the right to add another form.
7. Use **Finalise pallet** when ready. Review the consolidation, then choose **Print / Save PDF**.
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
- A4 portrait print previews, configurable copy count and browser PDF printing.
- Settings for origin, preparer and copies. Optional receiver contact details, Emergency and Special Pick-up flags.

**Printing uses the browser/Windows print dialog.** Copies are repeated in the generated document; leave the system dialog at one copy. Saving or finalising opens a preview and does not claim that a physical print succeeded. Choose one app copy when saving a single PDF archive.

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
| `transport_order/printing.py` | Versioned form and consolidation documents |
| `transport_order/web/` | Browser interface, styles and interactions |
| `tests/` | Import, routing, workflow, persistence and API tests |
| `docs/` | Extracted workbook rules, architecture and test guide |

## Validation

```bash
python -m unittest discover -s tests -v
node --check transport_order/web/app.js
```

Node is only needed for the optional JavaScript syntax check and developer UI checks; it is not needed to run the app. See [the test guide](docs/TESTING.md) for the Windows and printer acceptance checks.

The UI layout takes inspiration from [Cargix TMS](https://dribbble.com/shots/26814297-Cargix-TMS-Logistics-Web-Dashboard). Implementation, icons and styles are original; this is a prototype, not an official ASML product.
