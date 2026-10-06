import { fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UploadJob } from '$lib/stores/uploadQueue';

const actions = vi.hoisted(() => ({ cancel: vi.fn(), remove: vi.fn() }));
const jobs = writable<UploadJob[]>([]);
vi.mock('$lib/stores/uploadQueue', () => ({
	uploadQueue: { subscribe: (run: (jobs: UploadJob[]) => void) => jobs.subscribe(run), ...actions }
}));
import UploadDock from '$lib/components/UploadDock.svelte';

const job: UploadJob = {
	id: 'upload-1', name: 'report.csv', kind: 'object', containerName: 'bucket', prefix: '',
	status: 'uploading', loaded: 0, total: 100, startTime: Date.now()
};

beforeEach(() => {
	jobs.set([{ ...job }]);
	vi.clearAllMocks();
});

describe('UploadDock transfer state', () => {
	it('is indeterminate before bytes move and stops active motion on each terminal outcome', async () => {
		render(UploadDock);
		await tick();
		const track = screen.getByRole('progressbar', { name: 'report.csv 업로드 진행률' });
		expect(track.getAttribute('aria-valuenow')).toBeNull();
		expect(track.getAttribute('aria-valuetext')).toBe('업로드 준비 중');
		expect(screen.getByText('1개 업로드 중')).toBeTruthy();

		jobs.set([{ ...job, loaded: 40 }]);
		await tick();
		expect(track.getAttribute('aria-valuenow')).toBe('40');
		expect(track.getAttribute('data-active')).toBe('true');

		for (const [status, tone, label] of [['success', 'success', '완료'], ['error', 'danger', '오류'], ['canceled', 'neutral', '취소됨']] as const) {
			jobs.set([{ ...job, loaded: 40, status }]);
			await tick();
			expect(track.getAttribute('data-active')).toBeNull();
			expect(track.getAttribute('data-tone')).toBe(tone);
			expect(track.getAttribute('aria-valuetext')).toBe(label);
			expect(screen.queryByText('1개 업로드 중')).toBeNull();
		}
	});

	it('preserves job rows while collapsed and retains cancel/remove actions and unload protection', async () => {
		render(UploadDock);
		await tick();
		const track = screen.getByRole('progressbar');
		const header = screen.getByRole('button', { name: /1개 업로드 중/ });
		await fireEvent.click(header);
		expect(header.getAttribute('aria-expanded')).toBe('false');
		await fireEvent.click(header);
		expect(screen.getByRole('progressbar')).toBe(track);
		await fireEvent.click(screen.getByRole('button', { name: 'report.csv 업로드 취소' }));
		expect(actions.cancel).toHaveBeenCalledWith('upload-1');
		const unloading = new Event('beforeunload', { cancelable: true });
		window.dispatchEvent(unloading);
		expect(unloading.defaultPrevented).toBe(true);
		jobs.set([{ ...job, status: 'success', loaded: 100 }]);
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: 'report.csv 업로드 결과 닫기' }));
		expect(actions.remove).toHaveBeenCalledWith('upload-1');
		const completedUnload = new Event('beforeunload', { cancelable: true });
		window.dispatchEvent(completedUnload);
		expect(completedUnload.defaultPrevented).toBe(false);
	});
});
