import { t } from '$lib/i18n/ns/chat-panel';
import type { ModelCapabilities } from './chatContracts';
import { aggregateCitations } from './chatCitations';
import {
	mergeToolActivity,
	parseAssistantToolCalls,
	toolActivityFromCanonicalParts,
	toolNameFromResultMeta,
	type ToolActivityItem
} from './chatToolActivity';
import type { RunActivityItem } from './chatRunReducer';

import type { ModelCatalogRow } from './modelCatalog';
/** Shared presentation contracts for bounded active-path message pages. */

export type ChatRole = 'user' | 'assistant' | 'tool';


/** 채팅에서 선택 가능한 모델. 백엔드 GET /chat/models 응답 형태. */
export interface AvailableModel extends ModelCatalogRow {
	provider_id: number;
	/** Connection protocol, distinct from the public API provider qualifier. */
	provider_type: string;
	/** Lumen orders the catalog by provider rank/ID, then model rank/ID. */
	provider_sort_order: number;
	sort_order: number;
	model_kind?: string;
	/** External compatibility API model ID. Falls back to model_name during rolling upgrades. */
	api_model_name?: string;
	/** Stable external compatibility API provider selector. */
	api_provider?: string;
	provider_api_key_configured?: boolean;
	capabilities?: ModelCapabilities | null;
	context_limit?: number | null;
	/** Lumen admission이 reasoning_effort="none"을 받는지(없으면 false로 취급). */
	reasoning_none_supported?: boolean;
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
	billing_scope?: 'domain' | 'user';
	payer_domain_id?: string | null;
	balance_credits?: string | number | null;
	reserved_credits?: string | number | null;
	monthly_used_credits?: string;
	effective_monthly_limit_credits?: string | null;
	is_active?: boolean;
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
		model_row_id?: number | null;
		/** Actual UTC run.started journal time, independent of message/reload time. */
		started_at?: string | null;
		/** Actual observed journal cursor; never a temporary message position. */
		last_seq?: number;
		agent_id?: string | null;
		skill_ids?: number[];
		skills?: { id: number; name: string }[];
		status?: string;
		retryable?: boolean;
		tool_durations_ms?: Record<string, number>;
		activity?: RunActivityItem[] | null;
		activity_status?: 'available' | 'unavailable';
		activity_error_code?: 'history_activity_invalid' | 'history_activity_limit' | 'history_activity_missing' | null;
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
			name: toolNameFromResultMeta(message.tool_calls) ?? t('tree.tool'),
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
			projected.push({ ...finalAssistant, tool_items: tools, citations: aggregateCitations(assistants) });
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
 * Preserve the latest assistant route; legacy messages may only have a model name.
 */
export function lastAssistantModel(path: readonly ChatMessage[]): ChatMessage | null {
	for (let i = path.length - 1; i >= 0; i--) {
		const message = path[i];
		if (message.role === 'assistant' && (message.execution?.model_row_id != null || message.model_name)) return message;
	}
	return null;
}
