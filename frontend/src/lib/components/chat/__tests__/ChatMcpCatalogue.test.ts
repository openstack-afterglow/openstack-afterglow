import { grantLumen, pendingLumen, setVerifiedLumenActor } from './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { auth } from '$lib/stores/auth';
import { projectPermissions } from '$lib/stores/servicePermissions';
import type { Writable } from 'svelte/store';
import type { PermissionState } from '$lib/stores/servicePermissions';
import type { CloudToolsCatalogue } from '$lib/api/chatContracts';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error {} }));
import ChatMcpCatalogue from '../ChatMcpCatalogue.svelte';
import type { ApprovedMcpServer } from '../ChatMcpCatalogue.svelte';

const actor = { token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user-1', username: 'tester', projectId: 'project-1', projectName: 'Research', availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false };
const disabled: CloudToolsCatalogue = { available: true, enabled: false, access_level: 'read', project_id: 'project-1', project_name: 'Research', source: 'lumen', allowed_projects: [], selection_name: null, tool_count: 0 };
const approved = { id: 7, name: 'Reviewed source', url: 'https://mcp.example/mcp', auth_mode: 'none' as const, server_is_active: true, is_active: false, config_version: 4 };
function allowManagement() {
	(projectPermissions as Writable<PermissionState>).set({ permissions: { is_owner: false, is_manager: false, can_write: true, service_permissions: {} }, loading: false, error: '' });
}
function deferred<T>() { return Promise.withResolvers<T>(); }

beforeEach(() => {
	vi.clearAllMocks();
	setVerifiedLumenActor(actor);
	api.get.mockResolvedValue(disabled);
	api.post.mockResolvedValue({});
	api.patch.mockResolvedValue({});
	api.delete.mockResolvedValue({});
});

function mount(servers: ApprovedMcpServer[] = [approved]) { return render(ChatMcpCatalogue, { servers, loading: false, oauthStatus: {}, onChanged: async () => {} }); }

describe('Approved MCP consent', () => {
	it('never grants on load or modal open/cancel and activates only after explicit scope approval', async () => {
		mount();
		const trigger = await screen.findByRole('button', { name: 'Afterglow MCP 활성화' });
		await waitFor(() => expect(trigger.hasAttribute('disabled')).toBe(false));
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.click(trigger);
		expect(api.post).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: '읽기 및 관리' }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		expect(screen.queryByRole('dialog')).toBeNull();
		await fireEvent.click(trigger);
		api.post.mockImplementation(async () => { api.get.mockResolvedValue({ ...disabled, enabled: true, allowed_projects: [{ id: 'project-1', name: 'Research' }] }); });
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		await screen.findByRole('button', { name: '비활성화' });
	});

	it('approves management only with current write authority and stops after confirmed revocation', async () => {
		allowManagement();
		mount();
		const trigger = await screen.findByRole('button', { name: 'Afterglow MCP 활성화' });
		await waitFor(() => expect(trigger.hasAttribute('disabled')).toBe(false));
		await fireEvent.click(trigger);
		await fireEvent.click(screen.getByRole('button', { name: '읽기 및 관리' }));
		pendingLumen();
		await waitFor(() => expect(screen.getByRole('button', { name: '승인하고 활성화' }).hasAttribute('disabled')).toBe(true));
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		expect(api.post).not.toHaveBeenCalled();
		grantLumen('lumen-tools_user', 'lumen-mcp_editor');
		allowManagement();
		await waitFor(() => expect(screen.getByRole('button', { name: '승인하고 활성화' }).hasAttribute('disabled')).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		await waitFor(() => expect(api.post.mock.calls[0]?.[1]).toEqual({ access_level: 'manage' }));
	});

	it('pins remote approval to the displayed configuration and refuses stale consent', async () => {
		const view = mount();
		await fireEvent.click(await screen.findByRole('button', { name: 'Reviewed source 활성화' }));
		expect(screen.getByRole('dialog').textContent).toContain('https://mcp.example/mcp');
		await view.rerender({ servers: [{ ...approved, config_version: 5 }] });
		expect(screen.getByRole('button', { name: '승인하고 활성화' }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		expect(api.patch).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '취소' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Reviewed source 활성화' }));
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});

	it('discards a late approved response after an ABA identity transition', async () => {
		const old = deferred<void>();
		api.post.mockReturnValue(old.promise);
		mount([]);
		const trigger = await screen.findByRole('button', { name: 'Afterglow MCP 활성화' });
		await waitFor(() => expect(trigger.hasAttribute('disabled')).toBe(false));
		await fireEvent.click(trigger);
		await fireEvent.click(screen.getByRole('button', { name: '승인하고 활성화' }));
		await waitFor(() => expect(api.post).toHaveBeenCalled());
		auth.set({ ...actor, projectId: 'project-2' });
		// Returning to the same values is a new verified epoch, not the old owner.
		setVerifiedLumenActor(actor);
		await tick();
		old.resolve();
		await tick();
		await tick();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByRole('button', { name: '비활성화' })).toBeNull();
		expect(screen.getByRole('button', { name: 'Afterglow MCP 활성화' }).hasAttribute('disabled')).toBe(false);
	});

	it('deactivates a pending OAuth opt-in without requiring a connected effective server', async () => {
		mount([{ ...approved, auth_mode: 'oauth', activation_is_active: true }]);
		await fireEvent.click(screen.getByRole('button', { name: '비활성화' }));
		await waitFor(() => expect(api.patch.mock.calls[0]?.[1]).toEqual({ is_active: false, config_version: 4 }));
	});
});
