/**
 * Collapse one synchronous burst of native table-condition callbacks (for example a batched
 * mobile filter-sheet apply that changes several provider filters and the sort) into a single
 * trailing reload that reads the final state. Separate user actions still reload individually.
 */
export function coalesceReload(reload: () => void): () => void {
	let queued = false;
	return () => {
		if (queued) return;
		queued = true;
		queueMicrotask(() => {
			queued = false;
			reload();
		});
	};
}
