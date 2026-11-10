import { fireEvent, render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import UsageScheduleFields from '../UsageScheduleFields.svelte';
import { defaultUsageDraft } from '$lib/utils/instanceUsage';

describe('usage schedule fields', () => {
	it('offers no volume deletion for default archive and requires separate consent for delete', async () => {
		const draft = defaultUsageDraft();
		const onchange = vi.fn();
		const { container, rerender } = render(UsageScheduleFields, { value: draft, onchange });
		expect(container.querySelector('input[type="checkbox"]')).toBeNull();
		await fireEvent.change(container.querySelector('select')!, { target: { value: 'delete' } });
		const deleting = onchange.mock.lastCall![0];
		expect(deleting).toMatchObject({ expiryAction: 'delete', deleteVolumes: false });
		await rerender({ value: deleting, onchange });
		const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
		expect(checkbox.checked).toBe(false);
		await fireEvent.click(checkbox);
		expect(onchange.mock.lastCall![0].deleteVolumes).toBe(true);
		await rerender({ value: { ...deleting, deleteVolumes: true }, onchange });
		await fireEvent.change(container.querySelector('select')!, { target: { value: 'shelve' } });
		expect(onchange.mock.lastCall![0]).toMatchObject({ expiryAction: 'shelve', deleteVolumes: false });
	});

	it('labels native date input and disables every editing control for read-only or pending state', () => {
		const { container } = render(UsageScheduleFields, { value: defaultUsageDraft(), onchange: vi.fn(), disabled: true, idPrefix: 'readonly' });
		const date = container.querySelector<HTMLInputElement>('#readonly-expires')!;
		expect(date.type).toBe('datetime-local');
		expect(container.querySelector('label[for="readonly-expires"]')).not.toBeNull();
		expect(date.getAttribute('aria-describedby')).toBe('readonly-expires-message');
		for (const control of container.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select')) expect(control.disabled).toBe(true);
	});

	it('shows the reason only for an extended expiry or an existing reason', async () => {
		const onchange = vi.fn();
		const { container, rerender } = render(UsageScheduleFields, { value: defaultUsageDraft(), onchange });
		expect(container.querySelector('input[type="text"]')).toBeNull();
		await fireEvent.input(container.querySelector('input[type="datetime-local"]')!, { target: { value: '2035-12-31T15:45' } });
		await rerender({ value: onchange.mock.lastCall![0], onchange });
		expect(container.querySelector('input[type="text"]')).not.toBeNull();
		await rerender({ value: { ...defaultUsageDraft(), reason: 'kept' }, onchange });
		expect(container.querySelector('input[type="text"]')).not.toBeNull();
		await rerender({ value: defaultUsageDraft(), onchange });
		expect(container.querySelector('input[type="text"]')).toBeNull();
	});

	it('publishes immutable local datetime and long reason changes without truncating UTF-8 input', async () => {
		const draft = defaultUsageDraft();
		const onchange = vi.fn();
		const { container, rerender } = render(UsageScheduleFields, { value: draft, onchange });
		await fireEvent.input(container.querySelector('input[type="datetime-local"]')!, { target: { value: '2035-12-31T15:45' } });
		expect(onchange.mock.lastCall![0].expiresLocal).toBe('2035-12-31T15:45');
		expect(draft.expiresLocal).not.toBe('2035-12-31T15:45');
		await rerender({ value: onchange.mock.lastCall![0], onchange });
		const longReason = '가'.repeat(100);
		await fireEvent.input(container.querySelector('input[type="text"]')!, { target: { value: longReason } });
		expect(onchange.mock.lastCall![0].reason).toBe(longReason);
		expect(draft.reason).toBe('');
	});
});
