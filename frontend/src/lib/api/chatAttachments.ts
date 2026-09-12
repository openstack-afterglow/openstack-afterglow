/**
 * Scanned canonical chat assets. The API returns an opaque asset id; object keys
 * and signed URLs never cross the browser boundary.
 */
import { fetchWithAuth } from './client';

/** Backend asset metadata plus local upload state. */
export interface ChatAttachment {
	assetId?: string;
	mime: string;
	name: string;
	previewUrl?: string;
	status: 'uploading' | 'done' | 'error';
}

export interface AttachmentRef {
	id: string;
	mime_type: string;
	name: string;
}

const CHAT_IMAGE_MIME_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

export function isChatImageMime(mime: string): boolean {
	return CHAT_IMAGE_MIME_TYPES.has(mime);
}

export function isChatDocumentMime(mime: string): boolean {
	return mime === 'application/pdf';
}

/** Mark a successfully scanned upload as ready for a subsequent chat run. */
export function completeChatAttachment(item: ChatAttachment, ref: AttachmentRef): ChatAttachment {
	return {
		...item,
		assetId: ref.id,
		mime: ref.mime_type,
		name: ref.name,
		status: 'done'
	};
}

export function toInputParts(items: ChatAttachment[]) {
	return items
		.filter(
			(item): item is ChatAttachment & { assetId: string } =>
				item.status === 'done' &&
				Boolean(item.assetId) &&
				(isChatImageMime(item.mime) || isChatDocumentMime(item.mime))
		)
		.map((item) => ({
			type: isChatImageMime(item.mime) ? ('image' as const) : ('document' as const),
			asset_id: item.assetId
		}));
}

interface UploadOptions {
	token?: string;
	projectId?: string;
	signal?: AbortSignal;
}

interface DownloadOptions {
	token?: string;
	projectId?: string;
	signal?: AbortSignal;
}

/** Upload a supported image or PDF through the scanned asset pipeline. */
export async function uploadChatAttachment(
	file: File,
	{ token, projectId, signal }: UploadOptions = {}
): Promise<AttachmentRef> {
	const form = new FormData();
	form.append('file', file);

	const res = await fetchWithAuth('/api/v1/chat/assets', {
		method: 'POST',
		body: form,
		signal
	}, token, projectId);
	if (!res.ok) {
		let detail = res.statusText;
		try {
			const t = await res.text();
			if (t) detail = t;
		} catch {
			/* ignore */
		}
		throw new Error(detail || `첨부 업로드 실패 (${res.status})`);
	}

	const payload = (await res.json()) as AttachmentRef;
	return { id: payload.id, mime_type: payload.mime_type, name: payload.name };
}


/** Stream an owned asset through the authenticated same-origin BFF. */
export async function downloadChatAsset(
	assetId: string,
	{ token, projectId, signal }: DownloadOptions = {}
): Promise<Blob> {
	const res = await fetchWithAuth(
		`/api/v1/chat/assets/${encodeURIComponent(assetId)}/download`,
		{ signal },
		token,
		projectId
	);
	if (!res.ok) throw new Error(`파일 다운로드 실패 (${res.status})`);
	return res.blob();
}
