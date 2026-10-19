import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import QuotaEditor from '../QuotaEditor.svelte';

afterEach(cleanup);

it('allows the first limit on an unconfigured policy without inventing other limits', async () => {
	const onSave = vi.fn();
	const { container } = render(QuotaEditor, { values: {}, onSave });
	const instances = container.querySelector('input[id$="-instances"]') as HTMLInputElement;
	expect(instances.value).toBe('');
	await fireEvent.input(instances, { target: { value: '5' } });
	await fireEvent.click(screen.getByRole('button'));
	expect(onSave).toHaveBeenCalledExactlyOnceWith({ instances: 5 });
});

it('preserves zero and unlimited while removing an explicitly cleared policy limit', async () => {
	const onSave = vi.fn();
	const { container } = render(QuotaEditor, { values: { instances: 0, cores: -1, ram: 512 }, onSave });
	expect((container.querySelector('input[id$="-instances"]') as HTMLInputElement).value).toBe('0');
	expect((container.querySelector('input[id$="-cores"]') as HTMLInputElement).value).toBe('-1');
	await fireEvent.input(container.querySelector('input[id$="-ram"]')!, { target: { value: '' } });
	await fireEvent.click(screen.getByRole('button'));
	expect(onSave).toHaveBeenCalledExactlyOnceWith({ instances: 0, cores: -1 });
});
