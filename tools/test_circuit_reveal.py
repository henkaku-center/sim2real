#!/usr/bin/env python3
"""Test the design graph inside the existing published build guide (headless)."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--url',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--enable-unsafe-swiftshader'])
        try:
            context=browser.new_context(viewport={'width':390,'height':844})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(a.url+'?step=final-wiring-checks&lang=en&renderer=webgl',wait_until='domcontentloaded')
            page.wait_for_function('window.sesameCircuit && document.querySelector("#loader").hidden',timeout=90000)
            assert page.locator('iframe').count()==0
            assert page.locator('#lookup').count()==0
            query=page.evaluate("sesameCircuit.query('hub.OE')")
            assert query['pin']['state']=='no_connect' and query['nets']==[]
            page.evaluate("sesameCircuit.highlight('SDA')")
            page.wait_for_function('sesameCircuit.revealState().ghosted.length > 0')
            assert 'carrier.display' in page.evaluate('sesameCircuit.revealState().ghosted')
            page.screenshot(path=str(a.output/'sda-mobile.png'),full_page=True)
            page.evaluate('sesameCircuit.clear()')
            page.wait_for_function('sesameCircuit.revealState().ghosted.length === 0')
            page.evaluate("sesameCircuit.highlight('hub.OE')")
            page.wait_for_function('sesameCircuit.revealState().ghosted.length === 0')
            assert not errors,errors
            context.close()
            print('PASS: existing guide only; OE query; coloured CAD/reversible obstruction reveal')
        finally:browser.close()


if __name__=='__main__':main()
