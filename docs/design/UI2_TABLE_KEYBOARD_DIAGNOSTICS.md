# UI2 native table-keyboard wait diagnosis

## Scope and conclusion

Investigation started from `737a2a228582ee2efcc4d9f6af971152edbe0a7b`, hosted run [43208381966](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43208381966). Both attempts timed out in `test_native_get_selection_and_table_keyboard_without_js` waiting for browser-side `requestAnimationFrame` polling after ArrowRight.

**Confirmed cause: a brittle test wait in a JavaScript-disabled context, not a non-overflowing table or failed native keyboard scrolling.** No application CSS, templates, JS, services or historical assertions change in this investigation. U1–U4, including the explicit owner approval, remain intact.

## Actual browser evidence

Diagnostic-only commit `cb7f812d4fc21b9deb7e9082f0c93976f34b31a1` retained the failing predicate and timeout. [Hosted run 43210804671](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43210804671), frontend job `131157595453`, captured:

| Property | Before ArrowRight | After the five-second wait timed out |
| --- | --- | --- |
| Viewport width | 390px | 390px |
| Region clientWidth | 314px | 314px |
| Region scrollWidth / table width | 640px / 640px | 640px / 640px |
| Region scrollLeft | 0 | **40** |
| Active element | table region DIV, `focused=true` | same region, `focused=true` |
| Computed overflow-x / overflow-y | auto / auto | auto / auto |
| Document visibility | visible | visible |

The table genuinely requires 326px of local horizontal scrolling. Its labelled region has `tabindex="0"`. Focus and keyboard scrolling work with application JavaScript disabled. The diagnostic predicate nevertheless timed out; this was reproduced locally as well.

Hosted environment: Ubuntu 24.04 Actions runner, Python 3.12.16, Playwright 1.65.0, managed headless Chromium **158.0.8127.18**. Local Debian 13 / Python 3.12.14 used the same locked Playwright and downloaded managed Chromium **158.0.8127.18**. System Chromium 156.0.8078.79 also showed 314/640px and 0→40px. At 320px, both browser versions showed clientWidth244, scrollWidth640 and 0→40px. These are synthetic real-template fixtures, not student records or live sessions.

## Independent polling reproduction

Using Playwright 1.65.0 and managed Chromium158, run this synthetic probe inside the existing hashed browser-test environment:

```python
from playwright.sync_api import sync_playwright, TimeoutError

with sync_playwright() as p:
    browser = p.chromium.launch()
    for enabled in (False, True):
        for polling in ('raf', 50):
            page = browser.new_page(java_script_enabled=enabled)
            page.set_content('<p>Synthetic polling probe</p>')
            try:
                page.wait_for_function(
                    '() => { window.probeCount=(window.probeCount||0)+1;'
                    'return window.probeCount>1; }',
                    polling=polling, timeout=500)
                result = 'passed'
            except TimeoutError:
                result = 'timed out'
            print(enabled, polling, result, page.evaluate('window.probeCount'))
            page.close()
    browser.close()
```

Observed: both disabled-JS variants timed out with count1; both enabled-JS variants passed with count2. A direct protocol evaluation still executes in the disabled-JS context. Thus a first predicate check that sees an early scroll offset of zero can time out even though the browser subsequently scrolls. If the first check already sees movement, the old test passes, explaining intermittent results. Replacing rAF with browser-side timer polling also reproduced a timeout and is not the correction.

## Narrow correction and negative control

The test now reads the region's native `scrollLeft` through separate protocol evaluations, polling from Python at 50ms intervals with the **same five-second bound**. It does not assign scrollLeft, inject scrolling JS, enable application JS, increase the timeout, retry key presses or skip the test.

Before ArrowRight it requires genuine overflow, focused region and `overflow-x:auto`; afterwards it requires strictly increased scrollLeft and retained focus. Before/after measurements remain in CI logs. The native GET-selector assertions are unchanged.

A test-only keydown-prevention mutation verifies that the same helper **fails when ArrowRight cannot scroll** despite focus and overflow, then passes when that listener is removed. The short timeout applies only to the deliberate negative control; the positive no-JS regression retains five seconds. Existing enlarged-layout mutation coverage remains unchanged.

## Verification

Run all three browser suites with the hashed dependencies and managed Chromium:

```sh
python tools/test_frontend_foundation_browser.py -v
python tools/test_premium_auth_browser.py -v
python tools/test_dashboard_browser.py -v
```

Expected methods: UI1 10, premium-auth 5, UI2 12, including both negative controls. Final exact-head hosted results are recorded in PR #44. PostgreSQL 17 restricted-role CI must pass separately; static browser fixtures do not verify database behavior. No merge, deployment or UI3 work is included.

The final verification also checks the complementary non-overflowing 1440px table with JavaScript disabled: all columns fit, focus is retained, and ArrowRight requires no horizontal movement. The overflowing-table helper must reject this fixture at its overflow precondition. This is separate from the 390px positive scrolling and blocked-key negative control.
