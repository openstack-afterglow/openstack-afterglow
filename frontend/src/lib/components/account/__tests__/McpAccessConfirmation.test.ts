import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acceptAuthVerification, clearAuth, getAuthVerificationEpoch, logoutInProgress, projectSwitching, setAuth } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/account';
import { t as tc } from '$lib/i18n/ns/common';
import { confirmDialog, dialogState } from '$lib/stores/confirm.svelte';
import ConfirmDialog from '$lib/components/ui/ConfirmDialog.svelte';
import McpAccessSection from '../McpAccessSection.svelte';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class extends Error {}, getBaseUrl: () => 'https://api.example.test' }));
vi.mock('$app/stores', async () => {
	// Vitest hoists this factory before static imports; obtain its store at the mock boundary.
	const { readable } = await import('svelte/store');
	return { page: readable({ data: {}, url: new URL('https://example.test/dashboard/account/mcp') }) };
});

const record = {
	id: 'private-token', grant_id: 'private-grant', name: 'Private prior actor connection', source: 'personal_token',
	owner_project_id: 'origin-project', owner_project_name: 'Saved private origin', access_level: 'read',
	project_scope: 'current', project_ids: ['origin-project'], projects: [{ id: 'origin-project', name: 'Saved private origin' }],
	status: 'active', visible_prefix: 'mcp-example', issued_at: null, expires_at: null, last_used_at: null,
	revoked_at: null, is_lumen_default: false, client_observations: [],
};

function signIn(userId = 'actor') {
	setAuth({ token: `token-${userId}`, userId, projectId: null, domainId: null, identityDomainId: 'home' });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
}

async function openRemoval() {
	const view = render(McpAccessSection);
	render(ConfirmDialog);
	await fireEvent.click(await screen.findByRole('button', { name: t('mcp.methodApiKey') }));
	await screen.findByText(record.name, { selector: '.record-title strong' });
	await fireEvent.click(screen.getByRole('button', { name: t('mcp.revoke') }));
	await screen.findByRole('dialog', { name: t('mcp.revokeConfirm', { name: record.name }) });
	return view;
}

beforeEach(() => {
	vi.clearAllMocks();
	dialogState.reject();
	clearAuth();
	logoutInProgress.set(false);
	projectSwitching.set(false);
	initLocale('en');
	signIn();
	siteConfig.update(config => ({ ...config, services: { ...config.services, mcp: true } }));
	api.get.mockImplementation((path: string, token: string) => Promise.resolve(path === '/api/v1/auth/mcp-tokens' && token === 'token-actor' ? [record] : []));
});
afterEach(() => {
	cleanup();
	dialogState.reject();
	logoutInProgress.set(false);
	projectSwitching.set(false);
	clearAuth();
	initLocale('ko');
	siteConfig.update(config => ({ ...config, services: { ...config.services, mcp: false } }));
});

describe('MCP-owned real confirmation privacy', () => {
	it.each(['actor', 'logout', 'unmount'] as const)('dismisses private removal text on %s and never revokes after sign-in', async boundary => {
		const view = await openRemoval();
		if (boundary === 'actor') signIn('other-actor');
		else if (boundary === 'logout') logoutInProgress.set(true);
		else view.unmount();
		expect(dialogState.open).toBe(false);
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(document.body.textContent).not.toContain(record.name);
		if (boundary === 'logout') { clearAuth(); logoutInProgress.set(false); signIn('other-actor'); }
		if (boundary !== 'unmount') await screen.findByText(t('mcp.emptyTokens'));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(api.delete).not.toHaveBeenCalled();
	});

	it.each(['actor', 'unmount'] as const)('does not dismiss an unrelated newer dialog on %s', async boundary => {
		const view = await openRemoval();
		const newer = confirmDialog('Unrelated current confirmation');
		const request = dialogState.requestId;
		await screen.findByRole('dialog', { name: 'Unrelated current confirmation' });
		if (boundary === 'actor') signIn('other-actor');
		else view.unmount();
		expect(dialogState.requestId).toBe(request);
		expect(dialogState.open).toBe(true);
		expect(screen.getByRole('dialog', { name: 'Unrelated current confirmation' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: tc('actions.cancel') }));
		await expect(newer).resolves.toBe(false);
		expect(api.delete).not.toHaveBeenCalled();
	});
});
