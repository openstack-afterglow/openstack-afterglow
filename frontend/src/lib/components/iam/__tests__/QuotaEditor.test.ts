import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/workspace-iam';
import type * as Reactivity from 'svelte/reactivity';

const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async (importOriginal) => {
	const original = await importOriginal<typeof Reactivity>();
	return { ...original, MediaQuery: class { get current() { return viewport.desktop; } } };
});
import QuotaEditor from '../QuotaEditor.svelte';

afterEach(() => { cleanup(); viewport.desktop = true; });

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

it('keeps labeled policy inputs and unlimited values usable in compact cards', async () => {
	viewport.desktop = false;
	const onSave = vi.fn();
	const { container } = render(QuotaEditor, { values: { instances: 0, cores: -1 }, onSave });
	expect(screen.queryByRole('table')).toBeNull();
	const instances = screen.getByLabelText(t('field.instances')) as HTMLInputElement;
	expect(instances.value).toBe('0');
	expect((screen.getByLabelText(t('field.cores')) as HTMLInputElement).value).toBe('-1');
	expect(container.querySelectorAll('input[id$="-instances"]')).toHaveLength(1);
	await fireEvent.input(instances, { target: { value: '7' } });
	await fireEvent.click(screen.getByRole('button', { name: t('save') }));
	expect(onSave).toHaveBeenCalledExactlyOnceWith({ instances: 7, cores: -1 });
});

it('preserves unavailable project limits and mutation locks in compact cards', () => {
	viewport.desktop = false;
	render(QuotaEditor, { values: { instances: 3 }, projectMode: true, disabled: true, onSave: vi.fn(), native: {
		project_id: 'project-a', compute: { instances: { limit: 3, in_use: 2, reserved: 1 } }, volume: null, network: null, file_storage: null,
		availability: { compute: true, volume: false, network: false, file_storage: false }, errors: { volume: 'service_disabled' }
	} });
	expect((screen.getByLabelText(t('field.instances')) as HTMLInputElement).disabled).toBe(true);
	expect((screen.getByRole('button', { name: t('save') }) as HTMLButtonElement).disabled).toBe(true);
	expect(screen.getAllByText(t('unknown')).length).toBeGreaterThan(0);
});
