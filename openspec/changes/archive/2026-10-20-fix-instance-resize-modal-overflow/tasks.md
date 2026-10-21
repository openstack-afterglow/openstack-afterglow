# Tasks

- [x] Identify the resize panel overflow source and compare existing modal sizing. Shared Modal already owns padding; the width100% child plus horizontal margins exceeds its scroller (Chromium452px client/480px scroll).
- [x] Bound the shared resize panel and long choice content without changing resize behavior.36 Chromium cases across9widths×2themes×short/long choices have zero horizontal overflow.
- [x] Repair current-flavor verification with real Nova metadata and preserve resize safety.69 focused backend tests pass; actual SDK2.61→loopback Nova HTTP lists/submits in user/admin modes, current catalog missing cases, same/disk/quota rejection verified. Native admin POST unchanged.
- [x] Verify actual Chromium geometry and existing resize interactions; record evidence and archive.36responsive+126locale cases,40focused frontend,69focused backend,instances1288backend/601frontend passed; svelte-check0errors/16existing warnings,4backend Ruff check/format passed. No full gate/deploy/cloud mutation. Docs updated; owned UI runtime/browser stopped and throwaway harness removed.
- [x] Final classic-scrollbar edge: constrain28rem panel to100% of actual Modal content box (not100vw); forced scroll/gutter11widths overflow0. Preserve previous locale/test receipts as preceding sizing verification.
