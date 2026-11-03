export interface RoleSelectionMetadata {
	name: string;
	retired?: boolean;
	assignable?: boolean;
}

// Exact identities shipped by the former service IAM presets. Prefix matching
// would incorrectly retire legitimate operator-defined roles.
const retiredNames = new Set([
	...['waygate', 'lumen', 'drover', 'palimpsest'].flatMap(service =>
		['reader', 'user', 'editor', 'admin'].map(grade => `${service}_${grade}`)),
	'waygate-inventory_reader', 'waygate-connect_user', 'waygate-clients_editor',
	'waygate-gateways_editor', 'waygate-clients_admin', 'waygate-gateways_admin', 'waygate-routing_admin',
	'lumen-inventory_reader', 'lumen-history_reader', 'lumen-chat_user', 'lumen-images_user',
	'lumen-audio_user', 'lumen-tools_user', 'lumen-assets_editor', 'lumen-agents_editor',
	'lumen-mcp_editor', 'lumen-keys_editor', 'lumen-history_editor', 'lumen-resources_admin',
	'drover-inventory_reader', 'drover-access_user', 'drover-clusters_editor', 'drover-workloads_editor',
	'drover-clusters_admin', 'drover-access_admin',
	'palimpsest-inventory_reader', 'palimpsest-download_user', 'palimpsest-publish_editor',
	'palimpsest-keys_editor', 'palimpsest-keys_admin'
]);

export function isRetiredRole(role: RoleSelectionMetadata): boolean {
	return role.retired === true || retiredNames.has(role.name.toLowerCase());
}

export function isAssignableRole(role: RoleSelectionMetadata): boolean {
	return role.name.toLowerCase() !== 'admin' && role.assignable !== false && !isRetiredRole(role);
}
