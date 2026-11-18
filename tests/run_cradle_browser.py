"""Rendered CAD workbench smoke test; no physical measurements or hardware actions.

python tests/run_cradle_browser.py --url URL --output DIRECTORY
Uses the already installed Playwright interpreter, not a new dependency.
"""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        try:
            for width in (390, 1280):
                context = browser.new_context(viewport={'width': width, 'height': 900}, accept_downloads=True)
                try:
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(args.url, wait_until='domcontentloaded')
                    expect(page.locator('#download-step')).to_be_enabled(timeout=45000)
                    assert '52 × 49 × 8.4' in page.locator('#outer').inner_text()
                    assert page.locator('#viewport canvas').count() == 1
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.locator('#preset').select_option('1')
                    assert page.locator('#download-step').is_disabled()
                    page.locator('#build').click()
                    expect(page.locator('#download-step')).to_be_enabled(timeout=45000)
                    assert '83 × 72 × 8.4' in page.locator('#outer').inner_text()
                    with page.expect_download() as download:
                        page.locator('#download-step').click()
                    file = args.output / f'anker-{width}.step'
                    download.value.save_as(str(file))
                    assert 'ISO-10303-21' in file.read_text()
                    with page.expect_download() as download:
                        page.locator('#download-stl').click()
                    file = args.output / f'anker-{width}.stl'
                    download.value.save_as(str(file))
                    assert file.stat().st_size > 1000
                    page.locator('#battery-visible').uncheck()
                    page.locator('#fit').click()
                    page.screenshot(path=str(args.output / f'cradle-{width}.png'), full_page=True)
                    # Invalid edits must retain the last good view but disable its
                    # downloads. A failed build cannot silently reuse old exports.
                    page.locator('[name="base"]').fill('1')
                    assert page.locator('#download-step').is_disabled()
                    page.locator('#build').click()
                    expect(page.locator('#error')).to_be_visible()
                    assert 'base must be' in page.locator('#error').inner_text()
                    assert page.locator('#download-stl').is_disabled()
                    page.locator('[name="base"]').fill('2.4')
                    page.locator('#build').click()
                    expect(page.locator('#download-step')).to_be_enabled(timeout=45000)
                    assert 'length=82' in page.url
                    # Ignore AbortSignal deliberately: a late success must still
                    # be discarded by the request token after the inputs change.
                    # Reuse a real CAD response so this exercises the UI guard,
                    # not merely its malformed-result/error path.
                    data = page.request.post(args.url.rstrip('/') + '/api/build',
                                             data={'length': 82, 'width': 51, 'height': 36}).json()
                    page.evaluate('''data => {
                        const original = window.fetch;
                        window.fetch = (url, options) => String(url) === 'api/build'
                          ? new Promise(resolve => { window.releaseOldBuild = () => {
                              window.fetch = original;
                              resolve({ok: true, json: async () => data});
                            }; }) : original(url, options);
                    }''', data)
                    page.locator('#build').click()
                    page.locator('[name="width"]').fill('52')
                    page.locator('[name="width"]').fill('51')
                    page.evaluate('async () => { window.releaseOldBuild(); await new Promise(requestAnimationFrame); }')
                    assert page.locator('#download-step').is_disabled()
                    assert page.locator('#download-stl').is_disabled()
                    assert 'Previous build' in page.locator('#model-state').inner_text()
                    assert not errors, errors
                    print(f'PASS {width}px: real geometry, preset edit, STEP/STL, stale/invalid and late-response guards, no overflow/errors')
                finally:
                    context.close()
        finally:
            browser.close()


if __name__ == '__main__':
    main()
