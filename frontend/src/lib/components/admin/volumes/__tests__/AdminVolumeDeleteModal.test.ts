import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ remove: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { delete: mocks.remove }, ApiError: class extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));

import AdminVolumeDeleteModal from '../AdminVolumeDeleteModal.svelte';

const volume = {
	id: '7ad67d9a-2050-4a9b-ab1f-89b56c5dafc8', name: 'unfinished-image', status: 'creating',
	size: 10, project_id: 'project', created_at: '2026-11-15T00:00:00Z',
};

beforeEach(() => {
	mocks.remove.mockReset().mockRejectedValue(new Error('native deletion refused'));
});

describe('administrator volume creation-stage delete guidance', () => {
	it.each(['creating', 'downloading'])('opens detail diagnostics after native %s delete refusal without force deletion', async (status) => {
		const onClose = vi.fn();
		const onSuccess = vi.fn();
		const onDiagnose = vi.fn();
		render(AdminVolumeDeleteModal, { volume: { ...volume, status }, onClose, onSuccess, onDiagnose });
		expect(screen.queryByRole('button', { name: '상세 진단 열기' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '삭제' }));
		await fireEvent.click(await screen.findByRole('button', { name: '상세 진단 열기' }));
		expect(mocks.remove).toHaveBeenCalledExactlyOnceWith(`/api/v1/admin/volumes/${volume.id}`, 'token', 'project');
		expect(onDiagnose).toHaveBeenCalledExactlyOnceWith(volume.id);
		expect(onClose).toHaveBeenCalledOnce();
		expect(onSuccess).not.toHaveBeenCalled();
	});

	it('preserves ordinary deletion failure without creation-stage guidance', async () => {
		render(AdminVolumeDeleteModal, { volume: { ...volume, status: 'available' }, onClose: vi.fn(), onSuccess: vi.fn(), onDiagnose: vi.fn() });
		await fireEvent.click(screen.getByRole('button', { name: '삭제' }));
		await screen.findByText('삭제 실패');
		expect(screen.queryByRole('button', { name: '상세 진단 열기' })).toBeNull();
	});
});
