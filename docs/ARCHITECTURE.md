# Local web MVP architecture

The existing JSON schema stays the same: courses have a name, unique code, credit units, optional semester and actual grade; assignments have a title, course code, due date and completion flag. Old courses without a semester or grade still work.

| Layer | Responsibility |
| --- | --- |
| `academic_logic.py` | Pure validation, the shared A=5 through F=0 scale, weighted summaries, hypothetical predictions, and target-CGPA math. Returns values and warning messages instead of printing or saving. |
| CLI modules | Keep terminal prompts, menus, and output. The overview and target planner reuse extracted calculations; all CLI features retain their existing entry points. `gpa.py` re-exports the grading scale for backward-compatible imports. |
| `web_actions.py` | Validate proposed course and assignment changes. Return copies so failed edits cannot mutate the loaded snapshot. Keep extra fields and prevent duplicate course codes or removal of courses linked to assignments. |
| `web_data.py` | Load a snapshot of original bytes plus parsed records. Refuse damaged data, check stale snapshots, preserve backups, serialize before writing, and atomically replace the destination. |
| `web_app.py` | Display Streamlit pages, collect explicit form submissions, call business rules, and translate exceptions into helpful messages. No CLI prompts are called. |

The first valid course per trimmed, uppercase code is included once in calculations, following the overview's existing rule. Valid ungraded courses reserve their code too. Missing semesters use Unassigned; free-text semester names retain record order. Actual F grades contribute credits and zero points. Missing grades contribute neither points nor attempted credits.

Predictions use a new in-memory set of hypothetical records, not the saved records. They are discarded when leaving the form/session; they never enter actual summaries or storage. Target planning uses Decimal arithmetic to preserve exact 0 and 5 boundaries. It assumes current grades stay fixed and students enter all remaining credits, without inferring university policies.

Web forms hold a session snapshot until a successful save or an explicit reload. This prevents Streamlit reruns from silently accepting stale edits after an external change. Each page shares the current session snapshot; no student records are placed in a global Streamlit cache.

Saving is deliberately conservative. Malformed JSON and non-list roots block editing. A failed read is never treated as an empty list. A missing file is an empty new workspace, but reading it does not create it. Before replacing an existing file, the web adapter preserves its bytes in a new private backup. Serialization, permissions, backup, or replacement failures leave the destination untouched. Tests simulate these failures.

This is not a database or a multi-user application. Snapshot comparison detects ordinary stale forms, but does not lock out a second process between the final check and replacement. Use one writer at a time and close the CLI before web editing. Two-file changes are avoided: course codes remain fixed, and courses with linked assignments cannot be removed until those assignments are removed. The legacy CLI storage keeps its existing behavior; the stricter web storage does not silently change that contract.

Streamlit is the only direct web dependency. Its charts and testing tools supply the UI and interaction tests. The CLI and business rules use only the standard library. Tests and browser checks must use synthetic records in temporary directories, never real student data.

Future authentication, user isolation, database transactions, deployment, and backup retention are outside this milestone. Public multi-user hosting must wait for a storage and security design that isolates each student's records.

## Separate Django database foundation (Milestone 2A)

`server/` now holds an independent Django 5.2 LTS/PostgreSQL 17 foundation. It
reuses academic validators but does not read legacy JSON or change CLI/Streamlit
storage. UUID accounts own semesters, courses and assignments. Database checks
and composite foreign keys protect data integrity; request-level owner isolation
is deferred to Milestone 2B. See [DATABASE_FOUNDATION.md](DATABASE_FOUNDATION.md)
for model relationships, exact numeric storage, migrations and security boundaries.
