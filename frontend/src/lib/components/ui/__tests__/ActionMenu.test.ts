import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import ActionMenuFixture from './ActionMenuFixture.svelte';

async function openMenu() {
	const trigger = screen.getByRole('button', { name: '인스턴스 작업' });
	await fireEvent.click(trigger);
	await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: '시작' })));
	return trigger;
}

describe('ActionMenu', () => {
	it('labels its trigger and focuses the first enabled action', async () => {
		render(ActionMenuFixture);
		const trigger = await openMenu();

		expect(trigger.getAttribute('aria-expanded')).toBe('true');
		expect(screen.getByRole('group', { name: '인스턴스 작업 옵션' })).toBeTruthy();
	});

	it('closes one menu with Escape and restores trigger focus', async () => {
		render(ActionMenuFixture);
		const trigger = await openMenu();

		await fireEvent.keyDown(document.activeElement as HTMLElement, { key: 'Escape' });

		expect(screen.queryByRole('group', { name: '인스턴스 작업 옵션' })).toBeNull();
		expect(document.activeElement).toBe(trigger);
	});

	it('does not bubble an action click into the resource row', async () => {
		render(ActionMenuFixture);
		await openMenu();

		await fireEvent.click(screen.getByRole('button', { name: '시작' }));

		expect(screen.getByTestId('action-count').textContent).toBe('1');
		expect(screen.getByTestId('row-count').textContent).toBe('0');
	});

	it('closes on an outside click without taking focus from the target', async () => {
		render(ActionMenuFixture);
		await openMenu();
		const outside = screen.getByRole('button', { name: '메뉴 밖' });

		outside.focus();
		await fireEvent.click(outside);

		expect(screen.queryByRole('group', { name: '인스턴스 작업 옵션' })).toBeNull();
		expect(document.activeElement).toBe(outside);
	});
});
