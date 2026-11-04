import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
const mocks = vi.hoisted(() => ({ entries: [] as unknown[], dismiss: vi.fn(), refresh: vi.fn(), mount: vi.fn(() => () => {}) }));
vi.mock('$lib/stores/k3sOperations.svelte', () => ({ k3sOperations: mocks }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'synthetic', userId: 'user', projectId: 'project', sessionId: 'login' }), authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false) }));
vi.mock('$lib/stores/k3sPermissions', () => ({ k3sPermissions: writable({ inventory: true }) }));
import { createK3sProgress, type K3sProgressController } from '$lib/stores/k3sProgress.svelte';
import K3sOperationDock from '../K3sOperationDock.svelte';
let progress: K3sProgressController;
beforeEach(() => {
	vi.clearAllMocks();
	progress = createK3sProgress(); progress.begin('create'); progress.visible = false;
	mocks.entries = [{ id: 'entry', name: 'Cluster', progress }];
});
afterEach(() => { progress.end(); cleanup(); });
describe('persistent Drover background operation', () => {
	it('minimizes and restores its content without a close action until genuine terminal status', async () => {
		render(K3sOperationDock);
		expect(screen.queryByRole('button', { name: '닫기' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '최소화' }));
		expect(screen.queryByRole('progressbar')).toBeNull();
		expect(mocks.dismiss).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '펼치기' }));
		expect(screen.getByRole('progressbar')).toBeTruthy();
		progress.apply({ step: 'completed', progress: 100, message: '완료' });
		await fireEvent.click(await screen.findByRole('button', { name: '닫기' }));
		expect(mocks.dismiss).toHaveBeenCalledWith('entry');
	});
	it('reopens details and Escape minimizes rather than dismisses the operation', async () => {
		render(K3sOperationDock);
		await fireEvent.click(screen.getByRole('button', { name: '상세' }));
		const dialog = screen.getByRole('dialog');
		expect(dialog).toBeTruthy();
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.getByRole('region', { name: '백그라운드 작업' })).toBeTruthy();
		expect(mocks.dismiss).not.toHaveBeenCalled();
	});
	it('keeps unknown transport outcomes pending and exposes a GET-only recheck action', async () => {
		progress.disconnect('network lost');
		render(K3sOperationDock);
		expect(screen.queryByRole('button', { name: '닫기' })).toBeNull();
		expect(screen.getByRole('status').textContent).toContain('완료 또는 실패는 아직 확인되지 않았습니다');
		await fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }));
		expect(mocks.refresh).toHaveBeenCalledOnce();
	});

	it.each(['completed', 'failed'] as const)('announces %s without expanding a minimized operation', async step => {
		progress.apply({ step: 'waiting_callback', progress: 10, message: 'callback pending' });
		render(K3sOperationDock);
		await fireEvent.click(screen.getByRole('button', { name: '최소화' }));
		const status = screen.getByRole('status');
		expect(status.textContent).toContain('k3s 초기화');
		expect(status.getAttribute('aria-live')).toBe('polite');
		expect(status.getAttribute('aria-atomic')).toBe('true');
		progress.apply({ step, progress: step === 'completed' ? 100 : 10, message: step, ...(step === 'failed' ? { error: 'native failure details' } : {}) });
		expect(await screen.findByText(step === 'completed' ? '완료' : '실패', { selector: '[role="status"]' })).toBe(status);
		expect(screen.queryByRole('progressbar')).toBeNull();
		expect(screen.getByRole('button', { name: '펼치기' })).toBeTruthy();
		expect(mocks.dismiss).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '펼치기' }));
		expect(screen.getByRole('button', { name: '닫기' })).toBeTruthy();
		if (step === 'failed') expect(screen.getByRole('status').textContent).toContain('native failure details');
	});
});

it('uses normal stack flow while preserving the non-dismissible pending operation', () => {
	render(K3sOperationDock, { inline: true });
	const region = screen.getByRole('region', { name: '백그라운드 작업' });
	expect(region.classList.contains('fixed')).toBe(false);
	expect(region.classList.contains('relative')).toBe(true);
	expect(screen.queryByRole('button', { name: '닫기' })).toBeNull();
});
