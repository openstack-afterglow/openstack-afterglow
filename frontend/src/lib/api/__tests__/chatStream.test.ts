import { describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { __test__, ChatHttpError, ChatProtocolError, createChatRun, followChatRun, parseChatRunDescriptor } from '../chatStream';

describe('durable chat SSE framing', () => {
	it('preserves multiline data and ignores keepalive comments', () => {
		const parsed = __test__.takeFrames(
			': keepalive\n\nid: run-1:1\nevent: part.delta\ndata: {"first":\ndata: "second"}\n\n'
		);
		expect(parsed.rest).toBe('');
		expect(parsed.frames).toEqual([
			{ id: 'run-1:1', event: 'part.delta', data: '{"first":\n"second"}' }
		]);
	});

	it('retains incomplete frames for the next UTF-8 decode chunk', () => {
		const parsed = __test__.takeFrames('id: run-1:1\ndata: {"type":"run.started"}');
		expect(parsed.frames).toEqual([]);
		expect(parsed.rest).toContain('run.started');
	});

	it('appends replay position after existing descriptor query parameters', () => {
		expect(__test__.eventsUrlWithAfterSeq('/api/v1/chat/runs/run-1/events?ticket=abc', 7)).toBe(
			'/api/v1/chat/runs/run-1/events?ticket=abc&after_seq=7'
		);
	});

	it('identifies malformed protocol failures distinctly', () => {
		expect(new ChatProtocolError('bad event').name).toBe('ChatProtocolError');
	});

	it.each(['awaiting_input', 'waiting_children'] as const)(
		'accepts the v2 %s descriptor status',
		(status) => {
			expect(
				parseChatRunDescriptor({
					run_id: 'run-1',
					conversation_id: 'conversation-1',
					temp_thread_id: null,
					status,
					run_kind: 'completion',
					events_url: '/v1/runs/run-1/events',
					cancel_url: '/v1/runs/run-1/cancel'
				})
			).toMatchObject({
				status,
				events_url: '/api/v1/chat/runs/run-1/events',
				cancel_url: '/api/v1/chat/runs/run-1/cancel'
			});
		}
	);

	it('rejects absolute and cross-origin descriptor URLs', () => {
		expect(() =>
			parseChatRunDescriptor({
				run_id: 'run-1',
				conversation_id: 'conv-1',
				temp_thread_id: null,
				status: 'running',
				run_kind: 'completion',
				events_url: 'http://evil.com/v1/runs/run-1/events',
				cancel_url: '/v1/runs/run-1/cancel'
			})
		).toThrow(ChatProtocolError);

		expect(() =>
			parseChatRunDescriptor({
				run_id: 'run-1',
				conversation_id: 'conv-1',
				status: 'running',
				run_kind: 'completion',
				events_url: '//evil.com/v1/runs/run-1/events',
				cancel_url: '/v1/runs/run-1/cancel'
			})
		).toThrow(ChatProtocolError);
	});

	it('requires run_kind and preserves compaction descriptors', () => {
		const descriptor = {
			run_id: 'run-compaction',
			conversation_id: 'conv-1',
			temp_thread_id: null,
			status: 'running',
			run_kind: 'compaction',
			events_url: '/v1/runs/run-compaction/events',
			cancel_url: '/v1/runs/run-compaction/cancel'
		};
		expect(parseChatRunDescriptor(descriptor)).toMatchObject({ run_kind: 'compaction' });
		const { run_kind: _runKind, ...legacyDescriptor } = descriptor;
		expect(() => parseChatRunDescriptor(legacyDescriptor)).toThrow(ChatProtocolError);
	});
	it('preserves HTTP status on durable run admission errors', async () => {
		const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
			new Response(JSON.stringify({ detail: 'context revision changed' }), {
				status: 409,
				headers: { 'Content-Type': 'application/json' }
			})
		);
		try {
			await expect(createChatRun('/api/v1/chat/conversations/c1/compactions', {})).rejects.toMatchObject({
				status: 409
			});
			await expect(createChatRun('/api/v1/chat/conversations/c1/compactions', {})).rejects.toBeInstanceOf(ChatHttpError);
		} finally {
			fetchMock.mockRestore();
		}
	});
	it('refreshes an initial 401 before consuming the recovered event stream', async () => {
		auth.set({
			token: 'old-token',
			refreshToken: 'refresh-token',
			accessExpiresAt: null,
			userId: 'user',
			username: 'user',
			projectId: 'project-1',
			projectName: 'Project 1',
			availableProjects: [],
			roles: [],
			isSystemAdmin: false,
			federated: false,
		});
		const event = {
			event_id: 'run-1:1',
			run_id: 'run-1',
			seq: 1,
			type: 'run.completed',
			created_at: '2026-09-11T00:00:00Z',
			payload: { status: 'completed', message_id: 'message-1' },
		};
		const encoder = new TextEncoder();
		const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
			const url = String(input);
			if (url.endsWith('/api/v1/auth/refresh')) {
				return Promise.resolve(new Response(JSON.stringify({ token: 'new-token', refresh_token: 'new-refresh-token' })));
			}
			if (new Headers(init?.headers).get('Authorization') === 'Bearer old-token') {
				return Promise.resolve(new Response(null, { status: 401 }));
			}
			return Promise.resolve(new Response(new ReadableStream<Uint8Array>({
				start(controller) {
					controller.enqueue(encoder.encode(`id: run-1:1\nevent: run.completed\ndata: ${JSON.stringify(event)}\n\n`));
					controller.close();
				},
			})));
		});
		try {
			const received = [];
			for await (const item of followChatRun({
				run_id: 'run-1',
				conversation_id: 'conversation-1',
				temp_thread_id: null,
				status: 'queued',
				run_kind: 'completion',
				events_url: '/api/v1/chat/runs/run-1/events',
				cancel_url: '/api/v1/chat/runs/run-1/cancel',
			}, { token: 'old-token', projectId: 'project-1' })) {
				received.push(item);
			}
			expect(received).toEqual([event]);
			expect(fetchMock.mock.calls
				.filter(([input]) => String(input).includes('/events?after_seq=0'))
				.map(([, init]) => new Headers(init?.headers).get('Authorization')))
				.toEqual(['Bearer old-token', 'Bearer new-token']);
		} finally {
			fetchMock.mockRestore();
			auth.set({
				token: null,
				refreshToken: null,
				accessExpiresAt: null,
				userId: null,
				username: null,
				projectId: null,
				projectName: null,
				availableProjects: [],
				roles: [],
				isSystemAdmin: false,
				federated: false,
			});
		}
	});

	it('preserves refresh service failures instead of retrying them as disconnected streams', async () => {
		const originalAuth = get(auth);
		auth.update((state) => ({
			...state, token: 'expiring-stream-token', refreshToken: 'stream-refresh', accessExpiresAt: 1,
		}));
		const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
			new Response(JSON.stringify({ detail: 'refresh service unavailable' }), { status: 503 }),
		);
		try {
			const stream = followChatRun({
				run_id: 'run-1', conversation_id: 'conversation-1', temp_thread_id: null,
				status: 'queued', run_kind: 'completion',
				events_url: '/api/v1/chat/runs/run-1/events',
				cancel_url: '/api/v1/chat/runs/run-1/cancel',
			}, { token: 'expiring-stream-token' });
			await expect(stream.next()).rejects.toMatchObject({ status: 503 });
			expect(fetchMock).toHaveBeenCalledOnce();
			expect(get(auth).token).toBe('expiring-stream-token');
		} finally {
			fetchMock.mockRestore();
			auth.set(originalAuth);
		}
	});
});
