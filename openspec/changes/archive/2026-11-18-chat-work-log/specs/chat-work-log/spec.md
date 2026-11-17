# Chat work log

## Requirements

- Before any public answer/step arrives, show the existing quiet response-preparation line. Once the work panel carries progress, suppress competing preparation and window-level stage indicators.
- A live panel lists actual journal steps in sequence, with current state emphasized. Reasoning disclosures contain only already-public provider summaries. Tool detail and failed results remain reachable.
- Pending approval appears inline at its journal position. Reuse `tool.approval_required`, `tool.approval_resolved` and the existing project-scoped approval endpoint. Never infer consent or dispatch a decision from rendering. Newly requested permission reopens a user-collapsed live log. Decision controls disable while authority is unavailable or a decision is pending.
- A terminal event closes the outer work log once. Its native disclosure remains keyboard operable and can subsequently stay open. The final answer follows the single elapsed-time line.
- Elapsed seconds derive from the actual `run.started` and terminal event UTC timestamps. Live updates use the same start boundary. Missing history boundaries do not acquire fabricated elapsed values. Completion freezes elapsed time.
- Lumen's bounded indexed message page includes public `execution.activity` on the owned run's exact final assistant ID, including reachable owned forks. Foreign-user/project run metadata remains excluded. Existing encrypted persistent journals provide history; temporary-thread purge remains unchanged.
- The additive activity boundary is `{id: "started:<seq>", kind: "started", seq, createdAt}`. The browser excludes this metadata-only entry from visible step rows. Terminal entries already carry the finish boundary. No new database migration or approval wire event is introduced.
- All control copy uses the nine-locale chat namespace. Synthetic tutorial transcript/tool payloads are data, not translated UI. Native buttons/disclosures retain focus and expanded-state semantics. Motion uses existing tokens and honors reduced-motion preferences. Mobile controls remain reachable without page overflow.

## Evidence scope

Focused frontend suites cover preparation, live time, approval, completion, reopening, failed tools, reduced motion, existing run/session lifecycle and tutorial transport. Real disposable MariaDB/Redis proves indexed repeated readback, exact stored journal timestamps, owned-fork history and foreign-user denial. Browser proof exercises synthetic tutorial data at desktop/mobile/tablet widths; it does not prove live provider, native IAM or cloud mutation execution.
