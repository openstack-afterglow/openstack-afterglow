import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import ResourceIdentifier from '../ResourceIdentifier.svelte';

const id = '3e29e7c4-856c-41e7-8a7c-201121b21571';

describe('ResourceIdentifier', () => {
	it('copies the exact native identifier rather than its compact display', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		const view = render(ResourceIdentifier, { id });
		expect(view.queryByRole('status')).toBeNull();
		await fireEvent.click(view.getByRole('button'));
		flushSync();
		expect(writeText).toHaveBeenCalledWith(id);
		expect(view.container.querySelector('[aria-live="polite"]')?.textContent?.trim()).not.toBe('');
	});

	it('makes the full identifier selectable after clipboard denial', async () => {
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } });
		const view = render(ResourceIdentifier, { id });
		await fireEvent.click(view.getByRole('button'));
		flushSync();
		expect(view.container.querySelector('[aria-live="polite"]')?.textContent).toContain(id);
	});
	it('does not offer copying for an unavailable identifier', () => {
		const view = render(ResourceIdentifier, { id: null });
		expect(view.queryByRole('button')).toBeNull();
		expect(view.container.textContent?.trim()).not.toBe('');
	});
});
