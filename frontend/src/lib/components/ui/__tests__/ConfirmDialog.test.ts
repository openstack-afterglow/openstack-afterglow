import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/common';
import { confirmDialog, dialogState } from '$lib/stores/confirm.svelte';
import ConfirmDialog from '../ConfirmDialog.svelte';

const gateOptions = {
	requiredText: '제거',
	requiredTextLabel: '계속하려면 제거를 입력하세요',
	confirmLabel: 'Remove',
};

function confirmButton() {
	return screen.getByRole('button', { name: 'Remove' }) as HTMLButtonElement;
}

function typedInput() {
	return screen.getByRole('textbox', { name: gateOptions.requiredTextLabel }) as HTMLInputElement;
}

afterEach(() => {
	dialogState.reject();
	cleanup();
});

describe('ConfirmDialog typed gate', () => {
	it('requires exact input and disables confirmation again when the matching text changes', async () => {
		render(ConfirmDialog);
		const result = confirmDialog('Attached volumes will be deleted', gateOptions);
		await tick();
		const input = typedInput();
		expect(input.value).toBe('');
		expect(input.getAttribute('aria-describedby')).toBe('confirm-dialog-message');
		expect(confirmButton().disabled).toBe(true);

		for (const value of ['삭제', ' 제거', '제거 ', '제거'.normalize('NFD')]) {
			await fireEvent.input(input, { target: { value } });
			expect(confirmButton().disabled).toBe(true);
			await fireEvent.click(confirmButton());
			expect(screen.getByRole('dialog')).toBeTruthy();
		}

		await fireEvent.input(input, { target: { value: '제거' } });
		expect(confirmButton().disabled).toBe(false);
		await fireEvent.input(input, { target: { value: '제' } });
		expect(confirmButton().disabled).toBe(true);
		await fireEvent.input(input, { target: { value: '제거' } });
		await fireEvent.click(confirmButton());
		await expect(result).resolves.toBe(true);
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it.each(['button', 'Escape'])('allows cancellation through %s without matching input', async (method) => {
		render(ConfirmDialog);
		const result = confirmDialog('Attached volumes will be deleted', gateOptions);
		await tick();
		await fireEvent.input(typedInput(), { target: { value: 'wrong' } });
		if (method === 'button') {
			await fireEvent.click(screen.getByRole('button', { name: t('actions.cancel') }));
		} else {
			await fireEvent.keyDown(document, { key: 'Escape' });
		}
		await expect(result).resolves.toBe(false);
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('clears matching input when the same dialog is canceled and reopened before rendering', async () => {
		render(ConfirmDialog);
		const first = confirmDialog('Attached volumes will be deleted', gateOptions);
		await tick();
		await fireEvent.input(typedInput(), { target: { value: '제거' } });
		expect(confirmButton().disabled).toBe(false);

		dialogState.reject();
		const second = confirmDialog('Attached volumes will be deleted', gateOptions);
		await tick();
		await expect(first).resolves.toBe(false);
		expect(typedInput().value).toBe('');
		expect(confirmButton().disabled).toBe(true);
		dialogState.reject();
		await expect(second).resolves.toBe(false);
	});

	it('clears matching input after acceptance before a later gated dialog', async () => {
		render(ConfirmDialog);
		const first = confirmDialog('First', gateOptions);
		await tick();
		await fireEvent.input(typedInput(), { target: { value: '제거' } });
		await fireEvent.click(confirmButton());
		await expect(first).resolves.toBe(true);

		const second = confirmDialog('Second', gateOptions);
		await tick();
		expect(typedInput().value).toBe('');
		expect(confirmButton().disabled).toBe(true);
		dialogState.reject();
		await expect(second).resolves.toBe(false);
	});

	it('does not accept IME composition Enter or the legacy composition key before ordinary Enter', async () => {
		render(ConfirmDialog);
		const settled = vi.fn();
		const result = confirmDialog('Attached volumes will be deleted', gateOptions);
		void result.then(settled);
		await tick();
		const input = typedInput();
		await fireEvent.input(input, { target: { value: 'wrong' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(dialogState.open).toBe(true);

		await fireEvent.input(input, { target: { value: '제거' } });
		await fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
		expect(dialogState.open).toBe(true);
		await fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });
		expect(dialogState.open).toBe(true);
		expect(settled).not.toHaveBeenCalled();

		await fireEvent.keyDown(input, { key: 'Enter' });
		await expect(result).resolves.toBe(true);
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('keeps ungated confirmations input-free and immediately actionable after a gated request', async () => {
		render(ConfirmDialog);
		const gated = confirmDialog('First', gateOptions);
		await tick();
		dialogState.reject();
		await expect(gated).resolves.toBe(false);

		const result = confirmDialog('No automatically deleted volumes', { confirmLabel: 'Remove' });
		await tick();
		expect(screen.queryByRole('textbox')).toBeNull();
		expect(confirmButton().disabled).toBe(false);
		await fireEvent.click(confirmButton());
		await expect(result).resolves.toBe(true);
	});

	it('uses the required text as the visible field label when no label is supplied', async () => {
		render(ConfirmDialog);
		const result = confirmDialog('Delete', { requiredText: '제거', confirmLabel: 'Remove' });
		await tick();
		const input = screen.getByRole('textbox', { name: '제거' });
		await fireEvent.input(input, { target: { value: '제거' } });
		await fireEvent.click(confirmButton());
		await expect(result).resolves.toBe(true);
	});
});
