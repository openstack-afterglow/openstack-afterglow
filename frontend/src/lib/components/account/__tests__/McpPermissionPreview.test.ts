import { cleanup, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/public-entry';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { McpConsentProject } from '$lib/utils/mcpConsentPermissions';
import McpPermissionPreview from '../McpPermissionPreview.svelte';

const member: McpConsentProject = {
	id: 'member-project', name: 'Member project', can_write: true,
	service_permissions: {
		drover: ['drover-inventory_reader', 'drover-clusters_editor'],
		palimpsest: ['palimpsest-publish_editor'], waygate: [],
		lumen: ['lumen-keys_editor'],
	},
	service_errors: {},
};
const reader: McpConsentProject = { ...member, id: 'reader-project', name: 'Reader project', can_write: false };

function row(project: McpConsentProject) {
	return screen.getByRole('listitem', { name: `${project.name} ${project.id}` });
}
function cloud(project: McpConsentProject, authority: 'native' | 'effective') {
	const element = row(project).querySelector(`[data-cloud-authority="${authority}"]`);
	expect(element).not.toBeNull();
	return within(element as HTMLElement);
}

beforeEach(() => initLocale('en'));
afterEach(cleanup);

describe('MCP permission preview authority separation', () => {
	it('shows a member management capability even with a read key, then attenuates only the effective selection', async () => {
		const view = render(McpPermissionPreview, { projects: [member], accessLevel: 'read' });
		expect(cloud(member, 'native').getByText(t('mcpConsent.preview.nativeCloudAccess.manage'))).toBeTruthy();
		expect(cloud(member, 'effective').getByText(t('mcpConsent.preview.cloud.read'))).toBeTruthy();
		expect(within(row(member)).queryByText('drover-clusters_editor')).toBeNull();
		expect(within(row(member)).getByText('drover-inventory_reader')).toBeTruthy();
		await view.rerender({ projects: [member], accessLevel: 'manage' });
		expect(cloud(member, 'native').getByText(t('mcpConsent.preview.nativeCloudAccess.manage'))).toBeTruthy();
		expect(cloud(member, 'effective').getByText(t('mcpConsent.preview.cloud.manage'))).toBeTruthy();
		expect(within(row(member)).getByText('drover-clusters_editor')).toBeTruthy();
		await view.rerender({ projects: [member], accessLevel: 'read' });
		expect(cloud(member, 'effective').getByText(t('mcpConsent.preview.cloud.read'))).toBeTruthy();
		expect(within(row(member)).queryByText('drover-clusters_editor')).toBeNull();
	});

	it('keeps a mixed all-project selection per-project and does not infer service authority from cloud capability', () => {
		render(McpPermissionPreview, { projects: [member, reader], accessLevel: 'manage' });
		expect(cloud(member, 'effective').getByText(t('mcpConsent.preview.cloud.manage'))).toBeTruthy();
		expect(cloud(reader, 'native').getByText(t('mcpConsent.preview.nativeCloudAccess.read'))).toBeTruthy();
		expect(cloud(reader, 'effective').getByText(t('mcpConsent.preview.cloud.read'))).toBeTruthy();
		expect(within(row(reader)).getByText('drover-clusters_editor')).toBeTruthy();
		expect(screen.queryByText('Lumen')).toBeNull();
		expect(screen.queryByText('lumen-keys_editor')).toBeNull();
	});

	it('keeps unknown authority unknown across access changes and only restores independently confirmed services', async () => {
		const unknown = { ...member, can_write: null, service_errors: { drover: 'permission_check_unavailable' } };
		const view = render(McpPermissionPreview, { projects: [unknown], accessLevel: 'read' });
		for (const accessLevel of ['read', 'manage'] as const) {
			await view.rerender({ projects: [unknown], accessLevel });
			expect(cloud(unknown, 'native').getByText(t('mcpConsent.preview.nativeCloudAccess.unknown'))).toBeTruthy();
			expect(cloud(unknown, 'effective').getByText(t('mcpConsent.preview.cloud.unknown'))).toBeTruthy();
			expect(within(row(unknown)).queryByText('drover-inventory_reader')).toBeNull();
			expect(within(row(unknown)).getByText(t('mcpConsent.preview.service.unavailable'))).toBeTruthy();
		}
		expect(within(row(unknown)).getByText('palimpsest-publish_editor')).toBeTruthy();
		await view.rerender({ projects: [member], accessLevel: 'manage' });
		expect(cloud(member, 'native').getByText(t('mcpConsent.preview.nativeCloudAccess.manage'))).toBeTruthy();
		expect(cloud(member, 'effective').getByText(t('mcpConsent.preview.cloud.manage'))).toBeTruthy();
		expect(within(row(member)).getByText('drover-clusters_editor')).toBeTruthy();
	});
});
