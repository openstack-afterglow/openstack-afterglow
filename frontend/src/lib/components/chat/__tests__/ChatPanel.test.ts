import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { auth } from '$lib/stores/auth';
import { parseChatRunEvent } from '$lib/api/chatContracts';
import { invalidateChatModels } from '$lib/stores/chatModels';
import ChatPanel from '../ChatPanel.svelte';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	patch: vi.fn(),
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
	},
	ApiError: class ApiError extends Error {
		status: number;
		constructor(message: string, status: number) {
			super(message);
			this.status = status;
		}
	},
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		post: mocks.post,
		patch: mocks.patch,
		put: vi.fn(),
		delete: vi.fn()
	},
	ApiError: mocks.ApiError
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
		matches: query.includes('prefers-reduced-motion') || query.includes('max-width: 1023px'),
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
	it('refreshes an opened picker after invalidation without replacing a valid selection', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		let catalog = [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
		mocks.get.mockImplementation((path: string, ...args: unknown[]) =>
			path === '/api/v1/chat/models' ? Promise.resolve(catalog) : fallback(path, ...args));
		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: 'Model 1' }));
		catalog = [{ id: 2, model_name: 'new-opaque-id', display_name: 'New model' }, ...catalog];
		invalidateChatModels();
		expect(await screen.findByText('New model')).toBeTruthy();
		catalog = [{ id: 4, model_name: 'another-opaque-id', display_name: 'Another new model' }, ...catalog];
		await fireEvent.click(screen.getByRole('button', { name: '목록 새로고침' }));
		expect(await screen.findByText('Another new model')).toBeTruthy();
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.getByRole('button', { name: 'Model 1' })).toBeTruthy();
	});

	it('rejects late catalog responses and preserves the current model after a refresh failure', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		let resolveOld!: (value: unknown) => void;
		let mode = 'initial';
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => {
			if (path !== '/api/v1/chat/models') return fallback(path, ...args);
			if (mode === 'pending') return new Promise((resolve) => { resolveOld = resolve; });
			if (mode === 'failed') return Promise.reject(new Error('unavailable'));
			return Promise.resolve([{ id: 1, model_name: 'model-1', display_name: mode === 'fresh' ? 'Fresh model' : 'Model 1' }]);
		});
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		mode = 'pending';
		await fireEvent(window, new Event('focus'));
		mode = 'fresh';
		invalidateChatModels();
		await screen.findByRole('button', { name: 'Fresh model' });
		resolveOld([{ id: 3, model_name: 'obsolete', display_name: 'Obsolete model' }]);
		await tick();
		expect(screen.queryByRole('button', { name: 'Obsolete model' })).toBeNull();
		mode = 'failed';
		await fireEvent(window, new Event('focus'));
		await tick();
		expect(screen.getByRole('button', { name: 'Fresh model' })).toBeTruthy();
	});

	it('selects an available replacement on visible refresh and fences old project responses', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		let catalog = [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
		let resolveOld!: (value: unknown) => void;
		let pending = false;
		mocks.get.mockImplementation((path: string, requestToken: string, project: string) => {
			if (path !== '/api/v1/chat/models') return fallback(path, requestToken, project);
			if (pending && project === 'project-1') return new Promise((resolve) => { resolveOld = resolve; });
			return Promise.resolve(catalog);
		});
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		catalog = [{ id: 2, model_name: 'model-2', display_name: 'Model 2' }];
		await fireEvent(document, new Event('visibilitychange'));
		await screen.findByRole('button', { name: 'Model 2' });
		pending = true;
		await fireEvent(window, new Event('focus'));
		catalog = [{ id: 3, model_name: 'model-3', display_name: 'Other project model' }];
		auth.update((state) => ({ ...state, projectId: 'project-2' }));
		await screen.findByRole('button', { name: 'Other project model' });
		resolveOld([{ id: 1, model_name: 'model-1', display_name: 'Old project model' }]);
		await tick();
		expect(screen.getByRole('button', { name: 'Other project model' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Old project model' })).toBeNull();
	});

	it('recalculates active context when Search is enabled and disabled', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/models') return [{
				id: 1, model_name: 'model-1', display_name: 'Search model',
				capabilities: { web_search: true, feature_gates: { web_search: { available: true, mode: 'native', pricing_available: true, reason_code: null } } }
			}];
			if (path === '/api/v1/chat/conversations') return [{ id: 'conv-search', title: '검색 대화', model_name: 'model-1', workspace_id: null }];
			if (path.startsWith('/api/v1/chat/conversations/conv-search/messages')) return { messages: [], active_leaf_id: null };
			return fallback(path, ...args);
		});
		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		await fireEvent.click(await screen.findByRole('button', { name: '검색 대화' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Search 웹 검색' }));
		await waitFor(() => expect(mocks.previewContext.mock.calls.at(-1)?.[1]?.features.web_search).toMatchObject({ enabled: true, mode: 'native', provider_id: null }));
		await fireEvent.click(screen.getByRole('button', { name: 'Search 웹 검색' }));
		await waitFor(() => expect(mocks.previewContext.mock.calls.at(-1)?.[1]?.features.web_search.enabled).toBe(false));
	});
	it('renders an empty chat without a derived-state initialization error', () => {
		render(ChatPanel);

		expect(screen.getByRole('heading', { name: '무엇을 도와드릴까요?' })).toBeTruthy();
	});

	it('opens compact history to reach settings, then closes it with Escape', async () => {
		render(ChatPanel);

		const historyControl = await screen.findByRole('button', { name: '대화 기록과 설정 열기' });
		expect(historyControl.getAttribute('aria-expanded')).toBe('false');
		await fireEvent.click(historyControl);
		expect(historyControl.getAttribute('aria-expanded')).toBe('true');

		await fireEvent.click(screen.getByRole('button', { name: /tester/i }));
		await fireEvent.click(screen.getByRole('menuitem', { name: '설정' }));
		expect(mocks.goto).toHaveBeenCalledWith('/dashboard/chat/settings?section=usage');

		await fireEvent.keyDown(document, { key: 'Escape' });
		flushAnimationFrames();
		expect(historyControl.getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(historyControl);
	});

	it('closes compact history when the workspace backdrop is pressed', async () => {
		render(ChatPanel);
		const historyControl = await screen.findByRole('button', { name: '대화 기록과 설정 열기' });

		await fireEvent.click(historyControl);
		await fireEvent.click(screen.getByRole('button', { name: '대화 기록 바깥쪽 닫기' }));
		flushAnimationFrames();

		expect(historyControl.getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(historyControl);
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
			if (path === '/api/v1/chat/conversations/conv-manual/messages?anchor=latest&limit=40') {
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
			if (path === '/api/v1/chat/conversations/conv-resume-c/messages?anchor=latest&limit=40') {
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


	it('invalidates stale capacity on preview failure and recovers without losing the draft', async () => {
		const defaultGet = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/conversations') return [{ id: 'context-chat', title: '컨텍스트 대화', model_name: 'model-1', updated_at: at }];
			if (path.includes('/context-chat/messages')) return { messages: [], tree_nodes: [], active_leaf_id: null, has_more: false, next_before_id: null };
			return defaultGet(path);
		});
		let unavailable = false;
		mocks.previewContext.mockImplementation(async () => {
			if (unavailable) throw new mocks.ChatHttpError('private-provider-response', 503);
			return {
				model_name: 'model-1', context_limit: 16000, output_reserve: 4096, safety_reserve: 2048,
				input_budget: 9856, input_tokens: 3000, utilization: 0.3, measurement: 'tokenizer',
				recommendation: 'none', can_compact: false, reason_code: null, revision: 'context-rev',
				checkpoint_id: null, active_compaction_run_id: null
			};
		});
		render(ChatPanel);
		await fireEvent.click(await screen.findByText('컨텍스트 대화'));
		await screen.findByRole('button', { name: '컨텍스트 용량 세부 정보' });
		const textbox = screen.getByRole('textbox') as HTMLTextAreaElement;
		unavailable = true;
		await fireEvent.input(textbox, { target: { value: '보존할 초안' } });
		expect(screen.queryByRole('button', { name: '컨텍스트를 표시할 수 없는 이유' })).toBeNull();
		const reason = await screen.findByRole('button', { name: '컨텍스트를 표시할 수 없는 이유' });
		expect(screen.queryByRole('button', { name: '컨텍스트 용량 세부 정보' })).toBeNull();
		await fireEvent.click(reason);
		expect(screen.getByRole('dialog', { name: '컨텍스트 윈도우' }).textContent).not.toContain('private-provider-response');
		expect(textbox.value).toBe('보존할 초안');
		unavailable = false;
		await fireEvent.input(textbox, { target: { value: '보존할 초안 계속' } });
		await screen.findByRole('button', { name: '컨텍스트 용량 세부 정보' });
		expect(screen.queryByRole('dialog', { name: '컨텍스트 윈도우' })).toBeNull();
		expect(textbox.value).toBe('보존할 초안 계속');
	});

	it('keeps the server pending state beyond thirty seconds and shows a late generated title', async () => {
		vi.useFakeTimers();
		const started = Date.now();
		const pending = { id: 'slow-title', title: null, title_status: 'pending', title_revision: 1, model_name: 'model-1', workspace_id: null, updated_at: at };
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/models') return [{ id: 1, model_name: 'model-1', display_name: 'Model 1' }];
			if (path === '/api/v1/chat/conversations') return [pending];
			if (path === '/api/v1/chat/conversations/slow-title') {
				return Date.now() - started >= 45_000
					? { ...pending, title: 'OpenStack 배포 권장 구성', title_status: 'ready', title_revision: 2 }
					: pending;
			}
			return [];
		});
		const view = render(ChatPanel);
		try {
			await vi.advanceTimersByTimeAsync(31_000);
			expect(screen.getByText(/제목 요약 중/)).toBeTruthy();
			await vi.advanceTimersByTimeAsync(15_000);
			expect(screen.getByText('OpenStack 배포 권장 구성')).toBeTruthy();
		} finally {
			view.unmount();
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

	it('keeps at most three 40-message pages and performs one request per history step', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		const page = (start: number, hasBefore: boolean, beforeCursor: string | null, hasAfter: boolean, afterCursor: string | null) => ({
			messages: Array.from({ length: 40 }, (_, offset) => ({
				id: String(start + offset), conversation_id: 'conv-history', role: 'user' as const,
				parent_id: start + offset === 1 ? null : String(start + offset - 1),
				content: `history-${start + offset}`, created_at: at, position: start + offset - 1, branch: null
			})),
			active_leaf_id: '160', history_revision: 7, has_before: hasBefore, has_after: hasAfter,
			before_cursor: beforeCursor, after_cursor: afterCursor
		});
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') {
				return [{ id: 'conv-history', title: '긴 대화', model_name: 'model-1', workspace_id: null }];
			}
			if (path.endsWith('/messages?anchor=latest&limit=40')) return page(121, true, 'cursor-4', false, null);
			if (path.includes('cursor=cursor-4')) return page(81, true, 'cursor-3', true, 'after-3');
			if (path.includes('cursor=cursor-3')) return page(41, true, 'cursor-2', true, 'after-2');
			if (path.includes('cursor=cursor-2')) return page(1, false, null, true, 'after-1');
			return fallback(path, ...args);
		});

		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		await fireEvent.click(await screen.findByRole('button', { name: '긴 대화' }));
		await screen.findByText('history-160');
		for (const cursor of ['cursor-4', 'cursor-3', 'cursor-2']) {
			await fireEvent.click(screen.getByRole('button', { name: '이전' }));
			await waitFor(() => expect(mocks.get.mock.calls.some(([path]) => String(path).includes(`cursor=${cursor}`))).toBe(true));
		}

		await screen.findByText('history-1');
		expect(screen.queryByText('history-160')).toBeNull();
		const historyRequests = mocks.get.mock.calls.filter(([path]) => String(path).includes('/conv-history/messages?'));
		expect(historyRequests).toHaveLength(4);
		expect(document.querySelectorAll('[data-history-message-id]')).toHaveLength(120);
	});

	it('alerts on a stale cursor and re-queries the latest window exactly once', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		let latestRequests = 0;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') {
				return [{ id: 'conv-stale', title: '변경된 대화', model_name: 'model-1', workspace_id: null }];
			}
			if (path.endsWith('/messages?anchor=latest&limit=40')) {
				latestRequests += 1;
				return {
					messages: [{ id: latestRequests, conversation_id: 'conv-stale', role: 'user', parent_id: null, content: latestRequests === 1 ? 'old-latest' : 'refreshed-latest', created_at: at }],
					active_leaf_id: latestRequests, history_revision: latestRequests, has_before: latestRequests === 1,
					has_after: false, before_cursor: latestRequests === 1 ? 'stale-cursor' : null, after_cursor: null
				};
			}
			if (path.includes('cursor=stale-cursor')) throw new mocks.ApiError('stale', 409);
			return fallback(path, ...args);
		});

		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		await fireEvent.click(await screen.findByRole('button', { name: '변경된 대화' }));
		await screen.findByText('old-latest');
		await fireEvent.click(screen.getByRole('button', { name: '이전' }));

		await screen.findByText('refreshed-latest');
		expect(screen.getByRole('alert').textContent).toContain('대화 기록이 변경되어 최신 위치를 다시 불러왔습니다.');
		expect(latestRequests).toBe(2);
		expect(mocks.get.mock.calls.filter(([path]) => String(path).includes('/conv-stale/messages?'))).toHaveLength(3);
	});

	it('switches versions with server-projected sibling ids and recursive descent', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.patch.mockResolvedValue({ active_leaf_id: 99 });
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') {
				return [{ id: 'conv-branch', title: '분기 대화', model_name: 'model-1', workspace_id: null }];
			}
			if (path.includes('/conv-branch/messages?')) {
				return {
					messages: [{ id: 42, conversation_id: 'conv-branch', role: 'assistant', parent_id: 1, content: 'current branch', created_at: at, branch: { previous_id: 41, next_id: null } }],
					active_leaf_id: 42, history_revision: 3, has_before: false, has_after: false, before_cursor: null, after_cursor: null
				};
			}
			return fallback(path, ...args);
		});

		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		await fireEvent.click(await screen.findByRole('button', { name: '분기 대화' }));
		await screen.findByText('current branch');
		await fireEvent.click(screen.getByRole('button', { name: '이전 버전' }));

		await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(
			'/api/v1/chat/conversations/conv-branch/active-leaf',
			{ message_id: 41, descend: true },
			'token',
			'project-1'
		));
	});

});
