import { get, writable } from 'svelte/store';
import { ApiError, api } from '$lib/api/client';

export type UploadKind = 'object' | 'image';

export interface UploadJob {
	id: string;
	name: string;
	kind: UploadKind;
	containerName: string;
	prefix: string;
	status: 'uploading' | 'success' | 'error' | 'canceled';
	loaded: number;
	total: number;
	startTime: number;
	error?: string;
	sha256?: string;
	abort?: () => void;
	onComplete?: (job: UploadJob) => void;
}

/** 브라우저 SHA-256 계산 상한. 초과분은 서버가 저장 바이트로만 무결성을 검증한다. */
export const CLIENT_HASH_MAX_BYTES = 256 * 1024 * 1024;

interface UploadResponse {
	success: boolean;
	name: string;
	bytes: number;
	etag: string;
	content_type?: string;
	sha256?: string;
	detected_content_type?: string;
}

/** Blob.arrayBuffer 가 없는 런타임(구형 Safari, jsdom)에서도 바이트를 읽는다. */
function fileBytes(file: File): Promise<ArrayBuffer> {
	if (typeof file.arrayBuffer === 'function') return file.arrayBuffer();
	const { promise, resolve, reject } = Promise.withResolvers<ArrayBuffer>();
	const reader = new FileReader();
	reader.onload = () => resolve(reader.result as ArrayBuffer);
	reader.onerror = () => reject(reader.error ?? new Error('파일을 읽지 못했습니다'));
	reader.readAsArrayBuffer(file);
	return promise;
}

async function sha256Hex(file: File): Promise<string> {
	const digest = await crypto.subtle.digest('SHA-256', await fileBytes(file));
	return Array.from(new Uint8Array(digest))
		.map((b) => b.toString(16).padStart(2, '0'))
		.join('');
}

const jobs = writable<UploadJob[]>([]);

function enqueue(
	file: File,
	params: {
		/** object-storage 업로드 시 사용. image 업로드 시에는 endpoint를 직접 지정. */
		containerName?: string;
		prefix?: string;
		/** image 업로드 시 '/api/v1/images' 등 엔드포인트를 직접 지정. */
		endpoint?: string;
		/** 추가 FormData 필드 (이미지 name, disk_format 등). */
		extraFields?: Record<string, string>;
		kind?: UploadKind;
		token?: string;
		projectId?: string;
		onComplete?: (job: UploadJob) => void;
	}
): string {
	const id = crypto.randomUUID();
	const kind: UploadKind = params.kind ?? 'object';

	const job: UploadJob = {
		id,
		name: file.name,
		kind,
		containerName: params.containerName ?? '',
		prefix: params.prefix ?? '',
		status: 'uploading',
		loaded: 0,
		total: file.size,
		startTime: Date.now(),
		onComplete: params.onComplete
	};
	jobs.update((arr) => [...arr, job]);

	const formData = new FormData();
	formData.append('file', file, file.name);

	let uploadUrl: string;
	if (params.endpoint) {
		uploadUrl = params.endpoint;
		if (params.extraFields) {
			for (const [k, v] of Object.entries(params.extraFields)) {
				formData.append(k, v);
			}
		}
	} else {
		uploadUrl = `/api/v1/object-storage/${encodeURIComponent(params.containerName ?? '')}/upload`;
		if (params.prefix) formData.append('prefix', params.prefix);
	}

	let canceledBeforeStart = false;
	_patch(id, { abort: () => { canceledBeforeStart = true; } });

	void (async () => {
		if (kind === 'object' && file.size <= CLIENT_HASH_MAX_BYTES && globalThis.crypto?.subtle) {
			try {
				formData.append('sha256', await sha256Hex(file));
			} catch {
				throw new Error('무결성 해시 계산 실패');
			}
		}
		if (canceledBeforeStart) throw new DOMException('aborted', 'AbortError');

		const { promise, abort } = api.uploadWithProgress<UploadResponse>(
			uploadUrl,
			formData,
			(e) => _patch(id, { loaded: e.loaded }),
			params.token,
			params.projectId
		);
		_patch(id, { abort });
		return promise;
	})()
		.then((res) => _patch(id, { loaded: file.size, status: 'success', sha256: res?.sha256 }, true))
		.catch((e: unknown) => {
			// DOMException 은 환경에 따라 Error 를 상속하지 않으므로 name/message 로 판정한다.
			const named = typeof e === 'object' && e !== null ? e : {};
			const name = 'name' in named && typeof named.name === 'string' ? named.name : '';
			const message = 'message' in named && typeof named.message === 'string' ? named.message : '';
			const isCancel = (e instanceof ApiError && e.status === 0) || name === 'AbortError';
			_patch(id, { status: isCancel ? 'canceled' : 'error', error: message || '업로드 실패' }, true);
		});

	return id;
}

function _patch(id: string, patch: Partial<UploadJob>, terminal = false) {
	jobs.update((arr) => arr.map((j) => (j.id === id ? { ...j, ...patch } : j)));
	if (terminal) {
		const j = get(jobs).find((x) => x.id === id);
		j?.onComplete?.(j);
	}
}

function cancel(id: string) {
	const j = get(jobs).find((x) => x.id === id);
	j?.abort?.();
}

function remove(id: string) {
	jobs.update((arr) => arr.filter((j) => j.id !== id));
}

export const uploadQueue = { subscribe: jobs.subscribe, enqueue, cancel, remove };
