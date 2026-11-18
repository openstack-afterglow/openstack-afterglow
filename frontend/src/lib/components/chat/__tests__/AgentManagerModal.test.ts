import { grantLumen } from './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/chat-studio';
import { t as settingsT } from '$lib/i18n/ns/chat-settings';
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

it('filters by provider and saves the chosen row even when names match', async () => {
	grantLumen('lumen-agents_editor');
	const models = [
		{ id: 41, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, provider: 'Provider A', model_name: 'shared', display_name: 'Shared' },
		{ id: 57, provider_id: 2, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, provider: 'Provider B', model_name: 'shared', display_name: 'Shared' }
	];
	render(AgentManagerModal, { open: true, models, onClose: vi.fn() });
	await fireEvent.click(await screen.findByRole('button', { name: t('agentManager.create') }));
	await fireEvent.input(screen.getByPlaceholderText(settingsT('agentBuilder.name.placeholder')), { target: { value: 'Pinned agent' } });
	const provider = screen.getByRole('combobox', { name: t('modelPicker.providers') });
	const model = screen.getByRole('combobox', { name: settingsT('agentBuilder.model.label') }) as HTMLSelectElement;
	await fireEvent.change(provider, { target: { value: '1' } });
	expect([...model.options].map((option) => option.value)).toEqual(['', '41']);
	await fireEvent.change(model, { target: { value: '41' } });
	await fireEvent.change(provider, { target: { value: '2' } });
	expect([...model.options].map((option) => option.value)).toEqual(['', '57']);
	expect(model.value).toBe('');
	await fireEvent.change(model, { target: { value: '57' } });
	await fireEvent.click(screen.getByRole('button', { name: settingsT('agentBuilder.actions.create') }));
	await waitFor(() => expect(calls.post).toHaveBeenCalledWith('/api/v1/chat/agents',
		expect.objectContaining({ name: 'Pinned agent', model_name: 'shared', model_row_id: 57 }), 'token', 'project'));
});
