import { writable } from 'svelte/store';

function createSidebarStore(initialOpen = false) {
	const { subscribe, set, update } = writable(initialOpen);
	return {
		subscribe,
		open()  { set(true); },
		close() { set(false); },
		toggle() { update(v => !v); },
	};
}

export const sidebarOpen = createSidebarStore();
export const sidebarExpanded = createSidebarStore(true);
