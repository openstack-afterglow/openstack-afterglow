import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { get } from 'svelte/store';

vi.stubGlobal('crypto', {
	randomUUID: vi.fn(() => 'job-uuid'),
	subtle: { digest: vi.fn(async () => new Uint8Array(32).fill(0xab).buffer) },
});

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

type UploadResp = { success: boolean; name: string; bytes: number; etag: string; sha256?: string };

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

	it('업로드 전에 브라우저 SHA-256 을 계산해 FormData 에 넣는다', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		uploadQueue.enqueue(new File(['abc'], 'a.txt'), { containerName: 'c' });
		await vi.waitFor(() => expect(api.uploadWithProgress).toHaveBeenCalled());

		const fd = mockedUpload(api).mock.calls[0][1] as FormData;
		expect(fd.get('sha256')).toBe('ab'.repeat(32));
	});

	it('상한을 넘는 파일은 브라우저 해시 없이 업로드한다', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue, CLIENT_HASH_MAX_BYTES } = await import('../uploadQueue');
		mockSuccess(api);

		const file = new File(['abc'], 'big.bin');
		Object.defineProperty(file, 'size', { value: CLIENT_HASH_MAX_BYTES + 1 });
		uploadQueue.enqueue(file, { containerName: 'c' });
		await vi.waitFor(() => expect(api.uploadWithProgress).toHaveBeenCalled());

		const fd = mockedUpload(api).mock.calls[0][1] as FormData;
		expect(fd.get('sha256')).toBeNull();
	});

	it('이미지 업로드는 오브젝트 체크섬을 보내지 않는다', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		uploadQueue.enqueue(new File(['abc'], 'disk.img'), { endpoint: '/api/v1/images', kind: 'image' });
		await vi.waitFor(() => expect(api.uploadWithProgress).toHaveBeenCalled());

		expect((mockedUpload(api).mock.calls[0][1] as FormData).get('sha256')).toBeNull();
	});

	it('해시 계산 실패는 업로드하지 않고 오류로 끝난다', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);
		vi.mocked(crypto.subtle.digest).mockRejectedValueOnce(new Error('no subtle'));

		uploadQueue.enqueue(new File(['abc'], 'a.txt'), { containerName: 'c' });
		await vi.waitFor(() => expect(get(uploadQueue)[0].status).toBe('error'));

		expect(get(uploadQueue)[0].error).toBe('무결성 해시 계산 실패');
		expect(api.uploadWithProgress).not.toHaveBeenCalled();
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

		await vi.waitFor(() => expect(api.uploadWithProgress).toHaveBeenCalledTimes(1));
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
		// 업로드는 해시 계산 뒤에 시작하므로, 호출 시점에 rejection 을 만들어야
		// 핸들러가 붙기 전 unhandled rejection 으로 새지 않는다.
		mockedUpload(api).mockImplementation(() => ({
			promise: Promise.reject(new ApiError(500, '서버 오류')),
			abort: vi.fn()
		}));

		const file = new File(['x'], 'file.txt');
		uploadQueue.enqueue(file, { containerName: 'c' });
		await vi.waitFor(() => expect(get(uploadQueue)[0].status).toBe('error'));

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
		await vi.waitFor(() => expect(api.uploadWithProgress).toHaveBeenCalled());

		uploadQueue.cancel(id);
		expect(abort).toHaveBeenCalledOnce();

		// abort 가 promise 를 ApiError(0) 로 reject 한 효과 모사
		rejectFn!(new ApiError(0, '업로드가 취소되었습니다'));
		await vi.waitFor(() => expect(get(uploadQueue)[0].status).toBe('canceled'));
	});

	it('해시 계산 중 취소하면 업로드를 시작하지 않는다', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		const id = uploadQueue.enqueue(new File(['x'], 'file.txt'), { containerName: 'c' });
		uploadQueue.cancel(id);
		await vi.waitFor(() => expect(get(uploadQueue)[0].status).toBe('canceled'));

		expect(api.uploadWithProgress).not.toHaveBeenCalled();
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
		await vi.waitFor(() => expect(api.uploadWithProgress).toHaveBeenCalled());
	});

	it('prefix 가 FormData 에 포함', async () => {
		const { api } = await import('$lib/api/client');
		const { uploadQueue } = await import('../uploadQueue');
		mockSuccess(api);

		const file = new File(['x'], 'notes.md');
		uploadQueue.enqueue(file, { containerName: 'bucket', prefix: 'docs/' });

		await vi.waitFor(() => expect(api.uploadWithProgress).toHaveBeenCalled());
		const fd = mockedUpload(api).mock.calls[0][1] as FormData;
		expect(fd.get('prefix')).toBe('docs/');
		// job.prefix 는 file.name 과 합쳐지지 않고 그대로 보존
		expect(get(uploadQueue)[0].prefix).toBe('docs/');
	});
});
