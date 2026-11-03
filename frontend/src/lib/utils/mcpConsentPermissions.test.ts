import { describe, expect, it } from 'vitest';
import { consentCloudAccess, consentServiceAccess, consentServiceLabelKey, type McpConsentProject } from './mcpConsentPermissions';

const nativeLeaves = {
	drover: ['drover-inventory_reader', 'drover-access_user', 'drover-clusters_editor', 'drover-workloads_editor', 'drover-clusters_admin', 'drover-access_admin'],
	palimpsest: ['palimpsest-inventory_reader', 'palimpsest-download_user', 'palimpsest-publish_editor', 'palimpsest-keys_editor', 'palimpsest-keys_admin'],
	waygate: ['waygate-inventory_reader', 'waygate-connect_user', 'waygate-clients_editor', 'waygate-gateways_editor', 'waygate-clients_admin', 'waygate-gateways_admin', 'waygate-routing_admin'],
	lumen: ['lumen-inventory_reader', 'lumen-history_reader', 'lumen-chat_user', 'lumen-images_user', 'lumen-audio_user', 'lumen-tools_user', 'lumen-assets_editor', 'lumen-agents_editor', 'lumen-mcp_editor', 'lumen-keys_editor', 'lumen-history_editor', 'lumen-resources_admin'],
};
const readLeaves = {
	drover: ['drover-inventory_reader', 'drover-access_user'],
	palimpsest: ['palimpsest-inventory_reader', 'palimpsest-download_user'],
	waygate: ['waygate-inventory_reader', 'waygate-connect_user'],
	lumen: ['lumen-inventory_reader', 'lumen-history_reader'],
};
const project: McpConsentProject = { id: 'p', name: 'Project', can_write: false, service_permissions: nativeLeaves, service_errors: {} };

describe('MCP consent permission attenuation', () => {
	it.each(Object.keys(nativeLeaves) as Array<keyof typeof nativeLeaves>)('keeps %s native authority independent from core cloud write and never expands grades', (service) => {
		expect(consentServiceAccess(project, service, 'manage')).toEqual({ state: 'allowed', leaves: nativeLeaves[service] });
		expect(consentCloudAccess(project, 'manage')).toBe('read');
		expect(consentServiceAccess({ ...project, service_permissions: { [service]: [] }, can_write: true }, service, 'manage')).toEqual({ state: 'denied', leaves: [] });
	});

	it.each(Object.keys(nativeLeaves) as Array<keyof typeof nativeLeaves>)('clamps %s to exact read and download leaves, excluding execute/edit/admin', (service) => {
		expect(consentServiceAccess(project, service, 'read')).toEqual({ state: 'allowed', leaves: readLeaves[service] });
		expect(consentCloudAccess({ ...project, can_write: true }, 'read')).toBe('read');
		for (const leaf of nativeLeaves[service]) expect(consentServiceLabelKey(leaf)).not.toBeNull();
	});

	it('does not treat future native execution capabilities as safe reads', () => {
		const future = { ...project, service_permissions: { lumen: ['lumen-future_user'] } };
		expect(consentServiceAccess(future, 'lumen', 'read')).toEqual({ state: 'attenuated', leaves: [] });
		expect(consentServiceLabelKey('lumen-future_user')).toBeNull();
	});

	it('distinguishes verified denial, consent attenuation and unavailable authority', () => {
		expect(consentServiceAccess({ ...project, service_permissions: { lumen: [] } }, 'lumen', 'read').state).toBe('denied');
		expect(consentServiceAccess({ ...project, service_permissions: { lumen: ['lumen-tools_user'] } }, 'lumen', 'read').state).toBe('attenuated');
		expect(consentServiceAccess({ ...project, service_permissions: undefined }, 'lumen', 'manage')).toEqual({ state: 'unavailable', leaves: [] });
		expect(consentServiceAccess({ ...project, service_errors: { lumen: 'permission_check_unavailable' } }, 'lumen', 'manage')).toEqual({ state: 'unavailable', leaves: [] });
		expect(consentServiceAccess({ ...project, service_errors: { lumen: '' } }, 'lumen', 'manage').state).toBe('unavailable');
		expect(consentServiceAccess({ ...project, service_permissions: { lumen: ['drover-inventory_reader'] } }, 'lumen', 'manage').state).toBe('unavailable');
	});

	it('never turns absent project write metadata into write authority', () => {
		expect(consentCloudAccess({ id: 'p', name: 'Legacy project' }, 'manage')).toBe('unknown');
		expect(consentCloudAccess({ id: 'p', name: 'Legacy project' }, 'read')).toBe('unknown');
		expect(consentCloudAccess({ ...project, can_write: null }, 'read')).toBe('unknown');
		expect(consentCloudAccess({ ...project, can_write: null }, 'manage')).toBe('unknown');
		expect(consentCloudAccess({ ...project, can_write: true }, 'manage')).toBe('manage');
	});
});
