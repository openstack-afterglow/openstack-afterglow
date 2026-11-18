import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/chat-settings';
import { initLocale } from '$lib/i18n/runtime.svelte';

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: toasts }));

import ChatSdkExamples from '../ChatSdkExamples.svelte';

const baseUrl = 'https://lumen.example/tenant';

function code(): string {
	return screen.getByRole('region').textContent ?? '';
}

async function choose(name: string) {
	await fireEvent.click(screen.getByRole('tab', { name }));
}

describe('ChatSdkExamples', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		initLocale('ko');
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
	});
	afterEach(cleanup);

	it('prefills each SDK and language with the configured Lumen URL', async () => {
		render(ChatSdkExamples, { baseUrl });
		expect(screen.getByRole('heading', { name: t('apiKeys.sdk.title') })).toBeTruthy();
		expect(code()).toContain(`base_url="${baseUrl}/v1"`);
		expect(screen.getByText('python -m pip install openai')).toBeTruthy();

		await choose('JavaScript');
		expect(code()).toContain(`baseURL: "${baseUrl}/v1"`);
		expect(screen.getByText('npm install openai')).toBeTruthy();

		await choose('Anthropic');
		expect(code()).toContain(`baseURL: "${baseUrl}"`);
		expect(code()).not.toContain(`${baseUrl}/v1`);
		expect(screen.getByText('npm install @anthropic-ai/sdk')).toBeTruthy();

		await choose('Gemini');
		expect(code()).toContain(`httpOptions: { baseUrl: "${baseUrl}", apiVersion: 'v1beta' }`);
		await choose('Python');
		expect(code()).toContain(`HttpOptions(base_url="${baseUrl}", api_version="v1beta")`);
		expect(screen.getByText('python -m pip install google-genai')).toBeTruthy();

		await choose('curl');
		expect(code()).toBe(`curl --fail-with-body --silent --show-error '${baseUrl}/v1beta/models' \\\n  -H "x-goog-api-key: $LUMEN_API_KEY"`);
		expect(screen.queryByText(/pip install|npm install/)).toBeNull();
		await choose('Anthropic');
		expect(code()).toContain('-H "anthropic-version: 2023-06-01"');
		expect(code()).toContain(`'${baseUrl}/v1/models'`);
		expect(code()).not.toContain('sk-afgl-');
	});

	it('marks the selected tabs and exposes their panels', async () => {
		render(ChatSdkExamples, { baseUrl });
		const gemini = screen.getByRole('tab', { name: 'Gemini' });
		await fireEvent.click(gemini);
		expect(gemini.getAttribute('aria-selected')).toBe('true');
		expect(screen.getByRole('tab', { name: 'OpenAI' }).getAttribute('aria-selected')).toBe('false');
		expect(screen.getAllByRole('tabpanel')).toHaveLength(2);
		expect(screen.getByRole('tablist', { name: t('apiKeys.sdk.provider') })).toBeTruthy();
		expect(screen.getByRole('tablist', { name: t('apiKeys.sdk.language') })).toBeTruthy();
	});

	it('copies the visible example and reports clipboard failure', async () => {
		render(ChatSdkExamples, { baseUrl });
		await choose('Anthropic');
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.sdk.copy') }));
		expect(navigator.clipboard.writeText).toHaveBeenCalledWith(code());
		expect(toasts.success).toHaveBeenCalledWith(t('apiKeys.toast.copied'));

		vi.mocked(navigator.clipboard.writeText).mockRejectedValueOnce(new Error('denied'));
		await fireEvent.click(screen.getByRole('button', { name: t('apiKeys.sdk.copy') }));
		await vi.waitFor(() => expect(toasts.error).toHaveBeenCalledWith(t('apiKeys.toast.copyFailed')));
	});

	it('links the tutorial in the active documentation language', () => {
		render(ChatSdkExamples, { baseUrl });
		expect(screen.getByRole('link', { name: t('apiKeys.sdk.tutorial') }).getAttribute('href'))
			.toBe('https://openstack-afterglow.github.io/openstack-afterglow/lumen-sdk.html');
		cleanup();
		initLocale('en');
		render(ChatSdkExamples, { baseUrl });
		expect(screen.getByRole('link', { name: t('apiKeys.sdk.tutorial') }).getAttribute('href'))
			.toBe('https://openstack-afterglow.github.io/openstack-afterglow/en/lumen-sdk.html');
	});
});
