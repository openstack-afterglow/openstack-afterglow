import { api } from '$lib/api/client';

/** Project resources indexed by the global search surfaces (command palette and mobile navigation). */
export type ResourceSearchKind = 'instance' | 'volume' | 'image' | 'network' | 'router';

export interface ResourceSearchEntry {
	id: string;
	name: string;
	kind: ResourceSearchKind;
	href: string;
}

export const resourceSearchIcons: Record<ResourceSearchKind | 'route', string> = {
	route: 'M4 6h16M4 12h16M4 18h7',
	instance: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
	volume: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7',
	image: 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14',
	network: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3',
	router: 'M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z',
};

const sources: Array<{ kind: ResourceSearchKind; path: string; href: (id: string) => string }> = [
	{ kind: 'instance', path: '/api/v1/instances', href: id => `/dashboard/compute/instances/${id}` },
	{ kind: 'volume', path: '/api/v1/volumes', href: id => `/dashboard/volumes/${id}` },
	{ kind: 'image', path: '/api/v1/images', href: () => '/dashboard/compute/images' },
	{ kind: 'network', path: '/api/v1/networks', href: () => '/dashboard/network/networks' },
	{ kind: 'router', path: '/api/v1/routers', href: () => '/dashboard/network/routers' },
];

/** Loads every indexed resource kind; a failed kind is omitted without failing the others. */
export async function loadResourceSearchEntries(token?: string, project?: string): Promise<ResourceSearchEntry[]> {
	const results = await Promise.allSettled(sources.map(source => api.get<Array<{ id: string; name?: string }>>(source.path, token, project)));
	return results.flatMap((result, index) => {
		if (result.status !== 'fulfilled') return [];
		const source = sources[index];
		return (result.value ?? []).map(row => ({ id: row.id, name: row.name || row.id.slice(0, 12), kind: source.kind, href: source.href(row.id) }));
	});
}

/** Ordered-subsequence match used by the global search surfaces. */
export function fuzzyMatch(needle: string, haystack: string): boolean {
	if (!needle) return true;
	const n = needle.toLowerCase();
	const h = haystack.toLowerCase();
	let ni = 0;
	for (let i = 0; i < h.length && ni < n.length; i++) {
		if (h[i] === n[ni]) ni++;
	}
	return ni === n.length;
}
