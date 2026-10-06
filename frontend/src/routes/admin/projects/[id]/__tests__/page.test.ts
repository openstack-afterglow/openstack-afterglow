import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$app/stores', () => ({ page: writable({ params: { id: 'project-1' }, data: {} }) }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'admin-project' }) }));

import Page from '../+page.svelte';

describe('project detail loading boundaries', () => {
	it('renders primary project data while members remain independently pending or failed', async () => {
		const project = Promise.withResolvers<Record<string, unknown>>();
		const members = Promise.withResolvers<unknown[]>();
		mockGet.mockImplementation((path: string) => path.endsWith('/members') ? members.promise : project.promise);

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		project.resolve({
			id: 'project-1',
			name: 'Project One',
			description: 'Primary content',
			enabled: true,
		});
		expect((await screen.findAllByText('Project One')).length).toBeGreaterThan(0);

		await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
		expect(screen.getByRole('status').textContent).toContain('멤버를 불러오는 중...');
		members.reject(new Error('members unavailable'));
		expect(await screen.findByText('멤버 조회 실패')).toBeTruthy();
		expect(screen.queryByText('멤버를 불러오는 중...')).toBeNull();
		expect(screen.getAllByText('Project One').length).toBeGreaterThan(0);
	});
});
