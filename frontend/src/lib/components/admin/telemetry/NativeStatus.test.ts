import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { setLocale } from '$lib/i18n/runtime.svelte';
import NativeStatus from './NativeStatus.svelte';

afterEach(() => { cleanup(); setLocale('ko'); });
describe('native telemetry states in the rendered console', () => {
	it.each([
		['ko', '네이티브 API 조회 가능'], ['en', 'Native API readable'],
		['ja', 'ネイティブ API を取得可能'], ['zh-CN', '可读取原生 API'],
	] as const)('renders the verified-readability label in %s without a fallback key', (locale, expected) => {
		setLocale(locale); render(NativeStatus, { status: 'available' });
		expect(screen.getByText(expected)).toBeTruthy();
	});
	it.each([
		['not_configured', 'This native service is not configured in your authenticated catalog. Existing monitoring remains available.'],
		['forbidden', 'Native access is forbidden. No verified data is available for this section.'],
		['unavailable', 'The native service could not be read. This is not an empty result or a healthy zero.'],
		['partial', 'Partial native response. Some information is unavailable; this is not a verified total.'],
		['not_found', 'The native resource was not found. Reread before making another change.'],
	] as const)('keeps %s distinct and never displays upstream error material', (status, expected) => {
		setLocale('en'); render(NativeStatus, { status, error: 'https://private.invalid/webhook?secret=hidden' });
		expect(screen.getByText(expected)).toBeTruthy();
		expect(document.body.textContent).not.toContain('secret=hidden');
		expect(screen.queryByRole('link')).toBeNull();
	});
});
