import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { auth, clearAuth, setAuth } from '$lib/stores/auth';

const { api, ApiError, getBaseUrl, mockController } = vi.hoisted(() => {
	let currentImage: { id: string; name: string } | null = { id: 'img-123', name: 'Ubuntu 22.04' };
	return {
		api: {
			get: vi.fn(),
			post: vi.fn(),
			put: vi.fn(),
			delete: vi.fn(),
			downloadBlob: vi.fn(),
		},
		ApiError: class ApiError extends Error {
			status?: number;
			constructor(message: string, status?: number) {
				super(message);
				this.name = 'ApiError';
				this.status = status;
			}
		},
		getBaseUrl: vi.fn(() => 'https://api.example.test'),
		mockController: {
			get image() {
				return currentImage;
			},
			set image(val: { id: string; name: string } | null) {
				currentImage = val;
			},
		},
	};
});

vi.mock('$lib/api/client', () => ({ api, ApiError, getBaseUrl }));
vi.mock('$lib/stores/imageDetailController.svelte', () => ({
	useImageDetailController: () => mockController,
}));


vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
const capabilityLeaves = {
	set(leaves: string[]) { (serviceCapabilities as Writable<(leaf: string) => boolean>).set(leaf => leaves.includes(leaf)); },
};
import ImageExportSection from '../ImageExportSection.svelte';

describe('ImageExportSection', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.clearAllMocks();
		clearAuth();
		setAuth({
			token: 'test-token',
			refreshToken: 'refresh-token',
			userId: 'user-1',
			username: 'test-user',
			projectId: 'proj-123',
			projectName: 'Project 123',
			accessExpiresAt: null,
			roles: [],
		});
		mockController.image = { id: 'img-123', name: 'Ubuntu 22.04' };
		api.get.mockResolvedValue([]);
		capabilityLeaves.set(['palimpsest-inventory_reader', 'palimpsest-publish_editor', 'palimpsest-download_user']);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	it('renders default qcow2 format selected and displays all six format options', async () => {
		render(ImageExportSection);

		const select = screen.getByLabelText(/디스크 포맷/) as HTMLSelectElement;
		expect(select).toBeTruthy();
		expect(select.value).toBe('qcow2');

		const options = Array.from(select.options).map((opt) => ({
			value: opt.value,
			label: opt.text,
		}));

		expect(options).toEqual([
			{ value: 'qcow2', label: 'QCOW2 (QEMU Image)' },
			{ value: 'raw', label: 'RAW (Raw Disk)' },
			{ value: 'vmdk', label: 'VMDK (VMware)' },
			{ value: 'vdi', label: 'VDI (VirtualBox)' },
			{ value: 'vhd', label: 'VHD (VPC)' },
			{ value: 'vhdx', label: 'VHDX (Hyper-V)' },
		]);

		expect(screen.queryByText(/VMX는 VM 설정 파일입니다/)).toBeNull();
	});

	it('displays VMX explanation help text when VMDK format is selected and hides it for other formats', async () => {
		render(ImageExportSection);

		const select = screen.getByLabelText(/디스크 포맷/);
		await fireEvent.change(select, { target: { value: 'vmdk' } });

		expect(
			screen.getByText('VMX는 VM 설정 파일입니다. VMware용 디스크 포맷은 VMDK를 선택하세요.')
		).toBeTruthy();

		await fireEvent.change(select, { target: { value: 'raw' } });
		expect(screen.queryByText(/VMX는 VM 설정 파일입니다/)).toBeNull();
	});

	it('sends exact POST body when initiating an export with default or selected format', async () => {
		api.post.mockResolvedValueOnce({
			id: 'job-1',
			source_image_id: 'img-123',
			target_disk_format: 'qcow2',
			status: 'queued',
			progress_pct: 0,
		});

		render(ImageExportSection);

		const exportBtn = screen.getByRole('button', { name: '내보내기' });
		await fireEvent.click(exportBtn);

		expect(api.post).toHaveBeenCalledWith(
			'/api/v1/palimpsest/hub/image-exports',
			{ image_id: 'img-123', disk_format: 'qcow2' },
			'test-token',
			'proj-123'
		);
	});

	it('sends updated format in POST body when a different format is selected before export', async () => {
		api.post.mockResolvedValueOnce({
			id: 'job-2',
			source_image_id: 'img-123',
			target_disk_format: 'vmdk',
			status: 'queued',
			progress_pct: 0,
		});

		render(ImageExportSection);

		const select = screen.getByLabelText(/디스크 포맷/);
		await fireEvent.change(select, { target: { value: 'vmdk' } });

		const exportBtn = screen.getByRole('button', { name: '내보내기' });
		await fireEvent.click(exportBtn);

		expect(api.post).toHaveBeenCalledWith(
			'/api/v1/palimpsest/hub/image-exports',
			{ image_id: 'img-123', disk_format: 'vmdk' },
			'test-token',
			'proj-123'
		);
	});

	it('polls nonterminal jobs and renders status, progress, and disables controls during processing', async () => {
		api.get.mockResolvedValueOnce([
			{
				id: 'job-1',
				source_image_id: 'img-123',
				target_disk_format: 'qcow2',
				status: 'downloading',
				progress_pct: 10,
			},
		]);

		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);

		expect(screen.getByText('다운로드 중')).toBeTruthy();
		expect(screen.getByText('10%')).toBeTruthy();

		const select = screen.getByLabelText(/디스크 포맷/) as HTMLSelectElement;
		expect(select.disabled).toBe(true);
		const btn = screen.getByRole('button', { name: '처리 중...' }) as HTMLButtonElement;
		expect(btn.disabled).toBe(true);

		api.get.mockResolvedValueOnce({
			id: 'job-1',
			source_image_id: 'img-123',
			target_disk_format: 'qcow2',
			status: 'converting',
			progress_pct: 50,
		});

		api.get.mockResolvedValueOnce({
			id: 'job-1',
			source_image_id: 'img-123',
			target_disk_format: 'qcow2',
			status: 'finalizing',
			progress_pct: 90,
		});

		await vi.advanceTimersByTimeAsync(2000);

		expect(api.get).toHaveBeenCalledWith(
			'/api/v1/palimpsest/hub/image-exports/job-1',
			'test-token',
			'proj-123',
			expect.objectContaining({ refresh: true })
		);
		expect(screen.getByText('변환 중')).toBeTruthy();
		expect(screen.getByText('50%')).toBeTruthy();

		await vi.advanceTimersByTimeAsync(2000);
		expect(screen.getByText('마무리 중')).toBeTruthy();
		expect(screen.getByText('90%')).toBeTruthy();
	});

	it('renders job error message in an Alert when job status is error', async () => {
		api.get.mockResolvedValueOnce([
			{
				id: 'job-1',
				source_image_id: 'img-123',
				target_disk_format: 'qcow2',
				status: 'error',
				progress_pct: 50,
				error_message: 'Glance image missing',
			},
		]);

		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);

		expect(screen.getByText('내보내기 오류')).toBeTruthy();
		expect(screen.getByText('Glance image missing')).toBeTruthy();
	});

	it('renders actionError in an Alert when export request or polling fails', async () => {
		api.post.mockRejectedValueOnce(new ApiError('용량 초과 오류'));

		render(ImageExportSection);

		const exportBtn = screen.getByRole('button', { name: '내보내기' });
		await fireEvent.click(exportBtn);

		expect(screen.getByText('용량 초과 오류')).toBeTruthy();
	});

	it('cancels polling and aborts request on component unmount', async () => {
		api.get.mockResolvedValueOnce([
			{
				id: 'job-1',
				source_image_id: 'img-123',
				target_disk_format: 'qcow2',
				status: 'queued',
				progress_pct: 0,
			},
		]);

		const { unmount } = render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);

		api.get.mockClear();

		unmount();

		await vi.advanceTimersByTimeAsync(4000);

		expect(api.get).not.toHaveBeenCalled();
	});

	it('cancels polling and ignores superseded job responses on image change', async () => {
		const { promise: job1PollingPromise, resolve: resolveJob1Polling } = Promise.withResolvers<unknown>();

		api.get
			.mockResolvedValueOnce([
				{
					id: 'job-1',
					source_image_id: 'img-123',
					target_disk_format: 'qcow2',
					status: 'downloading',
					progress_pct: 10,
				},
			])
			.mockReturnValueOnce(job1PollingPromise);

		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);

		await vi.advanceTimersByTimeAsync(2000);
		expect(api.get).toHaveBeenCalledWith(
			'/api/v1/palimpsest/hub/image-exports/job-1',
			'test-token',
			'proj-123',
			expect.objectContaining({ refresh: true })
		);

		// Mutate getter-backed image property and update reactive auth store to trigger $effect
		mockController.image = { id: 'img-456', name: 'Fedora 38' };
		api.get.mockResolvedValueOnce([]);
		auth.update((a) => ({ ...a }));

		await vi.advanceTimersByTimeAsync(0);

		expect(api.get).toHaveBeenCalledWith(
			'/api/v1/palimpsest/hub/image-exports?source_image_id=img-456&limit=1',
			'test-token',
			'proj-123',
			expect.objectContaining({ refresh: true })
		);

		// Resolve the late response from job-1 polling
		resolveJob1Polling({
			id: 'job-1',
			source_image_id: 'img-123',
			target_disk_format: 'qcow2',
			status: 'complete',
			progress_pct: 100,
		});

		await vi.advanceTimersByTimeAsync(0);

		// Verify job-1 response was ignored and download button / 100% from job-1 is NOT rendered
		expect(screen.queryByRole('button', { name: '다운로드' })).toBeNull();
		expect(screen.queryByText('100%')).toBeNull();
	});

	it('does not auto-download when export job reaches complete status', async () => {
		api.get.mockResolvedValueOnce([
			{
				id: 'job-1',
				source_image_id: 'img-123',
				target_disk_format: 'qcow2',
				status: 'complete',
				progress_pct: 100,
				download_path: '/api/v1/palimpsest/hub/image-exports/job-1/blob',
			},
		]);

		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);

		expect(screen.getByText('완료')).toBeTruthy();
		expect(screen.getByText('100%')).toBeTruthy();

		const downloadBtn = screen.getByRole('button', { name: '다운로드' });
		expect(downloadBtn).toBeTruthy();

		expect(api.post).not.toHaveBeenCalled();
		expect(api.downloadBlob).not.toHaveBeenCalled();
	});

	it('requests a ticket and clicks a temporary anchor on explicit download click without calling buffered blob helpers', async () => {
		api.get.mockResolvedValueOnce([
			{
				id: 'job-1',
				source_image_id: 'img-123',
				target_disk_format: 'qcow2',
				status: 'complete',
				progress_pct: 100,
				download_path: '/api/v1/palimpsest/hub/image-exports/job-1/blob',
			},
		]);

		api.post.mockResolvedValueOnce({
			url: '/api/v1/palimpsest/hub/image-exports/job-1/download?dl_token=ticket-xyz',
			expires_in: 60,
		});

		const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
		const appendChildSpy = vi.spyOn(document.body, 'appendChild');
		const removeSpy = vi.spyOn(HTMLAnchorElement.prototype, 'remove');

		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);

		const downloadBtn = screen.getByRole('button', { name: '다운로드' });
		await fireEvent.click(downloadBtn);

		expect(api.post).toHaveBeenCalledWith(
			'/api/v1/palimpsest/hub/image-exports/job-1/download-token',
			{},
			'test-token',
			'proj-123'
		);

		expect(appendChildSpy).toHaveBeenCalled();
		const createdAnchor = appendChildSpy.mock.calls.find(
			(call) => call[0] instanceof HTMLAnchorElement
		)?.[0] as HTMLAnchorElement;

		expect(createdAnchor).toBeTruthy();
		expect(createdAnchor.href).toBe(
			'https://api.example.test/api/v1/palimpsest/hub/image-exports/job-1/download?dl_token=ticket-xyz'
		);
		expect(createdAnchor.rel).toBe('noopener');
		expect(clickSpy).toHaveBeenCalled();
		expect(removeSpy).toHaveBeenCalled();
		expect(api.downloadBlob).not.toHaveBeenCalled();
	});

	it('renders actionError Alert when download token request fails', async () => {
		api.get.mockResolvedValueOnce([
			{
				id: 'job-1',
				source_image_id: 'img-123',
				target_disk_format: 'qcow2',
				status: 'complete',
				progress_pct: 100,
			},
		]);

		api.post.mockRejectedValueOnce(new ApiError('다운로드 토큰 발급에 실패했습니다.'));

		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);

		const downloadBtn = screen.getByRole('button', { name: '다운로드' });
		await fireEvent.click(downloadBtn);

		expect(screen.getByText('다운로드 토큰 발급에 실패했습니다.')).toBeTruthy();
	});

	it('keeps export and download denied while permissions are pending or failed', async () => {
		capabilityLeaves.set([]);
		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);
		expect((screen.getByRole('button', { name: '내보내기' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '내보내기' }));
		expect(api.get).not.toHaveBeenCalled();
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each([
		{ leaf: 'palimpsest-inventory_reader', exportAllowed: false, downloadAllowed: false },
		{ leaf: 'palimpsest-download_user', exportAllowed: false, downloadAllowed: true },
		{ leaf: 'palimpsest-publish_editor', exportAllowed: true, downloadAllowed: false },
		{ leaf: 'palimpsest-keys_admin', exportAllowed: false, downloadAllowed: false },
	])('separates export and content download for $leaf', async ({ leaf, exportAllowed, downloadAllowed }) => {
		capabilityLeaves.set(['palimpsest-inventory_reader', leaf]);
		api.get.mockResolvedValueOnce([{ id: 'job-1', source_image_id: 'img-123', target_disk_format: 'qcow2', status: 'complete', progress_pct: 100 }]);
		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);
		expect((screen.getByRole('button', { name: '내보내기' }) as HTMLButtonElement).disabled).toBe(!exportAllowed);
		expect((screen.getByRole('button', { name: '다운로드' }) as HTMLButtonElement).disabled).toBe(!downloadAllowed);
	});

	it('drops a pending download ticket after capability downgrade', async () => {
		api.get.mockResolvedValueOnce([{ id: 'job-1', source_image_id: 'img-123', target_disk_format: 'qcow2', status: 'complete', progress_pct: 100 }]);
		const pending = Promise.withResolvers<{ url: string; expires_in: number }>();
		api.post.mockReturnValueOnce(pending.promise);
		const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
		render(ImageExportSection);
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByRole('button', { name: '다운로드' }));
		capabilityLeaves.set(['palimpsest-inventory_reader']);
		await vi.advanceTimersByTimeAsync(0);
		pending.resolve({ url: '/ticket-must-not-open', expires_in: 60 });
		await vi.advanceTimersByTimeAsync(0);
		expect(click).not.toHaveBeenCalled();
		expect((screen.getByRole('button', { name: '다운로드' }) as HTMLButtonElement).disabled).toBe(true);
	});
});
