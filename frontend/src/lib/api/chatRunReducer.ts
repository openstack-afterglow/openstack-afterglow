import type { ChatPart, ChatRunEvent, ChatRunKind, ChatRunStatus, ContextUpdatedPayload, RunStage, UsageComponent } from './chatContracts';

export interface RunToolView {
	callId: string;
	name: string;
	source: 'builtin' | 'managed' | 'custom_http' | 'mcp' | 'workspace' | 'agent';
	category: string;
	arguments: Record<string, unknown>;
	status: 'running' | 'completed' | 'failed';
	content: ChatPart[];
	errorCode: string | null;
	durationMs: number | null;
}

export type RunActivityItem =
	| {
			id: string;
			kind: 'stage';
			seq: number;
			createdAt: string;
			stage: RunStage;
			toolName: string | null;
	  }
	| {
			id: string;
			kind: 'context';
			seq: number;
			createdAt: string;
			phase: 'compacting' | 'compacted';
			cause: ContextUpdatedPayload['cause'];
			beforeTokens: number | null;
			afterTokens: number | null;
	  }
	| {
			id: string;
			kind: 'reasoning';
			seq: number;
			createdAt: string;
			text: string;
			active: boolean;
	  }
	| {
			id: string;
			kind: 'tool';
			seq: number;
			createdAt: string;
			callId: string;
			name: string;
			source: 'builtin' | 'managed' | 'custom_http' | 'mcp' | 'workspace' | 'agent';
			category: string;
			arguments: Record<string, unknown>;
			status: 'running' | 'completed' | 'failed';
			content: ChatPart[];
			errorCode: string | null;
			durationMs: number | null;
	  };

export interface RunViewState {
	runId: string;
	lastSeq: number;
	status: ChatRunStatus;
	runKind: ChatRunKind;
	messageId: string | null;
	parts: ChatPart[];
	partsByMessage: Record<string, ChatPart[]>;
	tools: Record<string, RunToolView>;
	usage: { promptTokens: number; completionTokens: number; components: UsageComponent[] } | null;
	activity: RunActivityItem[];
	context: ContextUpdatedPayload | null;
	error: string | null;
	stage: RunStage | null;
	stageStartedAt: string | null;
	stageToolName: string | null;
}

export function createRunViewState(runId: string): RunViewState {
	return {
		runId,
		lastSeq: 0,
		status: 'queued',
		runKind: 'completion',
		messageId: null,
		parts: [],
		partsByMessage: {},
		tools: {},
		usage: null,
		activity: [],
		context: null,
		error: null,
		stage: null,
		stageStartedAt: null,
		stageToolName: null,
	};
}
function replacePart(parts: ChatPart[], index: number, part: ChatPart): ChatPart[] {
	const next = parts.slice();
	next[index] = part;
	return next;
}

function applyDelta(parts: ChatPart[], index: number, type: 'text' | 'reasoning', delta: string): ChatPart[] {
	const existing = parts[index];
	if (existing?.type === type) {
		return replacePart(parts, index, { ...existing, text: existing.text + delta });
	}
	const part: ChatPart = type === 'text' ? { type: 'text', text: delta } : { type: 'reasoning', text: delta, visibility: 'user' };
	return replacePart(parts, index, part);
}

function replaceActivity(activity: RunActivityItem[], item: RunActivityItem): RunActivityItem[] {
	const index = activity.findIndex((current) => current.id === item.id);
	if (index < 0) return [...activity, item];
	const next = activity.slice();
	next[index] = item;
	return next;
}

/** Applies a strictly contiguous event; duplicates are harmless and gaps are rejected. */
export function reduceRunEvent(state: RunViewState, event: ChatRunEvent): RunViewState {
	if (event.run_id !== state.runId) throw new Error('chat event run mismatch');
	if (event.seq <= state.lastSeq) return state;
	if (event.seq !== state.lastSeq + 1) throw new Error('chat event sequence gap');
	let next: RunViewState = { ...state, lastSeq: event.seq };

	switch (event.type) {
		case 'run.started':
			next.status = 'running';
			next.runKind = event.payload.run_kind;
			break;
		case 'context.updated':
			next.context = event.payload;
			if (event.payload.phase === 'compacting' || event.payload.phase === 'compacted') {
				next.activity = replaceActivity(next.activity, {
					id: `context:${event.seq}`,
					kind: 'context',
					seq: event.seq,
					createdAt: event.created_at,
					phase: event.payload.phase,
					cause: event.payload.cause,
					beforeTokens: event.payload.before_tokens,
					afterTokens: event.payload.after_tokens
				});
			}
			break;
		case 'run.stage.changed':
			next.stage = event.payload.stage;
			next.stageStartedAt = event.created_at;
			next.stageToolName = event.payload.tool_name;
			next.activity = [
				...next.activity,
				{
					id: `stage:${event.seq}`,
					kind: 'stage',
					seq: event.seq,
					createdAt: event.created_at,
					stage: event.payload.stage,
					toolName: event.payload.tool_name
				}
			];
			break;
		case 'message.created': {
			const parts = next.partsByMessage[event.payload.message_id] ?? [];
			next.messageId = event.payload.message_id;
			next.partsByMessage = { ...next.partsByMessage, [event.payload.message_id]: parts };
			next.parts = parts;
			break;
		}
		case 'part.delta': {
			const parts = applyDelta(
				next.partsByMessage[event.payload.message_id] ?? [],
				event.payload.part_index,
				event.payload.part_type,
				event.payload.delta
			);
			next.partsByMessage = { ...next.partsByMessage, [event.payload.message_id]: parts };
			if (event.payload.message_id === next.messageId) next.parts = parts;
			if (event.payload.part_type === 'reasoning') {
				const id = `reasoning:${event.payload.message_id}:${event.payload.part_index}`;
				const existing = next.activity.find(
					(item): item is Extract<RunActivityItem, { kind: 'reasoning' }> => item.id === id && item.kind === 'reasoning'
				);
				next.activity = replaceActivity(next.activity, {
					id,
					kind: 'reasoning',
					seq: existing?.seq ?? event.seq,
					createdAt: existing?.createdAt ?? event.created_at,
					text: (parts[event.payload.part_index] as Extract<ChatPart, { type: 'reasoning' }>).text,
					active: true
				});
			}
			break;
		}
		case 'part.completed': {
			const parts = replacePart(
				next.partsByMessage[event.payload.message_id] ?? [],
				event.payload.part_index,
				event.payload.part
			);
			next.partsByMessage = { ...next.partsByMessage, [event.payload.message_id]: parts };
			if (event.payload.message_id === next.messageId) next.parts = parts;
			if (event.payload.part.type === 'reasoning') {
				const id = `reasoning:${event.payload.message_id}:${event.payload.part_index}`;
				const existing = next.activity.find(
					(item): item is Extract<RunActivityItem, { kind: 'reasoning' }> => item.id === id && item.kind === 'reasoning'
				);
				next.activity = replaceActivity(next.activity, {
					id,
					kind: 'reasoning',
					seq: existing?.seq ?? event.seq,
					createdAt: existing?.createdAt ?? event.created_at,
					text: event.payload.part.text,
					active: false
				});
			}
			break;
		}
		case 'tool.call.started':
			next.tools = {
				...next.tools,
				[event.payload.call_id]: {
					callId: event.payload.call_id,
					name: event.payload.name,
					source: event.payload.source,
					category: event.payload.category,
					arguments: event.payload.arguments,
					status: 'running',
					content: [],
					errorCode: null,
					durationMs: null
				}
			};
			next.activity = replaceActivity(next.activity, {
				id: `tool:${event.payload.call_id}`,
				kind: 'tool',
				seq: event.seq,
				createdAt: event.created_at,
				callId: event.payload.call_id,
				name: event.payload.name,
				source: event.payload.source,
				category: event.payload.category,
				arguments: event.payload.arguments,
				status: 'running',
				content: [],
				errorCode: null,
				durationMs: null
			});
			break;
		case 'tool.call.completed': {
			const existing = next.tools[event.payload.call_id];
			const existingActivity = next.activity.find(
				(item): item is Extract<RunActivityItem, { kind: 'tool' }> =>
					item.id === `tool:${event.payload.call_id}` && item.kind === 'tool'
			);
			const started = existingActivity ? Date.parse(existingActivity.createdAt) : NaN;
			const completed = Date.parse(event.created_at);
			const durationMs =
				existing?.durationMs ??
				(Number.isNaN(started) || Number.isNaN(completed) ? null : Math.max(0, completed - started));
			next.tools = {
				...next.tools,
				[event.payload.call_id]: {
					callId: event.payload.call_id,
					name: event.payload.name,
					source: event.payload.source,
					category: event.payload.category,
					arguments: existing?.arguments ?? {},
					status: event.payload.status,
					content: event.payload.content,
					errorCode: event.payload.error_code,
					durationMs
				}
			};
			next.activity = replaceActivity(next.activity, {
				id: `tool:${event.payload.call_id}`,
				kind: 'tool',
				seq: existingActivity?.seq ?? event.seq,
				createdAt: existingActivity?.createdAt ?? event.created_at,
				callId: event.payload.call_id,
				name: event.payload.name,
				source: existingActivity?.source ?? event.payload.source,
				category: existingActivity?.category ?? event.payload.category,
				arguments: existingActivity?.arguments ?? {},
				status: event.payload.status,
				content: event.payload.content,
				errorCode: event.payload.error_code,
				durationMs
			});
			break;
		}
		case 'usage.updated':
			next.usage = {
				promptTokens: event.payload.prompt_tokens,
				completionTokens: event.payload.completion_tokens,
				components: event.payload.components
			};
			break;
		case 'run.completed':
			next.status = 'completed';
			next.messageId = event.payload.message_id;
			break;
		case 'run.failed':
		case 'run.canceled':
			next.status = event.payload.status;
			next.messageId = event.payload.message_id;
			next.error = event.payload.safe_message;
			break;
		default:
			break;
	}
	return next;
}
