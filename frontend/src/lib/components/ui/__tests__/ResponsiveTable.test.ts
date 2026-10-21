import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = {
		matches: true,
		media: '(min-width: 1024px)',
		onchange: null,
		addEventListener: events.addEventListener.bind(events),
		removeEventListener: events.removeEventListener.bind(events),
		dispatchEvent: events.dispatchEvent.bind(events),
		addListener: () => undefined,
		removeListener: () => undefined,
	};
	vi.stubGlobal('matchMedia', () => query);
	return query;
});

import Probe from './_ResponsiveResourceProbe.svelte';

beforeEach(() => { media.matches = true; });

async function setDesktop(desktop: boolean) {
	media.matches = desktop;
	media.dispatchEvent(new Event('change'));
	await waitFor(() => expect(screen.queryByRole('table') !== null).toBe(desktop));
}

describe('responsive resource presentation', () => {
	it('preserves selected resources and their action across tablet/desktop transitions', async () => {
		const onInspect = vi.fn();
		render(Probe, { onInspect });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Select VM' }));
		await setDesktop(false);
		expect((screen.getByRole('checkbox', { name: 'Select VM' }) as HTMLInputElement).checked).toBe(true);
		expect(screen.getAllByRole('button', { name: 'Inspect VM' })).toHaveLength(1);
		await fireEvent.click(screen.getByRole('button', { name: 'Inspect VM' }));
		expect(onInspect).toHaveBeenCalledTimes(1);
		await setDesktop(true);
		expect((screen.getByRole('checkbox', { name: 'Select VM' }) as HTMLInputElement).checked).toBe(true);
		expect(screen.queryByRole('article')).toBeNull();
	});

	it('retains secondary metadata behind a native disclosure in compact mode', async () => {
		const view = render(Probe, { onInspect: vi.fn() });
		await setDesktop(false);
		const disclosure = view.container.querySelector('details');
		expect(disclosure?.open).toBe(false);
		await fireEvent.click(screen.getByText('상세 정보'));
		expect(disclosure?.open).toBe(true);
		expect(screen.getByText('vm-immutable-id')).toBeTruthy();
		expect(screen.queryByRole('table')).toBeNull();
	});
});
