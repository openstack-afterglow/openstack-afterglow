export interface McpConsentProject {
	id: string;
	name: string;
	// Older or unavailable metadata is unknown, never proof of write access.
	can_write?: boolean | null;
	scope_error?: 'scope_validation_unavailable' | null;
	service_permissions?: Record<string, string[]>;
	service_errors?: Record<string, string>;
	domain_id?: string | null;
	domain_name?: string | null;
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

/** Native project capability, independent of a key's selected access ceiling. */
export function nativeCloudAccess(project: McpConsentProject): 'read' | 'manage' | 'unknown' {
	if (project.scope_error) return 'unknown';
	if (typeof project.can_write !== 'boolean') return 'unknown';
	return project.can_write ? 'manage' : 'read';
}

export function consentCloudAccess(project: McpConsentProject, access: 'read' | 'manage'): 'read' | 'manage' | 'unknown' {
	const native = nativeCloudAccess(project);
	if (native === 'unknown') return 'unknown';
	return access === 'manage' ? native : 'read';
}

export interface ConsentServiceAccess {
	state: 'unavailable' | 'denied' | 'attenuated' | 'allowed';
	leaves: string[];
	// Closed native policy failure reason; present only when state is unavailable.
	reason?: string;
}

export function consentServiceAccess(project: McpConsentProject, service: string, access: 'read' | 'manage'): ConsentServiceAccess {
	if (project.scope_error) return { state: 'unavailable', leaves: [] };
	if (service === 'lumen') return { state: 'unavailable', leaves: [] };
	if (Object.hasOwn(project.service_errors ?? {}, service)) {
		return { state: 'unavailable', leaves: [], reason: project.service_errors?.[service] || 'permission_check_unavailable' };
	}
	const leaves = project.service_permissions?.[service];
	if (!Array.isArray(leaves) || leaves.some((leaf) => typeof leaf !== 'string' || !leaf.startsWith(`${service}-`))) {
		return { state: 'unavailable', leaves: [] };
	}
	const allowed = access === 'read' ? leaves.filter((leaf) => READ_SERVICE_LEAVES[leaf] === true) : leaves;
	return {
		state: leaves.length === 0 ? 'denied' : allowed.length === 0 ? 'attenuated' : 'allowed',
		leaves: allowed,
	};
}

const POLICY_REASON_LABEL_KEYS = {
	policy_unauthorized: 'mcpConsent.preview.reason.unauthorized',
	policy_forbidden: 'mcpConsent.preview.reason.forbidden',
	policy_not_found: 'mcpConsent.preview.reason.notFound',
	policy_upstream_error: 'mcpConsent.preview.reason.upstreamError',
	policy_unreachable: 'mcpConsent.preview.reason.unreachable',
	policy_timeout: 'mcpConsent.preview.reason.timeout',
	policy_invalid_response: 'mcpConsent.preview.reason.invalid',
	permission_check_unavailable: 'mcpConsent.preview.service.unavailable',
} as const;

type ConsentReasonKey = (typeof POLICY_REASON_LABEL_KEYS)[keyof typeof POLICY_REASON_LABEL_KEYS];

/** Maps a closed native failure reason to its explanation; unknown codes fall back to the generic message. */
export function consentServiceReasonKey(reason: string | undefined): ConsentReasonKey {
	return reason !== undefined && Object.hasOwn(POLICY_REASON_LABEL_KEYS, reason)
		? POLICY_REASON_LABEL_KEYS[reason as keyof typeof POLICY_REASON_LABEL_KEYS] : 'mcpConsent.preview.service.unavailable';
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
