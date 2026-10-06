import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/svelte';

const { fetchWithAuth } = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));

vi.mock('$lib/api/client', () => ({ fetchWithAuth }));

import K3sRotateProgressModal from '../K3sRotateProgressModal.svelte';
import { t } from '$lib/i18n/ns/drover';

function sseResponse(events: object[], { disconnect = false } = {}) {
	const chunks = events.map((event) => new TextEncoder().encode(`data: ${JSON.stringify(event)}\n`));
	return {
		ok: true,
		status: 200,
		body: {
			getReader: () => ({
				read: async () => {
					const value = chunks.shift();
					if (value) return { value, done: false };
					if (disconnect) throw new Error('network reset');
					return { value: undefined, done: true };
				},
			}),
		},
	};
}

function stepStates() {
	return within(screen.getByRole('list')).getAllByRole('listitem').map((item) => item.getAttribute('data-state'));
}

describe('K3sRotateProgressModal', () => {
	it('marks the step the server was on when the rotation stream reports a failure', async () => {
		fetchWithAuth.mockResolvedValue(
			sseResponse([
				{ step: 'rotate_discover', progress: 10, message: '노드 3개 발견' },
				{ step: 'rotate_server', progress: 40, message: 'server-1 재시작' },
				{ step: 'failed', progress: 40, message: 'server-1 응답 없음', error: 'timeout' },
			]),
		);

		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose: vi.fn() });

		await waitFor(() => expect(stepStates()).toEqual(['done', 'failed', 'pending']));
		expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('40');
		expect(screen.queryByRole('status')).toBeNull();
	});

	it('keeps the reported steps and fails the current one when the stream drops mid-rotation', async () => {
		fetchWithAuth.mockResolvedValue(
			sseResponse(
				[
					{ step: 'rotate_discover', progress: 10, message: '노드 3개 발견' },
					{ step: 'rotate_server', progress: 50, message: 'server-2 재시작' },
				],
				{ disconnect: true },
			),
		);

		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose: vi.fn() });

		await waitFor(() => expect(stepStates()).toEqual(['done', 'failed', 'pending']));
		expect(screen.getByText('server-2 재시작')).toBeTruthy();
		expect(screen.getByText('network reset')).toBeTruthy();
		expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('50');
	});

	it('ends activity without claiming an outcome when the stream closes without a result', async () => {
		fetchWithAuth.mockResolvedValue(sseResponse([
			{ step: 'rotate_discover', progress: 10, message: '노드 3개 발견' },
			{ step: 'rotate_server', progress: 50, message: 'server-2 재시작' },
		]));
		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose: vi.fn() });

		await waitFor(() => expect(screen.getAllByRole<HTMLButtonElement>('button').every((button) => !button.disabled)).toBe(true));
		const statuses = screen.getAllByRole('status');
		expect(statuses).toHaveLength(1);
		expect(statuses[0].textContent).toContain(t('rotateProgress.unreported'));
		const states = screen.queryAllByRole('listitem').map((item) => item.getAttribute('data-state'));
		expect(states).not.toContain('failed');
		expect(states).not.toContain('active');
		expect(states).not.toContain('done');
		expect(screen.getByText('server-2 재시작')).toBeTruthy();
		const bar = screen.getByRole('progressbar');
		expect(bar.getAttribute('aria-valuenow')).toBe('50');
		expect(bar.getAttribute('aria-busy')).not.toBe('true');
		expect(['success', 'danger']).not.toContain(bar.getAttribute('data-tone'));
	});

	it('shows no step as started before the first progress report', () => {
		fetchWithAuth.mockReturnValue(Promise.withResolvers<never>().promise);

		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose: vi.fn() });

		expect(stepStates()).toEqual(['pending', 'pending', 'pending']);
		expect(screen.getByRole('progressbar').hasAttribute('aria-valuenow')).toBe(false);
		expect(screen.getAllByRole('status')).toHaveLength(1);
		expect(screen.getAllByRole<HTMLButtonElement>('button').filter((button) => button.disabled)).toHaveLength(1);
	});
});
