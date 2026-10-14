# Full-screen portal and sidebar icons

Working branch: `fix/ui-ux-20261014`. This continues the previously tested UI fixes.

- The portal occupies the full browser content width at 100% zoom, with no centered outer margins.
- Every teacher and student navigation item has a distinct inline SVG icon. Recovery phone, Sign out, Refresh and Demo Mode also have icons. No icon font, CDN or extra frontend dependency is required.
- Dashboard cards, statistics and tables use the main column's available width.
- On wide screens, Ask LabTwin places its composer beside a scrolling answer feed. Smaller screens stack them.
- Wide teacher course pages place compact settings beside the material library. Student materials use the full main column.
- Assessment settings adapt from four columns to two and one. Several questions use a grid; a single question receives full width. Short-answer assessment and practice fields are multiline text areas; numerical fields remain compact inputs.
- Coding practice places its prompt beside a larger editor on wide screens. The legacy programming lab remains available and contained within the main column.
- Learning paths use multiple columns when space allows. Mastery graphs keep contained scrolling, progress reports keep printable output, and viva answers have a larger writing area.
- Sign out remains accessible. Existing authentication, student-only controls, citations, topic validation, assessment grading and mastery persistence are retained.

No backend application files, APIs, database schema, records, uploaded materials or deployment settings were changed. This branch is not merged or deployed.

## Validation

Local frontend lint, production build, 31 frontend tests and 50 backend regressions passed. The expanded browser suite checks full viewport use, readable SVG icons, every navigation page at desktop/laptop/mobile widths, tutor/course panel stacking, sidebar controls, citations, real submissions and saved mastery. Final result: [GitHub Actions run 38608489840](https://github.com/fjprojects/LabTwin-Track-D-2026/actions/runs/38608489840) passed on code commit `5743962c0cda45de9e818fc100988fc8a1fc606f`, including both browser suites. The run includes screenshots of every navigation page and confirms full viewport width, visible icons, responsive panel stacking, citations, submissions and mastery persistence. The final accessibility correction keeps short-answer labels stable after typing. This documentation-only follow-up does not change the tested application code.

## Update the Windows frontend

Preserve any uncommitted local work before switching branches. Keep the existing backend running; these commands do not reset or migrate a database.

```powershell
Set-Location "C:\Users\francis\LabTwin-Track-D-2026"
git status --short
git fetch origin
git switch fix/ui-ux-20261014
git pull --ff-only
Set-Location .\frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Stop the old Vite terminal with Ctrl+C if it already occupies port 5173. Open `http://localhost:5173` and press Ctrl+0. Manually check your actual Java PDF and normal Windows display scaling before submission.
