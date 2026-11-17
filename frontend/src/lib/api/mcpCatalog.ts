export interface McpConnection {
	id: number;
	name: string;
	scope: 'user' | 'domain' | 'global';
	owner_domain_id?: string | null;
	owner_user_id?: string | null;
	owner_project_id?: string | null;
	url: string | null;
	transport: string;
	auth_mode: 'none' | 'oauth' | 'admin';
	has_headers?: boolean;
	auth_connected?: boolean;
	is_active: boolean;
	server_is_active: boolean;
	activation_is_active?: boolean;
	activation_config_version?: number | null;
	config_version: number;
	template_key?: string | null;
	connection_label?: string | null;
	tool_count?: number;
	tools?: { name: string; description?: string | null }[];
	catalog_error?: string | null;
}
export interface McpTemplate {
	id: string;
	name: string;
	registry_name: string;
	description: string;
	url: string | null;
	transport: string | null;
	variables: string[];
	header_hints: { name?: string | null; description: string; required?: boolean | null; secret?: boolean | null }[];
	docs_url?: string | null;
	access: 'open' | 'oauth' | 'credentials' | 'configure' | 'unreachable' | 'unavailable' | 'managed';
	featured: boolean;
	unavailable_reason?: string | null;
	state?: string;
	connections?: McpConnection[];
	managed?: { profile: string; available: boolean; reason: string | null; tools: string[] } | null;
}
export interface McpSettingsPage {
	entries: McpTemplate[];
	total: number;
	offset: number;
	limit: number;
	next_offset: number | null;
	domain_id: string;
	can_manage_domain: boolean;
	custom_connections: McpConnection[];
}
export interface McpDomainPage {
	connections: McpConnection[];
	total: number;
	next_offset: number | null;
}

/** Never turn another owner's returned row into an action target. Server remains authoritative. */
export function visibleMcpConnection(row: McpConnection, userId: string, projectId: string, domainId: string): boolean {
	if (row.scope === 'domain') return row.owner_domain_id === domainId;
	if (row.scope === 'user') return row.owner_user_id === userId && row.owner_project_id === projectId;
	return row.scope === 'global';
}

export function mcpConnectionState(row: McpConnection): 'active' | 'stale' | 'needsAuth' | 'inactive' {
	if (row.activation_is_active && row.activation_config_version !== row.config_version) return 'stale';
	if (row.auth_mode === 'oauth' && row.auth_connected !== true) return 'needsAuth';
	if (row.auth_mode === 'admin' && row.has_headers !== true) return 'needsAuth';
	return row.is_active ? 'active' : 'inactive';
}
