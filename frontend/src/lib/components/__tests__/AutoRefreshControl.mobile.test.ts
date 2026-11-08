import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { t } from '$lib/i18n/ns/common';

vi.hoisted(() => {
	vi.stubGlobal('matchMedia', (media: string) => {
		const events = new EventTarget();
		return {
			media,
			matches: media.includes('max-width: 767.98px'),
			onchange: null,
			addEventListener: events.addEventListener.bind(events),
			removeEventListener: events.removeEventListener.bind(events),
			dispatchEvent: events.dispatchEvent.bind(events),
			addListener: () => undefined,
			removeListener: () => undefined,
		};
	});
});

import AutoRefreshControlWrapper from './_AutoRefreshControlWrapper.svelte';

describe('AutoRefreshControl on mobile', () => {
	it('renders only an icon refresh button and keeps the bound polling preference', async () => {
		const onManualRefresh = vi.fn();
		render(AutoRefreshControlWrapper, { active: true, intervalSeconds: 30, onManualRefresh });
		expect(screen.queryByRole('combobox')).toBeNull();
		expect(screen.queryByText(t('autoRefresh.label'))).toBeNull();
		const button = screen.getByRole('button', { name: t('autoRefresh.refreshNow') });
		expect(button.textContent?.trim()).toBe('');
		expect(button.classList.contains('btn-icon')).toBe(true);
		await fireEvent.click(button);
		expect(onManualRefresh).toHaveBeenCalledOnce();
		expect(screen.getByTestId('active-state').textContent).toBe('true');
		expect(screen.getByTestId('interval-state').textContent).toBe('30');
	});

	it('announces and blocks a pending refresh', () => {
		render(AutoRefreshControlWrapper, { refreshing: true });
		const button = screen.getByRole('button', { name: t('autoRefresh.loading') }) as HTMLButtonElement;
		expect(button.disabled).toBe(true);
		expect(button.getAttribute('aria-busy')).toBe('true');
	});
});
