import { parseChatRunEvent, type ChatRunEvent, type ChatRunDescriptor } from '$lib/api/chatContracts';
import { createRunViewState, reduceRunEvent } from '$lib/api/chatRunReducer';

/** Synthetic tutorial journal. No native IAM, provider or cloud operation runs. */
const conversationId = 'tutorial-work-log';
let runId = 'tutorial-work-log-run';
let messageId = 'tutorial-answer';
const startedAt = '2026-11-17T00:00:00Z';
const answer = '튜토리얼 작업을 마쳤습니다. 도구 오류와 공개된 추론 요약은 위 작업 내역에서 다시 확인할 수 있습니다.';
let decision: 'approve' | 'deny' | null = null;
let live = false;
let runStartedAt = startedAt;
let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
let timers: ReturnType<typeof setTimeout>[] = [];
const encoder = new TextEncoder();
const historyKey = 'afterglow.tutorial.chat-work-log';
let journal: ChatRunEvent[] = [];

function event(type: string, payload: unknown, seconds: number): ChatRunEvent {
	const seq = journal.length + 1;
	const result = { event_id: `${runId}:${seq}`, run_id: runId, seq, type,
		created_at: new Date(Date.parse(runStartedAt) + seconds * 1000).toISOString(), payload } as ChatRunEvent;
	journal.push(result);
	return result;
}
function send(type: string, payload: unknown, seconds: number) {
	const entry = event(type, payload, seconds);
	controller?.enqueue(encoder.encode(`id: ${entry.event_id}\nevent: ${entry.type}\ndata: ${JSON.stringify(entry)}\n\n`));
}
function finish() {
	if (!live) return;
	const elapsed = Math.floor((Date.now() - Date.parse(runStartedAt)) / 1000);
	send('tool.approval_resolved', { call_id: 'permission', decision, decided_by_user_id: null, decided_at: new Date().toISOString() }, elapsed);
	send('tool.call.started', { call_id: 'search', name: 'web_search', arguments: { query: 'tutorial' }, source: 'builtin', category: 'Web' }, elapsed);
	send('tool.call.completed', { call_id: 'search', name: 'web_search', status: 'failed', content: [{ type: 'text', text: '튜토리얼 검색 실패 — 실제 검색은 실행하지 않았습니다.' }], error_code: 'tutorial_unavailable', source: 'builtin', category: 'Web' }, elapsed);
	send('part.completed', { message_id: messageId, part_index: 0, part: { type: 'text', text: answer } }, elapsed);
	send('run.completed', { status: 'completed', message_id: messageId }, elapsed);
	live = false;
	if (typeof sessionStorage !== 'undefined') {
		sessionStorage.setItem(historyKey, JSON.stringify(journal));
	}
	controller?.close(); controller = null;
}
function initialHistory() {
	journal = [];
	event('run.started', { conversation_id: conversationId, temp_thread_id: null, model_name: 'tutorial-chat', effective_features: {}, run_kind: 'completion' }, 0);
	event('run.stage.changed', { stage: 'model_request', tool_name: null }, 1);
	event('part.completed', { message_id: messageId, part_index: 1, part: { type: 'reasoning', visibility: 'user', text: '공개된 요약: 프로젝트를 읽고 필요한 도구를 확인합니다.' } }, 2);
	event('tool.call.started', { call_id: 'search', name: 'web_search', arguments: {}, source: 'builtin', category: 'Web' }, 3);
	event('tool.call.completed', { call_id: 'search', name: 'web_search', status: 'failed', content: [{ type: 'text', text: '튜토리얼 검색 실패 — 실제 검색은 실행하지 않았습니다.' }], error_code: 'tutorial_unavailable', source: 'builtin', category: 'Web' }, 4);
	event('run.completed', { status: 'completed', message_id: messageId }, 12);
}
initialHistory();
// Tutorial-only public journal survives a browser reload, just like native owned history.
if (typeof sessionStorage !== 'undefined') {
	try {
		const saved = sessionStorage.getItem(historyKey);
		if (saved && saved.length <= 256_000) {
			const parsed: unknown = JSON.parse(saved);
			if (Array.isArray(parsed) && parsed.length && parsed.length <= 128) {
				const events = parsed.map(parseChatRunEvent);
				const state = events.reduce(reduceRunEvent, createRunViewState(events[0].run_id));
				if (state.status === 'completed' && state.messageId) {
					journal = events; runId = state.runId; messageId = state.messageId;
					runStartedAt = events[0].created_at;
				}
			}
		}
	} catch {
		sessionStorage.removeItem(historyKey);
	}
}
function descriptor(): ChatRunDescriptor {
	return { run_id: runId, conversation_id: conversationId, temp_thread_id: null, run_kind: 'completion', status: live ? 'running' : 'completed', events_url: `/api/v1/chat/runs/${runId}/events`, cancel_url: `/api/v1/chat/runs/${runId}/cancel` };
}
function conversation() { return { id: conversationId, title: '작업 내역 튜토리얼', model_name: 'tutorial-chat', active_leaf_id: messageId, workspace_id: null, agent_id: null, created_at: startedAt, updated_at: startedAt }; }
export function mockChatWorkLog(method: string, path: string, params: URLSearchParams, body: unknown): unknown | undefined {
	if (!path.startsWith('/api/v1/chat/')) return undefined;
	if (method === 'GET' && path === '/api/v1/chat/models' && !params.has('model_kind')) return [{ id: 1, provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'tutorial-chat', display_name: 'Tutorial · Synthetic', capabilities: { streaming: true, tool_call: true, reasoning: true, input_modalities: ['text'], output_modalities: ['text'] } }];
	if (method === 'GET' && ['/api/v1/chat/agents', '/api/v1/chat/workspaces', '/api/v1/chat/runs'].includes(path)) return [];
	if (method === 'GET' && path === '/api/v1/chat/conversations') return [conversation()];
	if (method === 'POST' && path === '/api/v1/chat/conversations') return conversation();
	if (method === 'GET' && path === `/api/v1/chat/conversations/${conversationId}`) return conversation();
	if (method === 'GET' && path === `/api/v1/chat/conversations/${conversationId}/runs`) return live ? [descriptor()] : [];
	if (method === 'POST' && path === `/api/v1/chat/runs/${runId}/approvals/permission`) {
		if (body && typeof body === 'object' && 'decision' in body && (body.decision === 'approve' || body.decision === 'deny')) decision = body.decision;
		finish(); return { run_status: 'queued', pending_approvals: 0 };
	}
	if (method === 'GET' && path === `/api/v1/chat/conversations/${conversationId}/messages`) {
		const state = journal.reduce(reduceRunEvent, createRunViewState(runId));
		const unavailable = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('work-log') === 'unavailable';
		return { messages: [
			{ id: 'tutorial-user', role: 'user', conversation_id: conversationId, parent_id: null, content: '작업 내역을 보여 주세요.', created_at: runStartedAt },
			{ id: messageId, role: 'assistant', conversation_id: conversationId, parent_id: 'tutorial-user', content: live ? '' : answer, created_at: runStartedAt, model_name: 'tutorial-chat', execution: {
				run_id: runId, status: state.status, started_at: unavailable ? null : state.startedAt,
				activity: unavailable ? null : state.activity, activity_status: unavailable ? 'unavailable' : 'available',
				activity_error_code: unavailable ? 'history_activity_invalid' : null
			} }
		], active_leaf_id: messageId, history_revision: 1, has_before: false, has_after: false, before_cursor: null, after_cursor: null };
	}
	return undefined;
}

export function mockChatWorkLogResponse(path: string, options: RequestInit): Response | null {
	const url = new URL(path, 'https://tutorial.invalid');
	if (options.method === 'POST' && url.pathname === `/api/v1/chat/conversations/${conversationId}/completions`) {
		timers.forEach(clearTimeout); timers = []; journal = []; decision = null; live = true;
		runStartedAt = new Date().toISOString();
		runId = crypto.randomUUID();
		messageId = `tutorial-answer-${runId}`;
		return Response.json(descriptor(), { status: 202 });
	}
	if (url.pathname !== `/api/v1/chat/runs/${runId}/events`) return null;
	const after = Number(url.searchParams.get('after_seq') ?? 0);
	return new Response(new ReadableStream<Uint8Array>({
		start(stream) {
			controller = stream;
			for (const entry of journal.filter((item) => item.seq > after)) stream.enqueue(encoder.encode(`id: ${entry.event_id}\nevent: ${entry.type}\ndata: ${JSON.stringify(entry)}\n\n`));
			if (!live) { stream.close(); controller = null; return; }
			if (!journal.length) {
				timers.push(setTimeout(() => {
					send('run.started', { conversation_id: conversationId, temp_thread_id: null, model_name: 'tutorial-chat', effective_features: {}, run_kind: 'completion' }, 3);
					send('message.created', { message_id: messageId, role: 'assistant', parent_id: null }, 3);
					send('run.stage.changed', { stage: 'model_request', tool_name: null }, 3);
					send('part.completed', { message_id: messageId, part_index: 1, part: { type: 'reasoning', visibility: 'user', text: '공개된 요약: 프로젝트를 읽고 필요한 도구를 확인합니다.' } }, 3);
				}, 3000));
				timers.push(setTimeout(() => send('tool.approval_required', {
					call_id: 'permission', name: 'afterglow_vm_create', source: 'mcp', effect: 'external_mutation', destination: 'https://tutorial.invalid', redacted_arguments: { name: 'tutorial-vm' }, preview: [{ type: 'text', text: '튜토리얼 가상 머신을 생성할까요? 실제 자원은 만들지 않습니다.' }], expected_state_revision: null, writer_fence: null, expires_at: new Date(Date.now() + 300000).toISOString()
				}, 8), 8000));
			}
			options.signal?.addEventListener('abort', () => { timers.forEach(clearTimeout); timers = []; if (controller === stream) { controller = null; stream.close(); } }, { once: true });
		},
		cancel() { timers.forEach(clearTimeout); timers = []; controller = null; }
	}), { headers: { 'Content-Type': 'text/event-stream' } });
}
