import { grantLumen, pendingLumen, setVerifiedLumenActor } from './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { parseChatRunEvent } from '$lib/api/chatContracts';
import { createRunViewState, reduceRunEvent, type RunActivityItem } from '$lib/api/chatRunReducer';
import { invalidateChatModels } from '$lib/stores/chatModels';
import ChatPanel from '../ChatPanel.svelte';
import { siteConfig } from '$lib/config/site';
import { projectSwitching } from '$lib/stores/auth';
import type { CloudToolsCatalogue } from '$lib/api/chatContracts';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	patch: vi.fn(),
	createRun: vi.fn(),
	followRun: vi.fn(),
	cancelRun: vi.fn(),
	previewContext: vi.fn(),
	goto: vi.fn(),
	setPageState: vi.fn(),
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

vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	const initial = { data: {}, url: new URL('http://localhost/dashboard/chat'), state: {} };
	const page = writable(initial);
	mocks.setPageState.mockImplementation((state) => page.set({ ...initial, state }));
	return { page };
});
vi.mock('$app/navigation', () => ({
	goto: mocks.goto,
	pushState: (_url: URL, state: unknown) => mocks.setPageState(state)
}));

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
	sessionStorage.clear();
	mocks.setPageState({});
	siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
	setVerifiedLumenActor({
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
		federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false
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
	it.each(['completed', 'failed', 'canceled'] as const)('restores and pages causal temporary turns while inspecting unpositioned legacy runs separately after %s', async (outcome) => {
		const finish = Promise.withResolvers<void>();
		const observed = Promise.withResolvers<void>();
		let settled = false;
		let changedCursorObserved = false;
		const descriptor = { run_id: 'run-1', conversation_id: null, temp_thread_id: 'temp-1', status: 'running', run_kind: 'completion', events_url: '/events', cancel_url: '/cancel' };
		const nativeActivity = (status: 'completed' | 'failed' | 'canceled' | 'running'): RunActivityItem[] => [
			{ id: 'stage:1', kind: 'stage', seq: 1, createdAt: at, stage: 'queued', toolName: null },
			...(status === 'running' ? [] : [{
				id: 'terminal:4', kind: 'terminal' as const, seq: 4, createdAt: at, status,
				errorCode: status === 'completed' ? null : 'interrupted', message: status === 'completed' ? null : 'recorded interruption'
			}])
		];
		const turn = (index: number, role: 'user' | 'assistant', content: string, runId?: string, status: 'completed' | 'failed' | 'canceled' | 'running' = 'completed') => ({
			id: `saved:${index}`, role, content, conversation_id: '', parent_id: null, created_at: at,
			temporary_history_order: [index, 1, 0],
			...(runId ? { execution: { run_id: runId, status, ...(role === 'assistant' ? { activity: nativeActivity(status) } : {}) } } : {})
		});
		const snapshot = (full: boolean) => {
			const currentStatus = settled ? outcome : 'running';
			const currentUser = turn(8, 'user', 'current question', 'run-1', currentStatus);
			const currentAnswer = turn(9, 'assistant', 'current answer', 'run-1', currentStatus);
			if (!(settled && outcome === 'completed')) {
				currentUser.id = 'temp:run-1:user';
				currentAnswer.id = 'temp:run-1:assistant';
				currentUser.temporary_history_order = [8, 0, 12];
				currentAnswer.temporary_history_order = [8, 0, 13];
			}
			const messages = [
				turn(0, 'user', 'legacy first question'), turn(1, 'assistant', 'legacy first answer'),
				turn(2, 'user', 'legacy later question'), turn(3, 'assistant', 'legacy later answer'),
				turn(4, 'user', 'first question', 'run-A'), turn(5, 'assistant', 'first answer', 'run-A'),
				turn(6, 'user', 'second question', 'run-B'), turn(7, 'assistant', 'second answer', 'run-B'),
				currentUser, currentAnswer
			];
			if (full) {
				const failedUser = turn(6, 'user', 'failed question', 'run-F', 'failed');
				const failedAnswer = turn(6, 'assistant', 'failed answer', 'run-F', 'failed');
				failedUser.id = 'temp:run-F:user';
				failedAnswer.id = 'temp:run-F:assistant';
				failedUser.temporary_history_order = [6, 0, 8];
				failedAnswer.temporary_history_order = [6, 0, 9];
				messages.push(failedUser, failedAnswer);
			}
			messages.sort((a, b) => a.temporary_history_order[0] - b.temporary_history_order[0] ||
				a.temporary_history_order[1] - b.temporary_history_order[1] || a.temporary_history_order[2] - b.temporary_history_order[2]);
			return {
				temp_thread_id: 'temp-1', messages, active_run: settled ? null : descriptor, active_run_positioned: true,
				run_history_has_more: !full, run_history_after: full ? null : 'older', run_history_revision: 'revision-before',
				unpositioned_runs: full ? [{
					run_id: 'legacy-failed', run_kind: 'completion', status: 'failed', model_name: 'model-1', order_unknown: true,
					input_parts: [{ type: 'text', text: 'legacy failed question' }], parts: [{ type: 'text', text: 'legacy failed answer' }],
					activity: [
						{ id: 'stage:1', kind: 'stage', seq: 1, createdAt: at, stage: 'queued', toolName: null },
						{ id: 'tool:old-call', kind: 'tool', seq: 2, createdAt: at, callId: 'old-call', name: 'lookup', source: 'builtin', category: '기본 도구',
							arguments: { query: 'legacy recorded input' }, status: 'completed', content: [{ type: 'text', text: 'legacy recorded result' }], errorCode: null, durationMs: null },
						{ id: 'terminal:4', kind: 'terminal', seq: 4, createdAt: at, status: 'failed', errorCode: 'interrupted', message: 'legacy interruption' }
					]
				}] : []
			};
		};
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path.startsWith('/api/v1/chat/temp-threads/temp-1')) {
				if (path.includes('run_after=older')) {
					if (outcome === 'completed' && !changedCursorObserved) {
						changedCursorObserved = true;
						throw new mocks.ApiError('temporary_history_changed', 409);
					}
					return snapshot(true);
				}
				return snapshot(settled);
			}
			return fallback(path, ...args);
		});
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'run.stage.changed', { stage: 'queued', tool_name: null });
			yield event(2, 'message.created', { message_id: 'current-answer', role: 'assistant', parent_id: null });
			yield event(3, 'part.completed', { message_id: 'current-answer', part_index: 0, part: { type: 'text', text: 'current answer' } });
			observed.resolve();
			await finish.promise;
			settled = true;
			if (outcome === 'completed') yield event(4, 'run.completed', { status: outcome, message_id: 'current-answer' });
			else yield event(4, `run.${outcome}`, { status: outcome, message_id: 'current-answer', error_code: 'interrupted', safe_message: 'recorded interruption' });
		});
		sessionStorage.setItem('chat:tempThreadId:domain-1:user-1:project-1', 'temp-1');
		const view = render(ChatPanel);
		await observed.promise;
		flushAnimationFrames();
		await tick();
		const currentRow = screen.getByText('current answer').closest('[data-history-message-id]')!;
		const currentTimeline = currentRow.querySelector<HTMLDetailsElement>('.execution-timeline')!;
		currentTimeline.open = false;
		await fireEvent(currentTimeline, new Event('toggle'));
		finish.resolve();
		await waitFor(() => expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull());
		expect(currentRow.querySelector('.execution-timeline')).toBe(currentTimeline);
		expect(currentTimeline.open).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: '임시 실행 기록 더 불러오기' }));
		if (outcome === 'completed') {
			await waitFor(() => expect(changedCursorObserved).toBe(true));
			await waitFor(() => expect(screen.getByRole('button', { name: '임시 실행 기록 더 불러오기' }).hasAttribute('disabled')).toBe(false));
			await fireEvent.click(screen.getByRole('button', { name: '임시 실행 기록 더 불러오기' }));
		}
		await screen.findByText('failed question');
		const expectedQuestions = ['legacy first question', 'legacy later question', 'first question', 'failed question', 'second question', 'current question'];
		expect([...view.container.querySelectorAll('[data-history-message-id] .user-text')].map((node) => node.textContent)).toEqual(expectedQuestions);
		expect(view.container.querySelector('[data-history-message-id="temp:run-F:assistant"]')?.textContent).toContain('failed answer');
		expect(view.container.querySelector('[data-history-message-id="saved:9"], [data-history-message-id="temp:run-1:assistant"]')?.querySelector('.execution-timeline')).toBe(currentTimeline);
		const detached = view.container.querySelector<HTMLDetailsElement>('[data-temporary-unpositioned]')!;
		expect(detached.open).toBe(false);
		await fireEvent.click(detached.querySelector('summary')!);
		expect(detached.textContent).toContain('대화 내 순서를 확인할 수 없어');
		expect(detached.textContent).toContain('legacy failed answer');
		await fireEvent.click(detached.querySelector('.execution-timeline > summary')!);
		await fireEvent.click(detached.querySelector('.tool-category > summary')!);
		await fireEvent.click(detached.querySelector<HTMLButtonElement>('.tool-head')!);
		expect(detached.textContent).toContain('legacy recorded input');
		expect(detached.textContent).toContain('legacy recorded result');
		expect(detached.querySelectorAll('.execution-timeline')).toHaveLength(1);
		expect(screen.queryByRole('button', { name: '임시 실행 기록 더 불러오기' })).toBeNull();
		view.unmount();
		const reloaded = render(ChatPanel);
		await screen.findByText('current answer');
		expect([...reloaded.container.querySelectorAll('[data-history-message-id] .user-text')].map((node) => node.textContent)).toEqual(expectedQuestions);
		expect(reloaded.container.querySelectorAll('[data-temporary-run-id="legacy-failed"]')).toHaveLength(1);
		expect(mocks.followRun).toHaveBeenCalledTimes(1);
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it('follows an unpositioned active temporary journal separately without inventing its place in legacy history', async () => {
		const finish = Promise.withResolvers<void>();
		const observed = Promise.withResolvers<void>();
		let settled = false;
		const descriptor = { run_id: 'run-1', conversation_id: null, temp_thread_id: 'temp-1', status: 'running', run_kind: 'completion', events_url: '/events', cancel_url: '/cancel' };
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/temp-threads/temp-1') return {
				temp_thread_id: 'temp-1', active_run: settled ? null : descriptor, active_run_positioned: false,
				messages: [
					{ id: 'saved-user', role: 'user', content: 'legacy saved question', conversation_id: '', parent_id: null, created_at: at, temporary_history_order: [0, 1, 0] },
					{ id: 'saved-answer', role: 'assistant', content: 'legacy saved answer', conversation_id: '', parent_id: 'saved-user', created_at: at, temporary_history_order: [1, 1, 0] }
				],
				unpositioned_runs: [{
					run_id: 'run-1', run_kind: 'completion', status: settled ? 'completed' : 'running', model_name: 'model-1', order_unknown: true,
					input_parts: [{ type: 'text', text: 'unpositioned current question' }],
					parts: settled ? [{ type: 'text', text: 'unpositioned live answer' }] : [],
					activity: settled ? [
						{ id: 'stage:1', kind: 'stage', seq: 1, createdAt: at, stage: 'queued', toolName: null },
						{ id: 'terminal:4', kind: 'terminal', seq: 4, createdAt: at, status: 'completed', errorCode: null, message: null }
					] : []
				}]
			};
			return fallback(path, ...args);
		});
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'run.stage.changed', { stage: 'queued', tool_name: null });
			yield event(2, 'message.created', { message_id: 'unpositioned-answer', role: 'assistant', parent_id: null });
			yield event(3, 'part.completed', { message_id: 'unpositioned-answer', part_index: 0, part: { type: 'text', text: 'unpositioned live answer' } });
			observed.resolve();
			await finish.promise;
			settled = true;
			yield event(4, 'run.completed', { status: 'completed', message_id: 'unpositioned-answer' });
		});
		sessionStorage.setItem('chat:tempThreadId:domain-1:user-1:project-1', 'temp-1');
		const view = render(ChatPanel);
		await observed.promise;
		flushAnimationFrames();
		await tick();
		expect([...view.container.querySelectorAll('[data-history-message-id] .user-text')].map((node) => node.textContent)).toEqual(['legacy saved question']);
		const detached = view.container.querySelector<HTMLDetailsElement>('[data-temporary-unpositioned]')!;
		await fireEvent.click(detached.querySelector('summary')!);
		expect(detached.textContent).toContain('unpositioned live answer');
		expect(detached.textContent).toContain('대화 내 순서를 확인할 수 없어');
		const timeline = detached.querySelector<HTMLDetailsElement>('.execution-timeline')!;
		timeline.open = false;
		await fireEvent(timeline, new Event('toggle'));
		finish.resolve();
		await waitFor(() => expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull());
		expect(detached.querySelector('.execution-timeline')).toBe(timeline);
		expect(timeline.open).toBe(false);
		expect(timeline.querySelector('[data-run-outcome="completed"]')).toBeTruthy();
		expect(view.container.querySelectorAll('[data-history-message-id]')).toHaveLength(2);
		view.unmount();
		const reloaded = render(ChatPanel);
		await screen.findByText('legacy saved answer');
		expect(reloaded.container.querySelectorAll('[data-history-message-id]')).toHaveLength(2);
		expect(reloaded.container.querySelector('[data-temporary-run-id="run-1"]')?.textContent).toContain('unpositioned live answer');
		expect(mocks.followRun).toHaveBeenCalledTimes(1);
	});

	it('stops an unpositioned timeline after follow failure without inventing a terminal outcome and resumes on reload', async () => {
		const fail = Promise.withResolvers<void>();
		const finish = Promise.withResolvers<void>();
		const observed = Promise.withResolvers<void>();
		const resumedObserved = Promise.withResolvers<void>();
		let attachments = 0;
		const descriptor = { run_id: 'run-1', conversation_id: null, temp_thread_id: 'temp-1', status: 'running', run_kind: 'completion', events_url: '/events', cancel_url: '/cancel' };
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/temp-threads/temp-1') return {
				temp_thread_id: 'temp-1', active_run: descriptor, active_run_positioned: false, messages: [],
				unpositioned_runs: [{
					run_id: 'run-1', run_kind: 'completion', status: 'running', model_name: 'model-1', order_unknown: true,
					input_parts: [{ type: 'text', text: 'unpositioned question' }], parts: [], activity: []
				}]
			};
			return fallback(path, ...args);
		});
		mocks.followRun.mockImplementation(async function* () {
			const attempt = ++attachments;
			yield event(1, 'run.stage.changed', { stage: 'model_request', tool_name: null });
			yield event(2, 'message.created', { message_id: 'unpositioned-answer', role: 'assistant', parent_id: null });
			yield event(3, 'part.completed', { message_id: 'unpositioned-answer', part_index: 0, part: { type: 'text', text: 'retained partial answer' } });
			if (attempt === 1) {
				observed.resolve();
				await fail.promise;
				throw new Error('journal follow unavailable');
			}
			resumedObserved.resolve();
			await finish.promise;
			yield event(4, 'run.completed', { status: 'completed', message_id: 'unpositioned-answer' });
		});
		sessionStorage.setItem('chat:tempThreadId:domain-1:user-1:project-1', 'temp-1');
		const view = render(ChatPanel);
		await observed.promise;
		flushAnimationFrames();
		await tick();
		const detached = view.container.querySelector('[data-temporary-run-id="run-1"]')!;
		const timeline = detached.querySelector<HTMLDetailsElement>('.execution-timeline')!;
		expect(timeline.querySelector('li.live')).toBeTruthy();
		const statusBeforeFailure = detached.querySelector('code:nth-of-type(3)')?.textContent;
		timeline.open = false;
		await fireEvent(timeline, new Event('toggle'));
		fail.resolve();
		await screen.findByText('journal follow unavailable');
		await waitFor(() => expect(timeline.querySelector('li.live')).toBeNull());
		expect(detached.querySelector('.execution-timeline')).toBe(timeline);
		expect(timeline.open).toBe(false);
		expect(detached.textContent).toContain('retained partial answer');
		expect(detached.querySelector('code:nth-of-type(3)')?.textContent).toBe(statusBeforeFailure);
		expect(timeline.querySelector('[data-run-outcome]')).toBeNull();
		expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull();
		view.unmount();

		const reloaded = render(ChatPanel);
		await resumedObserved.promise;
		expect(mocks.followRun).toHaveBeenCalledTimes(2);
		flushAnimationFrames();
		await tick();
		const resumed = reloaded.container.querySelector('[data-temporary-run-id="run-1"]')!;
		await waitFor(() => expect(resumed.querySelector('li.live')).toBeTruthy());
		finish.resolve();
		await waitFor(() => expect(resumed.querySelector('[data-run-outcome="completed"]')).toBeTruthy());
		expect(resumed.querySelector('li.live')).toBeNull();
		expect(resumed.textContent).toContain('retained partial answer');
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it.each([
		['persistent', 'run.completed'], ['persistent', 'run.failed'], ['persistent', 'run.canceled'],
		['temporary', 'run.completed'], ['temporary', 'run.failed'], ['temporary', 'run.canceled'],
		['resumed', 'run.completed'], ['resumed', 'run.failed'], ['resumed', 'run.canceled'],
		['temporary-resumed', 'run.completed'], ['temporary-resumed', 'run.failed'], ['temporary-resumed', 'run.canceled']
	] as const)('keeps the actual %s ChatPanel timeline and disclosures through %s and reload', async (mode, terminal) => {
		const temporary = mode.startsWith('temporary');
		const resumed = mode.endsWith('resumed');
		const finish = Promise.withResolvers<void>();
		const observed = Promise.withResolvers<void>();
		let settled = false;
		const descriptor = {
			run_id: 'run-1', conversation_id: temporary ? null : 'history-chat',
			temp_thread_id: temporary ? 'temp-1' : null, status: 'running',
			run_kind: 'completion', events_url: '/events', cancel_url: '/cancel'
		};
		const journal = [
			event(1, 'run.stage.changed', { stage: 'queued', tool_name: null }),
			event(2, 'message.created', { message_id: 'tool-answer', role: 'assistant', parent_id: null }),
			event(3, 'context.updated', { state: await mocks.previewContext(), phase: 'compacting', cause: 'automatic', before_tokens: 12000, after_tokens: null }),
			event(4, 'context.updated', { state: await mocks.previewContext(), phase: 'compacted', cause: 'automatic', before_tokens: 12000, after_tokens: 7000 }),
			event(5, 'run.stage.changed', { stage: 'model_request', tool_name: null }),
			event(6, 'run.stage.changed', { stage: 'model_response', tool_name: null }),
			event(7, 'tool.approval_required', {
				call_id: 'lookup', name: 'lookup', source: 'builtin', effect: 'read', destination: null,
				redacted_arguments: { query: '기록한 인자' }, preview: [{ type: 'text', text: '기록한 승인 미리보기' }],
				expected_state_revision: null, writer_fence: null, expires_at: '2026-07-26T00:10:00Z'
			}),
			event(8, 'tool.approval_resolved', { call_id: 'lookup', decision: 'approve', decided_by_user_id: 'user-1', decided_at: at }),
			event(9, 'run.stage.changed', { stage: 'tool_execution', tool_name: 'lookup' }),
			event(10, 'tool.call.started', { call_id: 'lookup', name: 'lookup', arguments: { query: '기록한 인자' }, source: 'builtin', category: '기본 도구' }),
			event(11, 'tool.call.progress', { call_id: 'lookup', name: 'lookup', text: '기록한 도구 진행' }),
			event(12, 'tool.call.completed', { call_id: 'lookup', name: 'lookup', status: 'completed', content: [{ type: 'text', text: '기록한 도구 결과' }] }),
			event(13, 'child.created', { child_run_id: 'child-1', call_id: 'delegate', wait_group_id: 'group-1', agent_id: 2, access: 'read', ordinal: 0, status: 'queued' }),
			event(14, 'child.completed', { child_run_id: 'child-1', call_id: 'delegate', wait_group_id: 'group-1', status: 'completed', summary: '기록한 하위 결과', artifacts: [] }),
			event(15, 'message.created', { message_id: 'answer', role: 'assistant', parent_id: 'tool-answer' }),
			event(16, 'run.stage.changed', { stage: 'response_writing', tool_name: null }),
			event(17, 'part.completed', { message_id: 'answer', part_index: 0, part: { type: 'text', text: '기록한 최종 답변' } }),
			event(18, 'run.stage.changed', { stage: 'finalizing', tool_name: null }),
		];
		const terminalEvent = terminal === 'run.completed'
			? event(19, terminal, { status: 'completed', message_id: 'answer' })
			: event(19, terminal, { status: terminal === 'run.failed' ? 'failed' : 'canceled', message_id: 'answer', error_code: 'interrupted', safe_message: '기록한 중단' });
		const state = [...journal, terminalEvent].reduce(reduceRunEvent, createRunViewState('run-1'));
		const answer = {
			id: 'answer', conversation_id: temporary ? '' : 'history-chat', parent_id: 'tool-answer',
			role: 'assistant', content: '기록한 최종 답변', model_name: 'model-1', created_at: at,
			execution: { run_id: 'run-1', status: state.status, activity: state.activity }
		};
		const persisted = [
			{ id: 'question', role: 'user', conversation_id: answer.conversation_id, parent_id: null, content: '확인해 주세요', created_at: at },
			{ id: 'tool-answer', role: 'assistant', conversation_id: answer.conversation_id, parent_id: 'question', content: '', created_at: at, parts: [
				{ type: 'tool_call', call_id: 'lookup', name: 'lookup', arguments: { query: '기록한 인자' }, status: 'completed' },
				{ type: 'tool_result', call_id: 'lookup', name: 'lookup', content: [{ type: 'text', text: '기록한 도구 결과' }], is_error: false }
			] },
			answer
		];
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') return temporary ? [] : [{ id: 'history-chat', title: '기록 대화', model_name: 'model-1', workspace_id: null }];
			if (path.includes('/history-chat/messages?')) return {
				messages: settled ? persisted : [], active_leaf_id: settled ? 'answer' : null,
				history_revision: 1, has_before: false, has_after: false, before_cursor: null, after_cursor: null
			};
			if (path === '/api/v1/chat/conversations/history-chat/runs?active=true') return resumed && !settled ? [descriptor] : [];
			if (path === '/api/v1/chat/temp-threads/temp-1') return {
				temp_thread_id: 'temp-1', messages: settled ? persisted : persisted.slice(0, 1),
				active_run: settled ? null : descriptor, latest_run: { ...descriptor, status: state.status }
			};
			return fallback(path, ...args);
		});
		mocks.createRun.mockResolvedValue(descriptor);
		mocks.followRun.mockImplementation(async function* () {
			for (const item of journal) yield item;
			observed.resolve();
			await finish.promise;
			settled = true;
			yield terminalEvent;
		});
		if (resumed && temporary) sessionStorage.setItem('chat:tempThreadId:domain-1:user-1:project-1', 'temp-1');
		const view = render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		if (!temporary) await fireEvent.click(await screen.findByText('기록 대화'));
		if (!resumed) {
			if (temporary) await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
			await fireEvent.input(screen.getByRole('textbox'), { target: { value: '확인해 주세요' } });
			await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		}
		await observed.promise;
		flushAnimationFrames();
		await tick();
		const timeline = view.container.querySelector<HTMLDetailsElement>('.execution-timeline')!;
		expect(timeline).toBeTruthy();
		expect(view.container.querySelectorAll('.execution-timeline')).toHaveLength(1);
		const category = timeline.querySelector<HTMLDetailsElement>('.tool-category')!;
		const tool = timeline.querySelector<HTMLButtonElement>('.tool-card .tool-head')!;
		timeline.open = true;
		category.open = true;
		await fireEvent(timeline, new Event('toggle'));
		await fireEvent(category, new Event('toggle'));
		await fireEvent.click(tool);
		const stepLabels = [...timeline.querySelectorAll('ol > li')].map((item) => item.textContent);
		finish.resolve();
		await waitFor(() => expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull());
		expect(view.container.querySelector('.execution-timeline')).toBe(timeline);
		expect(timeline.open && category.open).toBe(true);
		expect(tool.getAttribute('aria-expanded')).toBe('true');
		expect(timeline.querySelectorAll('.tool-card')).toHaveLength(1);
		expect(timeline.querySelector(`[data-run-outcome="${state.status}"]`)).toBeTruthy();
		expect(timeline.querySelectorAll('ol > li')).toHaveLength(stepLabels.length + 1);
		expect(timeline.textContent).toContain('기록한 하위 결과');
		expect(timeline.textContent).toContain('기록한 도구 진행');
		expect(timeline.textContent).toContain('기록한 인자');
		expect(timeline.textContent).toContain('기록한 승인 미리보기');
		const settledLabels = [...timeline.querySelectorAll('ol > li')].map((item) => item.textContent);
		view.unmount();
		const revisited = render(ChatPanel);
		if (!temporary) await fireEvent.click(await screen.findByText('기록 대화'));
		await screen.findByText('기록한 최종 답변');
		const restored = revisited.container.querySelector<HTMLDetailsElement>('.execution-timeline')!;
		expect(restored).toBeTruthy();
		await fireEvent.click(restored.querySelector<HTMLButtonElement>('.tool-card .tool-head')!);
		expect([...restored.querySelectorAll('ol > li')].map((item) => item.textContent)).toEqual(settledLabels);
		expect(revisited.container.querySelectorAll('.execution-timeline')).toHaveLength(1);
		expect(restored.querySelectorAll('.tool-card')).toHaveLength(1);
		expect(restored.querySelector('.live')).toBeNull();
	});

	it.each(['run.completed', 'run.failed', 'run.canceled'] as const)('retains completed-only TTFT through conversation creation and %s history reload', async (terminal) => {
		let now = 1000;
		const clock = vi.spyOn(performance, 'now').mockImplementation(() => now);
		const fallback = mocks.get.getMockImplementation()!;
		mocks.post.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/conversations') {
				now = 2500;
				return { id: 'ttft-chat', title: 'TTFT 대화', model_name: 'model-1', workspace_id: null, updated_at: at };
			}
			return {};
		});
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path.includes('/ttft-chat/messages?')) return {
				messages: [{ id: 'answer', conversation_id: 'ttft-chat', parent_id: null, role: 'assistant', content: '완료된 답변', created_at: at }],
				active_leaf_id: 'answer', history_revision: 1, has_before: false, has_after: false, before_cursor: null, after_cursor: null
			};
			return fallback(path, ...args);
		});
		mocks.createRun.mockResolvedValue({ run_id: 'run-1', conversation_id: 'ttft-chat', temp_thread_id: null, status: 'running', run_kind: 'completion', events_url: '/events', cancel_url: '/cancel' });
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'message.created', { message_id: 'answer', role: 'assistant', parent_id: null });
			now = 3000;
			yield event(2, 'part.delta', { message_id: 'answer', part_index: 1, part_type: 'reasoning', delta: '추론만 도착' });
			now = 3750;
			yield event(3, 'part.completed', { message_id: 'answer', part_index: 0, part: { type: 'text', text: '완료된 답변' } });
			now = 8000;
			if (terminal === 'run.completed') {
				yield event(4, terminal, { status: 'completed', message_id: 'answer' });
			} else {
				yield event(4, terminal, { status: terminal === 'run.failed' ? 'failed' : 'canceled', message_id: 'answer', error_code: 'interrupted', safe_message: '중단됨' });
			}
		});
		try {
			render(ChatPanel);
			await screen.findByRole('button', { name: 'Model 1' });
			await fireEvent.input(screen.getByRole('textbox'), { target: { value: '답변해 주세요' } });
			await fireEvent.click(screen.getByRole('button', { name: '전송' }));
			await screen.findByText('완료된 답변');
			await waitFor(() => expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull());
			expect(screen.getByText('TTFT 2.75초')).toBeTruthy();
			expect(screen.queryByText(/tok\/s/)).toBeNull();
		} finally {
			clock.mockRestore();
		}
	});

	it('never invents TTFT while replaying a resumed active run', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		const descriptor = { run_id: 'run-1', conversation_id: 'ttft-resume', temp_thread_id: null, status: 'running', run_kind: 'completion', events_url: '/events', cancel_url: '/cancel' };
		let completed = false;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') return [{ id: 'ttft-resume', title: '재연결 대화', model_name: 'model-1', workspace_id: null }];
			if (path.includes('/ttft-resume/messages?')) return {
				messages: completed ? [{ id: 'answer', conversation_id: 'ttft-resume', role: 'assistant', content: '재생된 답변', created_at: at }] : [],
				active_leaf_id: completed ? 'answer' : null, history_revision: 1, has_before: false, has_after: false, before_cursor: null, after_cursor: null
			};
			if (path === '/api/v1/chat/conversations/ttft-resume/runs?active=true') return [descriptor];
			return fallback(path, ...args);
		});
		const finish = Promise.withResolvers<void>();
		const observed = Promise.withResolvers<void>();
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'message.created', { message_id: 'answer', role: 'assistant', parent_id: null });
			yield event(2, 'part.delta', { message_id: 'answer', part_index: 0, part_type: 'text', delta: '재생된 답변' });
			observed.resolve();
			await finish.promise;
			completed = true;
			yield event(3, 'run.completed', { status: 'completed', message_id: 'answer' });
		});
		render(ChatPanel);
		await fireEvent.click(await screen.findByText('재연결 대화'));
		await observed.promise;
		expect(screen.queryByText(/TTFT/)).toBeNull();
		finish.resolve();
		await waitFor(() => expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull());
		expect(await screen.findByText('재생된 답변')).toBeTruthy();
		expect(screen.queryByText(/TTFT/)).toBeNull();
	});
	it('sends chat-only text with tool defaults explicitly disabled', async () => {
		grantLumen('lumen-chat_user');
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Text only' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalled());
		expect(mocks.createRun.mock.calls[0][1].features.tool_policy).toMatchObject({ mode: 'none', enabled_tool_ids: [], enabled_mcp_ids: [] });
	});

	it('does not send while permissions are pending or failed', async () => {
		pendingLumen();
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		expect(screen.getByRole('button', { name: '전송' }).hasAttribute('disabled')).toBe(true);
		pendingLumen('Permission service unavailable');
		await tick();
		expect(screen.getAllByRole('alert').some((item) => item.textContent?.includes('Permission service unavailable'))).toBe(true);
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

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

	it('shows the model request status without exposing a raw proxy response', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) =>
			path === '/api/v1/chat/models'
				? Promise.reject(new mocks.ApiError('secret upstream body', 503))
				: fallback(path, ...args));
		render(ChatPanel);
		await fireEvent.click(screen.getByRole('button', { name: /모델/ }));
		expect(await screen.findByText(/HTTP 503/)).toBeTruthy();
		expect(screen.queryByText(/secret upstream body/)).toBeNull();
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
		setVerifiedLumenActor({ ...get(auth), projectId: 'project-2' });
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
		let now = 1000;
		const clock = vi.spyOn(performance, 'now').mockImplementation(() => now);
		const finish = Promise.withResolvers<void>();
		const observed = Promise.withResolvers<void>();
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'message.created', { message_id: 'retry-answer', role: 'assistant', parent_id: null });
			now = 10500;
			yield event(2, 'part.completed', { message_id: 'retry-answer', part_index: 0, part: { type: 'text', text: '재시도 답변' } });
			observed.resolve();
			await finish.promise;
			yield event(3, 'run.completed', { status: 'completed', message_id: 'retry-answer' });
		});
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

		try {
		render(ChatPanel);
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '실패 후 재전송' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));

		await screen.findByText('응답 생성에 실패했습니다');
		expect(screen.getByText('실패 후 재전송')).toBeTruthy();
		expect(screen.queryByText(/TTFT/)).toBeNull();
		now = 10000;
		const retryButton = screen.getByRole('button', { name: '다시 전송' });
		await fireEvent.click(retryButton);
		await fireEvent.click(retryButton);

		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(2));
		const firstOptions = mocks.createRun.mock.calls[0][2];
		const retryOptions = mocks.createRun.mock.calls[1][2];
		expect(retryOptions.idempotencyKey).toBe(firstOptions.idempotencyKey);
		retry.resolve({
			run_id: 'run-1',
			conversation_id: 'conversation-1',
			temp_thread_id: null,
			status: 'queued',
			run_kind: 'completion',
			events_url: '/events',
			cancel_url: '/cancel'
		});
		await observed.promise;
		now = 10600;
		await waitFor(() => { flushAnimationFrames(); expect(screen.getByText('TTFT 0.5초')).toBeTruthy(); });
		finish.resolve();
		await waitFor(() => expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull());
		} finally {
			clock.mockRestore();
		}
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
	it('keeps a conversation creation failure actionable without revealing proxy body', async () => {
		mocks.post.mockRejectedValueOnce(new mocks.ApiError('secret upstream body', 503));
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '테스트' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await screen.findByRole('alert');
		expect(screen.queryByText(/secret upstream body/)).toBeNull();
	});

	it('shows the admission HTTP status and structured detail in the chat error bar', async () => {
		mocks.createRun.mockRejectedValue(new mocks.ChatHttpError('Model quota exceeded', 429));
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '테스트' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		expect(await screen.findByText('HTTP 429: Model quota exceeded')).toBeTruthy();
	});

	it('shows the safe failure code and detail after an accepted run, without an HTTP status', async () => {
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'run.failed', {
				status: 'failed', message_id: null,
				error_code: 'provider_unavailable', safe_message: '모델 제공자가 응답하지 않습니다.'
			});
		});
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: '테스트' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		expect(await screen.findByText('provider_unavailable: 모델 제공자가 응답하지 않습니다. (run: run-1)')).toBeTruthy();
		expect(screen.queryByText(/HTTP 202/)).toBeNull();
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
			const scroll = document.querySelector('.scroll') as HTMLDivElement;
			scroll.scrollTop = 0;
			await fireEvent.scroll(scroll);
			await waitFor(() => expect(mocks.get.mock.calls.some(([path]) => String(path).includes(`cursor=${cursor}`))).toBe(true));
		}

		await screen.findByText('history-1');
		expect(screen.queryByText('history-160')).toBeNull();
		const historyRequests = mocks.get.mock.calls.filter(([path]) => String(path).includes('/conv-history/messages?'));
		expect(historyRequests).toHaveLength(4);
		expect(document.querySelectorAll('[data-history-message-id]')).toHaveLength(120);
	});
	it('retains the selected transcript, draft and sidebar through project/history transitions', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') return [{ id: 'retained-chat', title: '계속 읽을 대화', model_name: 'model-1', workspace_id: null }];
			if (path.includes('/retained-chat/messages?')) return {
				messages: [{ id: 'retained-message', conversation_id: 'retained-chat', parent_id: null, role: 'user', content: '이미 읽고 있던 내용', created_at: at }],
				active_leaf_id: 'retained-message', history_revision: 1, has_before: false, has_after: false, before_cursor: null, after_cursor: null
			};
			return fallback(path, ...args);
		});
		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		await fireEvent.click(await screen.findByRole('button', { name: '계속 읽을 대화' }));
		await screen.findByText('이미 읽고 있던 내용');
		const editor = screen.getByRole('textbox') as HTMLTextAreaElement;
		const history = document.querySelector('.sidebar .list');
		await fireEvent.input(editor, { target: { value: '아직 보내지 않은 초안' } });
		const initialRequests = mocks.get.mock.calls.filter(([path]) => String(path) === '/api/v1/chat/conversations' || String(path).includes('/retained-chat/messages?')).length;
		for (let i = 0; i < 3; i++) {
			await fireEvent.click(screen.getByRole('button', { name: '대화 기록과 설정 열기' }));
			await fireEvent.click(screen.getByRole('button', { name: /^프로젝트$/ }));
			await screen.findByRole('heading', { name: '프로젝트' });
			await fireEvent.click(screen.getByRole('button', { name: '대화 기록과 설정 열기' }));
			await fireEvent.click(screen.getByRole('button', { name: '계속 읽을 대화' }));
			expect(screen.getByRole('textbox')).toBe(editor);
			expect(editor.value).toBe('아직 보내지 않은 초안');
			expect(document.querySelector('.sidebar .list')).toBe(history);
		}
		expect(mocks.get.mock.calls.filter(([path]) => String(path) === '/api/v1/chat/conversations' || String(path).includes('/retained-chat/messages?'))).toHaveLength(initialRequests);
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
		const scroll = document.querySelector('.scroll') as HTMLDivElement;
		scroll.scrollTop = 0;
		await fireEvent.scroll(scroll);

		await screen.findByText('refreshed-latest');
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

describe('ChatPanel cloud catalogue lifecycle', () => {
	const catalogue = (name = 'Research'): CloudToolsCatalogue => ({
		enabled: true, access_level: 'read', project_id: 'project-1', project_name: name,
		tool_count: 12, source: 'lumen', allowed_projects: [{ id: 'project-1', name }], selection_name: null,
	});
	function enableCloud(load: () => Promise<CloudToolsCatalogue>) {
		siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: true } }));
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/cloud-tools') return load();
			if (path === '/api/v1/chat/models') return Promise.resolve([{ id: 1, model_name: 'model-1', display_name: 'Model 1', capabilities: { tool_call: true } }]);
			return fallback(path, ...args);
		});
	}

	it('shows default cloud tools with zero custom entries without injecting a fake tool ID', async () => {
		enableCloud(async () => catalogue());
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await waitFor(() => expect((screen.getByRole('button', { name: '추가' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		expect(screen.getByRole('menuitem', { name: '클라우드 리소스' }).textContent).toContain('Research (project-1)');
		expect(screen.queryAllByRole('menuitemcheckbox')).toHaveLength(0);
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Inspect this project' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalled());
		expect(mocks.createRun.mock.calls[0][1].features.tool_policy).toMatchObject({ mode: 'agent_default', enabled_tool_ids: null, enabled_mcp_ids: null });
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/cloud-tools', 'token', 'project-1', { refresh: true, signal: expect.any(AbortSignal), suppressAuthRedirect: true });
	});

	it.each(['token', 'userId', 'projectId'] as const)('discards old cloud metadata after an ABA %s change', async (field) => {
		const old = Promise.withResolvers<CloudToolsCatalogue>();
		let requests = 0;
		enableCloud(() => ++requests === 1 ? old.promise : Promise.resolve(catalogue('Fresh owner')));
		render(ChatPanel);
		await waitFor(() => expect(requests).toBe(1));
		const initial = field === 'token' ? 'token' : field === 'userId' ? 'user-1' : 'project-1';
		auth.update((actor) => ({ ...actor, [field]: 'other-owner' }));
		// The returned actor has completed verification, but the old request's epoch is gone.
		setVerifiedLumenActor({ ...get(auth), [field]: initial });
		await waitFor(() => expect(requests).toBe(2));
		const oldSignal = mocks.get.mock.calls.find(([path]) => path === '/api/v1/chat/cloud-tools')![3].signal as AbortSignal;
		expect(oldSignal.aborted).toBe(true);
		await screen.findByRole('button', { name: 'Model 1' });
		await waitFor(() => expect((screen.getByRole('button', { name: '추가' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		expect(screen.getByRole('menuitem', { name: '클라우드 리소스' }).textContent).toContain('Fresh owner');
		old.resolve(catalogue('Prior owner secret project'));
		await tick();
		await tick();
		expect(screen.queryByText(/Prior owner secret project/)).toBeNull();
		expect(screen.getByRole('menuitem', { name: '클라우드 리소스' }).textContent).toContain('Fresh owner');
	});

	it('removes cloud metadata before project rescope and does not revive it after reload failure', async () => {
		let requests = 0;
		enableCloud(async () => {
			if (++requests > 1) throw new Error('Catalogue unavailable');
			return catalogue();
		});
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await waitFor(() => expect((screen.getByRole('button', { name: '추가' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		projectSwitching.set(true);
		await tick();
		expect(screen.queryByRole('menuitem', { name: '클라우드 리소스' })).toBeNull();
		projectSwitching.set(false);
		await waitFor(() => expect(requests).toBe(2));
		await tick();
		expect(screen.queryByRole('menuitem', { name: '클라우드 리소스' })).toBeNull();
	});
});

it('shows registered sources and factual tool progress before final text, then deduplicates final citations', async () => {
	const observed = Promise.withResolvers<void>();
	const finish = Promise.withResolvers<void>();
	const citation = { type: 'citation', citation_id: 'source-1', source_kind: 'web', url: 'https://example.org/queried', title: 'Queried page', snippet: 'Retrieved evidence' };
	mocks.followRun.mockImplementation(async function* () {
		yield event(1, 'message.created', { message_id: 'answer', role: 'assistant', parent_id: null });
		yield event(2, 'source.registered', { message_id: 'answer', citation });
		yield event(3, 'tool.call.started', { call_id: 'search-1', name: 'managed_web_search', arguments: { query: 'evidence' } });
		yield event(4, 'tool.call.progress', { call_id: 'search-1', name: 'managed_web_search', text: 'Read 2 selected pages' });
		observed.resolve();
		await finish.promise;
		yield event(5, 'tool.call.completed', { call_id: 'search-1', name: 'managed_web_search', content: [{ type: 'text', text: 'Retrieved evidence' }], status: 'completed' });
		yield event(6, 'part.completed', { message_id: 'answer', part_index: 1, part: citation });
		yield event(7, 'part.completed', { message_id: 'answer', part_index: 0, part: { type: 'text', text: 'Final answer' } });
		yield event(8, 'run.completed', { status: 'completed', message_id: 'answer' });
	});
	const view = render(ChatPanel);
	try {
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Find evidence' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await observed.promise;
		await waitFor(() => { flushAnimationFrames(); expect(screen.getByRole('link', { name: /Queried page/ })).toBeTruthy(); });
		expect(screen.queryByText('Final answer')).toBeNull();
		expect(screen.getByText('Read 2 selected pages')).toBeTruthy();
		finish.resolve();
		await waitFor(() => { flushAnimationFrames(); expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull(); });
		expect(screen.getAllByRole('link', { name: /Queried page/ })).toHaveLength(1);
		expect(screen.getByText('Final answer')).toBeTruthy();
	} finally {
		finish.resolve();
		view.unmount();
	}
});
