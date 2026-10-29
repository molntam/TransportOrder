# Validation and acceptance

## Automated checks

Run from the repository root:

```bash
python -m unittest discover -s tests -v
node --check transport_order/web/app.js
node tests/ui-smoke.cjs
```

The Python tests cover source parsing, values-only XLSX, decimal formats, identifier preservation, duplicate/conflicting records, quantity sums, ERP-document mapping, S4/I2 priority, the Weert scrap split, NL05 overrides, source-document mismatch, missing data, pallet compatibility, drafts, finalisation/reopening, immutable snapshots, removal, print escaping, persistence, stale-window rejection and local API session/origin checks.

The Node smoke check runs the actual frontend script against an isolated real local API, with a minimal DOM shell. It checks view rendering, the import-to-consolidation workflow, errors and print HTML. It does not claim visual layout, native dialogs or physical printing are verified.

The original supplied XLSX samples were also read with the application's parser: 54 Ship-to records / 54 HUs, and 60 quantity records / 54 HUs, with matching HU coverage and no import errors. Transaction rows are not test fixtures and are not committed.

## Windows/browser acceptance

These checks need the actual workstation and printer. A cloud headless Chromium binary was unavailable during implementation, so local browser layout and physical printing should be verified here before an operational trial.

1. Start with `start.bat`. Confirm the dedicated Edge window opens; also try `py -3 run.py --browser default` for Firefox/default-browser use.
2. In Settings, set the preparer and confirm the default origin. Choose one printed copy for initial testing.
3. In Data infeed, load fictional demo data. Confirm both table counts are shown.
4. Create a form with `DEMO-HU-001` and `DEMO-HU-002`. Check DN-01/DN-02, quantities 25/3, Building 21 / Motion and Emergency. Add a description and a custom remark.
5. Add `DEMO-HU-003`. Confirm that every conflicting HU is identified. Remove it and check the error clears.
6. Save as a draft. Close/restart the application and resume it through History.
7. Choose Print & keep open. Check the form preview contains both Emergency and the custom remark, then print/save PDF.
8. Confirm the new form editor is cleared and the pallet remains selected on the right. Use a separate fictional HU or manual row for another form; do not reuse an already assigned HU.
9. Finalise the pallet. Check all forms, the unique-DN summary, the HU details and quantities in the consolidated preview.
10. Reopen it from History with a reason. Confirm the previous consolidation says SUPERSEDED, edit a form and finalise again as revision 2.
11. Test `DEMO-HU-004` and `DEMO-HU-005` together: Weert scrap and re-use must not mix. Test `DEMO-HU-006`: select NL05 Weert or Eindhoven/BIC and enter the address-check reason.
12. Test Manual mode without an HU, using a description, positive quantity and a complete destination. Check the quick presets, free-text fields, optional contact details and Special Pick-up.
13. Open a second browser window using the same terminal link. Save in one, then try saving from the stale other window. It must reject the stale save and retain the unsaved editor; Refresh should allow review and retry.
14. Import fresh data after completing a form. Confirm the saved form/old revision did not change. Try an XLSX export as well as a direct paste.
15. Check 1366×768 desktop, a wide monitor and a narrow window. Material rows should scroll horizontally rather than overflow the entire page.
16. Print a form with many rows. Check repeated column headers, page breaks, signatures and the configured number of copies. Verify the workstation's follow-me print queue separately.

## Backup recovery

Use Settings → Export backup for a portable JSON copy. For manual recovery, close the app, preserve the current `transport-order.json`, copy a known-good backup into the data folder as `transport-order.json`, then restart. Do not edit workspace files while the app is running. A corrupt file stops startup rather than being silently overwritten.
