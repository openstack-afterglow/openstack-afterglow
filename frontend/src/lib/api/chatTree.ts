import type { ModelCapabilities } from './chatContracts';
import {
	mergeToolActivity,
	parseAssistantToolCalls,
	toolActivityFromCanonicalParts,
	toolNameFromResultMeta,
	type ToolActivityItem
} from './chatToolActivity';
import type { RunActivityItem } from './chatRunReducer';

/**
 * 채팅 메시지 버전 트리 파생 (순수 함수).
 *
 * 백엔드 `GET /conversations/{id}/messages` 는 전체 트리(parent_id 포함)와
 * active_leaf_id 를 반환한다. 화면에는 active_leaf 에서 루트까지의 선형 경로만
 * 렌더하고, 형제 버전(같은 parent_id) 사이를 이동할 수 있어야 한다.
 *
 * 이 로직은 UI 의 위험 중심이며 타입/디자인 검증이 잡아주지 못하므로
 * 순수 함수로 격리해 단위 테스트한다.
 */

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
	created_timezone?: string | null;
	/** Presentation-only aggregation for a run's collapsed tool activity. */
	tool_items?: ToolActivityItem[];
}

/** Lightweight, content-free message metadata used for version navigation. */
export interface ChatTreeNode {
	id: string;
	parent_id: string | null;
	role: ChatRole;
	created_at: string | null;
}

/**
 * active_leaf_id 에서 parent_id 를 역추적해 루트까지 올라간 뒤 reverse.
 * 이 선형 경로만 화면에 렌더한다.
 *
 * active_leaf_id 가 없거나 트리에서 못 찾으면, 가장 최근 created_at 을 가진
 * 리프를 추정해 그 경로를 반환한다(백엔드가 항상 active_leaf_id 를 주지만 방어).
 */
export function buildActivePath(
	messages: readonly ChatMessage[],
	activeLeafId: string | null | undefined
): ChatMessage[] {
	if (messages.length === 0) return [];
	const byId = new Map<string, ChatMessage>();
	for (const m of messages) byId.set(m.id, m);

	let leafId = activeLeafId && byId.has(activeLeafId) ? activeLeafId : null;
	if (!leafId) {
		// 폴백: 자식이 없는 메시지(리프) 중 가장 최근 것을 리프로 선택.
		const hasChild = new Set<string>();
		for (const m of messages) if (m.parent_id) hasChild.add(m.parent_id);
		const leaves = messages.filter((m) => !hasChild.has(m.id));
		const candidates = leaves.length > 0 ? leaves : [...messages];
		leafId = pickLatest(candidates)?.id ?? null;
	}

	const path: ChatMessage[] = [];
	const seen = new Set<string>();
	let cursor: string | null = leafId;
	while (cursor && byId.has(cursor) && !seen.has(cursor)) {
		seen.add(cursor);
		const node = byId.get(cursor)!;
		path.push(node);
		cursor = node.parent_id;
	}
	path.reverse();
	return path;
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

/**
 * 주어진 메시지의 형제 = 같은 parent_id 를 가진 같은 role 의 메시지들.
 * created_at 오름차순 정렬(안정적 순서). 자기 자신 포함.
 * 개수 > 1 이면 UI 에 `‹ n/m ›` 표시한다.
 */
export function getSiblings(messages: readonly ChatTreeNode[], message: ChatTreeNode): ChatTreeNode[] {
	const siblings = messages.filter(
		(m) => m.parent_id === message.parent_id && m.role === message.role
	);
	return sortByCreatedAt(siblings);
}

export interface SiblingInfo {
	/** 형제 목록(정렬됨) */
	siblings: ChatTreeNode[];
	/** 현재 메시지의 1-based 인덱스 */
	index: number;
	/** 형제 총 개수 */
	total: number;
}

export function getSiblingInfo(messages: readonly ChatTreeNode[], message: ChatTreeNode): SiblingInfo {
	const siblings = getSiblings(messages, message);
	const idx = siblings.findIndex((m) => m.id === message.id);
	return { siblings, index: idx + 1, total: siblings.length };
}

/**
 * 형제 버전으로 전환할 때 PATCH active-leaf 에 넘길 message_id 를 결정한다.
 *
 * 형제 자체가 리프가 아니면(하위에 답변/후속 대화가 이어져 있으면) 그 subtree 를
 * 결정론적으로 따라 내려가 리프를 고른다. 각 단계에서 가장 최근 created_at 자식을
 * 선택한다. 그냥 형제 id 를 넘기면 하위 트리가 있는 경우 화면이 잘린다.
 */
export function resolveLeafFor(messages: readonly ChatTreeNode[], startId: string): string {
	const childrenOf = new Map<string, ChatTreeNode[]>();
	for (const m of messages) {
		if (!m.parent_id) continue;
		const arr = childrenOf.get(m.parent_id);
		if (arr) arr.push(m);
		else childrenOf.set(m.parent_id, [m]);
	}

	let cursor = startId;
	const seen = new Set<string>();
	while (!seen.has(cursor)) {
		seen.add(cursor);
		const children = childrenOf.get(cursor);
		if (!children || children.length === 0) break;
		const next = pickLatest(children);
		if (!next) break;
		cursor = next.id;
	}
	return cursor;
}

/**
 * 형제 방향 이동(prev=-1 / next=+1) 후 전환 대상 리프 id 를 계산한다.
 * 이동 불가(경계)면 null.
 */
export function siblingLeafInDirection(
	messages: readonly ChatTreeNode[],
	message: ChatTreeNode,
	direction: -1 | 1
): string | null {
	const siblings = getSiblings(messages, message);
	const idx = siblings.findIndex((m) => m.id === message.id);
	if (idx === -1) return null;
	const target = siblings[idx + direction];
	if (!target) return null;
	return resolveLeafFor(messages, target.id);
}

function pickLatest<T extends ChatTreeNode>(items: readonly T[]): T | null {
	if (items.length === 0) return null;
	let best = items[0];
	for (let i = 1; i < items.length; i++) {
		if (compareCreatedAt(items[i], best) > 0) best = items[i];
	}
	return best;
}

function sortByCreatedAt<T extends ChatTreeNode>(items: T[]): T[] {
	return [...items].sort(compareCreatedAt);
}

/**
 * created_at 오름차순 비교. null/동률이면 id 로 안정 정렬.
 */
function compareCreatedAt(a: ChatTreeNode, b: ChatTreeNode): number {
	const ta = a.created_at ? Date.parse(a.created_at) : NaN;
	const tb = b.created_at ? Date.parse(b.created_at) : NaN;
	const va = Number.isNaN(ta) ? 0 : ta;
	const vb = Number.isNaN(tb) ? 0 : tb;
	if (va !== vb) return va - vb;
	return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}
