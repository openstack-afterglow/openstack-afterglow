export interface McpConsentProject {
	id: string;
	name: string;
	// Older or unavailable metadata is unknown, never proof of write access.
	can_write?: boolean | null;
	service_permissions?: Record<string, string[]>;
	service_errors?: Record<string, string>;
}

export const MCP_CONSENT_SERVICES = [
	{ id: 'drover', name: 'Drover' },
	{ id: 'palimpsest', name: 'Palimpsest' },
	{ id: 'waygate', name: 'Waygate' },
] as const;

// Consent attenuation only: these exact native leaves are read/download access.
// Never expand service grades or derive service authority from can_write.
const READ_SERVICE_LEAVES: Record<string, true> = {
	'drover-inventory_reader': true, 'drover-access_user': true,
	'palimpsest-inventory_reader': true, 'palimpsest-download_user': true,
	'waygate-inventory_reader': true, 'waygate-connect_user': true,
};

export function consentCloudAccess(project: McpConsentProject, access: 'read' | 'manage'): 'read' | 'manage' | 'unknown' {
	if (typeof project.can_write !== 'boolean') return 'unknown';
	return access === 'manage' && project.can_write ? 'manage' : 'read';
}

export function consentServiceAccess(project: McpConsentProject, service: string, access: 'read' | 'manage') {
	if (service === 'lumen') return { state: 'unavailable' as const, leaves: [] };
	const leaves = project.service_permissions?.[service];
	if (Object.hasOwn(project.service_errors ?? {}, service) || !Array.isArray(leaves)
		|| leaves.some((leaf) => typeof leaf !== 'string' || !leaf.startsWith(`${service}-`))) {
		return { state: 'unavailable' as const, leaves: [] };
	}
	const allowed = access === 'read' ? leaves.filter((leaf) => READ_SERVICE_LEAVES[leaf] === true) : leaves;
	return {
		state: leaves.length === 0 ? 'denied' as const : allowed.length === 0 ? 'attenuated' as const : 'allowed' as const,
		leaves: allowed,
	};
}

const SERVICE_PERMISSION_LABEL_KEYS = {
	'drover-inventory_reader': 'mcpConsent.permission.droverInventory',
	'drover-access_user': 'mcpConsent.permission.droverAccess',
	'drover-clusters_editor': 'mcpConsent.permission.droverClustersEdit',
	'drover-workloads_editor': 'mcpConsent.permission.droverWorkloads',
	'drover-clusters_admin': 'mcpConsent.permission.droverClustersAdmin',
	'drover-access_admin': 'mcpConsent.permission.droverAccessAdmin',
	'palimpsest-inventory_reader': 'mcpConsent.permission.palimpsestInventory',
	'palimpsest-download_user': 'mcpConsent.permission.palimpsestDownload',
	'palimpsest-publish_editor': 'mcpConsent.permission.palimpsestPublish',
	'palimpsest-keys_editor': 'mcpConsent.permission.palimpsestKeysEdit',
	'palimpsest-keys_admin': 'mcpConsent.permission.palimpsestKeysAdmin',
	'waygate-inventory_reader': 'mcpConsent.permission.waygateInventory',
	'waygate-connect_user': 'mcpConsent.permission.waygateConnect',
	'waygate-clients_editor': 'mcpConsent.permission.waygateClientsEdit',
	'waygate-gateways_editor': 'mcpConsent.permission.waygateGatewaysEdit',
	'waygate-clients_admin': 'mcpConsent.permission.waygateClientsAdmin',
	'waygate-gateways_admin': 'mcpConsent.permission.waygateGatewaysAdmin',
	'waygate-routing_admin': 'mcpConsent.permission.waygateRouting',
} as const;

/** Human descriptions never replace the exact native permission identifier. */
export function consentServiceLabelKey(leaf: string) {
	return Object.hasOwn(SERVICE_PERMISSION_LABEL_KEYS, leaf)
		? SERVICE_PERMISSION_LABEL_KEYS[leaf as keyof typeof SERVICE_PERMISSION_LABEL_KEYS] : null;
}
