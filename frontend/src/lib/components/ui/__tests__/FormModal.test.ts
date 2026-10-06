import { render } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import FormModal from '../FormModal.svelte';

const children = createRawSnippet(() => ({ render: () => '<span>입력 항목</span>' }));

describe('FormModal', () => {
	it('shows labelled work only while submitting and keeps a stable submit label', async () => {
		const onSubmit = vi.fn();
		const view = render(FormModal, { open: true, title: '생성', onSubmit, submitLabel: '생성하기', submitting: true, children });
		expect(view.getByRole('status').textContent?.trim()).toBeTruthy();
		const submit = view.getByRole('button', { name: '생성하기' }) as HTMLButtonElement;
		expect(submit.getAttribute('aria-busy')).toBe('true');
		expect(submit.disabled).toBe(true);
		await view.rerender({ open: true, title: '생성', onSubmit, submitLabel: '생성하기', submitting: false, children });
		expect(view.queryByRole('status')).toBeNull();
		expect(submit.getAttribute('aria-busy')).toBe('false');
		expect(submit.disabled).toBe(false);
	});
});
