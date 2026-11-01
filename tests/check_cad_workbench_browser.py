"""Exercise a running watcher using a disposable parameter file and HTTPS URL."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True);p.add_argument('--params',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    original=args.params.read_text();params=json.loads(original);args.output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1360,'height':960});errors=[];failed=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('requestfailed',lambda r:failed.append(r.url))
        def snapshot():return page.evaluate('window.__cadWorkbench.snapshot()')
        def same_view(a,b):return all(abs(x-y)<1e-6 for key in ['position','target'] for x,y in zip(a[key],b[key]))
        def wait_ready():page.wait_for_function('window.__cadWorkbench?.snapshot().status?.state==="ready" && Object.keys(window.__cadWorkbench.snapshot().status.parts).length===3',timeout=120000)
        def wait_loaded():page.wait_for_function('()=>{const s=window.__cadWorkbench.snapshot();return s.loadedKey.includes(s.status.parts[s.part].current.mesh)}',timeout=30000)
        def write():args.params.write_text(json.dumps(params,indent=2)+'\n')
        try:
            page.goto(args.url);wait_ready();wait_loaded();before=snapshot();view=before['view']
            params['head_cover']['cable_notch_width_mm']=10;write()
            page.wait_for_function('window.__cadWorkbench.snapshot().status.parts.head.current.parameters.head_cover.cable_notch_width_mm===10',timeout=60000);wait_ready();wait_loaded()
            after=snapshot();assert same_view(after['view'],view),(view,after['view'])
            for kind in ['frame','spacer']:assert after['status']['parts'][kind]['current']['mesh']==before['status']['parts'][kind]['current']['mesh']
            assert after['status']['parts']['head']['previous']['mesh']==before['status']['parts']['head']['current']['mesh']
            for mode in ['previous','overlay','current']:
                page.locator(f'[data-mode="{mode}"]').click();s=snapshot();assert same_view(s['view'],view),(view,s['view'])
                assert s['currentVisible']==(mode!='previous') and s['previousVisible']==(mode!='current')
                page.screenshot(path=str(args.output/(mode+'.png')))
            keep=snapshot()['loadedKey'];args.params.write_text('{')
            page.wait_for_function('window.__cadWorkbench.snapshot().status.state==="error"',timeout=10000)
            assert snapshot()['loadedKey']==keep and page.locator('#error').is_visible()
            write();wait_ready()
            params['pcb_pilot_diameter_mm']=1.4;write()
            page.wait_for_function('window.__cadWorkbench.snapshot().status.parts.frame.current.parameters.pcb_pilot_diameter_mm===1.4',timeout=60000);wait_ready()
            page.select_option('#part','frame');wait_loaded();page.locator('[data-mode="overlay"]').click()
            page.screenshot(path=str(args.output/'frame-overlay.png'))
            params['pcb_standoff_height_mm']=4;write()
            page.wait_for_function('window.__cadWorkbench.snapshot().status.parts.spacer.current.parameters.pcb_standoff_height_mm===4',timeout=60000);wait_ready()
            page.select_option('#part','spacer');wait_loaded();page.set_viewport_size({'width':390,'height':844});page.locator('#fit').click()
            page.screenshot(path=str(args.output/'spacer-mobile.png'))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            for record in snapshot()['status']['parts'].values():
                for version in ['current','previous']:
                    if record.get(version):
                        for field in ['mesh','step','receipt']:assert page.request.get(args.url+record[version][field]).ok
            assert not errors,errors;assert not failed,failed
            print('PASS HTTPS assets/downloads, selective watch rebuilds, fixed camera, comparison modes, failed-save recovery, frame/spacer previews and mobile layout')
        finally:
            args.params.write_text(original)
            page.wait_for_function('(expected)=>{const s=window.__cadWorkbench?.snapshot().status;return s?.state==="ready"&&Object.values(s.parts).every(p=>JSON.stringify(p.current.parameters)===JSON.stringify(expected))}',arg=json.loads(original),timeout=120000)
            browser.close()


if __name__=='__main__':main()
