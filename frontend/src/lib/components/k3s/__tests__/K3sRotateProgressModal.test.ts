import { beforeEach, describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { t } from '$lib/i18n/ns/drover';

vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));

const { fetchWithAuth } = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));

vi.mock('$lib/api/client', () => ({ fetchWithAuth }));

import K3sRotateProgressModal from '../K3sRotateProgressModal.svelte';


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
	const list = screen.getByRole('list');
	const stages = [
		['rotate_discover', t('rotateProgress.steps.discover')],
		['rotate_server', t('rotateProgress.steps.server')],
		['rotate_verify', t('rotateProgress.steps.verify')],
	];
	expect(within(list).getAllByRole('listitem')).toHaveLength(stages.length);
	return Object.fromEntries(stages.map(([id, label]) => [
		id,
		within(list).getByText(label).closest('li')!.getAttribute('data-state'),
	]));
}

describe('K3sRotateProgressModal', () => {
	beforeEach(() => {
		fetchWithAuth.mockReset();
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'drover-clusters_admin');
	});
	it('does not start rotation for an editor even when mounted directly', () => {
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'drover-clusters_editor');
		const onclose = vi.fn();
		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose });
		expect(fetchWithAuth).not.toHaveBeenCalled();
		expect(onclose).toHaveBeenCalledOnce();
	});
	it('sends the destructive rotation POST once even when the token prop refreshes or grants go pending mid-stream', async () => {
		fetchWithAuth.mockReturnValue(Promise.withResolvers<never>().promise);
		const { rerender } = render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', token: 'token-a', projectId: 'p', onclose: vi.fn() });
		await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledOnce());
		expect(fetchWithAuth).toHaveBeenCalledWith('/api/v1/k3s/clusters/c-1/rotate-certs', { method: 'POST' }, 'token-a', 'p');
		await rerender({ clusterId: 'c-1', clusterName: 'demo', token: 'token-a2', projectId: 'p', onclose: vi.fn() });
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set(() => false);
		(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'drover-clusters_admin');
		await Promise.resolve();
		expect(fetchWithAuth).toHaveBeenCalledOnce();
	});
	it('marks the step the server was on when the rotation stream reports a failure', async () => {
		fetchWithAuth.mockResolvedValue(
			sseResponse([
				{ step: 'rotate_discover', progress: 10, message: '노드 3개 발견' },
				{ step: 'rotate_server', progress: 40, message: 'server-1 재시작' },
				{ step: 'failed', progress: 40, message: 'server-1 응답 없음', error: 'timeout' },
			]),
		);

		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose: vi.fn() });

		await waitFor(() => expect(stepStates()).toEqual({ rotate_discover: 'done', rotate_server: 'failed', rotate_verify: 'pending' }));
		const bar = screen.getByRole('progressbar');
		expect(bar.getAttribute('aria-valuenow')).toBe('40');
		expect(bar.getAttribute('data-tone')).toBe('danger');
		expect(bar.getAttribute('data-active')).toBeNull();
		expect(screen.getByText('server-1 응답 없음')).toBeTruthy();
		expect(screen.getByText('timeout')).toBeTruthy();
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

		await waitFor(() => expect(stepStates()).toEqual({ rotate_discover: 'done', rotate_server: 'failed', rotate_verify: 'pending' }));
		expect(screen.getByText('server-2 재시작')).toBeTruthy();
		expect(screen.getByText('network reset')).toBeTruthy();
		const bar = screen.getByRole('progressbar');
		expect(bar.getAttribute('aria-valuenow')).toBe('50');
		expect(bar.getAttribute('data-tone')).toBe('danger');
		expect(bar.getAttribute('data-active')).toBeNull();
		expect(screen.queryByRole('status')).toBeNull();
	});

	it('ends activity without claiming an outcome when the stream closes without a result', async () => {
		fetchWithAuth.mockResolvedValue(sseResponse([
			{ step: 'rotate_discover', progress: 10, message: '노드 3개 발견' },
			{ step: 'rotate_server', progress: 50, message: 'server-2 재시작' },
		]));
		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose: vi.fn() });

		await waitFor(() => expect(screen.getByRole('progressbar').getAttribute('data-tone')).toBe('neutral'));
		expect(screen.getByRole('status')).toBeTruthy();
		expect(screen.queryByRole('list')).toBeNull();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.getByText('server-2 재시작')).toBeTruthy();
		const bar = screen.getByRole('progressbar');
		expect(bar.getAttribute('aria-valuenow')).toBe('50');
		expect(bar.getAttribute('data-active')).toBeNull();
		const close = screen.getAllByRole('button', { name: t('rotateProgress.close') })
			.find((button) => button.textContent?.trim()) as HTMLButtonElement;
		expect(close.disabled).toBe(false);
	});

	it('marks every rotation stage done only after a completed event and releases the close action', async () => {
		fetchWithAuth.mockResolvedValue(sseResponse([
			{ step: 'rotate_discover', progress: 10, message: 'discovered nodes' },
			{ step: 'rotate_verify', progress: 90, message: 'verifying nodes' },
			{ step: 'completed', progress: 100, message: 'rotation complete' },
		]));
		const onclose = vi.fn();
		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose });
		await waitFor(() => expect(stepStates()).toEqual({ rotate_discover: 'done', rotate_server: 'done', rotate_verify: 'done' }));
		const bar = screen.getByRole('progressbar');
		expect(bar.getAttribute('aria-valuenow')).toBe('100');
		expect(bar.getAttribute('data-tone')).toBe('success');
		expect(bar.getAttribute('data-active')).toBeNull();
		expect(screen.queryByRole('status')).toBeNull();
		const close = screen.getAllByRole('button', { name: t('rotateProgress.close') })
			.find((button) => button.textContent?.trim()) as HTMLButtonElement;
		expect(close.disabled).toBe(false);
		await fireEvent.click(close);
		expect(onclose).toHaveBeenCalledOnce();
	});

	it('shows no step as started before the first progress report', () => {
		fetchWithAuth.mockReturnValue(Promise.withResolvers<never>().promise);

		render(K3sRotateProgressModal, { clusterId: 'c-1', clusterName: 'demo', onclose: vi.fn() });

		expect(stepStates()).toEqual({ rotate_discover: 'pending', rotate_server: 'pending', rotate_verify: 'pending' });
		const bar = screen.getByRole('progressbar');
		expect(bar.hasAttribute('aria-valuenow')).toBe(false);
		expect(bar.getAttribute('data-active')).toBe('true');
		expect(screen.getByRole('status')).toBeTruthy();
		expect((screen.getByRole('button', { name: t('rotateProgress.running') }) as HTMLButtonElement).disabled).toBe(true);
	});
});
