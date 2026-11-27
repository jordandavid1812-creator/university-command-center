# UI2 U2 — approved historical presentation assertions

**Status: OWNER-APPROVED — U2 approval condition resolved.** The project owner explicitly approved exactly the three presentation assertion changes below on 12 November 2026, recorded in [PR #44 comment #6822116700](https://github.com/jordandavid1812-creator/university-command-center/pull/44#issuecomment-6822116700). This explicit approval supersedes the earlier pending status; it is not inferred from CI or implementation permission.

These edits already existed in reviewed head `02966075872327d4c4f934e819671a287c73fac4`, relative to base `ed8890982d99b7be5262d997e2e76266a4b65b0c`. This correction preserves them and their corresponding presentation, as requested; it makes no further changes to `server/web_tests/test_polish.py`.

| Historical assertion / test | Original at base | Authorized change | Exact justification and scope |
| --- | --- | --- | --- |
| `test_first_time_dashboard_gives_ordered_next_steps` | `assertLess(response.content.index(b'Actual CGPA'), response.content.index(b'Current semester'))` | Same order assertion with **`Selected semester`** instead of `Current semester` | The selector is a GET-only view choice, not a stored active/current semester. Preserves the check that actual CGPA precedes selection; changes only the expected visible heading. Explicit owner approval covers this heading change. |
| `test_existing_workspace_does_not_repeat_first_time_onboarding`, pinned 11 Nov 2026 request | `assertContains(response, 'Review 0 overdue assignments')` | `assertNotContains(response, 'Review 0 overdue assignments')` **plus** `assertEqual(response.context['totals']['overdue'], 0)` | UI2 uses a conditional attention link only when overdue is positive. Removes the requirement to show a zero-overdue review link, while explicitly retaining the real count check. This reverses a historical presentation expectation and has explicit owner approval. |
| Same test, pinned 12 Nov 2026 request | `assertContains(overdue, 'Review 1 overdue assignments')` | `assertContains(overdue, 'Review 1 overdue assignment')` | Singularizes the accessible link label for one assignment. Date boundary, actual overdue logic and positive attention behavior remain checked. Explicit owner approval covers this grammar-only assertion edit. |

Inspect exact existing changes with:

```sh
git diff ed8890982d99b7be5262d997e2e76266a4b65b0c 02966075872327d4c4f934e819671a287c73fac4 -- server/web_tests/test_polish.py
```

The website suite passed at `99a586ef4153c25ef0d33af89ba9dcfba85823cc` **with these now-authorized assertion changes**. This is not a claim that the unmodified historical assertions pass. No mathematical, ownership, security, query-budget or authentication assertion is changed by these edits or this documentation update.

## Approval boundary and remaining review gate

The approval covers exactly the three listed presentation assertions. It does not authorize weakening academic, authorization, isolation, security, query-budget or other regression checks. This documentation update preserves their exact scope and rationale and makes no application, CSS, browser-test or historical-assertion changes.

U1, U3 and U4 corrections remain intact. Independent review of the corrected exact head remains a pre-merge gate. PR #44 remains draft; no merge, deployment, UI3 implementation or security-branch change is authorized.
