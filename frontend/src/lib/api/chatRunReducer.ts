import { t } from '$lib/i18n/ns/chat-diagnostics';
import type { ChatPart, ChatRunEvent, ChatRunKind, ChatRunStatus, ContextUpdatedPayload, RunStage, ToolActivitySource, UsageComponent } from './chatContracts';

export interface RunToolView {
	callId: string;
	name: string;
	source: ToolActivitySource;
	category: string;
	arguments: Record<string, unknown>;
	status: 'running' | 'completed' | 'failed';
	content: ChatPart[];
	errorCode: string | null;
	durationMs: number | null;
	progress?: string[];
}

export interface RunChildView {
	childRunId: string;
	callId: string;
	waitGroupId: string;
	agentId: number | null;
	access: 'read' | 'write' | null;
	ordinal: number | null;
	initialStatus: 'queued' | 'waiting_resource' | null;
	status: 'requested' | 'completed' | 'failed' | 'canceled';
	errorCode: string | null;
	summary: string;
	artifacts: Extract<ChatPart, { type: 'file' }>[];
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
			source: ToolActivitySource;
			category: string;
			arguments: Record<string, unknown>;
			status: 'running' | 'completed' | 'failed';
			content: ChatPart[];
			errorCode: string | null;
			durationMs: number | null;
			progress?: string[];
	  }
	| {
			id: string;
			kind: 'approval';
			seq: number;
			createdAt: string;
			callId: string;
			name: string | null;
			arguments: Record<string, unknown>;
			preview: ChatPart[];
			effect: string | null;
			destination: string | null;
			expiresAt: string | null;
			decision: 'approve' | 'deny' | null;
			decidedAt: string | null;
	  }
	| {
			id: string;
			kind: 'terminal';
			seq: number;
			createdAt: string;
			status: 'completed' | 'failed' | 'canceled';
			errorCode: string | null;
			message: string | null;
	  }
	| (RunChildView & { id: string; kind: 'child'; seq: number; createdAt: string });

export interface RunViewState {
	runId: string;
	lastSeq: number;
	status: ChatRunStatus;
	runKind: ChatRunKind;
	messageId: string | null;
	parts: ChatPart[];
	partsByMessage: Record<string, ChatPart[]>;
	sources: Extract<ChatPart, { type: 'citation' }>[];
	tools: Record<string, RunToolView>;
	children: Record<string, RunChildView>;
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
		sources: [],
		tools: {},
		children: {},
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
	if (event.run_id !== state.runId) throw new Error(t('reducer.runMismatch'));
	if (event.seq <= state.lastSeq) return state;
	if (event.seq !== state.lastSeq + 1) throw new Error(t('protocol.sequenceGap'));
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
		case 'source.registered': {
			const citation = event.payload.citation;
			const index = next.sources.findIndex((item) => item.citation_id === citation.citation_id);
			next.sources = index < 0 ? [...next.sources, citation] : next.sources.map((item, i) => i === index ? citation : item);
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
			if (event.payload.part.type === 'citation') {
				const citation = event.payload.part;
				const index = next.sources.findIndex((item) => item.citation_id === citation.citation_id);
				next.sources = index < 0 ? [...next.sources, citation] : next.sources.map((item, i) => i === index ? citation : item);
			}
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
		case 'child.created': {
			const payload = event.payload;
			const existing = next.children[payload.child_run_id];
			if (existing && (existing.callId !== payload.call_id || existing.waitGroupId !== payload.wait_group_id || existing.status !== 'requested')) throw new Error('child task identity conflict');
			if (existing) break;
			const child: RunChildView = {
				childRunId: payload.child_run_id, callId: payload.call_id, waitGroupId: payload.wait_group_id,
				agentId: payload.agent_id, access: payload.access, ordinal: payload.ordinal,
				initialStatus: payload.status, status: 'requested', errorCode: null, summary: '', artifacts: []
			};
			next.children = { ...next.children, [payload.child_run_id]: child };
			next.activity = replaceActivity(next.activity, { ...child, id: `child:${payload.child_run_id}`, kind: 'child', seq: event.seq, createdAt: event.created_at });
			break;
		}
		case 'child.completed': {
			const payload = event.payload;
			const existing = next.children[payload.child_run_id];
			if (existing && (existing.callId !== payload.call_id || existing.waitGroupId !== payload.wait_group_id)) throw new Error('child task identity conflict');
			const first = next.activity.find((item) => item.kind === 'child' && item.childRunId === payload.child_run_id);
			const child: RunChildView = {
				childRunId: payload.child_run_id, callId: payload.call_id, waitGroupId: payload.wait_group_id,
				agentId: existing?.agentId ?? null, access: existing?.access ?? null, ordinal: existing?.ordinal ?? null,
				initialStatus: existing?.initialStatus ?? null, status: payload.status,
				errorCode: payload.error_code, summary: payload.summary, artifacts: payload.artifacts
			};
			next.children = { ...next.children, [payload.child_run_id]: child };
			next.activity = replaceActivity(next.activity, { ...child, id: `child:${payload.child_run_id}`, kind: 'child', seq: first?.seq ?? event.seq, createdAt: first?.createdAt ?? event.created_at });
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
		case 'tool.call.progress': {
			const tool = next.tools[event.payload.call_id];
			if (!tool || tool.name !== event.payload.name || tool.status !== 'running') throw new Error('tool progress has no active matching call');
			const progress = tool.progress?.at(-1) === event.payload.text ? tool.progress : [...(tool.progress ?? []), event.payload.text].slice(-32);
			next.tools = { ...next.tools, [event.payload.call_id]: { ...tool, progress } };
			next.activity = next.activity.map((item) => item.kind === 'tool' && item.callId === event.payload.call_id
				? { ...item, progress } : item);
			break;
		}
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
					durationMs,
					...(existing?.progress ? { progress: existing.progress } : {}),
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
				durationMs,
				...(existingActivity?.progress ? { progress: existingActivity.progress } : {}),
			});
			break;
		}
		case 'tool.approval_required':
			next.activity = replaceActivity(next.activity, {
				id: `approval:${event.payload.call_id}`, kind: 'approval', seq: event.seq,
				createdAt: event.created_at, callId: event.payload.call_id, name: event.payload.name,
				arguments: event.payload.redacted_arguments, preview: event.payload.preview,
				effect: event.payload.effect, destination: event.payload.destination, expiresAt: event.payload.expires_at,
				decision: null, decidedAt: null
			});
			break;
		case 'tool.approval_resolved': {
			const id = `approval:${event.payload.call_id}`;
			const existing = next.activity.find(
				(item): item is Extract<RunActivityItem, { kind: 'approval' }> => item.id === id && item.kind === 'approval'
			);
			next.activity = replaceActivity(next.activity, {
				id, kind: 'approval', seq: existing?.seq ?? event.seq, createdAt: existing?.createdAt ?? event.created_at,
				callId: event.payload.call_id, name: existing?.name ?? null,
				arguments: existing?.arguments ?? {}, preview: existing?.preview ?? [],
				effect: existing?.effect ?? null, destination: existing?.destination ?? null, expiresAt: existing?.expiresAt ?? null,
				decision: event.payload.decision, decidedAt: event.payload.decided_at
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
		case 'run.failed':
		case 'run.canceled':
			next.status = event.payload.status;
			next.messageId = event.payload.message_id;
			next.error = event.type === 'run.completed' ? null : event.payload.safe_message;
			next.activity = [...next.activity, {
				id: `terminal:${event.seq}`, kind: 'terminal', seq: event.seq, createdAt: event.created_at,
				status: event.payload.status,
				errorCode: event.type === 'run.completed' ? null : event.payload.error_code,
				message: event.type === 'run.completed' ? null : event.payload.safe_message
			}];
			break;
		default:
			break;
	}
	return next;
}
