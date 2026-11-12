# UI2 U2 — historical presentation assertions awaiting owner approval

**Status: AWAITING EXPLICIT OWNER APPROVAL. Not resolved.** No approval for the three edits below has been recorded. The independent-review correction prompt explicitly is **not** approval. CI success, implementation permission and a reviewer recommendation do not supply that approval.

These edits already existed in reviewed head `02966075872327d4c4f934e819671a287c73fac4`, relative to base `ed8890982d99b7be5262d997e2e76266a4b65b0c`. This correction preserves them and their corresponding presentation, as requested; it makes no further changes to `server/web_tests/test_polish.py`.

| Historical assertion / test | Original at base | Current proposed change | Exact justification and scope |
| --- | --- | --- | --- |
| `test_first_time_dashboard_gives_ordered_next_steps` | `assertLess(response.content.index(b'Actual CGPA'), response.content.index(b'Current semester'))` | Same order assertion with **`Selected semester`** instead of `Current semester` | The selector is a GET-only view choice, not a stored active/current semester. Preserves the check that actual CGPA precedes selection; changes only the expected visible heading. Requires owner approval despite the blueprint's proposed wording. |
| `test_existing_workspace_does_not_repeat_first_time_onboarding`, pinned 11 Nov 2026 request | `assertContains(response, 'Review 0 overdue assignments')` | `assertNotContains(response, 'Review 0 overdue assignments')` **plus** `assertEqual(response.context['totals']['overdue'], 0)` | UI2 proposes a conditional attention link only when overdue is positive. Removes the requirement to show a zero-overdue review link, while explicitly retaining the real count check. This reverses a historical presentation expectation and requires owner approval. |
| Same test, pinned 12 Nov 2026 request | `assertContains(overdue, 'Review 1 overdue assignments')` | `assertContains(overdue, 'Review 1 overdue assignment')` | Singularizes the accessible link label for one assignment. Date boundary, actual overdue logic and positive attention behavior remain checked. It is still a historical assertion edit requiring approval. |

Inspect exact existing changes with:

```sh
git diff ed8890982d99b7be5262d997e2e76266a4b65b0c 02966075872327d4c4f934e819671a287c73fac4 -- server/web_tests/test_polish.py
```

The current full website suite passes **with these proposed assertion changes**. That is not a claim that the unmodified historical assertions pass, nor that U2 is approved. No mathematical, ownership, security, query-budget or authentication assertion is changed by these edits or by this correction.

## Required decision before acceptance / merge

The project owner must explicitly approve the three listed changes, with the approval recorded in the PR or an attributable owner instruction. Until then, U2 remains a pre-merge blocker and PR #44 remains draft.

If approval is declined, restore the original assertions and reconcile the relevant visible presentation for review. Do not hide obsolete strings off-screen, weaken core assertions or treat no response as consent. Pending approval is not a rejection: the current instruction is to preserve the implementation while documenting the pending decision, not silently redesign it or infer permission.
