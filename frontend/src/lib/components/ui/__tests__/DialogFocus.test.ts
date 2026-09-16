import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import DialogFocusFixture from './DialogFocusFixture.svelte';

async function openParent() {
	const opener = screen.getByRole('button', { name: '부모 열기' });
	opener.focus();
	await fireEvent.click(opener);
	const parent = screen.getByRole('dialog', { name: '부모 대화상자' });
	await waitFor(() => expect(document.activeElement).toBe(within(parent).getByRole('button', { name: '대화상자 닫기' })));
	return { opener, parent };
}

describe('dialogFocus', () => {
	it('isolates the active layer and cycles Tab inside it', async () => {
		render(DialogFocusFixture);
		const { parent } = await openParent();
		const background = screen.getByTestId('background-control') as HTMLElement;
		expect(background.inert).toBe(true);

		const controls = within(parent).getAllByRole('button');
		controls.at(-1)?.focus();
		await fireEvent.keyDown(controls.at(-1) as HTMLElement, { key: 'Tab' });
		expect(document.activeElement).toBe(controls[0]);
	});

	it('closes only the top dialog and restores focus layer by layer', async () => {
		render(DialogFocusFixture);
		const { opener } = await openParent();
		const childOpener = screen.getByRole('button', { name: '자식 열기' });
		childOpener.focus();
		await fireEvent.click(childOpener);
		await waitFor(() => expect(screen.getByRole('dialog', { name: '자식 대화상자' })).toBeTruthy());

		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.queryByRole('dialog', { name: '자식 대화상자' })).toBeNull();
		expect(screen.getByRole('dialog', { name: '부모 대화상자' })).toBeTruthy();
		await waitFor(() => expect(document.activeElement).toBe(childOpener));

		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.queryByRole('dialog', { name: '부모 대화상자' })).toBeNull();
		await waitFor(() => expect(document.activeElement).toBe(opener));
	});

	it('keeps non-dismissible dialogs open until their explicit action completes', async () => {
		render(DialogFocusFixture);
		await fireEvent.click(screen.getByRole('button', { name: '잠금 열기' }));
		const dialog = screen.getByRole('dialog', { name: '잠금 대화상자' });
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.getByRole('dialog', { name: '잠금 대화상자' })).toBe(dialog);
		await fireEvent.click(within(dialog).getByRole('button', { name: '대화상자 닫기' }));
		expect(screen.getByRole('dialog', { name: '잠금 대화상자' })).toBe(dialog);
		await fireEvent.click(within(dialog).getByRole('button', { name: '완료' }));
		expect(screen.queryByRole('dialog', { name: '잠금 대화상자' })).toBeNull();
	});
});
