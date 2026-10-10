import { grantLumen } from './lumenPermissionFixture';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/chat-studio';
import AgentManagerModal from '../AgentManagerModal.svelte';

const calls = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: calls, ApiError: class extends Error {} }));
beforeEach(() => {
	vi.clearAllMocks();
	auth.update((state) => ({ ...state, token: 'token', projectId: 'project', userId: 'owner' }));
	calls.get.mockImplementation(async (path: string) => path.split('?')[0].endsWith('/agents') ? [{ id: 1, name: 'Owned agent', is_owner: true, tool_ids: [], mcp_ids: [], visibility: 'private' }] : []);
});

it('lets agents editors edit their listed agent without allowing deletion', async () => {
	grantLumen('lumen-agents_editor');
	render(AgentManagerModal, { open: true, models: [], onClose: vi.fn() });
	await screen.findByText('Owned agent');
	expect(screen.getByRole('button', { name: t('agentManager.create') }).hasAttribute('disabled')).toBe(false);
	expect(screen.getByRole('button', { name: t('agentManager.edit') }).hasAttribute('disabled')).toBe(false);
	const remove = screen.getByRole('button', { name: t('agentManager.delete') });
	expect(remove.hasAttribute('disabled')).toBe(true);
	await fireEvent.click(remove);
	expect(calls.delete).not.toHaveBeenCalled();
});

it('does not turn tool execution authority into agent editing', async () => {
	grantLumen('lumen-tools_user');
	render(AgentManagerModal, { open: true, models: [], onClose: vi.fn() });
	await screen.findByText('Owned agent');
	expect(screen.getByRole('button', { name: t('agentManager.create') }).hasAttribute('disabled')).toBe(true);
	expect(screen.getByRole('button', { name: t('agentManager.edit') }).hasAttribute('disabled')).toBe(true);
});
