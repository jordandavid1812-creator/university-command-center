"""Export bitmap favicon fallbacks from the committed, self-contained UC vector.

Offline design tool only; uses the existing hashed test-only Playwright dependency.
Set UCC_CHROMIUM_EXECUTABLE for an explicit local browser override. Browser rasterisation
can differ between versions; SVG is the authoritative source, not a PNG byte hash.
"""
import os
from pathlib import Path
import struct

from playwright.sync_api import sync_playwright


def main():
    folder = Path(__file__).resolve().parents[1] / 'server/accounts/static/accounts/brand'
    svg = (folder / 'favicon.svg').read_text()
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'),
                                         args=['--disable-background-networking'])
        try:
            page = browser.new_page()
            page.route('**/*', lambda route: route.abort())
            images = {}
            for size in (16, 32, 180):
                page.set_viewport_size({'width': size, 'height': size})
                page.set_content('<style>html,body{margin:0;padding:0}svg{display:block;width:100vw;height:100vh}</style>' + svg)
                images[size] = page.screenshot(omit_background=True)
            entries, payload, offset = [], [], 6 + 16 * 2
            for size in (16, 32):
                png = images[size]
                entries.append(struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(png), offset))
                payload.append(png)
                offset += len(png)
            (folder / 'favicon.ico').write_bytes(struct.pack('<HHH', 0, 1, 2) + b''.join(entries + payload))
            (folder / 'apple-touch-icon.png').write_bytes(images[180])
            print('Generated 16/32px favicon and 180px touch icon using Chromium', browser.version)
        finally:
            browser.close()


if __name__ == '__main__':
    main()
