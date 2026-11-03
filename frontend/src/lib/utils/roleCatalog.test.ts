import { describe, expect, it } from 'vitest';
import { isAssignableRole, isRetiredRole } from './roleCatalog';

describe('project role selection catalog', () => {
	it.each(['waygate', 'lumen', 'drover', 'palimpsest'])('retires only the exact shipped %s grades in old snapshots', service => {
		for (const grade of ['reader', 'user', 'editor', 'admin']) {
			expect(isAssignableRole({ name: `${service}_${grade}` })).toBe(false);
			expect(isRetiredRole({ name: `${service}_${grade}`.toUpperCase() })).toBe(true);
		}
		expect(isAssignableRole({ name: `${service}-custom_reader` })).toBe(true);
		expect(isAssignableRole({ name: `${service}_operator` })).toBe(true);
	});
	it.each([
		'waygate-inventory_reader', 'waygate-connect_user', 'waygate-clients_editor',
		'waygate-gateways_editor', 'waygate-clients_admin', 'waygate-gateways_admin', 'waygate-routing_admin',
		'lumen-inventory_reader', 'lumen-history_reader', 'lumen-chat_user', 'lumen-images_user',
		'lumen-audio_user', 'lumen-tools_user', 'lumen-assets_editor', 'lumen-agents_editor',
		'lumen-mcp_editor', 'lumen-keys_editor', 'lumen-history_editor', 'lumen-resources_admin',
		'drover-inventory_reader', 'drover-access_user', 'drover-clusters_editor', 'drover-workloads_editor',
		'drover-clusters_admin', 'drover-access_admin',
		'palimpsest-inventory_reader', 'palimpsest-download_user', 'palimpsest-publish_editor',
		'palimpsest-keys_editor', 'palimpsest-keys_admin'
	])('excludes the retired action identity %s even without metadata', name => {
		expect(isAssignableRole({ name, retired: false, assignable: true })).toBe(false);
	});
	it('honors current server flags without retiring unrelated custom roles or native readers/writers', () => {
		expect(isAssignableRole({ name: 'custom_reader', retired: true })).toBe(false);
		expect(isAssignableRole({ name: 'custom_reader', assignable: false })).toBe(false);
		for (const name of ['member', 'reader', 'manager', 'project_admin', 'project_member', 'project_reader', 'custom_reader']) {
			expect(isAssignableRole({ name })).toBe(true);
		}
		for (const name of ['admin', 'ADMIN']) expect(isAssignableRole({ name, assignable: true })).toBe(false);
	});
});
