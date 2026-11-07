> Spotfire is temporarily disabled because the current report omits deliveries. SAP paste/import is the active source for new and existing workspaces. The integration code is retained for a future complete report.

# Spotfire data infeed

## Workstation setup

1. Update the repository and run **`setup_spotfire.bat`** once. It installs the pinned Python Playwright dependency. Normal SAP paste/import still runs without it.
2. Start **`start.bat`**. With Spotfire selected and automatic collection enabled, the app opens a visible Microsoft Edge window containing the workspace and a separate report tab. Google Chrome can be selected in **Data infeed**; restart the app after changing the browser.
3. Sign in to Spotfire normally in that report tab using your own account. Open **Data Table Monitor**, check the report's filters and leave the tab open. No ASML password is entered in TransportOrder.
4. In **Data infeed**, check the connection message, last successful import and HU count. **Check now** requests an immediate check. **Save & open report** saves the URL and resumes collection.

The report URL keeps its `file=` library path. Session-specific `waid` and `wavid` parameters from a copied link are discarded.

The collector uses the workstation's installed Edge or Chrome. It does not install or replace a browser or change corporate browser policies. If automation is unavailable under workstation policy, use **Import Spotfire CSV** or **Use SAP paste/import**. Do not change company policy to enable it.

## Collection and mapping

After each attempt the collector waits 60 seconds before checking again, while the app is running and Spotfire is selected. It reloads the report, selects **Data Table Monitor**, and requests the table's CSV export, preferring **Export table (without value formatting)**. It imports the entire exported table rather than reading only the visible grid rows. Network/report loading time is additional to the interval.

This retrieves the data and filters exposed by the report. Reloading the page does not guarantee a new SAP/backend refresh. Check Spotfire's own data freshness and ensure its filters include the workload you intend to process. Export access is required.

| Spotfire column | TransportOrder use |
|---|---|
| Handling unit | HU; identifiers remain text, including leading zeroes |
| Original_ERP_Document | Delivery number / DN |
| Ship_To_Party_Description | Destination route lookup |
| Quantity | Item quantity; all rows for an HU are added |
| Document_Number | Internal document check; uses the DN if absent |
| ERP_Shipping_Condition / Shipping Conditions | Emergency for S4, I2 or an Emergency description |
| Storage bin | Current bin in Open orders |
| DHL KPI DateTime | Retained as FIFO information, separate from SAP change date/time |

UTF-16 tab-separated exports, including the supplied sample structure, and UTF-8 CSV/TSV are supported. An export is limited to 20 MB and 50,000 item rows. Invalid columns, quantities, conflicting DNs or conflicting destinations reject the whole snapshot. Both destination and quantity data are replaced together after successful validation. A failed check leaves the last valid snapshot loaded and marks the connection as needing attention. An unchanged export does not create another workspace revision.

Existing route codes are recognised, with these additional description aliases:

| Description | Route code |
|---|---|
| ASML Bld 9, DESK9 | DESK9C |
| DHL.TOOLS | DHL.TOOLSC |
| WH 21 MPS | WH21-MPSC / Building 21 |
| Weert 1A / ASML Weert 1A | WH-WEERT1A |

Descriptions such as **ASML Netherlands BV** do not identify a unique building. They are listed for destination review and block automatic completion until the operator selects a destination and records an override reason. Add further verified description mappings in `transport_order/integrations/spotfire.py`; do not guess a building from a generic company name.

## Weert 1A

Spotfire has no External Delivery ID, so entering a Weert 1A HU opens a required **Scrap / Normal** choice. Scrap routes to **Weert 1A / SCRAP**; Normal routes to **Weert 1A / Reverse Logistics / Re-use parts**. Cancelling leaves the form incomplete. Changing the Weert HU set requires a new choice. The server also checks the choice before completing or printing an automatic order. The choice and source are saved with the form.

SAP imports retain their existing External Delivery ID logic. Manual entry still allows an explicitly chosen destination.

## Switching sources and saved work

Spotfire is the default primary source. **Use SAP paste/import** selects the existing two SAP tables; applying either SAP table also selects SAP. While SAP is selected, background Spotfire collection is paused. **Use Spotfire data** or importing a Spotfire CSV selects Spotfire again. Sources are never silently merged.

Completed forms and printed revisions retain their saved values. Drafts and new forms are resolved against the active source when completed. The active source's unprocessed HU count and Open orders update as data arrives. Daily workspace archiving and reset still apply.

The report's browser session stays in the workstation data directory under `spotfire-browser-profile`. Do not share this directory or include it in backups intended for other users. The collector does not extract credentials or send the browser profile to Supabase. Closing the report tab pauses collection; **Save & open report** opens another tab without closing the preparation workspace.

## Verification

`python -m unittest discover -s tests -v` covers parsing, totals, destination validation, Weert choices, source isolation, saved snapshots and API validation. `python tests/spotfire_browser_check.py` additionally exercises browser CSV download and the actual app UI against a synthetic report. Install the optional requirements and run `python -m playwright install chromium` for that developer check; an existing Chromium executable can instead be provided through `SPOTFIRE_TEST_BROWSER`.

The private ASML report cannot be exercised from the development environment. First use on an authorised workstation must verify sign-in, the actual report tab/table/export menu, filters and counts, a one-minute refresh and Weert 1A routing. If the report's export menu differs, the collector may need a selector adjustment. The CSV import and SAP fallback remain available while that is checked.
