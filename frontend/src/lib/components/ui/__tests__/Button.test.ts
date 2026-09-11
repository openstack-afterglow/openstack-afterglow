import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import Button from '../Button.svelte';

const textSnippet = (text: string) => createRawSnippet(() => ({ render: () => text }));

describe('Button', () => {
	it('renders a native button by default', () => {
		render(Button, { children: textSnippet('Save') });
		expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy();
	});

	it('renders an anchor when href is supplied', () => {
		render(Button, { href: '/x', children: textSnippet('Open') });
		const link = screen.getByRole('link', { name: 'Open' });
		expect(link.getAttribute('href')).toBe('/x');
	});

	it('removes navigation and focus from disabled links', async () => {
		const onclick = vi.fn();
		const { container } = render(Button, { href: '/x', disabled: true, onclick, children: textSnippet('Unavailable') });
		const link = container.querySelector('a') as HTMLAnchorElement;
		expect(link.getAttribute('href')).toBeNull();
		expect(link.getAttribute('aria-disabled')).toBe('true');
		expect(link.tabIndex).toBe(-1);
		await fireEvent.click(link);
		expect(onclick).not.toHaveBeenCalled();
	});

	it('forwards stable tutorial hooks', () => {
		render(Button, { dataTour: 'create-vm', children: textSnippet('Create') });
		expect(screen.getByRole('button', { name: 'Create' }).getAttribute('data-tour')).toBe('create-vm');
	});

	it('applies the accent variant class', () => {
		render(Button, { variant: 'accent', children: textSnippet('Run') });
		expect(screen.getByRole('button', { name: 'Run' }).classList.contains('btn-accent')).toBe(true);
	});

	it('applies the xs size class', () => {
		render(Button, { size: 'xs', children: textSnippet('Tiny') });
		expect(screen.getByRole('button', { name: 'Tiny' }).classList.contains('btn-xs')).toBe(true);
	});

	it('disables native buttons', () => {
		render(Button, { disabled: true, children: textSnippet('Disabled') });
		expect((screen.getByRole('button', { name: 'Disabled' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('calls onclick once for enabled click', async () => {
		const onclick = vi.fn();
		render(Button, { onclick, children: textSnippet('Click') });
		await fireEvent.click(screen.getByRole('button', { name: 'Click' }));
		expect(onclick).toHaveBeenCalledTimes(1);
	});

	it('emits intent on pointer entry without firing click', async () => {
		const onintent = vi.fn();
		const onclick = vi.fn();
		render(Button, { onintent, onclick, children: textSnippet('Warm') });
		await fireEvent.pointerEnter(screen.getByRole('button', { name: 'Warm' }));
		expect(onintent).toHaveBeenCalledOnce();
		expect(onclick).not.toHaveBeenCalled();
	});

	it('emits intent on keyboard focus and ignores disabled controls', async () => {
		const onintent = vi.fn();
		const { rerender } = render(Button, { onintent, children: textSnippet('Focus') });
		await fireEvent.focus(screen.getByRole('button', { name: 'Focus' }));
		expect(onintent).toHaveBeenCalledOnce();

		await rerender({ onintent, disabled: true, children: textSnippet('Focus') });
		await fireEvent.pointerEnter(screen.getByRole('button', { name: 'Focus' }));
		expect(onintent).toHaveBeenCalledOnce();
	});
});
