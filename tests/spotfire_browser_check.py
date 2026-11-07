import base64
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import expect, sync_playwright
from test_spotfire import sample
from transport_order.integrations.spotfire import DEFAULT_REPORT_URL, parse_export
from transport_order.integrations.spotfire_browser import collect_export
from transport_order.server import create_server
from transport_order.storage import Store


def check():
    with tempfile.TemporaryDirectory() as folder, sync_playwright() as playwright:
        executable = os.environ.get('SPOTFIRE_TEST_BROWSER')
        browser = playwright.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            encoded = base64.b64encode(sample()).decode()
            fixture = f'''<!doctype html><html lang="en"><body>
                <div hidden>Data Table Monitor</div><div hidden>Handling unit</div>
                <button onclick="document.querySelector('table').hidden=false">Data Table Monitor</button>
                <table role="grid" hidden><tr><th>Handling unit</th><th>Quantity</th></tr><tr><td>00001</td><td>2.5</td></tr></table>
                <div id="menu" hidden><button role="menuitem" onmouseover="document.querySelector('a').hidden=false">Export</button>
                <a role="menuitem" hidden href="data:text/csv;base64,{encoded}" download="fixture.csv">Export table (without value formatting)</a></div>
                <script>document.querySelector('table').oncontextmenu=e=>{{e.preventDefault();setTimeout(()=>document.querySelector('#menu').hidden=false,150);}};</script>
                </body></html>'''
            page.route('https://spotfire.asml.com/**', lambda route: route.fulfill(body=fixture, content_type='text/html'))
            page.goto(DEFAULT_REPORT_URL)
            result = parse_export(collect_export(page))
            assert result['rowCount'] == 3 and result['uniqueHus'] == 2
            assert page.get_by_role('grid').locator('tr').count() == 2
            print('Browser export collected all three CSV rows while only one item row was displayed.')

            store = Store(folder)
            server = create_server(store, 'browser-test-session', 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                errors = []
                app = browser.new_page(viewport={'width': 1440, 'height': 1000})
                app.on('pageerror', lambda error: errors.append(str(error)))
                app.goto(f'http://127.0.0.1:{server.server_port}/#session=browser-test-session')
                app.locator('#navigation').get_by_role('button', name='Data infeed', exact=True).click()
                fixture_path = Path(folder) / 'monitor.csv'
                fixture_path.write_bytes(sample('WH-WEERT1A'))
                app.locator('#spotfire-file').set_input_files(str(fixture_path))
                app.get_by_role('button', name='Use Spotfire data', exact=True).wait_for(state='visible')
                expect(app.locator('#spotfire-state')).to_contain_text('2 HUs')
                app.get_by_role('button', name='Create order', exact=True).click()
                hu = app.locator('[data-line-field="hu"]').first
                hu.fill('00001')
                hu.press('Tab')
                app.get_by_role('heading', name='Weert 1A — Scrap or Normal?').wait_for()
                app.get_by_role('button', name='Scrap', exact=True).click()
                expect(app.locator('[data-field="destination.department"]')).to_have_value('SCRAP')
                assert app.locator('[data-line-field="qty"]').first.input_value() == '5.0'
                assert app.locator('[data-line-field="dn"]').first.input_value() == '000901'
                assert '2 unprocessed HUs' in app.locator('#open-hu-count').inner_text()
                app.locator('[data-action="save"][data-intent="draft"]').click()
                app.locator('#navigation').get_by_role('button', name='Data infeed', exact=True).click()
                app.get_by_role('button', name='Use SAP paste/import', exact=True).click()
                expect(app.locator('#source-health')).to_contain_text('SAP data needed')
                assert store.snapshot()['settings']['dataSource'] == 'sap'
                assert not errors, errors
                print('Browser UI imported UTF-16, required Scrap/Normal, filled DN/quantity, saved draft and switched to SAP.')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        finally:
            browser.close()


if __name__ == '__main__':
    check()
