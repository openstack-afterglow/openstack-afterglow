import { grantLumen, pendingLumen, refreshLumenAuth, setVerifiedLumenActor } from './lumenPermissionFixture';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
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
import { experienceHealth, installExperienceCollector, type ExperienceCollectorController } from '$lib/utils/experience';

import { managedSandboxTools, setManagedSandboxTools } from '$lib/stores/managedSandboxTools';
import type { McpSettingsPage } from '$lib/api/mcpCatalog';
import { t as mcpT } from '$lib/i18n/ns/mcp-gallery';
import { t as studioT } from '$lib/i18n/ns/chat-studio';
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
		// Keep the client binding interface while these component tests own endpoint results.
		withExperience() { return this; },
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

function flushAnimationFrames(timestamp?: number) {
	const queued = [...animationFrames.values()];
	animationFrames.clear();
	for (const callback of queued) callback(timestamp ?? performance.now());
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
	localStorage.clear();
	mocks.setPageState({});
	siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
	setVerifiedLumenActor({
		token: 'token',
		sessionId: 'chat-test-session',
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
			return [{ id: 1, provider_id: 11, provider: 'Provider A', model_name: 'model-1', display_name: 'Model 1' }];
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
	it('retains the sidebar and shared inventories across a same-domain project change', async () => {
		const fallback = mocks.get.getMockImplementation()!;
		const history = { id: 'shared', title: 'Domain conversation', model_name: 'model-1', workspace_id: null, updated_at: at };
		mocks.get.mockImplementation((path: string, ...args: unknown[]) =>
			path === '/api/v1/chat/conversations' ? Promise.resolve([history]) : fallback(path, ...args));
		render(ChatPanel);
		const historyControl = await screen.findByRole('button', { name: '대화 기록과 설정 열기' });
		await fireEvent.click(historyControl);
		const row = await screen.findByText('Domain conversation');
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/workspaces', 'token', 'project-1'));
		projectSwitching.set(true);
		await tick();
		setVerifiedLumenActor({ ...get(auth), projectId: 'project-2', token: 'selected-token' });
		projectSwitching.set(false);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/usage', 'selected-token', 'project-2'));
		expect(screen.getByText('Domain conversation')).toBe(row);
		for (const endpoint of ['conversations', 'agents', 'workspaces', 'custom-tools', 'mcp-servers?active_only=true']) {
			expect(mocks.get.mock.calls.filter(([path]) => path === `/api/v1/chat/${endpoint}`)).toHaveLength(1);
		}
	});

	it('discards a late conversation list when the working domain changes', async () => {
		const previous = Promise.withResolvers<unknown[]>();
		const fallback = mocks.get.getMockImplementation()!;
		const history = (title: string) => ({ id: title, title, model_name: 'model-1', workspace_id: null, updated_at: at });
		mocks.get.mockImplementation((path: string, token: string, ...args: unknown[]) => path === '/api/v1/chat/conversations'
			? token === 'token' ? previous.promise : Promise.resolve([history('New domain conversation')])
			: fallback(path, token, ...args));
		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/conversations', 'token', 'project-1'));
		setVerifiedLumenActor({ ...get(auth), domainId: 'domain-2', projectId: 'project-2', token: 'other-domain' });
		expect(await screen.findByText('New domain conversation')).toBeTruthy();
		previous.resolve([history('Previous domain conversation')]);
		await tick();
		expect(screen.queryByText('Previous domain conversation')).toBeNull();
		expect(screen.getByText('New domain conversation')).toBeTruthy();
	});

	const duplicateRows = [
		{ id: 41, provider_id: 11, provider: 'Provider A', model_name: 'shared-model', display_name: 'Shared model' },
		{ id: 57, provider_id: 22, provider: 'Provider B', model_name: 'shared-model', display_name: 'Shared model' }
	];
	function loadDuplicateCatalog() {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...rest: unknown[]) => path === '/api/v1/chat/models'
			? Promise.resolve(duplicateRows) : fallback(path, ...rest));
	}

	it('persists the exact provider row and sends it after remount', async () => {
		loadDuplicateCatalog();
		const original = render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: 'Shared model · Provider A' }));
		const picker = within(screen.getByRole('dialog'));
		await fireEvent.click(picker.getByRole('button', { name: /Provider B/ }));
		await fireEvent.click(picker.getByRole('button', { name: 'Shared model 모델 선택' }));
		expect(localStorage.getItem('chat:lastModelId')).toBe('57');
		original.unmount();

		mocks.post.mockResolvedValue({ id: 'selected-provider', model_name: 'shared-model', workspace_id: null });
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Shared model · Provider B' });
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Use the second provider' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(mocks.createRun.mock.calls[0]?.[1]).toMatchObject({
			model_id: 'shared-model', model_row_id: 57
		}));
		expect(mocks.createRun.mock.calls[0][0]).toBe('/api/v1/chat/conversations/selected-provider/completions');
	});

	it('keeps the exact provider row when retained chat moves to another project in its domain', async () => {
		loadDuplicateCatalog();
		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: 'Shared model · Provider A' }));
		const picker = within(screen.getByRole('dialog'));
		await fireEvent.click(picker.getByRole('button', { name: /Provider B/ }));
		await fireEvent.click(picker.getByRole('button', { name: 'Shared model 모델 선택' }));
		const composer = screen.getByRole('textbox') as HTMLTextAreaElement;
		await fireEvent.input(composer, { target: { value: 'Keep provider B' } });

		projectSwitching.set(true);
		await tick();
		setVerifiedLumenActor({ ...get(auth), projectId: 'project-2', token: 'selected-token' });
		projectSwitching.set(false);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'selected-token', 'project-2'));
		await screen.findByRole('button', { name: 'Shared model · Provider B' });
		expect(screen.getByRole('textbox')).toBe(composer);
		expect(composer.value).toBe('Keep provider B');
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/chat/conversations')).toHaveLength(1);

		mocks.post.mockResolvedValue({ id: 'selected-provider', model_name: 'shared-model', workspace_id: null });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(mocks.createRun.mock.calls[0]?.[1]).toMatchObject({ model_id: 'shared-model', model_row_id: 57 }));
		expect(mocks.createRun.mock.calls[0][2]).toMatchObject({ token: 'selected-token', projectId: 'project-2' });
	});

	it('migrates a uniquely matching legacy chat model', async () => {
		localStorage.setItem('chat:lastModel', 'model-1');
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		expect(localStorage.getItem('chat:lastModelId')).toBe('1');
		expect(localStorage.getItem('chat:lastModel')).toBeNull();
	});

	it('leaves an ambiguous legacy name unselected and does not send it', async () => {
		loadDuplicateCatalog();
		localStorage.setItem('chat:lastModel', 'shared-model');
		render(ChatPanel);
		await fireEvent.click(screen.getByTitle('모델 선택'));
		const picker = within(screen.getByRole('dialog'));
		const choices = await picker.findAllByRole('button', { name: 'Shared model 모델 선택' });
		expect(choices.every((choice) => choice.getAttribute('aria-pressed') === 'false')).toBe(true);
		expect(localStorage.getItem('chat:lastModelId')).toBeNull();
		expect(localStorage.getItem('chat:lastModel')).toBe('shared-model');
	});

	const unreadyContext = { ready: false, reason_code: 'context_limit_unknown' } as const;
	const billingRows = [
		{ id: 1, provider_id: 11, provider: 'Provider A', model_name: 'model-1', display_name: 'Model 1', domain_billing: unreadyContext },
		{ id: 2, provider_id: 11, provider: 'Provider A', model_name: 'model-2', display_name: 'Model 2', domain_billing: { ready: true, reason_code: null } }
	];
	function loadBillingCatalog(rows: object[]) {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...rest: unknown[]) => path === '/api/v1/chat/models'
			? Promise.resolve(rows) : fallback(path, ...rest));
	}

	it('defaults to the first domain-billing-ready model and shows unready rows disabled with a reason', async () => {
		loadBillingCatalog(billingRows);
		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: 'Model 2' }));
		const picker = within(screen.getByRole('dialog'));
		const unready = picker.getByRole('button', { name: 'Model 1 모델 선택' });
		expect(unready.getAttribute('aria-disabled')).toBe('true');
		expect(picker.getByText(studioT('modelBilling.contextLimit'))).toBeTruthy();
		await fireEvent.click(unready);
		expect(screen.getByRole('dialog')).toBeTruthy();
		expect(localStorage.getItem('chat:lastModelId')).toBeNull();
	});

	it('replaces a remembered model that became unready and explains why', async () => {
		localStorage.setItem('chat:lastModelId', '1');
		loadBillingCatalog(billingRows);
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 2' });
		expect(screen.getByText(studioT('modelBilling.fallback', {
			previous: 'Model 1', next: 'Model 2', reason: studioT('modelBilling.contextLimit')
		}))).toBeTruthy();
		expect(localStorage.getItem('chat:lastModelId')).toBe('1');
		mocks.post.mockResolvedValue({ id: 'fallback-conversation', model_name: 'model-2', workspace_id: null });
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Use the ready model' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(mocks.createRun.mock.calls[0]?.[1]).toMatchObject({ model_id: 'model-2', model_row_id: 2 }));
	});

	it('selects nothing and guides the user when no model is ready for domain billing', async () => {
		loadBillingCatalog(billingRows.map((row) => ({ ...row, domain_billing: unreadyContext })));
		render(ChatPanel);
		expect(await screen.findByText(studioT('modelBilling.noneReady'))).toBeTruthy();
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Nothing can run' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(screen.getAllByText(studioT('modelBilling.noneReady')).length).toBeGreaterThan(1));
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it('maps a 422 domain_billing admission refusal to the localized reason', async () => {
		mocks.createRun.mockRejectedValue(new mocks.ChatHttpError('requested chat capability is not available: domain_billing (pricing_unavailable)', 422));
		mocks.post.mockResolvedValue({ id: 'refused-conversation', model_name: 'model-1', workspace_id: null });
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Refused at admission' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		expect(await screen.findByText(studioT('modelBilling.pricing'))).toBeTruthy();
	});

	it.each(['baseline', 'rich'] as const)('keeps %s unpositioned approval usable after SSE failure and restores its actual start after reload', async (shape) => {
		let decided = false;
		const descriptor = { run_id: 'run-1', conversation_id: null, temp_thread_id: 'temp-1', status: 'awaiting_input', run_kind: 'completion', events_url: '/events', cancel_url: '/cancel' };
		const request: RunActivityItem = {
			id: 'approval:owned-call', kind: 'approval', seq: 3, createdAt: at, callId: 'owned-call',
			name: 'inspect', effect: 'read', arguments: { target: '<redacted>' },
			preview: [{ type: 'text', text: 'Owned pending preview' }], expiresAt: '2099-01-01T00:00:00Z',
			destination: null, decision: null, decidedAt: null
		};
		const execution = () => ({
			run_id: 'run-1', run_kind: 'completion', status: decided ? 'completed' : 'awaiting_input', model_name: 'model-1',
			started_at: at, last_seq: decided ? 5 : 3, activity_status: 'available', activity_error_code: null,
			activity: [
				{ id: 'stage:2', kind: 'stage', seq: 2, createdAt: at, stage: 'model_request', toolName: null },
				{ ...request, decision: decided ? 'deny' : null, decidedAt: decided ? '2026-07-26T00:00:10Z' : null },
				...(decided ? [{ id: 'terminal:5', kind: 'terminal', seq: 5, createdAt: '2026-07-26T00:00:12Z', status: 'completed', errorCode: null, message: null }] : [])
			]
		});
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path !== '/api/v1/chat/temp-threads/temp-1') return fallback(path, ...args);
			const base = { temp_thread_id: 'temp-1', active_run: decided ? null : descriptor };
			return shape === 'baseline' ? {
				...base, latest_run: descriptor, latest_run_execution: execution(),
				public_history: [
					{ role: 'user', parts: [{ type: 'text', text: 'Saved question' }] },
					{ role: 'assistant', parts: [{ type: 'text', text: 'Saved answer' }] }
				]
			} : {
				...base, active_run_positioned: false,
				messages: [
					{ id: 'saved-user', role: 'user', content: 'Saved question', conversation_id: '', parent_id: null, created_at: at },
					{ id: 'saved-answer', role: 'assistant', content: 'Saved answer', conversation_id: '', parent_id: 'saved-user', created_at: at }
				],
				unpositioned_runs: [{ ...execution(), input_parts: [], parts: [], order_unknown: true }]
			};
		});
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'run.started', { conversation_id: null, temp_thread_id: 'temp-1', model_name: 'model-1', effective_features: {}, run_kind: 'completion' });
			yield event(2, 'run.stage.changed', { stage: 'model_request', tool_name: null });
			yield event(3, 'tool.approval_required', {
				call_id: 'owned-call', name: 'inspect', source: 'mcp', effect: 'read', destination: null,
				redacted_arguments: { target: '<redacted>' }, preview: request.preview,
				expected_state_revision: null, writer_fence: null, expires_at: request.expiresAt
			});
			throw new Error('Follower disconnected');
		});
		mocks.post.mockImplementation(async (path: string) => {
			if (path === '/api/v1/chat/runs/run-1/approvals/owned-call') decided = true;
			return { run_id: 'run-1', call_id: 'owned-call', decision: 'deny', status: 'denied', run_status: 'completed' };
		});
		sessionStorage.setItem('chat:tempThreadId:domain-1:user-1:project-1', 'temp-1');
		let view = render(ChatPanel);
		await screen.findByText('Follower disconnected');
		const detached = view.container.querySelector<HTMLDetailsElement>('[data-temporary-unpositioned]')!;
		expect(detached.open).toBe(true);
		expect(detached.querySelector('.execution-timeline[open]')).toBeTruthy();
		expect(screen.getByText('Owned pending preview')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '거부' }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/runs/run-1/approvals/owned-call', { decision: 'deny' }, 'token', 'project-1');
		await waitFor(() => expect(screen.queryByRole('button', { name: '이번만 허용하기' })).toBeNull());
		view.unmount();
		view = render(ChatPanel);
		await screen.findByText('Saved answer');
		await fireEvent.click(view.container.querySelector('[data-temporary-unpositioned] > summary')!);
		const summary = screen.getByText('12초 동안 작업함');
		expect((summary.closest('details') as HTMLDetailsElement).open).toBe(false);
		await fireEvent.click(summary);
		expect(screen.getByText('거부 · inspect')).toBeTruthy();
		expect(screen.queryByRole('button', { name: '이번만 허용하기' })).toBeNull();
		expect([...view.container.querySelectorAll('[data-history-message-id] .user-text')].map((node) => node.textContent)).toEqual(['Saved question']);
		view.unmount();
	});

	it('retains a positioned temporary pending card after follower error and sends its current run decision', async () => {
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'tool.approval_required', {
				call_id: 'positioned-call', name: 'inspect', source: 'mcp', effect: 'read', destination: null,
				redacted_arguments: {}, preview: [{ type: 'text', text: 'Positioned pending preview' }],
				expected_state_revision: null, writer_fence: null, expires_at: '2099-01-01T00:00:00Z'
			});
			throw new Error('Positioned follower disconnected');
		});
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => path === '/api/v1/chat/temp-threads/temp-1'
			? { temp_thread_id: 'temp-1', public_history: [], active_run: null, latest_run: null, latest_run_execution: null }
			: fallback(path, ...args));
		const view = render(ChatPanel);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'token', 'project-1'));
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Inspect' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await screen.findByText('Positioned follower disconnected');
		expect(screen.getByText('Positioned pending preview').closest('[data-history-message-id]')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '거부' }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/runs/run-1/approvals/positioned-call', { decision: 'deny' }, 'token', 'project-1');
		view.unmount();
	});

	it('does not reactivate a snapshot-decided approval when its older required event replays before another disconnect', async () => {
		const descriptor = { run_id: 'run-1', conversation_id: null, temp_thread_id: 'temp-1', status: 'running', run_kind: 'completion', events_url: '/events', cancel_url: '/cancel' };
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => path === '/api/v1/chat/temp-threads/temp-1' ? {
			temp_thread_id: 'temp-1', public_history: [], active_run: descriptor, latest_run: descriptor,
			latest_run_execution: {
				run_id: 'run-1', run_kind: 'completion', status: 'running', model_name: 'model-1', started_at: at, last_seq: 4,
				activity_status: 'available', activity_error_code: null, activity: [{
					id: 'approval:old-call', kind: 'approval', seq: 3, createdAt: at, callId: 'old-call', name: 'inspect',
					effect: 'read', arguments: {}, preview: [], expiresAt: '2099-01-01T00:00:00Z',
					destination: null, decision: 'deny', decidedAt: at
				}]
			}
		} : fallback(path, ...args));
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'run.started', { conversation_id: null, temp_thread_id: 'temp-1', model_name: 'model-1', effective_features: {}, run_kind: 'completion' });
			yield event(2, 'run.stage.changed', { stage: 'model_request', tool_name: null });
			yield event(3, 'tool.approval_required', {
				call_id: 'old-call', name: 'inspect', source: 'mcp', effect: 'read', destination: null,
				redacted_arguments: {}, preview: [], expected_state_revision: null, writer_fence: null,
				expires_at: '2099-01-01T00:00:00Z'
			});
			throw new Error('Replay follower disconnected');
		});
		sessionStorage.setItem('chat:tempThreadId:domain-1:user-1:project-1', 'temp-1');
		const view = render(ChatPanel);
		await screen.findByText('Replay follower disconnected');
		expect(screen.queryByRole('button', { name: '이번만 허용하기' })).toBeNull();
		expect(screen.queryByRole('button', { name: '거부' })).toBeNull();
		expect(screen.getByText('거부 · inspect')).toBeTruthy();
		view.unmount();
	});

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
	] as const)('keeps the actual %s ChatPanel timeline and disclosures through %s and reload without collecting raw chat content', async (mode, terminal) => {
		const temporary = mode.startsWith('temporary');
		const resumed = mode.endsWith('resumed');
		const finish = Promise.withResolvers<void>();
		const observed = Promise.withResolvers<void>();
		const streamed = Promise.withResolvers<void>();
		const continueStream = Promise.withResolvers<void>();
		const canaries = {
			prompt: 'CHAT_PROMPT_PRIVATE_8f9a',
			credential: 'CHAT_CREDENTIAL_PRIVATE_b28c',
			stream: 'CHAT_STREAM_PRIVATE_c71d',
			output: 'CHAT_OUTPUT_PRIVATE_d24e',
			arguments: 'CHAT_ARGUMENTS_PRIVATE_e53f',
			preview: 'CHAT_PREVIEW_PRIVATE_f86a',
			progress: 'CHAT_PROGRESS_PRIVATE_a19b',
			result: 'CHAT_RESULT_PRIVATE_b42c',
			child: 'CHAT_CHILD_PRIVATE_c75d',
			error: 'CHAT_ERROR_PRIVATE_d08e'
		};
		const prompt = `확인해 주세요 ${canaries.prompt} Bearer ${canaries.credential}`;
		const streamedAnswer = `기록한 스트림 ${canaries.stream}`;
		const finalAnswer = `${streamedAnswer} 기록한 최종 답변 ${canaries.output}`;
		const toolArguments = { query: `기록한 인자 ${canaries.arguments}` };
		const toolResult = `기록한 도구 결과 ${canaries.result}`;
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
				redacted_arguments: toolArguments, preview: [{ type: 'text', text: `기록한 승인 미리보기 ${canaries.preview}` }],
				expected_state_revision: null, writer_fence: null, expires_at: '2026-07-26T00:10:00Z'
			}),
			event(8, 'tool.approval_resolved', { call_id: 'lookup', decision: 'approve', decided_by_user_id: 'user-1', decided_at: at }),
			event(9, 'run.stage.changed', { stage: 'tool_execution', tool_name: 'lookup' }),
			event(10, 'tool.call.started', { call_id: 'lookup', name: 'lookup', arguments: toolArguments, source: 'builtin', category: '기본 도구' }),
			event(11, 'tool.call.progress', { call_id: 'lookup', name: 'lookup', text: `기록한 도구 진행 ${canaries.progress}` }),
			event(12, 'tool.call.completed', { call_id: 'lookup', name: 'lookup', status: 'completed', content: [{ type: 'text', text: toolResult }] }),
			event(13, 'child.created', { child_run_id: 'child-1', call_id: 'delegate', wait_group_id: 'group-1', agent_id: 2, access: 'read', ordinal: 0, status: 'queued' }),
			event(14, 'child.completed', { child_run_id: 'child-1', call_id: 'delegate', wait_group_id: 'group-1', status: 'completed', summary: `기록한 하위 결과 ${canaries.child}`, artifacts: [] }),
			event(15, 'message.created', { message_id: 'answer', role: 'assistant', parent_id: 'tool-answer' }),
			event(16, 'run.stage.changed', { stage: 'response_writing', tool_name: null }),
			event(17, 'part.delta', { message_id: 'answer', part_index: 0, part_type: 'text', delta: streamedAnswer }),
			event(18, 'part.completed', { message_id: 'answer', part_index: 0, part: { type: 'text', text: finalAnswer } }),
			event(19, 'run.stage.changed', { stage: 'finalizing', tool_name: null }),
		];
		const terminalEvent = terminal === 'run.completed'
			? event(20, terminal, { status: 'completed', message_id: 'answer' })
			: event(20, terminal, { status: terminal === 'run.failed' ? 'failed' : 'canceled', message_id: 'answer', error_code: 'interrupted', safe_message: `기록한 중단 ${canaries.error}` });
		const state = [...journal, terminalEvent].reduce(reduceRunEvent, createRunViewState('run-1'));
		const answer = {
			id: 'answer', conversation_id: temporary ? '' : 'history-chat', parent_id: 'tool-answer',
			role: 'assistant', content: finalAnswer, model_name: 'model-1', created_at: at,
			execution: { run_id: 'run-1', status: state.status, activity: state.activity }
		};
		const persisted = [
			{ id: 'question', role: 'user', conversation_id: answer.conversation_id, parent_id: null, content: prompt, created_at: at },
			{ id: 'tool-answer', role: 'assistant', conversation_id: answer.conversation_id, parent_id: 'question', content: '', created_at: at, parts: [
				{ type: 'tool_call', call_id: 'lookup', name: 'lookup', arguments: toolArguments, status: 'completed' },
				{ type: 'tool_result', call_id: 'lookup', name: 'lookup', content: [{ type: 'text', text: toolResult }], is_error: false }
			] },
			answer
		];
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') return temporary ? [] : [{ id: 'history-chat', title: '기록 대화', model_name: 'model-1', workspace_id: null }];
			if (path.includes('/history-chat/messages?')) return {
				messages: settled ? persisted : resumed ? persisted.slice(0, 1) : [], active_leaf_id: settled ? 'answer' : resumed ? 'question' : null,
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
			for (const item of journal) {
				yield item;
				if (item.type === 'part.delta') {
					streamed.resolve();
					await continueStream.promise;
				}
			}
			observed.resolve();
			await finish.promise;
			settled = true;
			yield terminalEvent;
		});
		if (resumed && temporary) sessionStorage.setItem('chat:tempThreadId:domain-1:user-1:project-1', 'temp-1');
		const wireEvents: { event_type: string; trace_id: string; feature: string; component: string; payload: { state?: string; step?: number; stage?: string; reason?: string } }[] = [];
		const wireBodies: string[] = [];
		const originalFetch = window.fetch;
		let collector: ExperienceCollectorController | undefined;
		// $lib/api/client and $lib/api/chatStream are mocked, as is collector HTTP acceptance.
		// ChatPanel's state/applied/committed instrumentation, reveal/reducer/render path
		// and collector serialization are real; API/stream experience binding is not exercised.
		{
			window.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
				if (String(input).endsWith('/experience-contract')) return Response.json({ schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 });
				if (!String(input).endsWith('/experience-events')) throw new Error('Unexpected replay fixture transport');
				const body = String(init?.body);
				wireBodies.push(body);
				const batch = JSON.parse(body);
				wireEvents.push(...batch.events);
				return Response.json({ schema_version: 2, accepted: batch.events.length, duplicates: 0 }, { status: 201 });
			});
			collector = installExperienceCollector({
				getOwner: () => get(auth), getRoute: () => '/dashboard/chat',
				getBaseUrl: () => 'http://localhost:8000', isEnabled: () => true, isSuppressed: () => false,
				subscribeOwner: (changed) => auth.subscribe(changed),
			});
		}
		try {
		const view = render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		if (!temporary) await fireEvent.click(await screen.findByText('기록 대화'));
		if (!resumed) {
			if (temporary) await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
			const composer = screen.getByRole('textbox') as HTMLTextAreaElement;
			await fireEvent.input(composer, { target: { value: prompt } });
			expect(composer.value).toBe(prompt);
			await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		}
		await streamed.promise;
		flushAnimationFrames(performance.now() + 50);
		await tick();
		await waitFor(() => expect(view.container.textContent).toContain(canaries.stream));
		expect(view.container.textContent).not.toContain(canaries.output);
		expect(view.container.textContent).toContain(canaries.prompt);
		expect(view.container.textContent).toContain(canaries.credential);
		continueStream.resolve();
		await observed.promise;
		// The manual RAF fixture must advance past ChatPanel's 50ms projection pacing.
		flushAnimationFrames(performance.now() + 100);
		await tick();
		await waitFor(() => expect(view.container.textContent).toContain(canaries.output));
		const timeline = view.container.querySelector<HTMLDetailsElement>('.execution-timeline')!;
		expect(timeline).toBeTruthy();
		expect(view.container.querySelectorAll('.execution-timeline')).toHaveLength(1);
		const tool = timeline.querySelector<HTMLButtonElement>('.tool-card .tool-head')!;
		timeline.open = true;
		await fireEvent(timeline, new Event('toggle'));
		await fireEvent.click(tool);
		const stepLabels = [...timeline.querySelectorAll('ol > li')].map((item) => item.textContent);
		finish.resolve();
		await waitFor(() => expect(screen.queryByRole('button', { name: '생성 중단' })).toBeNull());
		expect(view.container.querySelector('.execution-timeline')).toBe(timeline);
		expect(timeline.open).toBe(false);
		await fireEvent.click(timeline.querySelector('summary')!);
		expect(timeline.open).toBe(true);
		expect(tool.getAttribute('aria-expanded')).toBe('true');
		expect(timeline.querySelectorAll('.tool-card')).toHaveLength(1);
		expect(timeline.querySelector(`[data-run-outcome="${state.status}"]`)).toBeTruthy();
		expect(timeline.querySelectorAll('ol > li')).toHaveLength(stepLabels.length + 1);
		expect(timeline.textContent).toContain('기록한 하위 결과');
		expect(timeline.textContent).toContain('기록한 도구 진행');
		expect(timeline.textContent).toContain('기록한 인자');
		expect(timeline.textContent).toContain('기록한 승인 미리보기');
		for (const key of ['arguments', 'preview', 'progress', 'result', 'child'] as const) {
			expect(timeline.textContent).toContain(canaries[key]);
		}
		if (terminal !== 'run.completed') expect(view.container.textContent).toContain(canaries.error);
		const settledLabels = [...timeline.querySelectorAll('ol > li')].map((item) => item.textContent);
		expect(collector).toBeDefined();
		if (collector) {
			await tick();
			for (let batch = 0; batch < 10 && get(experienceHealth).queued; ++batch) await collector.flush();
			expect(get(experienceHealth).status).toBe('ready');
			expect(get(experienceHealth).queued).toBe(0);
			expect(wireBodies.length).toBeGreaterThan(0);
			const streamEvents = wireEvents.filter((row) => row.feature === 'lumen' && row.component === 'shared.stream');
			const projection = streamEvents.find((row) => row.event_type === 'view.state_changed' && row.payload.step === 4);
			expect(projection).toBeTruthy();
			const projectedTrace = streamEvents.filter((row) => row.trace_id === projection!.trace_id);
			expect(projectedTrace.some((row) => row.event_type === 'result.applied')).toBe(true);
			expect(projectedTrace.some((row) => row.event_type === 'result.committed')).toBe(true);
			for (const canary of Object.values(canaries)) expect(wireBodies.join('\n')).not.toContain(canary);
			if (temporary && terminal !== 'run.completed') {
				const terminalIndex = wireEvents.findLastIndex((row) => row.event_type === 'view.state_changed' && row.payload.step === 4 && row.payload.state === (terminal === 'run.failed' ? 'error' : 'disabled'));
				expect(terminalIndex).toBeGreaterThanOrEqual(0);
				const terminalTrace = wireEvents[terminalIndex].trace_id;
				const tail = wireEvents.slice(terminalIndex + 1).filter((row) => row.trace_id === terminalTrace);
				expect(tail.some((row) => row.event_type === 'result.applied')).toBe(true);
				expect(tail.some((row) => row.event_type === 'result.committed')).toBe(true);
				expect(tail.some((row) => row.event_type === 'result.discarded' && row.payload.stage === 'dom')).toBe(false);
			}
		}
		view.unmount();
		const revisited = render(ChatPanel);
		if (!temporary) await fireEvent.click(await screen.findByText('기록 대화'));
		await screen.findByText(finalAnswer);
		const restored = revisited.container.querySelector<HTMLDetailsElement>('.execution-timeline')!;
		expect(restored).toBeTruthy();
		await fireEvent.click(restored.querySelector<HTMLButtonElement>('.tool-card .tool-head')!);
		expect([...restored.querySelectorAll('ol > li')].map((item) => item.textContent)).toEqual(settledLabels);
		expect(revisited.container.querySelectorAll('.execution-timeline')).toHaveLength(1);
		expect(restored.querySelectorAll('.tool-card')).toHaveLength(1);
		expect(restored.querySelector('.live')).toBeNull();
		if (collector) {
			await tick();
			for (let batch = 0; batch < 10 && get(experienceHealth).queued; ++batch) await collector.flush();
			expect(get(experienceHealth).queued).toBe(0);
			for (const canary of Object.values(canaries)) expect(wireBodies.join('\n')).not.toContain(canary);
		}
		} finally {
			collector?.destroy();
			window.fetch = originalFetch;
		}
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

		await fireEvent.click(document.querySelector('.execution-timeline > summary')!);
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
			expect(document.querySelector('.execution-timeline > summary')).toBeTruthy();
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
				expires_at: '2099-07-27T12:00:00Z'
			});
		});

		render(ChatPanel);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/models', 'token', 'project-1'));
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'VM을 삭제해줘' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));

		await screen.findByText('Delete: server-1 (current state: ACTIVE)');
		await fireEvent.click(screen.getByRole('button', { name: '이번만 허용하기' }));

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

describe('ChatPanel failed-read presentation evidence', () => {
	it.each([
		['models', 'visible'], ['models', 'hidden'], ['models', 'unmounted'], ['models', 'owner-changed'],
		['history', 'visible'], ['history', 'unmounted'], ['history', 'owner-changed']
	] as const)('records only the current %s failure DOM when %s', async (read, lifetime) => {
		const pending = Promise.withResolvers<never>();
		const fallback = mocks.get.getMockImplementation()!;
		const canary = 'PRIVATE-CHAT-READ-ERROR-CANARY';
		const isTarget = (path: string) => read === 'models'
			? path === '/api/v1/chat/models'
			: path.includes('/failed-history/messages?');
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (isTarget(path)) return pending.promise;
			if (path === '/api/v1/chat/conversations') return [{ id: 'failed-history', title: '읽기 실패 대화', model_name: 'model-1', workspace_id: null }];
			return fallback(path, ...args);
		});
		type Row = { event_type: string; trace_id: string; feature: string; component: string; payload: { state?: string; step?: number; stage?: string; reason?: string } };
		const rows: Row[] = [];
		const bodies: string[] = [];
		const originalFetch = window.fetch;
		window.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
			if (String(input).endsWith('/experience-contract')) return Response.json({ schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 });
			if (!String(input).endsWith('/experience-events')) throw new Error('Unexpected failed-read fixture transport');
			const body = String(init?.body);
			bodies.push(body);
			const batch = JSON.parse(body);
			rows.push(...batch.events);
			return Response.json({ schema_version: 2, accepted: batch.events.length, duplicates: 0 }, { status: 201 });
		});
		// Endpoint results are controlled; mounted state, Svelte tick and serialization are real.
		const collector = installExperienceCollector({
			getOwner: () => get(auth), getRoute: () => '/dashboard/chat',
			getBaseUrl: () => 'http://localhost:8000', isEnabled: () => true, isSuppressed: () => false,
			subscribeOwner: (changed) => auth.subscribe(changed)
		});
		const view = render(ChatPanel);
		try {
			if (read === 'history') await fireEvent.click(await screen.findByText('읽기 실패 대화'));
			else if (lifetime === 'visible') await fireEvent.click(await screen.findByTitle('모델 선택'));
			await waitFor(() => expect(mocks.get.mock.calls.some(([path]) => isTarget(String(path)))).toBe(true));
			await collector.flush();
			const loading = rows.find((row) => row.feature === 'lumen' && row.event_type === 'view.state_changed' && row.payload.state === 'loading' && row.payload.step === (read === 'models' ? 0 : 1));
			expect(loading).toBeDefined();
			if (lifetime === 'unmounted') view.unmount();
			if (lifetime === 'owner-changed') {
				setVerifiedLumenActor({ ...get(auth), projectId: 'other-project', projectName: 'Other project' });
				await tick();
			}
			pending.reject(new mocks.ApiError(canary, 503));
			await tick();
			await tick();
			if (lifetime === 'visible') {
				const displayed = read === 'models'
					? '모델 목록을 갱신하지 못했습니다 (HTTP 503). 목록 새로고침으로 다시 시도하세요.'
					: canary;
				await screen.findByText(displayed);
			}
			for (let batch = 0; batch < 10 && get(experienceHealth).queued; ++batch) await collector.flush();
			const trace = rows.filter((row) => row.trace_id === loading!.trace_id);
			if (lifetime === 'visible' || lifetime === 'hidden') {
				expect(trace.some((row) => row.event_type === 'view.state_changed' && row.payload.state === 'error')).toBe(true);
				expect(trace.some((row) => row.event_type === 'result.applied')).toBe(true);
			}
			expect(trace.some((row) => row.event_type === 'result.committed')).toBe(lifetime === 'visible');
			if (lifetime === 'hidden') {
				expect(trace.some((row) => row.event_type === 'result.discarded' && row.payload.stage === 'dom')).toBe(true);
				expect(screen.queryByText(/모델 목록을 갱신하지 못했습니다/)).toBeNull();
			}
			if (lifetime === 'unmounted' || lifetime === 'owner-changed') {
				expect(trace.some((row) => row.event_type === 'result.applied')).toBe(false);
			}
			expect(bodies.join('\n')).not.toContain(canary);
			expect(mocks.createRun).not.toHaveBeenCalled();
		} finally {
			view.unmount();
			collector.destroy();
			window.fetch = originalFetch;
		}
	});
});

describe('ChatPanel explicit sandbox selection', () => {
	const page = (available = true): McpSettingsPage => ({
		entries: [{
			id: 'managed-browser', name: 'Browser', registry_name: 'browser', description: '',
			url: null, transport: null, variables: [], header_hints: [], access: 'managed', featured: true,
			managed: { profile: 'playwright', available, reason: available ? null : 'runtime_unavailable', tools: ['Browser_Navigate', 'Browser_Read'] }
		}],
		total: 1, offset: 0, limit: 100, next_offset: null, domain_id: 'domain-1',
		organization_available: false, can_manage_domain: false, custom_connections: []
	});
	function catalogue(read: () => Promise<McpSettingsPage> = async () => page()) {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => {
			if (path.startsWith('/api/v1/chat/mcp-settings?access=managed')) return read();
			if (path === '/api/v1/chat/models') return Promise.resolve([{ id: 1, model_name: 'model-1', display_name: 'Model 1', capabilities: { tool_call: true } }]);
			return fallback(path, ...args);
		});
	}
	async function mountTemporary() {
		const view = render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await waitFor(() => expect(get(managedSandboxTools).catalogLoaded).toBe(true));
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		return view;
	}
	async function submit(text = 'Use selected tools') {
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: text } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
	}
	const managedReads = () => mocks.get.mock.calls.filter(([path]) => String(path).startsWith('/api/v1/chat/mcp-settings?access=managed'));

	it('sends an explicit empty list without implicit allocation or a fresh availability read', async () => {
		catalogue();
		await mountTemporary();
		const reads = managedReads().length;
		await submit('Ordinary text');
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][1].features.tool_policy).toMatchObject({ enabled_sandbox_tools: [], enabled_mcp_ids: null, enabled_tool_ids: null });
		expect(managedReads()).toHaveLength(reads);
	});

	it('offers exact per-tool and profile choices through the composer menu without changing remote IDs', async () => {
		catalogue();
		const view = await mountTemporary();
		const add = screen.getByRole('button', { name: '추가' });
		await fireEvent.keyDown(add, { key: 'ArrowDown' });
		const tool = await screen.findByRole('menuitemcheckbox', { name: 'Browser_Navigate' });
		expect(document.activeElement?.getAttribute('role')).toBe('menuitemcheckbox');
		await fireEvent.click(tool);
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
		await fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Browser 도구 모두 선택' }));
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate', 'Browser_Read']);
		await fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Browser_Read' }));
		await fireEvent.keyDown(tool, { key: 'Escape' });
		expect(view.queryByRole('menu')).toBeNull();
		expect(document.activeElement).toBe(add);
		await submit();
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][1].features.tool_policy).toMatchObject({ enabled_sandbox_tools: ['Browser_Navigate'], enabled_mcp_ids: null });
	});

	it('refreshes nonempty selection once and prevents duplicate submits while preserving the pending draft', async () => {
		const pending = Promise.withResolvers<McpSettingsPage>();
		let reads = 0;
		catalogue(() => ++reads === 1 ? Promise.resolve(page()) : pending.promise);
		await mountTemporary();
		expect(setManagedSandboxTools(['Browser_Navigate'])).toBe(true);
		await submit('Pending draft');
		await waitFor(() => expect(reads).toBe(2));
		await fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		expect(reads).toBe(2);
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Pending draft');
		pending.resolve(page());
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][1].features.tool_policy.enabled_sandbox_tools).toEqual(['Browser_Navigate']);
	});

	it('cannot turn a pending first temporary send into a persisted conversation', async () => {
		const pending = Promise.withResolvers<McpSettingsPage>();
		let reads = 0;
		catalogue(() => ++reads === 1 ? Promise.resolve(page()) : pending.promise);
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		await submit('Temporary draft only');
		await waitFor(() => expect(reads).toBe(2));
		const toggle = document.querySelector<HTMLButtonElement>('.temp-btn')!;
		expect(toggle).not.toBeNull();
		expect(toggle.disabled).toBe(true);
		await fireEvent.click(toggle);
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Temporary draft only');
		pending.resolve(page());
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][0]).toBe('/api/v1/chat/temp-completions');
		expect(mocks.createRun.mock.calls[0][1]).toMatchObject({ model_id: 'model-1', model_row_id: 1 });
		expect(mocks.post.mock.calls.some(([path]) => path === '/api/v1/chat/conversations')).toBe(false);
	});

	it.each(['selection', 'user', 'project', 'logout', 'permission', 'readiness'] as const)('fences %s changes during fresh preflight', async (change) => {
		const pending = Promise.withResolvers<McpSettingsPage>();
		let reads = 0;
		catalogue(() => ++reads === 1 ? Promise.resolve(page()) : pending.promise);
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		await submit('Do not lose this draft');
		await waitFor(() => expect(reads).toBe(2));
		if (change === 'selection') setManagedSandboxTools([]);
		if (change === 'user') setVerifiedLumenActor({ ...get(auth), userId: 'other-user' });
		if (change === 'project') setVerifiedLumenActor({ ...get(auth), projectId: 'other-project' });
		if (change === 'logout') auth.update(actor => ({ ...actor, token: null, userId: null, sessionId: undefined }));
		if (change === 'permission') grantLumen('lumen-chat_user');
		if (change === 'readiness') projectSwitching.set(true);
		pending.resolve(page());
		await tick();
		await tick();
		expect(mocks.createRun).not.toHaveBeenCalled();
		if (change === 'selection' || change === 'permission') expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Do not lose this draft');
	});

	it('blocks newly unavailable tools without clearing the draft or silently sending text only', async () => {
		let reads = 0;
		catalogue(async () => page(++reads === 1));
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		await submit('Keep unavailable intent');
		await waitFor(() => expect(get(managedSandboxTools).issue).toBe('unavailable'));
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Keep unavailable intent');
		expect(screen.getAllByRole('alert').some(node => node.textContent?.includes('Browser_Navigate'))).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		await fireEvent.click(screen.getByRole('menuitem', { name: '로컬 도구 선택 해제' }));
		expect(get(managedSandboxTools).selected).toEqual([]);
		expect((screen.getByRole('button', { name: '전송' }) as HTMLButtonElement).disabled).toBe(false);
	});

	it('keeps revoked choices removable and their helper visible outside the menu', async () => {
		catalogue();
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		grantLumen('lumen-chat_user');
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Revoked draft' } });
		await waitFor(() => expect((screen.getByRole('button', { name: '전송' }) as HTMLButtonElement).disabled).toBe(true));
		expect(screen.getAllByRole('alert').some(node => node.textContent?.includes('선택을 해제'))).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		await fireEvent.click(screen.getByRole('menuitem', { name: '로컬 도구 선택 해제' }));
		expect(get(managedSandboxTools).selected).toEqual([]);
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Revoked draft');
	});

	it('preserves selected preferences during normal token renewal and sends with fresh credentials', async () => {
		const pending = Promise.withResolvers<McpSettingsPage>();
		let reads = 0;
		catalogue(() => ++reads === 1 ? Promise.resolve(page()) : pending.promise);
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		await submit();
		await waitFor(() => expect(reads).toBe(2));
		refreshLumenAuth('renewed-token');
		pending.resolve(page());
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
		expect(mocks.createRun.mock.calls[0][2]).toMatchObject({ token: 'renewed-token', projectId: 'project-1' });
	});

	it('fences the conversation creation wait before publishing its response or creating a failed snapshot', async () => {
		catalogue();
		const pending = Promise.withResolvers<object>();
		mocks.post.mockImplementation((path: string) => path === '/api/v1/chat/conversations' ? pending.promise : Promise.resolve({}));
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await waitFor(() => expect(get(managedSandboxTools).catalogLoaded).toBe(true));
		setManagedSandboxTools(['Browser_Navigate']);
		await submit('Old owner draft');
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/conversations', expect.any(Object), 'token', 'project-1'));
		setVerifiedLumenActor({ ...get(auth), projectId: 'other-project' });
		pending.resolve({ id: 'old-created', title: 'OLD-CONVERSATION-CANARY', model_name: 'model-1', workspace_id: null, updated_at: at });
		await tick();
		await tick();
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect(screen.queryByText('OLD-CONVERSATION-CANARY')).toBeNull();
		expect(screen.queryByRole('button', { name: '다시 전송' })).toBeNull();
		expect(sessionStorage.getItem('chat:activeConversationId:other-project')).not.toBe('old-created');
	});

	it('keeps failed-submit snapshot names and idempotency key instead of injecting changed preferences', async () => {
		catalogue();
		mocks.post.mockResolvedValue({ id: 'sandbox-conv', title: null, model_name: 'model-1', workspace_id: null, updated_at: at });
		mocks.createRun.mockRejectedValueOnce(new Error('temporary transport failure'));
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await waitFor(() => expect(get(managedSandboxTools).catalogLoaded).toBe(true));
		setManagedSandboxTools(['Browser_Navigate']);
		await submit();
		const retry = await screen.findByRole('button', { name: '다시 전송' });
		const original = mocks.createRun.mock.calls[0];
		setManagedSandboxTools(['Browser_Read']);
		await fireEvent.click(retry);
		await tick();
		await tick();
		expect(mocks.createRun).toHaveBeenCalledTimes(1);
		expect(original[1].features.tool_policy.enabled_sandbox_tools).toEqual(['Browser_Navigate']);
		setManagedSandboxTools(['Browser_Navigate']);
		await fireEvent.click(retry);
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(2));
		expect(mocks.createRun.mock.calls[1][1]).toEqual(original[1]);
		expect(mocks.createRun.mock.calls[1][2].idempotencyKey).toBe(original[2].idempotencyKey);
	});

	function historicalChat(retryable = false, frozenRowId?: number) {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') return Promise.resolve([{ id: 'sandbox-history', title: 'Sandbox history', model_name: 'model-1', workspace_id: null }]);
			if (path.includes('/sandbox-history/messages?')) return Promise.resolve({
				messages: [
					{ id: 'saved-user', conversation_id: 'sandbox-history', role: 'user', parent_id: null, content: 'saved question', created_at: at,
						...(retryable ? { execution: { run_id: 'saved-run', status: 'failed', retryable: true, model_row_id: frozenRowId } } : {}) },
					...(!retryable ? [{ id: 'saved-answer', conversation_id: 'sandbox-history', role: 'assistant', parent_id: 'saved-user', model_name: 'model-1', content: 'saved answer', created_at: at }] : [])
				],
				active_leaf_id: retryable ? 'saved-user' : 'saved-answer', history_revision: 1,
				has_before: false, has_after: false, before_cursor: null, after_cursor: null
			});
			return fallback(path, ...args);
		});
	}
	async function openHistoricalChat() {
		render(ChatPanel);
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Sandbox history' }));
		await screen.findByText('saved question');
		await waitFor(() => expect(get(managedSandboxTools).catalogLoaded).toBe(true));
	}

	it('includes current explicit names in context preview without fresh preflight or provisioning', async () => {
		catalogue();
		historicalChat();
		await openHistoricalChat();
		const reads = managedReads().length;
		setManagedSandboxTools(['Browser_Navigate']);
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Preview selection' } });
		await waitFor(() => expect(mocks.previewContext.mock.calls.at(-1)?.[1]?.features.tool_policy.enabled_sandbox_tools).toEqual(['Browser_Navigate']));
		expect(mocks.previewContext.mock.calls.at(-1)?.[1]).toMatchObject({ model_id: 'model-1', model_row_id: 1 });
		expect(managedReads()).toHaveLength(reads);
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('fresh-preflights regeneration and blocks newly unavailable selection before creating a run', async () => {
		let reads = 0;
		catalogue(async () => page(++reads === 1));
		historicalChat();
		await openHistoricalChat();
		setManagedSandboxTools(['Browser_Navigate']);
		await fireEvent.click(screen.getByTitle('다른 모델로 재생성'));
		await fireEvent.click(screen.getByRole('button', { name: '재생성' }));
		await waitFor(() => expect(reads).toBe(2));
		await waitFor(() => expect(get(managedSandboxTools).issue).toBe('unavailable'));
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect(screen.getByText('saved answer')).toBeTruthy();
	});

	it('sends exact current names on regeneration after fresh availability succeeds', async () => {
		catalogue();
		historicalChat();
		await openHistoricalChat();
		setManagedSandboxTools(['Browser_Read']);
		await fireEvent.click(screen.getByTitle('다른 모델로 재생성'));
		await fireEvent.click(screen.getByRole('button', { name: '재생성' }));
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][0]).toBe('/api/v1/chat/conversations/sandbox-history/messages/saved-answer/regenerate');
		expect(mocks.createRun.mock.calls[0][1]).toMatchObject({ model_id: 'model-1', model_row_id: 1 });
		expect(mocks.createRun.mock.calls[0][1].features.tool_policy).toMatchObject({ enabled_sandbox_tools: ['Browser_Read'], enabled_mcp_ids: null });
		expect(managedReads()).toHaveLength(2);
	});

	it.each([undefined, 57])('asserts the frozen retry row when execution reports it (%s)', async (frozenRowId) => {
		catalogue();
		historicalChat(true, frozenRowId);
		await openHistoricalChat();
		setManagedSandboxTools(['Browser_Read']);
		const reads = managedReads().length;
		await fireEvent.click(screen.getByRole('button', { name: '다시 전송' }));
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][0]).toBe('/api/v1/chat/conversations/sandbox-history/runs/saved-run/retry');
		expect(mocks.createRun.mock.calls[0][1]).toEqual(frozenRowId === undefined ? {} : { model_row_id: frozenRowId });
		expect(managedReads()).toHaveLength(reads);
	});

	it.each([undefined, false])('keeps missing/unsupported-model selections removable without a runtime-unavailable claim (%s)', async (toolCall) => {
		catalogue();
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/chat/models'
			? Promise.resolve([{ id: 1, model_name: 'model-1', display_name: 'Model 1', capabilities: { tool_call: toolCall } }])
			: fallback(path, ...args));
		invalidateChatModels();
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Unsupported model draft' } });
		await waitFor(() => expect((screen.getByRole('button', { name: '전송' }) as HTMLButtonElement).disabled).toBe(true));
		expect(screen.getByText(mcpT('selectionModelUnsupported'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		await fireEvent.click(screen.getByRole('menuitem', { name: '로컬 도구 선택 해제' }));
		expect(get(managedSandboxTools).selected).toEqual([]);
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Unsupported model draft');
	});

	it('keeps explicit remote MCP IDs independent from managed local choices', async () => {
		catalogue();
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/chat/mcp-servers?active_only=true'
			? Promise.resolve([{ id: 7, name: 'Remote A' }, { id: 9, name: 'Remote B' }])
			: fallback(path, ...args));
		await mountTemporary();
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		await fireEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'Remote A' }));
		await fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Browser_Navigate' }));
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		await submit();
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
		expect(mocks.createRun.mock.calls[0][1].features.tool_policy).toMatchObject({
			enabled_mcp_ids: [9], enabled_sandbox_tools: ['Browser_Navigate']
		});
	});

	it('blocks corrupt saved intent until explicit reset and preserves the draft', async () => {
		catalogue();
		const view = await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		const key = Object.keys(localStorage).find(key => key.startsWith('afterglow:managed-sandbox-tools:v1:'))!;
		view.unmount();
		localStorage.setItem(key, '{"version":1,"selected":["INVALID/TOOL"]}');
		render(ChatPanel);
		await waitFor(() => expect(get(managedSandboxTools).issue).toBe('invalid_saved'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Keep corrupt preference draft' } });
		expect((screen.getByRole('button', { name: '전송' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getAllByRole('alert').some(node => node.textContent?.includes('초기화'))).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '추가' }));
		await fireEvent.click(screen.getByRole('menuitem', { name: '로컬 도구 선택 해제' }));
		expect(get(managedSandboxTools).issue).toBeNull();
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Keep corrupt preference draft');
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it.each([
		['sandbox_tool_unavailable', 503, '실행 환경을 현재 사용할 수 없습니다'],
		['sandbox_selection_multiple_pools', 422, '도구 구성이 더 이상 유효하지 않습니다'],
		['sandbox_pool_full', 422, '현재 한도가 소진되었습니다'],
		['domain_credit_insufficient', 402, '도메인 크레딧이 부족합니다'],
		['sandbox_configuration_changed', 422, '샌드박스 구성이 변경되었습니다']
	] as const)('shows actionable native %s errors without automatic retry or clearing the selection', async (code, status, message) => {
		catalogue();
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		mocks.createRun.mockRejectedValueOnce(new mocks.ChatHttpError(code, status));
		await submit();
		await screen.findByText(new RegExp(message));
		expect(mocks.createRun).toHaveBeenCalledTimes(1);
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
	});

	it('reports a model downgrade during preflight distinctly and keeps the draft', async () => {
		const pending = Promise.withResolvers<McpSettingsPage>();
		let reads = 0;
		catalogue(() => ++reads === 1 ? Promise.resolve(page()) : pending.promise);
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		await submit('Model downgrade draft');
		await waitFor(() => expect(reads).toBe(2));
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => path === '/api/v1/chat/models'
			? Promise.resolve([{ id: 1, model_name: 'model-1', display_name: 'Model 1', capabilities: { tool_call: false } }])
			: fallback(path, ...args));
		invalidateChatModels();
		await screen.findByText(mcpT('selectionModelUnsupported'));
		pending.resolve(page());
		await waitFor(() => expect(get(managedSandboxTools).preparing).toBe(false));
		await tick();
		expect(screen.getAllByText(mcpT('selectionModelUnsupported')).length).toBeGreaterThan(0);
		expect(screen.queryByText(mcpT('selectionIssue.catalog_failed'))).toBeNull();
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Model downgrade draft');
	});

	it('maps native code/sandbox combination refusal without silently retrying or changing names', async () => {
		catalogue();
		await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		mocks.createRun.mockRejectedValueOnce(new mocks.ChatHttpError('sandbox_code_combination_unsupported', 422));
		await submit();
		await screen.findByText(mcpT('selectionNativeCodeUnsupported'));
		expect(mocks.createRun).toHaveBeenCalledTimes(1);
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
	});

	it.each(['bound', 'unbound'] as const)('retries the originating effective agent model with a different composer model (%s)', async (agentState) => {
		catalogue();
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/agents') return Promise.resolve([
				{ id: 17, name: 'Snapshot agent', model_name: 'model-1', model_row_id: 57, mcp_ids: [], tool_ids: [], visibility: 'private' }
			]);
			if (path === '/api/v1/chat/models') return Promise.resolve([
				{ id: 1, provider_id: 11, model_name: 'model-1', display_name: 'Model 1' },
				{ id: 57, provider_id: 22, model_name: 'model-1', display_name: 'Agent model' }
			]);
			return fallback(path, ...args);
		});
		mocks.post.mockResolvedValue({ id: 'agent-snapshot-conv', title: null, model_name: 'model-1', workspace_id: null, updated_at: at });
		mocks.createRun.mockRejectedValueOnce(new Error('temporary transport failure'));
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.click(screen.getByTitle('에이전트 선택'));
		await fireEvent.click(await screen.findByRole('menuitem', { name: /Snapshot agent/ }));
		await submit('Agent frozen draft');
		const retry = await screen.findByRole('button', { name: '다시 전송' });
		const original = mocks.createRun.mock.calls[0];
		expect(original[1]).toMatchObject({
			model_id: 'model-1', model_row_id: 57, agent_id: 17, features: { tool_policy: { enabled_sandbox_tools: [] } }
		});
		if (agentState === 'unbound') await fireEvent.click(screen.getByRole('button', { name: '에이전트 해제' }));
		await fireEvent.click(retry);
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(2));
		expect(mocks.createRun.mock.calls[1][1]).toEqual(original[1]);
		expect(mocks.createRun.mock.calls[1][2].idempotencyKey).toBe(original[2].idempotencyKey);
		expect(screen.queryByText(mcpT('selectionIssue.selection_changed'))).toBeNull();
	});

	it('keeps reset reachable for 101 saved names after tools permission is revoked', async () => {
		catalogue();
		const view = await mountTemporary();
		setManagedSandboxTools(['Browser_Navigate']);
		const key = Object.keys(localStorage).find(key => key.startsWith('afterglow:managed-sandbox-tools:v1:'))!;
		view.unmount();
		localStorage.setItem(key, JSON.stringify({
			version: 1,
			selected: Array.from({ length: 101 }, (_, index) => `Tool_${index}`)
		}));
		grantLumen('lumen-chat_user');
		render(ChatPanel);
		await waitFor(() => expect(get(managedSandboxTools).issue).toBe('too_many'));
		expect(get(managedSandboxTools).selected).toEqual([]);
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Keep oversized preference draft' } });
		expect((screen.getByRole('button', { name: '전송' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getByText(mcpT('selectionIssue.too_many'))).toBeTruthy();
		const add = screen.getByRole('button', { name: '추가' }) as HTMLButtonElement;
		expect(add.disabled).toBe(false);
		await fireEvent.click(add);
		await fireEvent.click(screen.getByRole('menuitem', { name: '로컬 도구 선택 해제' }));
		expect(get(managedSandboxTools).issue).toBeNull();
		expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Keep oversized preference draft');
		expect((screen.getByRole('button', { name: '전송' }) as HTMLButtonElement).disabled).toBe(false);
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it('does not let a stale admission rejection unlock another conversation preflight', async () => {
		const oldAdmission = Promise.withResolvers<unknown>();
		const preparation = Promise.withResolvers<McpSettingsPage>();
		let reads = 0;
		catalogue(() => ++reads === 1 ? Promise.resolve(page()) : preparation.promise);
		historicalChat();
		mocks.post.mockResolvedValue({ id: 'admission-A', title: null, model_name: 'model-1', workspace_id: null, updated_at: at });
		mocks.createRun.mockImplementationOnce(() => oldAdmission.promise);
		const view = render(ChatPanel);
		try {
			await screen.findByRole('button', { name: 'Model 1' });
			await waitFor(() => expect(get(managedSandboxTools).catalogLoaded).toBe(true));
			await submit('Conversation A pending admission');
			await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
			await fireEvent.click(screen.getByRole('button', { name: '대화 기록과 설정 열기' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Sandbox history' }));
			await screen.findByText('saved answer');
			setManagedSandboxTools(['Browser_Navigate']);
			await fireEvent.click(screen.getByTitle('다른 모델로 재생성'));
			await fireEvent.click(screen.getByRole('button', { name: '재생성' }));
			await waitFor(() => expect(reads).toBe(2));

			oldAdmission.reject(new Error('Old admission rejected'));
			await tick();
			await tick();
			await fireEvent.click(screen.getByTitle('다른 모델로 재생성'));
			await fireEvent.click(screen.getByRole('button', { name: '재생성' }));
			expect(mocks.createRun).toHaveBeenCalledTimes(1);
			preparation.resolve(page());
			await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(2));
			await tick();
			await tick();
			expect(mocks.createRun).toHaveBeenCalledTimes(2);
			expect(mocks.createRun.mock.calls[1][0]).toBe('/api/v1/chat/conversations/sandbox-history/messages/saved-answer/regenerate');
			expect(screen.queryByText('Old admission rejected')).toBeNull();
		} finally {
			oldAdmission.resolve({});
			preparation.resolve(page());
			view.unmount();
		}
	});

	it.each([
		['send', 'resolve'], ['send', 'reject'],
		['retry', 'resolve'], ['retry', 'reject']
	] as const)('does not let delayed %s conversation creation %s clear another running conversation', async (operation, outcome) => {
		const oldCreation = Promise.withResolvers<object>();
		const running = Promise.withResolvers<void>();
		const finish = Promise.withResolvers<void>();
		let creations = 0;
		catalogue();
		historicalChat();
		mocks.post.mockImplementation((path: string) => {
			if (path !== '/api/v1/chat/conversations') return Promise.resolve({});
			++creations;
			if (operation === 'retry' && creations === 1) return Promise.reject(new Error('Initial creation failed'));
			return oldCreation.promise;
		});
		mocks.createRun.mockResolvedValue({
			run_id: 'run-1', conversation_id: 'sandbox-history', temp_thread_id: null,
			status: 'running', run_kind: 'regenerate', events_url: '/events', cancel_url: '/cancel'
		});
		mocks.followRun.mockImplementation(async function* () {
			yield event(1, 'run.stage.changed', { stage: 'queued', tool_name: null });
			running.resolve();
			await finish.promise;
			yield event(2, 'run.completed', { status: 'completed', message_id: 'saved-answer' });
		});
		const view = render(ChatPanel);
		try {
			await screen.findByRole('button', { name: 'Model 1' });
			await waitFor(() => expect(get(managedSandboxTools).catalogLoaded).toBe(true));
			await submit('Conversation A pending creation');
			if (operation === 'retry') await fireEvent.click(await screen.findByRole('button', { name: '다시 전송' }));
			await waitFor(() => expect(creations).toBe(operation === 'retry' ? 2 : 1));
			expect(mocks.createRun).not.toHaveBeenCalled();

			await fireEvent.click(screen.getByRole('button', { name: '대화 기록과 설정 열기' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Sandbox history' }));
			await screen.findByText('saved answer');
			await fireEvent.click(screen.getByTitle('다른 모델로 재생성'));
			await fireEvent.click(screen.getByRole('button', { name: '재생성' }));
			await waitFor(() => expect(mocks.createRun).toHaveBeenCalledTimes(1));
			await waitFor(() => expect(mocks.followRun).toHaveBeenCalledTimes(1));
			await running.promise;
			await screen.findByRole('button', { name: '생성 중단' });

			if (outcome === 'resolve') oldCreation.resolve({
				id: 'late-A', title: 'LATE-A-CREATION-CANARY', model_name: 'model-1', workspace_id: null, updated_at: at
			});
			else oldCreation.reject(new Error('Late A creation rejected'));
			await oldCreation.promise.catch(() => {});
			await tick();
			await tick();

			expect(mocks.createRun).toHaveBeenCalledTimes(1);
			expect(mocks.createRun.mock.calls[0][0]).toBe('/api/v1/chat/conversations/sandbox-history/messages/saved-answer/regenerate');
			expect(screen.queryByText('LATE-A-CREATION-CANARY')).toBeNull();
			expect(screen.queryByText('Late A creation rejected')).toBeNull();
			await fireEvent.click(screen.getByRole('button', { name: '생성 중단' }));
			await waitFor(() => expect(mocks.cancelRun).toHaveBeenCalledTimes(1));
		} finally {
			finish.resolve();
			oldCreation.resolve({ id: 'late-A' });
			view.unmount();
		}
	});
});

describe('ChatPanel in the Personal domain', () => {
	const personalNotice = '개인 프로젝트에서는 대시보드 채팅을 사용할 수 없습니다. 조직(도메인)을 만들거나 조직 프로젝트로 전환해 사용하세요.';
	function workIn(kind: 'personal' | 'organization', canCreateDomain = false) {
		setVerifiedLumenActor({ ...get(auth), canCreateDomain, availableDomains: [{ id: 'domain-1', name: 'Domain', kind }] });
	}
	function withHistoryAndAgents() {
		const fallback = mocks.get.getMockImplementation()!;
		mocks.get.mockImplementation((path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') return Promise.resolve([{ id: 'kept', title: 'Personal history', model_name: 'model-1', workspace_id: null, updated_at: at }]);
			if (path === '/api/v1/chat/agents') return Promise.resolve([{ id: 17, name: 'Personal agent', model_name: 'model-1', mcp_ids: [], tool_ids: [], visibility: 'private' }]);
			if (path === '/api/v1/chat/models') return Promise.resolve([{ id: 1, provider_id: 11, model_name: 'model-1', display_name: 'Model 1', capabilities: { tool_call: true } }]);
			return fallback(path, ...args);
		});
	}

	it('explains the missing pool up front, blocks send, and keeps history and agents usable', async () => {
		workIn('personal');
		withHistoryAndAgents();
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		expect(screen.getByText(personalNotice)).toBeTruthy();
		expect(screen.getByRole('button', { name: '프로젝트 전환' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: '조직 만들기' })).toBeNull();
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Billed nowhere' } });
		const send = screen.getByRole('button', { name: '전송' });
		expect(send.hasAttribute('disabled')).toBe(true);
		expect(document.getElementById(send.getAttribute('aria-describedby')!)?.textContent).toBe(personalNotice);
		await fireEvent.click(send);
		await fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
		expect(mocks.createRun).not.toHaveBeenCalled();
		expect(mocks.post).not.toHaveBeenCalled();

		await fireEvent.click(screen.getByTitle('에이전트 선택'));
		await fireEvent.click(await screen.findByRole('menuitem', { name: /Personal agent/ }));
		await fireEvent.click(await screen.findByRole('button', { name: '대화 기록과 설정 열기' }));
		expect(await screen.findByText('Personal history')).toBeTruthy();
	});

	it('keeps version browsing and fork usable while disabling billed regenerate', async () => {
		workIn('personal');
		const fallback = mocks.get.getMockImplementation()!;
		mocks.patch.mockResolvedValue({ active_leaf_id: 99 });
		mocks.get.mockImplementation(async (path: string, ...args: unknown[]) => {
			if (path === '/api/v1/chat/conversations') return [{ id: 'conv-branch', title: '분기 대화', model_name: 'model-1', workspace_id: null }];
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
		expect(screen.getByRole('button', { name: '분기' }).hasAttribute('disabled')).toBe(false);
		expect(screen.getByTitle('다른 모델로 재생성').hasAttribute('disabled')).toBe(true);
		const previous = screen.getByRole('button', { name: '이전 버전' });
		expect(previous.hasAttribute('disabled')).toBe(false);
		await fireEvent.click(previous);
		await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(
			'/api/v1/chat/conversations/conv-branch/active-leaf', { message_id: 41, descend: true }, 'token', 'project-1'
		));
		expect(mocks.createRun).not.toHaveBeenCalled();
	});

	it('offers organization creation only under the existing create-domain policy', async () => {
		workIn('personal', true);
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		expect(screen.getByRole('button', { name: '조직 만들기' })).toBeTruthy();
	});

	it('leaves organization projects unaffected', async () => {
		workIn('organization', true);
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		expect(screen.queryByText(personalNotice)).toBeNull();
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Organization message' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		await waitFor(() => expect(mocks.createRun).toHaveBeenCalled());
	});

	it('asks organization members to request a top-up when Lumen refuses the domain pool', async () => {
		workIn('organization');
		mocks.createRun.mockRejectedValue(Object.assign(new mocks.ChatHttpError('Request failed', 402), { code: 'domain_credit_insufficient' }));
		render(ChatPanel);
		await screen.findByRole('button', { name: 'Model 1' });
		await fireEvent.click(screen.getByTitle('저장되지 않는 임시 채팅'));
		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'Unfunded' } });
		await fireEvent.click(screen.getByRole('button', { name: '전송' }));
		expect(await screen.findByText('도메인 크레딧이 부족합니다. 도메인 관리자 또는 시스템 관리자에게 충전을 요청하세요.')).toBeTruthy();
	});
});
