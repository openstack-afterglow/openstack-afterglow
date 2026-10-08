import { t } from '$lib/i18n/ns/chat-diagnostics';
import { fetchWithAuth } from './client';
import { get } from 'svelte/store';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { requireLumenCapability } from './lumenAccess';
import { chatRequestPermission, permissionReason } from './lumenPermissions';
import { ApiError } from './errors';
import { parseChatRunEvent, parseContextState, type ChatRunDescriptor, type ChatRunEvent, type ChatRunStatus, type ContextState } from './chatContracts';
export type { ChatRunDescriptor, ContextState } from './chatContracts';

export class ChatProtocolError extends Error {
	readonly status?: number;

	constructor(message: string, status?: number) {
		super(message);
		this.name = 'ChatProtocolError';
		this.status = status;
	}
}

/** A non-2xx HTTP response from the chat API, with its status preserved. */
export class ChatHttpError extends ChatProtocolError {
	readonly status: number;

	constructor(message: string, status: number) {
		super(message, status);
		this.name = 'ChatHttpError';
		this.status = status;
	}
}

export class ChatRunReloadRequiredError extends ChatProtocolError {
	constructor() {
		super(t('run.reloadRequired'));
		this.name = 'ChatRunReloadRequiredError';
	}
}

export interface CreateChatRunOptions {
	token?: string;
	projectId?: string;
	signal?: AbortSignal;
	idempotencyKey?: string;
}

export interface PreviewChatContextOptions {
	token?: string;
	projectId?: string;
	signal?: AbortSignal;
}

export interface FollowChatRunOptions {
	token?: string;
	projectId?: string;
	afterSeq?: number;
	signal?: AbortSignal;
}

type SseFrame = { id?: string; event?: string; data: string };
const RUN_STATUSES = [
	'queued',
	'running',
	'awaiting_approval',
	'awaiting_input',
	'waiting_children',
	'finalizing',
	'completed',
	'failed',
	'canceled'
] as const satisfies readonly ChatRunStatus[];

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === 'object';
}

function isRunStatus(value: unknown): value is ChatRunStatus {
	return typeof value === 'string' && RUN_STATUSES.some((status) => status === value);
}

function delay(milliseconds: number): Promise<void> {
	const { promise, resolve } = Promise.withResolvers<void>();
	setTimeout(resolve, milliseconds);
	return promise;
}


function headers(): HeadersInit {
	return { Accept: 'text/event-stream' };
}

function normalizeDescriptorUrl(url: unknown): string {
	if (typeof url !== 'string' || !url.startsWith('/') || url.startsWith('//')) {
		throw new ChatProtocolError(t('protocol.invalidDescriptor'));
	}
	if (url.startsWith('/v1/')) {
		return `/api/v1/chat${url.slice(3)}`;
	}
	if (url.startsWith('/api/v1/chat/')) {
		return url;
	}
	throw new ChatProtocolError(t('protocol.invalidDescriptor'));
}

export function parseChatRunDescriptor(value: unknown): ChatRunDescriptor {
	if (!isRecord(value)) throw new ChatProtocolError(t('protocol.invalidDescriptor'));
	const expectedKeys = ['run_id', 'conversation_id', 'temp_thread_id', 'status', 'run_kind', 'events_url', 'cancel_url'].sort();
	const actualKeys = Object.keys(value).sort();
	if (actualKeys.length !== expectedKeys.length || actualKeys.some((key, index) => key !== expectedKeys[index])) {
		throw new ChatProtocolError(t('protocol.invalidDescriptor'));
	}
	if (
		typeof value.run_id !== 'string' ||
		value.run_id.length === 0 ||
		(typeof value.conversation_id !== 'string' && value.conversation_id !== null) ||
		(typeof value.temp_thread_id !== 'string' && value.temp_thread_id !== null) ||
		!isRunStatus(value.status) ||
		(value.run_kind !== 'completion' && value.run_kind !== 'compaction')
	) {
		throw new ChatProtocolError(t('protocol.invalidDescriptor'));
	}
	const eventsUrl = normalizeDescriptorUrl(value.events_url);
	const cancelUrl = normalizeDescriptorUrl(value.cancel_url);
	return {
		run_id: value.run_id,
		conversation_id: value.conversation_id,
		temp_thread_id: value.temp_thread_id,
		status: value.status,
		run_kind: value.run_kind,
		events_url: eventsUrl,
		cancel_url: cancelUrl
	};
}

/** Localize fallbacks when constructing errors; keep server detail bounds and formatting unchanged. */
async function errorFrom(response: Response): Promise<ChatHttpError> {
	const maxBodyBytes = 4096;
	let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
	try {
		reader = response.body?.getReader();
	} catch {
		return new ChatHttpError(t('http.requestFailed'), response.status);
	}
	if (!reader) return new ChatHttpError(t('http.requestFailed'), response.status);
	let size = 0;
	const chunks: Uint8Array[] = [];
	try {
		while (true) {
			const { value, done } = await reader.read();
			if (done) break;
			size += value.byteLength;
			if (size > maxBodyBytes) return new ChatHttpError(t('http.requestFailed'), response.status);
			chunks.push(value);
		}
		const bytes = new Uint8Array(size);
		let offset = 0;
		for (const chunk of chunks) {
			bytes.set(chunk, offset);
			offset += chunk.byteLength;
		}
		const body: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
		if (isRecord(body)) {
			let detail: string | undefined;
			if (typeof body.detail === 'string') {
				detail = body.detail.trim();
			} else if (Array.isArray(body.detail) && body.detail.length > 0 && body.detail.length <= 3) {
				const messages: string[] = [];
				for (const item of body.detail) {
					if (!isRecord(item) || typeof item.msg !== 'string' || item.msg.length > 150) break;
					const location = Array.isArray(item.loc) && item.loc.length <= 4 &&
						item.loc.every((part: unknown) =>
							(typeof part === 'string' && /^[\w-]{1,40}$/.test(part)) ||
							(Number.isInteger(part) && (part as number) >= 0))
						? `${item.loc.join('.')}: ` : '';
					messages.push(`${location}${item.msg}`);
				}
				if (messages.length === body.detail.length) detail = messages.join('; ').trim();
			}
			if (detail && detail.length <= 300 && !/[\x00-\x1f\x7f]/.test(detail)) {
				return new ChatHttpError(detail, response.status);
			}
		}
	} catch {
		// Malformed, non-JSON, and unreadable responses reveal only the HTTP status.
	} finally {
		void reader.cancel().catch(() => {});
	}
	return new ChatHttpError(t('http.requestFailed'), response.status);
}

/** Creates exactly one durable run. The key remains stable for a caller retry. */
export async function createChatRun(
	path: string,
	body: unknown,
	{ token, projectId, signal, idempotencyKey = crypto.randomUUID() }: CreateChatRunOptions = {}
): Promise<ChatRunDescriptor> {
	requireLumenCapability('lumen-chat_user', token, projectId);
	const denied = chatRequestPermission(body, get(serviceCapabilities));
	if (denied) throw new ApiError(403, permissionReason(denied));
	const response = await fetchWithAuth(path, {
		method: 'POST',
		headers: {
			...headers(),
			'Content-Type': 'application/json',
			'Idempotency-Key': idempotencyKey
		},
		body: JSON.stringify(body),
		signal
	}, token, projectId);
	if (response.status !== 202) throw await errorFrom(response);
	return parseChatRunDescriptor(await response.json());
}

export async function previewChatContext(
	path: string,
	body: unknown,
	{ token, projectId, signal }: PreviewChatContextOptions = {}
): Promise<ContextState> {
	const response = await fetchWithAuth(path, {
		method: 'POST',
		headers: {
			...headers(),
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(body),
		signal
	}, token, projectId);
	if (!response.ok) throw await errorFrom(response);
	return parseContextState(await response.json());
}

function takeFrames(buffer: string): { frames: SseFrame[]; rest: string } {
	const frames: SseFrame[] = [];
	let boundary: number;
	while ((boundary = buffer.search(/\r?\n\r?\n/)) >= 0) {
		const raw = buffer.slice(0, boundary);
		const separatorLength = buffer[boundary] === '\r' ? (buffer[boundary + 1] === '\n' && buffer[boundary + 2] === '\r' ? 4 : 2) : 2;
		buffer = buffer.slice(boundary + separatorLength);
		let id: string | undefined;
		let event: string | undefined;
		const data: string[] = [];
		for (const line of raw.split(/\r?\n/)) {
			if (!line || line.startsWith(':')) continue;
			const colon = line.indexOf(':');
			const field = colon < 0 ? line : line.slice(0, colon);
			const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
			if (field === 'id') id = value;
			else if (field === 'event') event = value;
			else if (field === 'data') data.push(value);
		}
		if (data.length) frames.push({ id, event, data: data.join('\n') });
	}
	return { frames, rest: buffer };
}

async function* decodeFrames(body: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame> {
	const reader = body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			const parsed = takeFrames(buffer);
			buffer = parsed.rest;
			yield* parsed.frames;
		}
		buffer += decoder.decode();
		const parsed = takeFrames(buffer);
		yield* parsed.frames;
		if (parsed.rest.trim()) throw new ChatProtocolError(t('stream.unterminatedFrame'));
	} finally {
		reader.releaseLock();
	}
}

function eventsUrlWithAfterSeq(eventsUrl: string, afterSeq: number): string {
	const separator = eventsUrl.includes('?') ? '&' : '?';
	return `${eventsUrl}${separator}after_seq=${afterSeq}`;
}

/**
 * Replays the durable journal then tails it. Connection loss is never cancellation:
 * only transport failures retry, and every retry resumes at the last accepted seq.
 */
export async function* followChatRun(
	descriptor: ChatRunDescriptor,
	{ token, projectId, afterSeq = 0, signal }: FollowChatRunOptions = {}
): AsyncGenerator<ChatRunEvent> {
	let lastSeq = afterSeq;
	let attempts = 0;
	const waits = [250, 500, 1000];
	while (true) {
		let response: Response;
		try {
			response = await fetchWithAuth(eventsUrlWithAfterSeq(descriptor.events_url, lastSeq), {
				headers: { ...headers(), ...(lastSeq ? { 'Last-Event-ID': `${descriptor.run_id}:${lastSeq}` } : {}) },
				signal
			}, token, projectId);
		} catch (error) {
			if (signal?.aborted || error instanceof ApiError) throw error;
			if (attempts >= waits.length) throw new ChatProtocolError(t('stream.disconnected'));
			await delay(waits[attempts++]);
			continue;
		}
		if (response.status === 410) throw new ChatRunReloadRequiredError();
		if (!response.ok || !response.body) throw await errorFrom(response);
		try {
			for await (const frame of decodeFrames(response.body)) {
				let raw: unknown;
				try {
					raw = JSON.parse(frame.data);
				} catch {
					throw new ChatProtocolError(t('stream.invalidJson'));
				}
				const event = parseChatRunEvent(raw);
				if (frame.id && frame.id !== event.event_id) throw new ChatProtocolError(t('stream.idMismatch'));
				if (frame.event && frame.event !== event.type) throw new ChatProtocolError(t('stream.typeMismatch'));
				if (event.run_id !== descriptor.run_id) throw new ChatProtocolError(t('stream.runMismatch'));
				if (event.seq <= lastSeq) continue;
				if (event.seq !== lastSeq + 1) throw new ChatProtocolError(t('protocol.sequenceGap'));
				lastSeq = event.seq;
				attempts = 0;
				yield event;
				if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.canceled') return;
			}
		} catch (error) {
			if (signal?.aborted || error instanceof ChatProtocolError) throw error;
		}
		if (attempts >= waits.length) throw new ChatProtocolError(t('stream.disconnected'));
		await delay(waits[attempts++]);
	}
}

export async function cancelChatRun(
	descriptor: ChatRunDescriptor,
	{ token, projectId, signal }: Omit<CreateChatRunOptions, 'idempotencyKey'> = {}
): Promise<void> {
	const response = await fetchWithAuth(descriptor.cancel_url, {
		method: 'POST',
		headers: headers(),
		signal
	}, token, projectId);
	if (!response.ok) throw await errorFrom(response);
}

export const __test__ = { eventsUrlWithAfterSeq, takeFrames };
