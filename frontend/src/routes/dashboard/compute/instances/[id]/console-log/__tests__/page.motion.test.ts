import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$app/stores', () => ({ page: writable({ params: { id: 'instance-a' } }) }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project-a' }) }));
vi.mock('$lib/api/client', () => ({ api: { get }, ApiError: class ApiError extends Error {} }));
import Page from '../+page.svelte';

describe('standalone console log feedback', () => {
	it('keeps the previous log mounted while a real refresh is pending', async () => {
		get.mockResolvedValueOnce({ output: 'boot completed' });
		const { container } = render(Page);
		await screen.findByText('boot completed');
		const log = container.querySelector('pre');
		let resolve!: (value: { output: string }) => void;
		get.mockReturnValueOnce(new Promise<{ output: string }>((done) => { resolve = done; }));
		await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
		expect(screen.getByRole('status').textContent?.trim()).toBe('로딩...');
		expect(screen.getByRole('button', { name: '새로고침' }).hasAttribute('disabled')).toBe(true);
		expect(container.querySelector('pre')).toBe(log);
		resolve({ output: 'new log line' });
		await screen.findByText('new log line');
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect(container.querySelector('pre')).toBe(log);
	});
});
