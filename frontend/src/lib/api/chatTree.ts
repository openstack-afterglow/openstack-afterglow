import type { ModelCapabilities } from './chatContracts';
import {
	mergeToolActivity,
	parseAssistantToolCalls,
	toolActivityFromCanonicalParts,
	toolNameFromResultMeta,
	type ToolActivityItem
} from './chatToolActivity';
import type { RunActivityItem } from './chatRunReducer';

/** Shared presentation contracts for bounded active-path message pages. */

export type ChatRole = 'user' | 'assistant' | 'tool';


/** 채팅에서 선택 가능한 모델. 백엔드 GET /chat/models 응답 형태. */
export interface AvailableModel {
	id: number;
	model_name: string;
	/** External compatibility API model ID. Falls back to model_name during rolling upgrades. */
	api_model_name?: string;
	/** Stable external compatibility API provider selector. */
	api_provider?: string;
	display_name: string;
	provider?: string;
	capabilities?: ModelCapabilities | null;
	context_limit?: number | null;
}

/** 원장 기반 채팅 사용량. 백엔드 GET /chat/usage 계약 전체. */
export interface ChatUsage {
	found: boolean;
	total_credited_cost: number;
	lifetime_prompt_tokens: number;
	lifetime_completion_tokens: number;
	lifetime_request_count: number;
	month_credited_cost: number;
	week_credited_cost: number;
	month_prompt_tokens: number;
	month_completion_tokens: number;
	month_request_count: number;
	quota_used: number;
	quota_max: number;
	quota_weekly_max: number;
}

export interface ChatMessage {
	id: string;
	conversation_id: string;
	role: ChatRole;
	parent_id: string | null;
	content: string;
	tool_calls?: unknown;
	citations?: unknown;
	parts?: unknown;
	status?: 'streaming' | 'complete' | 'failed' | 'canceled' | null;
	execution?: {
		run_id?: string;
		agent_id?: string | null;
		skill_ids?: number[];
		skills?: { id: number; name: string }[];
		status?: string;
		retryable?: boolean;
		tool_durations_ms?: Record<string, number>;
		activity?: RunActivityItem[];
	} | null;
	reasoning?: string | null;
	token_prompt?: number | null;
	token_completion?: number | null;
	model_name?: string | null;
	created_at: string | null;
	created_at_local?: string | null;
	position?: number | null;
	branch?: {
		previous_id: number | null;
		next_id: number | null;
	} | null;
	created_timezone?: string | null;
	/** Presentation-only aggregation for a run's collapsed tool activity. */
	tool_items?: ToolActivityItem[];
}


function activityFromMessage(message: ChatMessage): ToolActivityItem[] {
	const canonical = toolActivityFromCanonicalParts(message.parts);
	const raw = canonical.length > 0 ? canonical : parseAssistantToolCalls(message.tool_calls);
	if (message.role === 'tool') {
		const metadata = Array.isArray(message.tool_calls) ? message.tool_calls[0] : null;
		const record = metadata && typeof metadata === 'object' ? (metadata as Record<string, unknown>) : null;
		const id = typeof record?.tool_call_id === 'string' ? record.tool_call_id : null;
		raw.push({
			id,
			name: toolNameFromResultMeta(message.tool_calls) ?? '도구',
			args: null,
			result: message.content,
			running: false
		});
	}
	const durations = message.execution?.tool_durations_ms ?? {};
	return raw.map((item) => ({
		...item,
		durationMs: item.id ? durations[item.id] ?? item.durationMs ?? null : item.durationMs ?? null
	}));
}

/**
 * A durable run stores model/tool boundaries as separate tree messages for replay.
 * The conversation surface collapses one uninterrupted assistant/tool segment into
 * its final assistant bubble so execution remains part of the same answer.
 */
export function projectMessagesForDisplay(path: readonly ChatMessage[]): ChatMessage[] {
	const projected: ChatMessage[] = [];
	let segment: ChatMessage[] = [];

	const flush = () => {
		if (segment.length === 0) return;
		const assistants = segment.filter((message) => message.role === 'assistant');
		const tools = mergeToolActivity(segment.flatMap(activityFromMessage));
		if (assistants.length === 0 || tools.length === 0) {
			projected.push(...segment);
		} else {
			const finalAssistant = assistants[assistants.length - 1];
			projected.push({ ...finalAssistant, tool_items: tools });
		}
		segment = [];
	};

	for (const message of path) {
		if (message.role === 'user') {
			flush();
			projected.push(message);
		} else {
			segment.push(message);
		}
	}
	flush();
	return projected;
}

/**
 * 활성 경로에서 가장 마지막 assistant 메시지의 model_name 을 반환한다.
 * (마지막 메시지가 아니라 마지막 assistant 를 찾는다 — 뒤에 tool 메시지가 붙을 수 있다.)
 * 이어서 질문할 때 그 모델을 유지하기 위한 용도. 없으면 null.
 */
export function lastAssistantModel(path: readonly ChatMessage[]): string | null {
	for (let i = path.length - 1; i >= 0; i--) {
		if (path[i].role === 'assistant' && path[i].model_name) return path[i].model_name ?? null;
	}
	return null;
}
