import type { AdminNetwork } from '$lib/types/networks';

export type NetworkFlagFilter = 'all' | 'yes' | 'no';

export interface NetworkListFilters {
	search: string;
	external: NetworkFlagFilter;
	shared: NetworkFlagFilter;
	internal: NetworkFlagFilter;
}

/** Flags overlap: an external network can also be shared; internal means neither. */
export function filterNetworks(
	networks: readonly AdminNetwork[],
	filters: NetworkListFilters,
	ownerNames: ReadonlyMap<string, string>,
	typeLabels: { external: string; shared: string; internal: string },
): AdminNetwork[] {
	const terms = filters.search.normalize('NFKC').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
	return networks.filter((network) => {
		const internal = !network.is_external && !network.is_shared;
		if (filters.external !== 'all' && network.is_external !== (filters.external === 'yes')) return false;
		if (filters.shared !== 'all' && network.is_shared !== (filters.shared === 'yes')) return false;
		if (filters.internal !== 'all' && internal !== (filters.internal === 'yes')) return false;
		if (terms.length === 0) return true;
		const fields = [
			network.name, network.id, network.project_id ?? '',
			(network.project_id ? ownerNames.get(network.project_id) : '') ?? network.project_name ?? '',
			network.is_external ? typeLabels.external : '',
			network.is_shared ? typeLabels.shared : '',
			internal ? typeLabels.internal : '',
		].map((value) => value.normalize('NFKC').toLocaleLowerCase());
		return terms.every((term) => fields.some((value) => value.includes(term)));
	});
}
