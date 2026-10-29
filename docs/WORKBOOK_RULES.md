# Workbook extraction and implemented rules

The reference workbook has five sheets: `Transportopdracht`, `FAQ's & Info`, `Dropdown`, `Review 5L List` and `Review of dropdown menu's`. Routing and controls are spread across formulas, hidden lists and VBA macros. The app uses one location directory plus explicit operational exceptions.

## Form and inputs

- Default source used by the operational buttons: Building 05 / Delivery Ops / B5L - Delivery Ops.
- Preserve origin, destination, ship-from, ship-to, preparer, form ID, date/time, optional telephone/email, remarks and signature space.
- Preserve 12NC/part number, description, quantity, HU and DN. Remove the fixed 20-row limit; the app supports 500 rows per form.
- Ship-to export: 12 columns, including the internal document, ERP document, HU, ship-to, priority and External Delivery ID.
- Quantity export: Document, Handling Unit, Quantity. Multiple rows per HU are legitimate and must be summed, not deduplicated.
- Neither export provides 12NC or description. `Number of Items` and `Number of Handling Units` are not the shipped quantity.

## Lookup and routing

| Requirement | Implementation |
|---|---|
| DN | ERP Document from the HU's Ship-to record |
| Quantity | Decimal sum of all quantity rows for that HU |
| Document consistency | Quantities.Document must match Ship-to.Outbound Delivery Order |
| Emergency | Any included HU with S4 or I2 |
| Destination compatibility | Same SAP ship-to and operational route, not merely the same building |
| Weert 1A SCRAP | External Delivery ID = SCRAP routes to the scrap department |
| Weert 1A re-use | Empty, 0 or KNIKKERBAK routes to Reverse Logistics / Re-use parts |
| Other Weert 1A external values | Explicit destination and override reason required |
| NL05C | Explicit selection of Weert or Eindhoven/BIC, with an override reason |
| Unknown ship-to | Explicit destination and override reason required |
| Destination override | Retain the original SAP code and record the explanation |

The location directory retains the workbook origin entries and destination dropdown entries, augmented by operational VBA presets for Weert 1A/1B, DC8, B23, WH21-MPSC, KEYSIGHT and B30-MOTION. The full approved route list is in `transport_order/locations.json`.

## Differences intentionally corrected

- Excel's priority lookups use shifting, limited source ranges. The app indexes the entire imported table for every HU.
- Excel's first-match lookups can hide duplicate conflicts. Imports reject conflicting HU records; automatic resolution also rejects ambiguity.
- An unknown HU can produce blank lookups in Excel without a specific explanation. The app identifies the HU and missing dataset.
- Excel's destination may retain previous values when no macro condition matches. The editor clears an unresolved automatic destination.
- Emergency macros can replace remarks. The app stores automatic Emergency, manual Emergency, Special Pick-up and free text separately.
- The print macro validates mostly the first material row. The app validates every used row before completion.
- Some labels differ between dropdowns and VBA, including Building 09 / Building 9, BLD58C-SCRP / BLD58-SCRP and CLE21MPSC / CLE21-MPSC. Canonical SAP codes and printed routing text are kept separately.
- The workbook's WH-WEERTC button actually fills Weert 1A scrap, while its dropdown defines WH-WEERTC as reverse logistics. The app exposes Weert 1A scrap as its own explicit preset and retains WH-WEERTC as a separate reverse-logistics destination.
- The workbook has a generic automatic DC8 route and distinct manual ASML/DEFA presets. These remain separate.

## Print behaviour

Excel supports A4 portrait, print preview/printer selection, three direct-print copies, hidden unused rows, a regenerated date/time-based form ID and a PDF export to SharePoint. It also has a keep/clear/cancel prompt for existing non-emergency remarks.

The app uses stable random form/pallet IDs, explicit completed revisions, A4 printable documents, user-selected copies and browser PDF printing. Blank unused rows are omitted. It keeps remarks on the current form and shows them in preview rather than automatically clearing them. Reprints retain the document's identity and saved revision. SharePoint export is deferred.

## New pallet workflow

Drafts may be incomplete. Completed forms can be saved/printed onto an open pallet without a QR. Pallets can collect several compatible forms over time. Finalisation creates an immutable consolidated document with a unique-DN summary and complete HU rows. Reopening requires a reason and preserves the old revision. Removing a form is a soft removal with retained history.
