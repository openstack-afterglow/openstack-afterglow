import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { auth } from '$lib/stores/auth';
import { parseChatRunEvent } from '$lib/api/chatContracts';
import ChatPanel from '../ChatPanel.svelte';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	createRun: vi.fn(),
	followRun: vi.fn(),
	cancelRun: vi.fn(),
	previewContext: vi.fn(),
	goto: vi.fn(),
	ChatHttpError: class ChatHttpError extends Error {
		status: number;
		constructor(message: string, status: number) {
			super(message);
			this.status = status;
		}
	}
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		post: mocks.post,
		patch: vi.fn(),
		put: vi.fn(),
		delete: vi.fn()
	},
	ApiError: class ApiError extends Error {}
}));

vi.mock('$app/navigation', () => ({ goto: mocks.goto }));

vi.mock('$lib/api/chatStream', () => ({
	createChatRun: mocks.createRun,
	followChatRun: mocks.followRun,
	cancelChatRun: mocks.cancelRun,
	previewChatContext: mocks.previewContext,
	parseChatRunDescriptor: (value: unknown) => value,
	ChatHttpError: mocks.ChatHttpError
}));

let nextAnimationFrame = 0;
const animationFrames = new Map<number, FrameRequestCallback>();

function flushAnimationFrames() {
	const queued = [...animationFrames.values()];
	animationFrames.clear();
	for (const callback of queued) callback(performance.now());
}

const at = '2026-07-26T00:00:00Z';

function event(seq: number, type: string, payload: object) {
	return parseChatRunEvent({
		event_id: `run-1:${seq}`,
		run_id: 'run-1',
		seq,
		type,
		created_at: at,
		payload
	});
}

beforeEach(() => {
	vi.clearAllMocks();
	auth.set({
		token: 'token',
		refreshToken: null,
		accessExpiresAt: null,
		userId: 'user-1',
		username: 'tester',
		projectId: 'project-1',
		projectName: 'Project',
		availableProjects: [],
		roles: [],
		isSystemAdmin: false,
		federated: false
	});
	vi.stubGlobal('matchMedia', (query: string) => ({
		matches: query.includes('prefers-reduced-motion'),
		media: query,
		onchange: null,
		addEventListener: () => {},
		removeEventListener: () => {},
		addListener: () => {},
		removeListener: () => {},
		dispatchEvent: () => false
	}));
	animationFrames.clear();
	nextAnimationFrame = 0;
	vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
		const frame = ++nextAnimationFrame;
		animationFrames.set(frame, callback);
		return frame;
	});
	vi.stubGlobal('cancelAnimationFrame', (frame: number) => animationFrames.delete(frame));
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/chat/models') {
			return [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
		}
		if (path === '/api/v1/chat/runs?active=true') return [];
		if (path === '/api/v1/chat/conversations') return [];
		if (path === '/api/v1/chat/usage') return {};
		return [];
	});
	mocks.createRun.mockResolvedValue({
		run_id: 'run-1',
		conversation_id: null,
		temp_thread_id: 'temp-1',
		status: 'running',
		run_kind: 'completion',
		events_url: '/events',
		cancel_url: '/cancel'
	});
	mocks.followRun.mockImplementation(async function* () {});
	mocks.post.mockResolvedValue({});
	mocks.cancelRun.mockResolvedValue(undefined);
	mocks.previewContext.mockResolvedValue({
		model_name: 'model-1',
		context_limit: 16000,
		output_reserve: 4096,
		safety_reserve: 2048,
		input_budget: 9856,
		input_tokens: 3000,
		utilization: 0.3,
		measurement: 'tokenizer',
		recommendation: 'none',
		can_compact: true,
		reason_code: null,
		revision: 'rev-1',
		checkpoint_id: null,
		active_compaction_run_id: null
	});
});

describe('ChatPanel', () => {
	it('renders an empty chat without a derived-state initialization error', () => {
		render(ChatPanel);

		expect(screen.getByRole('heading', { name: '무엇을 도와드릴까요?' })).toBeTruthy();
	});

	it('navigates to the dedicated settings page from the sidebar user menu', async () => {
		render(ChatPanel);

		await fireEvent.click(screen.getByRole('button', { name: /tester/i }));
		await fireEvent.click(screen.getByRole('menuitem', { name: '설정' }));

		expect(mocks.goto).toHaveBeenCalledWith('/dashboard/chat/settings?section=usage');
		expect(screen.queryByRole('dialog', { name: '채팅 설정' })).toBeNull();
	});


	it('opens the existing project dialog from the new-project slash command', async () => {
		render(ChatPanel);
		const composer = screen.getByRole('textbox');

		await fireEvent.input(composer, { target: { value: '/새 프로젝트' } });
		await fireEvent.keyDown(composer, { key: 'Enter' });

		expect(await screen.findByRole('heading', { name: '프로젝트 만들기' })).toBeTruthy();
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it('opens the existing model picker from the model-selection slash command', async () => {
		render(ChatPanel);
		await waitFor(() => expect(screen.getByRole('button', { name: 'Model 1' })).toBeTruthy());
		const composer = screen.getByRole('textbox');

		await fireEvent.input(composer, { target: { value: '/모델 선택' } });
		await fireEvent.keyDown(composer, { key: 'Enter' });

		expect(await screen.findByRole('dialog', { name: '모델 선택' })).toBeTruthy();
		expect(mocks.createRun).not.toHaveBeenCalled();
	});


	it('inserts a Lumen starter into the composer without directly starting a run', async () => {
		render(ChatPanel);

		await fireEvent.click(screen.getByRole('button', { name: '프로젝트 현황' }));

		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(
			'현재 프로젝트의 컴퓨팅, 스토리지, 네트워크 리소스를 읽기 전용으로 요약해 주세요.'
		);
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it('survives late conversation list response without wiping out newly created conversation and preserves monotone title_revision', async () => {
		const slowListPromise = Promise.withResolvers<object[]>();
		let listRequestCount = 0;
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/models') {
				return [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
			}
			if (path === '/api/v1/chat/conversations') {
				listRequestCount += 1;
				if (listRequestCount === 1) {
					return slowListPromise.promise;
				}
				return [
					{
						id: 'conv-race',
						title: '서버 제목 rev1',
						title_status: 'ready',
						title_revision: 1,
						model_name: 'model-1',
						workspace_id: null,
						updated_at: at
					}
				];
			}
			if (path === '/api/v1/chat/runs?active=true') return [];
			if (path === '/api/v1/chat/usage') return {};
			if (path === '/api/v1/chat/conversations/conv-race') {
				return {
					id: 'conv-race',
					title: null,
					title_status: 'pending',
					title_revision: 0,
					model_name: 'model-1',
					workspace_id: null,
					updated_at: at
				};
			}
			return [];
		});
		mocks.post.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/conversations') {
				return {
					id: 'conv-race',
					title: null,
					title_status: 'pending',
					title_revision: 0,
					model_name: 'model-1',
					workspace_id: null,
					updated_at: at
				};
			}
			return {};
		});

		render(ChatPanel);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'token', 'project-1'));
		await waitFor(() => expect(screen.getByRole('button', { name: 'Model 1' })).toBeTruthy());

		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '첫 메시지' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() =>
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/chat/conversations',
				expect.objectContaining({ title: null }),
				'token',
				'project-1'
			)
		);

		await waitFor(() => expect(screen.getByText(/제목 요약 중/)).toBeTruthy());

		slowListPromise.resolve([]);
		await tick();

		expect(screen.getByText(/제목 요약 중/)).toBeTruthy();

		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/conversations') {
				return [
					{
						id: 'conv-race',
						title: '최신 요약 제목 rev2',
						title_status: 'ready',
						title_revision: 2,
						model_name: 'model-1',
						workspace_id: null,
						updated_at: at
					}
				];
			}
			return [];
		});
		await fireEvent(window, new Event('focus'));
		await waitFor(() => expect(screen.getByText('최신 요약 제목 rev2')).toBeTruthy());

		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/conversations') {
				return [
					{
						id: 'conv-race',
						title: '오래된 제목 rev1',
						title_status: 'ready',
						title_revision: 1,
						model_name: 'model-1',
						workspace_id: null,
						updated_at: at
					}
				];
			}
			return [];
		});
		await fireEvent(window, new Event('focus'));
		await tick();
		expect(screen.getByText('최신 요약 제목 rev2')).toBeTruthy();
		expect(screen.queryByText('오래된 제목 rev1')).toBeNull();
	});

	it('executes manual compaction with empty-draft preview without creating assistant draft bubble and preserves user draft', async () => {
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/models') {
				return [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
			}
			if (path === '/api/v1/chat/conversations') {
				return [
					{
						id: 'conv-manual',
						title: '기존 대화',
						title_status: 'ready',
						title_revision: 1,
						model_name: 'model-1',
						workspace_id: null,
						updated_at: at
					}
				];
			}
			if (path === '/api/v1/chat/conversations/conv-manual/messages?limit=40') {
				return {
					messages: [
						{ id: 'm1', conversation_id: 'conv-manual', role: 'user', content: '안녕하세요', created_at: at }
					],
					tree_nodes: [],
					active_leaf_id: 'm1',
					has_more: false,
					next_before_id: null
				};
			}
			if (path === '/api/v1/chat/runs?active=true') return [];
			if (path === '/api/v1/chat/conversations/conv-manual/runs?active=true') return [];
			return [];
		});

		mocks.previewContext.mockResolvedValue({
			model_name: 'model-1',
			context_limit: 16000,
			output_reserve: 4096,
			safety_reserve: 2048,
			input_budget: 9856,
			input_tokens: 7500,
			utilization: 0.76,
			measurement: 'tokenizer',
			recommendation: 'compact',
			can_compact: true,
			reason_code: null,
			revision: 'rev-xyz',
			checkpoint_id: null,
			active_compaction_run_id: null
		});

		const compactionCompleted = Promise.withResolvers<void>();
		mocks.createRun.mockResolvedValue({
			run_id: 'run-compact-1',
			conversation_id: 'conv-manual',
			temp_thread_id: null,
			status: 'running',
			run_kind: 'compaction',
			events_url: '/events',
			cancel_url: '/cancel'
		});
		mocks.followRun.mockImplementation(async function* () {
			await compactionCompleted.promise;
			yield event(1, 'run.completed', { status: 'completed', message_id: null });
		});

		render(ChatPanel);
		await waitFor(() => expect(screen.getByText('기존 대화')).toBeTruthy());
		await fireEvent.click(screen.getByText('기존 대화'));
		await waitFor(() => expect(screen.getByText('안녕하세요')).toBeTruthy());

		const textbox = screen.getByRole('textbox') as HTMLTextAreaElement;
		await fireEvent.input(textbox, { target: { value: '작성 중인 중요 메모 /' } });
		expect(textbox.value).toBe('작성 중인 중요 메모 /');

		const compactCommand = await screen.findByRole('option', { name: /압축.*컨텍스트.*명령/i });
		await waitFor(() => expect((compactCommand as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(compactCommand);

		await waitFor(() => expect(mocks.previewContext).toHaveBeenCalled());
		const previewCall = mocks.previewContext.mock.calls.find(
			(call) => typeof call[0] === 'string' && call[0].includes('/context-preview')
		);
		expect(previewCall).toBeDefined();
		expect(previewCall![1].parts).toEqual([]);

		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledWith(
			'/api/v1/chat/conversations/conv-manual/compactions',
			expect.objectContaining({
				expected_context_revision: 'rev-xyz'
			}),
			expect.any(Object)
		));

		expect(screen.queryByText('...')).toBeNull();
		expect(textbox.value.trim()).toBe('작성 중인 중요 메모');
		expect(screen.getByRole('button', { name: '전송' }).hasAttribute('disabled')).toBe(true);
		expect(document.querySelector('.context-activity')?.textContent).toContain('컨텍스트 압축 중');

		compactionCompleted.resolve();
		await waitFor(() => expect(document.querySelector('.context-activity')).toBeNull());
	});
	it('uses the typed HTTP 409 status for a compaction revision conflict', async () => {
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/models') {
				return [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
			}
			if (path === '/api/v1/chat/conversations') {
				return [
					{
						id: 'conv-conflict',
						title: '충돌 대화',
						title_status: 'ready',
						title_revision: 1,
						model_name: 'model-1',
						workspace_id: null,
						updated_at: at
					}
				];
			}
			if (path === '/api/v1/chat/conversations/conv-conflict/messages?limit=40') {
				return { messages: [], tree_nodes: [], active_leaf_id: null, has_more: false, next_before_id: null };
			}
			if (path === '/api/v1/chat/runs?active=true') return [];
			if (path === '/api/v1/chat/conversations/conv-conflict/runs?active=true') return [];
			return [];
		});
		mocks.createRun.mockRejectedValueOnce(new mocks.ChatHttpError('stale revision', 409));

		render(ChatPanel);
		await waitFor(() => expect(screen.getByText('충돌 대화')).toBeTruthy());
		await fireEvent.click(screen.getByText('충돌 대화'));
		const textbox = screen.getByRole('textbox') as HTMLTextAreaElement;
		await fireEvent.input(textbox, { target: { value: '/' } });
		const compactCommand = await screen.findByRole('option', { name: /압축.*컨텍스트.*명령/i });
		await waitFor(() => expect((compactCommand as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(compactCommand);

		await waitFor(() => expect(screen.getByText('대화 상태가 변경되었습니다. 최신 대화를 확인해 주세요.')).toBeTruthy());
	});


	it('resumes an active compaction run without creating an assistant bubble and supports cancellation', async () => {
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/models') {
				return [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
			}
			if (path === '/api/v1/chat/conversations') {
				return [
					{
						id: 'conv-resume-c',
						title: '압축 중인 대화',
						title_status: 'ready',
						title_revision: 1,
						model_name: 'model-1',
						workspace_id: null,
						updated_at: at
					}
				];
			}
			if (path === '/api/v1/chat/conversations/conv-resume-c/messages?limit=40') {
				return {
					messages: [
						{ id: 'm-prior', conversation_id: 'conv-resume-c', role: 'user', content: '이전 대화', created_at: at }
					],
					tree_nodes: [],
					active_leaf_id: 'm-prior',
					has_more: false,
					next_before_id: null
				};
			}
			if (path === '/api/v1/chat/conversations/conv-resume-c/runs?active=true') {
				return [
					{
						run_id: 'run-active-compact',
						conversation_id: 'conv-resume-c',
						temp_thread_id: null,
						status: 'running',
						run_kind: 'compaction',
						events_url: '/v1/runs/run-active-compact/events',
						cancel_url: '/v1/runs/run-active-compact/cancel'
					}
				];
			}
			if (path === '/api/v1/chat/runs?active=true') {
				return [
					{
						run_id: 'run-active-compact',
						conversation_id: 'conv-resume-c',
						temp_thread_id: null,
						status: 'running',
						run_kind: 'compaction',
						events_url: '/v1/runs/run-active-compact/events',
						cancel_url: '/v1/runs/run-active-compact/cancel'
					}
				];
			}
			return [];
		});

		const holdRun = Promise.withResolvers<void>();
		mocks.followRun.mockImplementation(async function* () {
			await holdRun.promise;
		});

		render(ChatPanel);
		await waitFor(() => expect(screen.getByText('압축 중인 대화')).toBeTruthy());
		await fireEvent.click(screen.getByText('압축 중인 대화'));

		await waitFor(() =>
			expect(mocks.followRun).toHaveBeenCalledWith(
				expect.objectContaining({ run_id: 'run-active-compact', run_kind: 'compaction' }),
				expect.any(Object)
			)
		);

		const textbox = screen.getByRole('textbox') as HTMLTextAreaElement;
		await fireEvent.input(textbox, { target: { value: '/' } });
		const stopCommand = await screen.findByRole('option', { name: /압축 중단.*명령/i });
		await fireEvent.click(stopCommand);
		expect(mocks.cancelRun).toHaveBeenCalledWith(
			expect.objectContaining({ run_id: 'run-active-compact' }),
			expect.any(Object)
		);

		holdRun.resolve();
	});

	it('polls pending conversation titles with max 4 concurrent requests and respects document visibility', async () => {
		vi.useFakeTimers();
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/models') {
				return [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
			}
			if (path === '/api/v1/chat/conversations') {
				return [
					{ id: 'c1', title: null, title_status: 'pending', title_revision: 0, model_name: 'model-1', workspace_id: null, updated_at: at },
					{ id: 'c2', title: null, title_status: 'pending', title_revision: 0, model_name: 'model-1', workspace_id: null, updated_at: at },
					{ id: 'c3', title: null, title_status: 'pending', title_revision: 0, model_name: 'model-1', workspace_id: null, updated_at: at },
					{ id: 'c4', title: null, title_status: 'pending', title_revision: 0, model_name: 'model-1', workspace_id: null, updated_at: at },
					{ id: 'c5', title: null, title_status: 'pending', title_revision: 0, model_name: 'model-1', workspace_id: null, updated_at: at }
				];
			}
			if (path.startsWith('/api/v1/chat/conversations/c')) {
				const id = path.split('/')[5];
				return {
					id,
					title: `완료된 제목 ${id}`,
					title_status: 'ready',
					title_revision: 1,
					model_name: 'model-1',
					workspace_id: null,
					updated_at: at
				};
			}
			if (path === '/api/v1/chat/runs?active=true') return [];
			return [];
		});

		try {
			render(ChatPanel);
			await vi.advanceTimersByTimeAsync(0);

			const singlePolls = mocks.get.mock.calls.filter(
				(call) => typeof call[0] === 'string' && call[0].startsWith('/api/v1/chat/conversations/c')
			);
			expect(singlePolls.length).toBeGreaterThan(0);
			expect(singlePolls.length).toBeLessThanOrEqual(5);

			Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
			document.dispatchEvent(new Event('visibilitychange'));

			const countBeforeHidden = mocks.get.mock.calls.length;
			await vi.advanceTimersByTimeAsync(2000);
			expect(mocks.get.mock.calls.length).toBe(countBeforeHidden);

			Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
			document.dispatchEvent(new Event('visibilitychange'));
		} finally {
			vi.useRealTimers();
		}
	});

	it('keeps a pre-persistence send failure visible and retries with the same request key', async () => {
		mocks.post.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/conversations') {
				return {
					id: 'conversation-1',
					title: '재시도',
					model_name: 'model-1',
					workspace_id: null,
					updated_at: at
				};
			}
			return {};
		});
		const retry = Promise.withResolvers<object>();
		mocks.createRun
			.mockRejectedValueOnce(new Error('일시적으로 전송하지 못했습니다'))
			.mockImplementationOnce(() => retry.promise);

		render(ChatPanel);
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '실패 후 재전송' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));

		await screen.findByText('응답 생성에 실패했습니다');
		expect(screen.getByText('실패 후 재전송')).toBeTruthy();
		const retryButton = screen.getByRole('button', { name: '다시 전송' });
		await fireEvent.click(retryButton);
		await fireEvent.click(retryButton);

		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(2));
		const firstOptions = mocks.createRun.mock.calls[0][2];
		const retryOptions = mocks.createRun.mock.calls[1][2];
		expect(retryOptions.idempotencyKey).toBe(firstOptions.idempotencyKey);
		retry.resolve({
			run_id: 'run-retry',
			conversation_id: 'conversation-1',
			temp_thread_id: null,
			status: 'queued',
			run_kind: 'completion',
			events_url: '/events',
			cancel_url: '/cancel'
		});
	});
	it('keeps a failed conversation creation attempt visible with retry button and retries conversation creation on click', async () => {
		let attempts = 0;
		mocks.post.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/conversations') {
				attempts += 1;
				if (attempts === 1) {
					throw new Error('대화 생성 실패');
				}
				return {
					id: 'conversation-created',
					title: '첫 대화 생성 실패 후 복구',
					model_name: 'model-1',
					workspace_id: null,
					updated_at: at
				};
			}
			return {};
		});

		render(ChatPanel);
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '첫 생성 실패 메시지' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));

		await screen.findByText('응답 생성에 실패했습니다');
		expect(screen.getByText('첫 생성 실패 메시지')).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: '다시 전송' }));

		await waitFor(() => expect(attempts).toBe(2));
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][0]).toBe('/api/v1/chat/conversations/conversation-created/completions');
	});

	it('keeps the live bubble on the current message when a prior completion arrives late', async () => {
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'message.created', { message_id: 'assistant-1', role: 'assistant', parent_id: null });
			yield event(2, 'part.delta', {
				message_id: 'assistant-1',
				part_index: 1,
				part_type: 'reasoning',
				delta: '이전 추론'
			});
			yield event(3, 'part.delta', {
				message_id: 'assistant-1',
				part_index: 0,
				part_type: 'text',
				delta: '이전 본문'
			});
			yield event(4, 'message.created', { message_id: 'assistant-2', role: 'assistant', parent_id: null });
			yield event(5, 'part.completed', {
				message_id: 'assistant-1',
				part_index: 1,
				part: { type: 'reasoning', text: '이전 추론', visibility: 'user' }
			});
			yield event(6, 'part.completed', {
				message_id: 'assistant-1',
				part_index: 0,
				part: { type: 'text', text: '이전 본문' }
			});
			yield event(7, 'part.delta', {
				message_id: 'assistant-2',
				part_index: 0,
				part_type: 'text',
				delta: '현재 본문'
			});
			yield event(8, 'part.completed', {
				message_id: 'assistant-2',
				part_index: 0,
				part: { type: 'text', text: '현재 본문' }
			});
			yield event(9, 'run.completed', { status: 'completed', message_id: 'assistant-2' });
		});

		render(ChatPanel);
		await waitFor(() =>
			expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'token', 'project-1')
		);
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(
			screen.getByRole('textbox'),
			{ target: { value: '테스트' } }
		);
		await waitFor(() => expect(screen.getByRole('button', { name: '전송' }).hasAttribute('disabled')).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		await waitFor(() => {
			flushAnimationFrames();
			expect(screen.getByText('현재 본문')).toBeTruthy();
		});
		expect(screen.queryByText('이전 본문')).toBeNull();

		await fireEvent.click(screen.getByLabelText('작업 내역 열기'));
		await fireEvent.click(screen.getByRole('button', { name: '추론 과정' }));
		expect(screen.getByText('이전 추론')).toBeTruthy();
	});

	it('shows automatic context compaction through the active draft timeline', async () => {
		const finishRun = Promise.withResolvers<void>();
		const compactingState = {
			model_name: 'model-1',
			context_limit: 16000,
			output_reserve: 4096,
			safety_reserve: 2048,
			input_budget: 9856,
			input_tokens: 9000,
			utilization: 0.91,
			measurement: 'tokenizer',
			recommendation: 'required',
			can_compact: true,
			reason_code: null,
			revision: 'context-r3',
			checkpoint_id: 'checkpoint-r2',
			active_compaction_run_id: 'run-1'
		};
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'context.updated', {
				state: compactingState,
				phase: 'compacting',
				cause: 'automatic',
				before_tokens: 9000,
				after_tokens: null
			});
			await finishRun.promise;
			yield event(2, 'run.completed', { status: 'completed', message_id: null });
		});

		render(ChatPanel);
		await waitFor(() =>
			expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'token', 'project-1')
		);
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '긴 대화를 계속해 주세요' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));

		await waitFor(() => {
			flushAnimationFrames();
			expect(screen.getByLabelText('작업 내역 열기')).toBeTruthy();
			expect(screen.getAllByText('컨텍스트 자동 압축 중')).toHaveLength(2);
			expect(document.querySelector('.context-activity')).toBeNull();
		});
		finishRun.resolve();
		await waitFor(() => expect(screen.queryAllByText('컨텍스트 자동 압축 중')).toHaveLength(0));
	});

	it('renders an approval preview and sends an explicit project-scoped decision', async () => {
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'tool.approval_required', {
				call_id: 'call-1',
				name: 'afterglow_vm_delete',
				source: 'managed',
				effect: 'external_mutation',
				destination: null,
				redacted_arguments: { server_id: '[REDACTED]' },
				preview: [{ type: 'text', text: 'Delete: server-1 (current state: ACTIVE)' }],
				expected_state_revision: null,
				writer_fence: null,
				expires_at: '2026-07-27T12:00:00Z'
			});
		});

		render(ChatPanel);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'token', 'project-1'));
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'VM을 삭제해줘' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));

		await screen.findByText('Delete: server-1 (current state: ACTIVE)');
		await fireEvent.click(screen.getByRole('button', { name: '승인' }));

		expect(mocks.post).toHaveBeenCalledWith(
			'/api/v1/chat/runs/run-1/approvals/call-1',
			{ decision: 'approve' },
			'token',
			'project-1'
		);
	});
	it('reveals the terminal footer after a temporary run is canceled', async () => {
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'run.canceled', {
				status: 'canceled',
				message_id: null,
				error_code: 'canceled_by_user',
				safe_message: '생성을 중단했습니다.'
			});
		});

		render(ChatPanel);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'token', 'project-1'));
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '중단할 요청' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));

		await screen.findByText('생성을 중단했습니다.');
		await waitFor(() => expect(screen.getAllByRole('button', { name: '복사' })).toHaveLength(2));
	});

});
