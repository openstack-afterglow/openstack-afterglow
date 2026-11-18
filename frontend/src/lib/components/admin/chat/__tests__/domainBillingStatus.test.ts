import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-chat';
import { t as studioT } from '$lib/i18n/ns/chat-studio';

const calls = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	return { auth: writable({ token: 'token', projectId: 'project', userId: 'owner', sessionId: 'session', roles: [], isSystemAdmin: true }), authReady: writable(true), projectSwitching: writable(false) };
});
vi.mock('$lib/api/client', () => ({ api: calls, ApiError: class extends Error {} }));
vi.mock('$lib/stores/chatModels', () => ({ invalidateChatModels: vi.fn() }));
import ChatConfiguration from '../ChatConfiguration.svelte';

const provider = { id: 1, name: 'OpenAI fixture', provider_type: 'openai', api_provider: 'openai', auth_mode: 'api_key', has_api_key: true, is_active: true, sort_order: 0 };
function row(id: number, domain_billing?: { ready: boolean; reason_code: string | null }) {
	return {
		id, provider_id: 1, model_name: `model-${id}`, display_name: `Model ${id}`, model_kind: 'text', api_provider: 'openai', is_active: true, sort_order: id,
		input_price_per_million: '1', output_price_per_million: '2', effective_input_price_per_million: '1', effective_output_price_per_million: '2', effective_price_source: 'manual',
		...(domain_billing ? { domain_billing } : {})
	};
}

afterEach(() => { cleanup(); initLocale('ko'); });
beforeEach(() => {
	vi.clearAllMocks(); initLocale('ko');
	calls.get.mockImplementation(async (path: string) => {
		if (path.endsWith('/providers')) return [provider];
		if (path.endsWith('/admin/models')) return [
			row(1, { ready: true, reason_code: null }),
			row(2, { ready: false, reason_code: 'context_limit_unknown' }),
			row(3, { ready: false, reason_code: 'pricing_unavailable' }),
			row(4)
		];
		return [];
	});
});

describe('admin domain billing readiness', () => {
	it('badges each text model and links context limits to the capability editor', async () => {
		render(ChatConfiguration, { section: 'models' });
		expect(await screen.findByText(studioT('modelBilling.statusReady'))).toBeTruthy();
		expect(screen.getByText(studioT('modelBilling.statusBlocked', { reason: studioT('modelBilling.contextLimit') }))).toBeTruthy();
		expect(screen.getByText(studioT('modelBilling.statusBlocked', { reason: studioT('modelBilling.pricing') }))).toBeTruthy();
		// Older Lumen rows omit domain_billing and get no badge.
		expect(screen.getAllByText(new RegExp(studioT('modelBilling.statusReady')))).toHaveLength(1);
		expect(screen.getAllByTestId('model-domain-billing-hint')).toHaveLength(2);
		expect(screen.getByText(studioT('modelBilling.contextHint'))).toBeTruthy();
		expect(screen.getByRole('button', { name: studioT('modelBilling.pricingAction') })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: studioT('modelBilling.contextAction') }));
		expect(await screen.findByRole('dialog', { name: t('configuration.editModelCapabilities') })).toBeTruthy();
	});
});
