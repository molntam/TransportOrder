# Validation and acceptance

## Automated checks

Run from the repository root:

```bash
python -m unittest discover -s tests -v
node --check transport_order/web/app.js
node tests/ui-smoke.cjs
```

The Python tests cover source parsing, values-only XLSX, decimal formats, identifier preservation, duplicate/conflicting records, quantity sums, ERP-document mapping, S4/I2 priority, the Weert scrap split, NL05 overrides, source-document mismatch, missing data, pallet compatibility, drafts, finalisation/reopening, immutable snapshots, removal, print escaping, persistence, stale-window rejection and local API session/origin checks.

The Node smoke check runs the actual frontend script against an isolated real local API, with a minimal DOM shell. It checks view rendering, the import-to-consolidation workflow, editable-grid paste and serialisation, filtered destination labels, persisted themes, automatic print requests, errors and preview HTML. Native queue submission is mocked. It does not claim visual layout, native dialogs or physical printing are verified.

The original supplied XLSX samples were also read with the application's parser: 54 Ship-to records / 54 HUs, and 60 quantity records / 54 HUs, with matching HU coverage and no import errors. Transaction rows are not test fixtures and are not committed.

## Windows/browser acceptance

These checks need the actual workstation and printer. A cloud headless Chromium binary was unavailable during implementation, so local browser layout and physical printing should be verified here before an operational trial.

1. Start with `start.bat`. Confirm the dedicated Edge window opens; also try `py -3 run.py --browser default` for Firefox/default-browser use.
2. In Settings, set the preparer and origin. Confirm Windows default is selected, open copies = 1 and final copies = 2. Try Light, Dark and Follow system; check the top-bar theme toggle.
3. In Data infeed, load fictional demo data. Confirm both table counts are shown.
4. Create a form with `DEMO-HU-001` and `DEMO-HU-002`. Check DN-01/DN-02, quantities 25/3, Building 21 / Motion and Emergency. Add a description and a custom remark.
5. Add `DEMO-HU-003`. Confirm that every conflicting HU is identified. Remove it and check the error clears.
6. Save as a draft. Close/restart the application and resume it through History.
7. Choose Print & keep open. Confirm exactly one copy reaches the Windows queue and no browser print screen opens. Use History to preview the saved form and confirm both Emergency and the custom remark.
8. Confirm the new form editor is cleared and the pallet remains selected on the right. Use a separate fictional HU or manual row for another form; do not reuse an already assigned HU.
9. Finalise the pallet. Confirm two copies reach the Windows queue without a print screen. In History preview, check the DN summary and HU rows, no child-form IDs, unused 12NC/description columns omitted, and a labelled QR placeholder.
10. Reopen it from History with a reason. Confirm the previous consolidation says SUPERSEDED, edit a form and finalise again as revision 2.
11. Test `DEMO-HU-004` and `DEMO-HU-005` together: Weert scrap and re-use must not mix. Test `DEMO-HU-006`: select NL05 Weert or Eindhoven/BIC and enter the address-check reason.
12. Test Manual mode without an HU, using a description, positive quantity and a complete destination. Check the quick presets, free-text fields, optional contact details and Special Pick-up.
13. Open a second browser window using the same terminal link. Save in one, then try saving from the stale other window. It must reject the stale save and retain the unsaved editor; Refresh should allow review and retry.
14. Import fresh data after completing a form. Confirm saved revisions did not change. Try XLSX import, full-table paste with headers, data-only paste into A2, paste starting in a different cell, and Enter/arrow-key navigation. Check the grid retains leading zeros.
15. Check 1366×768 desktop, a wide monitor and a narrow window. Material rows should scroll horizontally rather than overflow the entire page.
16. Print a form with many rows. Check repeated column headers, page breaks, signatures and the configured number of copies. Verify the workstation's follow-me print queue separately.

## Backup recovery

Use Settings → Export backup for a portable JSON copy. For manual recovery, close the app, preserve the current `transport-order.json`, copy a known-good backup into the data folder as `transport-order.json`, then restart. Do not edit workspace files while the app is running. A corrupt file stops startup rather than being silently overwritten.

## Direct printing and migration checks

- Windows tests compile `NativePrinter.cs` and render a long document to a PNG without needing a printer or sending anything to a physical queue.
- Python tests verify native job defaults, explicit printer/copy overrides, request deduplication, preservation after errors, and legacy-settings migration.
- On the workstation, change the Windows default printer while the app setting remains Windows default. The next job must follow the new default. Selecting a fixed app printer must not alter Windows defaults.
- Try an unavailable printer. The form must remain saved, no successful submission should be claimed, and Retry must be an explicit action after checking the queue.
- Microsoft Print to PDF/XPS uses the workspace `printouts` folder. Third-party driver-specific dialogs and company PowerShell restrictions require local acceptance testing.
