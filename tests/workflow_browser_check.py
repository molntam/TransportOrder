import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transport_order.server import create_server
from transport_order.storage import Store

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-results' / 'workflow'
OUT.mkdir(parents=True, exist_ok=True)
TOKEN = 'a' * 64


class StaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def run_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f'http://127.0.0.1:{server.server_port}'


def fixture():
    dest = {'building':'Building 21','department':'Field Service Hub','shipTo':'NL15C'}
    def pallet(pid, hu, dn):
        return {'id':pid,'revision':1,'destination':dest,'forms':[{'id':'TO-'+pid,'lines':[{'hu':hu,'dn':dn,'qty':'2'}]}]}
    a, b = pallet('P-A','000001','DN-LOADED'), pallet('P-B','000002','DN-LEFT')
    return [
        {'id':'LOAD-DELIVERED','kind':'load','revision':1,'building':'Building 21','building_key':'building21','stage':'delivered','shipment_status':'delivered','created_at':'2026-11-11T09:00:00Z','collected_at':'2026-11-11T09:10:00Z','delivered_at':'2026-11-11T10:00:00Z','receiver_name':'Receiver Test','driver_name':'Driver Test','vehicle':'TRUCK-01','reason':'','snapshot':{'building':'Building 21','pallets':[{'id':'P-A','snapshot':a}]},'events':[{'action':'Delivery confirmed','at':'2026-11-11T10:00:00Z','detail':{'receiver':'Receiver Test'}}]},
        {'id':'LOAD-PARTIAL','kind':'load','revision':1,'building':'Building 21','building_key':'building21','stage':'collected','shipment_status':'partial','created_at':'2026-11-11T11:00:00Z','collected_at':'2026-11-11T11:10:00Z','driver_name':'Driver Test','vehicle':'TRUCK-02','reason':'Truck full. Take on next truck.','left_behind':1,'snapshot':{'building':'Building 21','pallets':[{'id':'P-C','snapshot':pallet('P-C','000003','DN-PARTIAL')}]},'events':[]},
        {'id':'P-B','kind':'pallet','revision':1,'building':'Building 21','building_key':'building21','stage':'in_process','shipment_status':'finalised','created_at':'2026-11-11T09:00:00Z','reason':'Truck full. Take on next truck.','snapshot':b,'events':[]},
        {'id':'TO-DEPT','kind':'form','revision':1,'building':'Weert 1A','building_key':'weert1a','stage':'in_process','shipment_status':'At Stagnation','created_at':'2026-11-11T09:00:00Z','snapshot':{'destination':{'building':'Weert 1A','department':'Re-use','shipTo':'WH-WEERT1A'},'lines':[{'hu':'DEPTHU','dn':'DEPTDN','qty':'1'}]},'events':[]}
    ]


def main():
    static = ThreadingHTTPServer(('127.0.0.1',0),partial(StaticHandler,directory=str(ROOT/'driver-site'/'dist')))
    website = run_server(static)
    temporary = tempfile.TemporaryDirectory()
    store = Store(temporary.name)
    store.snapshot()
    local_time=datetime.now(timezone.utc)+timedelta(hours=1)
    store.state['sources']['shipto']={'rows':[{'hu':'FIFO-HU','dn':'FIFO-EMERGENCY','document':'FIFO-ODO','condition':'S4','shipTo':'NL15C','externalId':'','bin':'PS_READY-INT','changedOn':local_time.strftime('%d.%m.%Y'),'changedAt':local_time.strftime('%H:%M:%S')}], 'count':1,'uniqueHus':1,'importedAt':datetime.now(timezone.utc).isoformat(),'warnings':[],'filename':'Browser fixture'}
    desktop = create_server(store,'browser-session',0)
    app_url = run_server(desktop)
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, **({'executable_path':os.environ['CHROMIUM_PATH']} if os.environ.get('CHROMIUM_PATH') else {}))
            context = browser.new_context(viewport={'width':1440,'height':1000})
            page = context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            data = fixture()
            def api(route):
                payload=route.request.post_data_json or {}
                if route.request.url.endswith('/transport_tracking_page'):
                    candidates=[r for r in data if (not payload.get('p_building') or r['building_key']==payload['p_building']) and (not payload.get('p_query') or payload['p_query'].lower() in json.dumps(r['snapshot']).lower() or payload['p_query'].lower() in r['id'].lower())]
                    counts={stage:sum(r['stage']==stage for r in candidates) for stage in ('in_process','ready','collected','delivered')}
                    found=[r for r in candidates if not payload.get('p_stage') or r['stage']==payload['p_stage']]
                    route.fulfill(json={'records':found,'total':len(found),'counts':counts,'hasMore':False,'authorized':True})
                elif route.request.url.endswith('/transport_driver'):
                    route.fulfill(json={'id':'LOAD-RELOAD','revision':1,'rowVersion':1,'building':'Building 21','status':'ready','createdAt':'2026-11-11T09:00:00Z','pallets':[{'id':'P-RELOAD','revision':1,'destination':{'building':'Building 21','department':'Motion','shipTo':'NL15C'},'forms':[{'id':'TO-RELOAD','lines':[{'dn':'RELOAD-DN','hu':'RELOAD-HU','qty':'1'}]}]}]})
                elif '/auth/v1/token' in route.request.url:
                    route.fulfill(json={'access_token':'browser-access','refresh_token':'browser-refresh','expires_in':3600})
                else:
                    route.fulfill(json={})
            page.route('https://cwwpuapvgwoelhpwserm.supabase.co/**',api)
            page.goto(website)
            expect(page.get_by_role('heading',name='Sign in to tracking')).to_be_visible()
            page.screenshot(path=str(OUT/'tracking-login.png'),full_page=True)
            page.get_by_label('Email address').fill('operator@example.invalid')
            page.get_by_label('Password',exact=True).fill('fictional-password')
            page.get_by_role('button',name='Sign in',exact=True).click()
            expect(page.locator('.building-tabs button')).to_have_count(10)
            expect(page.locator('.portal-result')).to_have_count(0)
            expect(page.get_by_role('searchbox')).to_be_visible()
            page.screenshot(path=str(OUT/'tracking-home.png'),full_page=True)
            page.get_by_role('button',name='Building 21',exact=True).click()
            expect(page.locator('.portal-result')).to_have_count(3)
            page.get_by_role('button',name='Delivered 1',exact=True).click()
            expect(page.locator('.portal-result')).to_have_count(1)
            expect(page.locator('.tracking-milestones')).to_contain_text('Receiver Test')
            expect(page.locator('.portal-result h2')).to_have_text('Building 21')
            page.locator('summary').click()
            expect(page.locator('.portal-table')).to_be_visible()
            expect(page.locator('.portal-table')).to_contain_text('DN-LOADED')
            page.wait_for_url('**document=LOAD-DELIVERED')
            saved_url=page.url
            page.reload()
            expect(page.locator('.portal-table')).to_be_visible()
            expect(page.locator('.portal-result')).to_have_count(1)
            assert page.url==saved_url
            expect(page.get_by_role('button',name='Sign out')).to_be_visible()
            page.screenshot(path=str(OUT/'tracking-delivered.png'),full_page=True)
            page.get_by_role('button',name='Collected 1',exact=True).click()
            expect(page.locator('.tracking-comment')).to_contain_text('Truck full')
            expect(page.locator('.portal-results')).not_to_contain_text('DN-LEFT')
            page.get_by_role('searchbox').fill('DN-LEFT')
            page.get_by_role('button',name='Search',exact=True).click()
            expect(page.locator('.portal-result')).to_have_count(1)
            expect(page.locator('.tracking-reference')).to_contain_text('P-B')
            page.goto(website+'?building=weert1a')
            expect(page.locator('.portal-result')).to_contain_text('At Stagnation')
            page.set_viewport_size({'width':390,'height':844})
            page.goto(website+'?building=building21')
            expect(page.locator('.portal-result')).to_have_count(3)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflows horizontally'
            assert page.get_by_role('searchbox').evaluate('el=>parseFloat(getComputedStyle(el).fontSize)')>=16
            page.screenshot(path=str(OUT/'tracking-mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(app_url+'/#session=browser-session')
            expect(page.get_by_role('heading',name='Prepare a transport order')).to_be_visible()
            page.get_by_role('button',name='Settings',exact=True).click()
            page.locator('#setting-department-mode').select_option('other')
            page.locator('#setting-department-name').fill('Stagnation')
            page.locator('#setting-department-location').fill('Building 58')
            page.get_by_role('button',name='Save preferences').click()
            expect(page.locator('#user-label')).to_contain_text('Stagnation')
            expect(page.locator('#navigation .nav-item')).to_have_count(3)
            page.get_by_role('button',name='Create order',exact=True).click()
            expect(page.get_by_role('button',name='Print transport order form',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='Print & keep open',exact=True)).to_have_count(0)
            expect(page.locator('#pallet-panel')).to_have_count(0)
            expect(page.get_by_role('button',name='Automatic',exact=True)).to_have_count(0)
            page.screenshot(path=str(OUT/'department-workspace.png'),full_page=True)
            page.get_by_role('button',name='Settings',exact=True).click()
            page.locator('#setting-department-mode').select_option('delivery_ops')
            page.get_by_role('button',name='Save preferences').click()
            expect(page.locator('#navigation')).to_contain_text('FIFO tracker')
            page.get_by_role('button',name='FIFO tracker',exact=True).click()
            expect(page.get_by_role('heading',name='FIFO tracker',exact=True)).to_be_visible()
            expect(page.locator('#main')).to_contain_text('FIFO-EMERGENCY')
            expect(page.locator('#fifo-alerts')).to_contain_text('Please process ASAP')
            page.screenshot(path=str(OUT/'fifo-tracker.png'),full_page=True)
            page.goto(website+'#'+TOKEN)
            expect(page.locator('h1')).to_have_text('Building 21')
            page.reload()
            expect(page.locator('h1')).to_have_text('Building 21')
            assert page.url.endswith('#'+TOKEN)
            page.locator('.brand').click()
            expect(page.get_by_role('heading',name='Return to your shipment')).to_be_visible()
            page.get_by_role('link',name='Building 21 · LOAD-RELOAD',exact=True).click()
            expect(page.locator('h1')).to_have_text('Building 21')
            page.goto(website+'?demo=1')
            expect(page.get_by_role('heading',name='Building 21',exact=True).first).to_be_visible()
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button',name='Scan pallets',exact=False).click()
            expect(page.locator('#scanner')).to_be_visible()
            assert page.locator('#scanner').evaluate('el=>el.getBoundingClientRect().width')<=390
            page.get_by_role('button',name='Scan next demo pallet',exact=True).click()
            expect(page.locator('#scan-count')).to_have_text('1')
            page.locator('#scanner .modal-foot').get_by_role('button',name='Close scanner',exact=True).click()
            page.get_by_role('button',name='Confirm pickup · 1 pallets',exact=True).click()
            page.locator('input[name="driver"]').fill('Driver Browser')
            page.locator('input[name="vehicle"]').fill('TRUCK-TEST')
            page.locator('textarea[name="reason"]').fill('Truck full')
            page.locator('#confirm-submit').click()
            expect(page.locator('.partial-note')).to_contain_text('Truck full')
            expect(page.locator('.pallet-item')).to_have_count(1)
            page.screenshot(path=str(OUT/'driver-partial-mobile.png'),full_page=True)
            page.get_by_role('button',name='Confirm delivery',exact=False).click()
            page.locator('select[name="building"]').select_option('Building 21')
            page.locator('input[name="receiver"]').fill('Receiver Browser')
            page.locator('input[name="arrival"]').check()
            page.locator('#confirm-submit').click()
            expect(page.locator('.shipment-receipt').first).to_contain_text('Receiver Browser')
            page.screenshot(path=str(OUT/'driver-delivered-mobile.png'),full_page=True)
            assert not errors, errors
            browser.close()
        print('Workflow browser checks passed: login, empty landing, building/status tabs, receiver, comments, current-view reload, mobile layout, department workspace, FIFO, partial pickup and delivery.')
    finally:
        desktop.shutdown();desktop.server_close();static.shutdown();static.server_close();temporary.cleanup()


if __name__=='__main__':
    main()
