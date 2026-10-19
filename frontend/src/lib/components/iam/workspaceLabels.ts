import { quotaFields, type QuotaField } from '$lib/api/workspaceIam';
import { t } from '$lib/i18n/ns/workspace-iam';

const categories = ['instances', 'volumes', 'floating_ips', 'networks', 'subnets', 'routers', 'security_groups', 'load_balancers', 'images', 'keypairs', 'database_instances', 'database_backups', 'k3s_clusters', 'waygate_gateways', 'containers', 'magnum_clusters', 'shares', 'share_snapshots', 'share_networks', 'security_services', 'buckets', 'volume_snapshots', 'volume_backups', 'packages', 'secrets', 'vcpus', 'ram_mb', 'volume_gb'] as const;
const fields: Record<string, true> = Object.fromEntries(Object.values(quotaFields).flat().map(field => [field, true as const]));
export function resourceLabel(metric: string): string {
	if (metric.startsWith('quota_') && fields[metric.slice(6)]) return t('allocationMetric', { resource: t(`field.${metric.slice(6) as QuotaField}`) });
	if (categories.includes(metric as typeof categories[number])) return t(`category.${metric as typeof categories[number]}`);
	return metric;
}
export function observationLabel(state: string): string {
	const known = ['ready', 'partial', 'unavailable', 'disabled', 'denied', 'unlimited'] as const;
	return known.includes(state as typeof known[number]) ? t(`state.${state as typeof known[number]}`) : t('unknown');
}
