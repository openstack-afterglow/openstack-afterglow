import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { get } from 'svelte/store';

vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'job-uuid') });

vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		status: number;
		constructor(status: number, message: string) {
			super(message);
			this.status = status;
		}
	}
	return {
		api: {
			uploadWithProgress: vi.fn()
		},
		ApiError,
		getBaseUrl: () => ''
	};
});

type UploadResp = { success: boolean; name: string; bytes: number; etag: string };

type ApiClient = typeof import('$lib/api/client').api;

function mockedUpload(api: ApiClient) {
	return vi.mocked(api.uploadWithProgress);
}

function mockSuccess(api: ApiClient, payload: Partial<UploadResp> = {}) {
	const promise = Promise.resolve<UploadResp>({
		success: true,
		name: 'file.txt',
		bytes: 7,
		etag: 'abc',
		...payload
	});
	const abort = vi.fn();
	mockedUpload(api).mockReturnValue({ promise, abort });
	return { abort };
}

describe('uploadQueue', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.clearAllMocks();
		(crypto.randomUUID as Mock).mockReturnValue('job-uuid');
	});

	it('enqueue() 호출 시 job 이 uploading 상태로 추가됨', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		const file = new File(['hello!\n'], 'test.txt', { type: 'text/plain' });
		uploadQueue.enqueue(file, { containerName: 'my-bucket' });

		const jobs = get(uploadQueue);
		expect(jobs).toHaveLength(1);
		expect(jobs[0].status).toBe('uploading');
		expect(jobs[0].name).toBe('test.txt');
		expect(jobs[0].containerName).toBe('my-bucket');
	});

	it('백엔드 /upload 경로로 FormData 전송', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		const file = new File(['x'], 'report.csv', { type: 'text/csv' });
		uploadQueue.enqueue(file, {
			containerName: 'bucket',
			token: 'tok',
			projectId: 'p'
		});

		expect(api.uploadWithProgress).toHaveBeenCalledTimes(1);
		const args = mockedUpload(api).mock.calls[0];
		expect(args[0]).toBe('/api/v1/object-storage/bucket/upload');
		expect(args[1]).toBeInstanceOf(FormData);
		expect(typeof args[2]).toBe('function');
		expect(args[3]).toBe('tok');
		expect(args[4]).toBe('p');

		const fd = args[1] as FormData;
		const sent = fd.get('file');
		expect(sent).toBeInstanceOf(File);
		expect((sent as File).name).toBe('report.csv');
	});

	it('성공 응답 시 status=success, loaded=file.size, onComplete 호출', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		const onComplete = vi.fn();
		const file = new File(['hello!\n'], 'file.txt');
		uploadQueue.enqueue(file, { containerName: 'c', onComplete });
		await new Promise((r) => setTimeout(r, 5));

		const job = get(uploadQueue)[0];
		expect(job.status).toBe('success');
		expect(job.loaded).toBe(file.size);
		expect(onComplete).toHaveBeenCalledOnce();
		expect(onComplete.mock.calls[0][0].status).toBe('success');
	});

	it('500 응답 시 status=error', async () => {
		const { api, ApiError } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockedUpload(api).mockReturnValue({
			promise: Promise.reject(new ApiError(500, '서버 오류')),
			abort: vi.fn()
		});

		const file = new File(['x'], 'file.txt');
		uploadQueue.enqueue(file, { containerName: 'c' });
		await new Promise((r) => setTimeout(r, 5));

		const job = get(uploadQueue)[0];
		expect(job.status).toBe('error');
		expect(job.error).toBe('서버 오류');
	});

	it('cancel(id) 시 abort 호출 → status=canceled', async () => {
		const { api, ApiError } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');

		const abort = vi.fn();
		let rejectFn: ((e: unknown) => void) | null = null;
		const promise = new Promise<UploadResp>((_res, rej) => {
			rejectFn = rej;
		});
		mockedUpload(api).mockReturnValue({ promise, abort });

		const file = new File(['x'], 'file.txt');
		const id = uploadQueue.enqueue(file, { containerName: 'c' });

		uploadQueue.cancel(id);
		expect(abort).toHaveBeenCalledOnce();

		// abort 가 promise 를 ApiError(0) 로 reject 한 효과 모사
		rejectFn!(new ApiError(0, '업로드가 취소되었습니다'));
		await new Promise((r) => setTimeout(r, 5));

		expect(get(uploadQueue)[0].status).toBe('canceled');
	});

	it('remove(id) 로 큐에서 제거', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		const file = new File(['x'], 'file.txt');
		const id = uploadQueue.enqueue(file, { containerName: 'c' });
		expect(get(uploadQueue)).toHaveLength(1);
		uploadQueue.remove(id);
		expect(get(uploadQueue)).toHaveLength(0);
	});

	it('prefix 가 FormData 에 포함', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		const file = new File(['x'], 'notes.md');
		uploadQueue.enqueue(file, { containerName: 'bucket', prefix: 'docs/' });

		const fd = mockedUpload(api).mock.calls[0][1] as FormData;
		expect(fd.get('prefix')).toBe('docs/');
		// job.prefix 는 file.name 과 합쳐지지 않고 그대로 보존
		expect(get(uploadQueue)[0].prefix).toBe('docs/');
	});
});
