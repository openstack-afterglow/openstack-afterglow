import type { TopologyNetwork } from '$lib/types/topology';
import type { CanvasDomainGroup } from './canvas/types';
import { t } from '$lib/i18n/ns/topology';

/** A shared/external network still has exactly one native owner, not one copy per consumer. */
export function groupNetworksByDomain(networks: readonly TopologyNetwork[]): CanvasDomainGroup[] {
	const groups = new Map<string, CanvasDomainGroup>();
	for (const network of networks) {
		const status = network.owner_status ?? (network.domain_id ? 'known' : 'unknown_owner');
		const domainId = network.domain_id || null;
		const id = domainId ? `domain:${domainId}` : network.project_id ? `project:${network.project_id}` : 'owner:unknown';
		let group = groups.get(id);
		if (!group) {
			group = { id, domainId, name: network.domain_name || null, status, netIds: [] };
			groups.set(id, group);
		}
		group.netIds.push(network.id);
	}
	return [...groups.values()].sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '') || a.id.localeCompare(b.id));
}

export function domainGroupLabel(group: CanvasDomainGroup): string {
	if (group.status === 'known' && group.domainId) return t('domain.label', { name: group.name || group.domainId, id: group.domainId });
	if (group.status === 'deleted_domain' && group.domainId) return t('domain.deleted', { id: group.domainId });
	if (group.id.startsWith('project:')) return t('domain.deletedProject', { id: group.id.slice(8) });
	return t('domain.unknown');
}
