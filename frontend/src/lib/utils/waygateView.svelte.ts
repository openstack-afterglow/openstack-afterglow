import type { TableViewState } from '$lib/utils/tableView.svelte';

/** Display-only conditions; never retain rows, credentials or pending operations. */
export interface WaygateViewState {
	servers: TableViewState & { search: string };
	clients: TableViewState & { search: string };
	attachments: TableViewState & { search: string };
	detailTarget: string | null;
}

export function createWaygateViewState(): WaygateViewState {
	const state = $state<WaygateViewState>({
		servers: { search: '', sort: null, filters: {} },
		clients: { search: '', sort: null, filters: {} },
		attachments: { search: '', sort: null, filters: {} },
		detailTarget: null,
	});
	return state;
}
