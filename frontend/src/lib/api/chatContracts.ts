/** Canonical chat wire contract and runtime parsers. No transport may bypass these parsers. */

export interface ModelCapabilities {
	streaming?: boolean;
	vision?: boolean;
	reasoning?: boolean;
	tool_call?: boolean;
	attachment?: boolean;
	function_calling?: boolean;
	structured_output?: boolean;
	web_search?: boolean;
	web_search_required?: boolean;
	web_fetch?: boolean;
	advisor?: boolean;
	responses_api?: boolean;
	mcp?: boolean;
	code_interpreter?: boolean;
	computer_use?: boolean;
	modalities?: { input?: string[]; output?: string[] } | null;
	input_modalities?: string[];
	output_modalities?: string[];
	allowed_output_combinations?: string[][];
	reasoning_options?: { type: string; values: string[] }[];
	context_limit?: number | null;
	feature_gates?: Record<string, { available: boolean; mode: 'native' | 'managed' | 'none'; reason_code: string | null; pricing_available: boolean }>;
}

export type ChatPart =
	| { type: 'text'; text: string }
	| { type: 'image'; asset_id: string; mime_type: string; name: string; width: number; height: number; alt_text?: string }
	| { type: 'audio'; asset_id: string; mime_type: string; name: string; duration_ms: number; transcript?: string }
	| { type: 'video'; asset_id: string; mime_type: string; name: string; duration_ms: number; width: number; height: number }
	| { type: 'document'; asset_id: string; mime_type: string; name: string; page_count: number }
	| { type: 'file'; asset_id: string; mime_type: string; name: string; size_bytes: number }
	| { type: 'tool_call'; call_id: string; name: string; arguments: Record<string, unknown>; status: 'pending' | 'running' | 'completed' | 'failed' | 'denied' }
	| { type: 'tool_result'; call_id: string; name: string; content: ChatPart[]; is_error: boolean }
	| { type: 'citation'; citation_id: string; source_kind: 'web' | 'document'; url?: string; document_index?: number; title?: string; snippet?: string; start_index?: number; end_index?: number }
	| { type: 'structured'; schema_name: string; schema_version: string; value: unknown; valid: boolean; validation_error?: string }
	| { type: 'reasoning'; text: string; visibility: 'user' };

export interface UnknownChatPart {
	type: 'unknown';
	original_type: string;
}

export type DisplayChatPart = ChatPart | UnknownChatPart;
export type UserInputPart = { type: 'text'; text: string } | { type: 'image' | 'audio' | 'video' | 'document'; asset_id: string };

export interface ChatFeatureOptions {
	web_search: {
		enabled: boolean;
		mode?: 'managed' | 'native';
		provider_id?: number | null;
		context_size: 'low' | 'medium' | 'high';
		allowed_domains: string[];
		blocked_domains: string[];
		approximate_location?: Record<string, string>;
		max_uses: number;
	};
	web_fetch: { enabled: boolean; allowed_domains: string[]; blocked_domains: string[]; max_uses: number };
	advisor: { enabled: boolean; model_id?: number; max_uses: number };
	memory: boolean;
	response_format: { kind: 'text' | 'json_object' | 'json_schema'; name?: string; version?: string; schema?: Record<string, unknown> };
	tool_policy: {
		mode: 'agent_default' | 'none';
		approval_mode: 'required_for_mutations' | 'always';
		enabled_tool_ids: string[] | null;
		enabled_mcp_ids?: number[] | null;
		workspace_write_mode?: 'ask' | 'auto_edit';
	};
	output_modalities: Array<'text' | 'image' | 'audio' | 'video'>;
	image_output?: { count: number; aspect_ratio: '1:1' | '16:9' | '9:16'; quality: 'standard' | 'high' };
	audio_output?: { voice: string; format: 'mp3' | 'wav' | 'opus' };
	video_output?: { duration_seconds: number; aspect_ratio: '16:9' | '9:16' };
}

export const defaultChatFeatureOptions = (): ChatFeatureOptions => ({
	web_search: { enabled: false, context_size: 'medium', allowed_domains: [], blocked_domains: [], max_uses: 1 },
	web_fetch: { enabled: false, allowed_domains: [], blocked_domains: [], max_uses: 1 },
	advisor: { enabled: false, max_uses: 1 },
	memory: true,
	response_format: { kind: 'text' },
	tool_policy: {
		mode: 'agent_default',
		approval_mode: 'required_for_mutations',
		enabled_tool_ids: null,
		enabled_mcp_ids: null,
		workspace_write_mode: 'ask'
	},
	output_modalities: ['text']
});


export type ChatExecutionMode = 'chat' | 'plan' | 'code';

export interface ChatCompletionRequest {
	parts: UserInputPart[];
	model_id: string;
	features: ChatFeatureOptions;
	agent_id?: string;
	skill_ids?: number[];
	execution_mode?: ChatExecutionMode;
	code_workspace_id?: string;
	client_timezone?: string | null;
}

export interface RegenerateRequest {
	model_id: string;
	features: ChatFeatureOptions;
	client_timezone?: string | null;
}

export type ChatRunStatus =
	| 'queued'
	| 'running'
	| 'awaiting_approval'
	| 'awaiting_input'
	| 'waiting_children'
	| 'finalizing'
	| 'completed'
	| 'failed'
	| 'canceled';

export type ChatRunKind = 'completion' | 'compaction';

export interface ChatRunDescriptor {
	run_id: string;
	conversation_id: string | null;
	temp_thread_id: string | null;
	status: ChatRunStatus;
	run_kind: ChatRunKind;
	events_url: string;
	cancel_url: string;
}

export interface ChatRunResponse {
	run_id: string;
	status: ChatRunStatus;
	conversation_id: string | null;
	temp_thread_id: string | null;
	run_kind: ChatRunKind;
	effective_features: Record<string, unknown>;
	public_history: unknown[] | null;
	last_seq: number;
	terminal: boolean;
}

export type ContextMeasurement = 'tokenizer' | 'estimated' | 'unknown';
export type ContextRecommendation = 'none' | 'compact' | 'required' | 'unavailable';
export type ContextPhase = 'ready' | 'compacting' | 'compacted' | 'failed';
export type ContextCause = 'automatic' | 'manual' | null;

export interface ContextComponent {
	id: string;
	tokens: number | null;
	measurement: ContextMeasurement;
	count: number | null;
	included: boolean;
	items: string[];
}

export interface ContextBreakdown {
	scope: 'preview' | 'request';
	complete: boolean;
	components: ContextComponent[];
	uncounted: string[];
}

export interface ContextState {
	model_name: string;
	context_limit: number | null;
	output_reserve: number;
	safety_reserve: number;
	input_budget: number | null;
	input_tokens: number | null;
	utilization: number | null;
	measurement: ContextMeasurement;
	recommendation: ContextRecommendation;
	can_compact: boolean;
	reason_code: string | null;
	revision: string;
	checkpoint_id: string | null;
	active_compaction_run_id: string | null;
	breakdown?: ContextBreakdown | null;
}

export interface ContextUpdatedPayload {
	state: ContextState;
	phase: ContextPhase;
	cause: ContextCause;
	before_tokens: number | null;
	after_tokens: number | null;
}

export interface ChatConversationTitleMetadata {
	title_source: 'legacy' | 'auto' | 'explicit';
	title_status: 'idle' | 'pending' | 'ready' | 'failed' | 'unavailable';
	title_revision: number;
}
export interface UsageComponent {
	segment_id: string;
	kind: 'input_tokens' | 'output_tokens' | 'cached_input_tokens' | 'cache_read_input_tokens' | 'cache_creation_5m_input_tokens' | 'cache_creation_1h_input_tokens' | 'reasoning_tokens' | 'embedding_tokens' | 'web_search_requests' | 'web_search_context' | 'web_fetch_requests' | 'web_fetch_context' | 'advisor_input_tokens' | 'advisor_output_tokens' | 'advisor_cache_read_tokens' | 'advisor_cache_creation_5m_tokens' | 'advisor_cache_creation_1h_tokens' | 'image_units' | 'audio_input_seconds' | 'audio_output_seconds' | 'video_seconds' | 'sandbox_seconds' | 'provider_adjustment';
	quantity: string;
	unit: 'token' | 'request' | 'context' | 'image' | 'second' | 'usd';
	unit_price_usd: string;
	cost_usd: string;
	source: 'executor' | 'advisor' | 'search' | 'fetch' | 'memory' | 'media' | 'sandbox' | 'system';
	model_name: string;
	metadata: Record<string, string | number | boolean | null>;
}

interface EventBase<T extends string, P> {
	event_id: string;
	run_id: string;
	seq: number;
	type: T;
	created_at: string;
	payload: P;
}

export type RunStage = 'queued' | 'model_request' | 'model_response' | 'tool_execution' | 'response_writing' | 'awaiting_input' | 'finalizing';

export type ToolActivitySource = 'builtin' | 'managed' | 'custom_http' | 'mcp' | 'workspace' | 'agent';



export type ChatRunEvent =
	| EventBase<'run.started', { conversation_id: string | null; temp_thread_id: string | null; model_name: string; effective_features: Record<string, unknown>; run_kind: ChatRunKind }>
	| EventBase<'run.stage.changed', { stage: RunStage; tool_name: string | null }>
	| EventBase<'run.warning', { code: string; safe_message: string }>
	| EventBase<'context.updated', ContextUpdatedPayload>
	| EventBase<'message.created', { message_id: string; role: 'assistant' | 'tool'; parent_id: string | null }>
	| EventBase<'part.delta', { message_id: string; part_index: number; part_type: 'text' | 'reasoning'; delta: string }>
	| EventBase<'part.completed', { message_id: string; part_index: number; part: ChatPart }>
	| EventBase<'tool.call.started', { call_id: string; name: string; arguments: Record<string, unknown>; source: ToolActivitySource; category: string }>
	| EventBase<'tool.call.completed', { call_id: string; name: string; content: ChatPart[]; status: 'completed' | 'failed'; error_code: string | null; source: ToolActivitySource; category: string }>
	| EventBase<'tool.approval_required', { call_id: string; name: string; source: 'builtin' | 'managed' | 'custom_http' | 'mcp' | 'workspace' | 'agent'; effect: 'read' | 'workspace_write' | 'process' | 'external_mutation'; destination: string | null; redacted_arguments: Record<string, unknown>; preview: ChatPart[]; expected_state_revision: number | null; writer_fence: number | null; expires_at: string }>
	| EventBase<'tool.approval_resolved', { call_id: string; decision: 'approve' | 'deny'; decided_by_user_id: string | null; decided_at: string }>
	| EventBase<'interaction.resolved', { interaction_id: string; status: 'answered' | 'timeout' | 'canceled'; response: { option_ids: string[]; text: string | null } | null }>
	| EventBase<'usage.updated', { components: UsageComponent[]; prompt_tokens: number; completion_tokens: number; raw_cost: string; credited_cost: string }>
	| EventBase<'run.completed', { status: 'completed'; message_id: string | null }>
	| EventBase<'run.failed', { status: 'failed'; message_id: string | null; error_code: string; safe_message: string }>
	| EventBase<'run.canceled', { status: 'canceled'; message_id: string | null; error_code: string; safe_message: string }>;

export class ChatContractError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'ChatContractError';
	}
}

function record(value: unknown, label: string): Record<string, unknown> {
	if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ChatContractError(`${label} must be an object`);
	return value as Record<string, unknown>;
}

function text(value: unknown, label: string, { optional = false }: { optional?: boolean } = {}): string | undefined {
	if (value === undefined && optional) return undefined;
	if (typeof value !== 'string' || value.length === 0) throw new ChatContractError(`${label} must be a non-empty string`);
	return value;
}

function integer(value: unknown, label: string): number {
	if (!Number.isInteger(value) || (value as number) < 0) throw new ChatContractError(`${label} must be a non-negative integer`);
	return value as number;
}

function bool(value: unknown, label: string): boolean {
	if (typeof value !== 'boolean') throw new ChatContractError(`${label} must be a boolean`);
	return value;
}

function chatPart(value: unknown, depth: number, display: boolean): DisplayChatPart {
	if (depth > 4) throw new ChatContractError('tool_result nesting exceeds 4');
	const source = record(value, 'chat part');
	const type = text(source.type, 'chat part type')!;
	const asset = () => ({ asset_id: text(source.asset_id, 'asset_id')!, mime_type: text(source.mime_type, 'mime_type')!, name: text(source.name, 'name')! });
	switch (type) {
		case 'text': return { type, text: text(source.text, 'text')! };
		case 'image': return { type, ...asset(), width: integer(source.width, 'width'), height: integer(source.height, 'height'), ...(text(source.alt_text, 'alt_text', { optional: true }) ? { alt_text: text(source.alt_text, 'alt_text', { optional: true })! } : {}) };
		case 'audio': return { type, ...asset(), duration_ms: integer(source.duration_ms, 'duration_ms'), ...(text(source.transcript, 'transcript', { optional: true }) ? { transcript: text(source.transcript, 'transcript', { optional: true })! } : {}) };
		case 'video': return { type, ...asset(), duration_ms: integer(source.duration_ms, 'duration_ms'), width: integer(source.width, 'width'), height: integer(source.height, 'height') };
		case 'document': return { type, ...asset(), page_count: integer(source.page_count, 'page_count') };
		case 'file': return { type, ...asset(), size_bytes: integer(source.size_bytes, 'size_bytes') };
		case 'tool_call': {
			const status = text(source.status, 'tool status')!;
			if (!['pending', 'running', 'completed', 'failed', 'denied'].includes(status)) throw new ChatContractError('invalid tool status');
			return { type, call_id: text(source.call_id, 'call_id')!, name: text(source.name, 'name')!, arguments: record(source.arguments, 'arguments'), status: status as 'pending' | 'running' | 'completed' | 'failed' | 'denied' };
		}
		case 'tool_result': {
			if (!Array.isArray(source.content) || source.content.length > 32) throw new ChatContractError('tool result content must be a bounded array');
			return { type, call_id: text(source.call_id, 'call_id')!, name: text(source.name, 'name')!, content: source.content.map((part) => {
				const parsed = chatPart(part, depth + 1, false);
				if (parsed.type === 'unknown') throw new ChatContractError('tool result cannot contain an unknown part');
				return parsed;
			}), is_error: bool(source.is_error, 'is_error') };
		}
		case 'citation': {
			const sourceKind = source.source_kind === 'document' ? 'document' : source.source_kind === 'web' || source.source_kind === undefined ? 'web' : null;
			if (sourceKind === null) throw new ChatContractError('invalid citation source_kind');
			const url = text(source.url, 'url', { optional: true });
			const documentIndex = source.document_index === undefined ? undefined : integer(source.document_index, 'document_index');
			if ((sourceKind === 'web' && !url) || (sourceKind === 'document' && documentIndex === undefined)) {
				throw new ChatContractError('citation is missing its source locator');
			}
			const startIndex = source.start_index === undefined ? undefined : integer(source.start_index, 'start_index');
			const endIndex = source.end_index === undefined ? undefined : integer(source.end_index, 'end_index');
			if ((startIndex === undefined) !== (endIndex === undefined) || (startIndex !== undefined && endIndex !== undefined && startIndex > endIndex)) {
				throw new ChatContractError('invalid citation inline range');
			}
			return {
				type,
				citation_id: text(source.citation_id, 'citation_id')!,
				source_kind: sourceKind,
				...(url ? { url } : {}),
				...(documentIndex !== undefined ? { document_index: documentIndex } : {}),
				...(text(source.title, 'title', { optional: true }) ? { title: text(source.title, 'title', { optional: true })! } : {}),
				...(text(source.snippet, 'snippet', { optional: true }) ? { snippet: text(source.snippet, 'snippet', { optional: true })! } : {}),
				...(startIndex !== undefined ? { start_index: startIndex, end_index: endIndex! } : {})
			};
		}
		case 'structured': return { type, schema_name: text(source.schema_name, 'schema_name')!, schema_version: text(source.schema_version, 'schema_version')!, value: source.value, valid: bool(source.valid, 'valid'), ...(text(source.validation_error, 'validation_error', { optional: true }) ? { validation_error: text(source.validation_error, 'validation_error', { optional: true })! } : {}) };
		case 'reasoning': if (source.visibility !== 'user') throw new ChatContractError('reasoning visibility must be user'); return { type, text: text(source.text, 'reasoning text')!, visibility: 'user' };
		default: if (display) return { type: 'unknown', original_type: type }; throw new ChatContractError(`unsupported chat part type: ${type}`);
	}
}

export function parseChatPartsStrict(value: unknown): ChatPart[] {
	if (!Array.isArray(value) || value.length > 32) throw new ChatContractError('chat parts must be a bounded array');
	return value.map((part) => {
		const parsed = chatPart(part, 0, false);
		if (parsed.type === 'unknown') throw new ChatContractError('unknown part is not accepted');
		return parsed;
	});
}

export function parseChatPartsForDisplay(value: unknown): DisplayChatPart[] {
	if (!Array.isArray(value) || value.length > 32) throw new ChatContractError('chat parts must be a bounded array');
	return value.map((part) => chatPart(part, 0, true));
}

function exact(source: Record<string, unknown>, keys: readonly string[], label: string): void {
	const actual = Object.keys(source).sort();
	const expected = [...keys].sort();
	if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
		throw new ChatContractError(`${label} contains unknown or missing fields`);
	}
}

function exactOptional(
	source: Record<string, unknown>,
	required: readonly string[],
	optional: readonly string[],
	label: string
): void {
	const keys = Object.keys(source);
	if (
		required.some((key) => !keys.includes(key)) ||
		keys.some((key) => !required.includes(key) && !optional.includes(key))
	) {
		throw new ChatContractError(`${label} contains unknown or missing fields`);
	}
}

function nullableText(value: unknown, label: string): string | null {
	if (value === null) return null;
	return text(value, label)!;
}

function enumValue<T extends string>(value: unknown, choices: readonly T[], label: string): T {
	if (typeof value !== 'string' || !choices.includes(value as T)) throw new ChatContractError(`invalid ${label}`);
	return value as T;
}
function nonNegativeNumber(value: unknown, label: string): number {
	if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
		throw new ChatContractError(`${label} must be a finite non-negative number`);
	}
	return value;
}

function nullableNonNegativeNumber(value: unknown, label: string): number | null {
	if (value === null) return null;
	return nonNegativeNumber(value, label);
}


function nullableNonNegativeInteger(value: unknown, label: string): number | null {
	if (value === null) return null;
	return integer(value, label);
}

const CONTEXT_COMPONENT_IDS = ['messages', 'system_prompt', 'workspace', 'memory', 'skills', 'agent', 'tools', 'deferred_tools', 'mcp_tools', 'summary', 'attachments', 'overhead'] as const;

function contextNames(value: unknown): string[] {
	if (!Array.isArray(value) || value.length > 128) throw new ChatContractError('context names must be bounded');
	return value.map((item) => {
		const name = text(item, 'context item')!;
		if (name.length > 512) throw new ChatContractError('context item is too long');
		return name;
	});
}

function parseContextBreakdown(value: unknown): ContextBreakdown | null {
	if (value === null) return null;
	const breakdown = record(value, 'context breakdown');
	exact(breakdown, ['scope', 'complete', 'components', 'uncounted'], 'context breakdown');
	if (!Array.isArray(breakdown.components) || breakdown.components.length > 64) {
		throw new ChatContractError('context components must be bounded');
	}
	const componentIds = new Set<string>();
	const parsed = {
		scope: enumValue(breakdown.scope, ['preview', 'request'] as const, 'context scope'),
		complete: bool(breakdown.complete, 'context complete'),
		uncounted: contextNames(breakdown.uncounted),
		components: breakdown.components.map((value) => {
			const component = record(value, 'context component');
			exact(component, ['id', 'tokens', 'measurement', 'count', 'included', 'items'], 'context component');
			const id = enumValue(component.id, CONTEXT_COMPONENT_IDS, 'context component id');
			if (componentIds.has(id)) throw new ChatContractError('duplicate context component id');
			componentIds.add(id);
			return {
				id,
				tokens: nullableNonNegativeInteger(component.tokens, 'context component tokens'),
				measurement: enumValue(component.measurement, ['tokenizer', 'estimated', 'unknown'] as const, 'component measurement'),
				count: nullableNonNegativeInteger(component.count, 'context component count'),
				included: bool(component.included, 'context component included'),
				items: contextNames(component.items)
			};
		})
	};
	if (new Set(parsed.uncounted).size !== parsed.uncounted.length || parsed.uncounted.some((id) => !componentIds.has(id))) {
		throw new ChatContractError('uncounted context entries must name unique components');
	}
	return parsed;
}

export function parseContextState(value: unknown): ContextState {
	const state = record(value, 'context state');
	exactOptional(
		state,
		[
			'model_name',
			'context_limit',
			'output_reserve',
			'safety_reserve',
			'input_budget',
			'input_tokens',
			'utilization',
			'measurement',
			'recommendation',
			'can_compact',
			'reason_code',
			'revision',
			'checkpoint_id',
			'active_compaction_run_id'
		],
		['breakdown'],
		'context state'
	);
	return {
		model_name: text(state.model_name, 'context model_name')!,
		...(state.breakdown === undefined ? {} : { breakdown: parseContextBreakdown(state.breakdown) }),
		context_limit: nullableNonNegativeInteger(state.context_limit, 'context_limit'),
		output_reserve: nonNegativeNumber(state.output_reserve, 'output_reserve'),
		safety_reserve: nonNegativeNumber(state.safety_reserve, 'safety_reserve'),
		input_budget: nullableNonNegativeInteger(state.input_budget, 'input_budget'),
		input_tokens: nullableNonNegativeInteger(state.input_tokens, 'input_tokens'),
		utilization: nullableNonNegativeNumber(state.utilization, 'utilization'),
		measurement: enumValue(state.measurement, ['tokenizer', 'estimated', 'unknown'] as const, 'context measurement'),
		recommendation: enumValue(state.recommendation, ['none', 'compact', 'required', 'unavailable'] as const, 'context recommendation'),
		can_compact: bool(state.can_compact, 'can_compact'),
		reason_code: nullableText(state.reason_code, 'reason_code'),
		revision: text(state.revision, 'context revision')!,
		checkpoint_id: nullableText(state.checkpoint_id, 'checkpoint_id'),
		active_compaction_run_id: nullableText(state.active_compaction_run_id, 'active_compaction_run_id')
	};
}

function parseContextUpdatedPayload(value: Record<string, unknown>): ContextUpdatedPayload {
	exact(value, ['state', 'phase', 'cause', 'before_tokens', 'after_tokens'], 'context.updated payload');
	return {
		state: parseContextState(value.state),
		phase: enumValue(value.phase, ['ready', 'compacting', 'compacted', 'failed'] as const, 'context phase'),
		cause: value.cause === null ? null : enumValue(value.cause, ['automatic', 'manual'] as const, 'context cause'),
		before_tokens: nullableNonNegativeInteger(value.before_tokens, 'before_tokens'),
		after_tokens: nullableNonNegativeInteger(value.after_tokens, 'after_tokens')
	};
}


function decimal(value: unknown, label: string, negative = false): string {
	const raw = text(value, label)!;
	const numeric = Number(raw);
	if (!Number.isFinite(numeric) || (!negative && numeric < 0)) throw new ChatContractError(`invalid ${label}`);
	return raw;
}

function usageComponent(value: unknown): UsageComponent {
	const component = record(value, 'usage component');
	exact(component, ['segment_id', 'kind', 'quantity', 'unit', 'unit_price_usd', 'cost_usd', 'source', 'model_name', 'metadata'], 'usage component');
	const kind = enumValue(component.kind, ['input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_read_input_tokens', 'cache_creation_5m_input_tokens', 'cache_creation_1h_input_tokens', 'reasoning_tokens', 'embedding_tokens', 'web_search_requests', 'web_search_context', 'web_fetch_requests', 'web_fetch_context', 'advisor_input_tokens', 'advisor_output_tokens', 'advisor_cache_read_tokens', 'advisor_cache_creation_5m_tokens', 'advisor_cache_creation_1h_tokens', 'image_units', 'audio_input_seconds', 'audio_output_seconds', 'video_seconds', 'sandbox_seconds', 'provider_adjustment'] as const, 'usage kind');
	const metadata = record(component.metadata, 'usage metadata');
	const safeMetadata: Record<string, string | number | boolean | null> = {};
	for (const [key, item] of Object.entries(metadata)) {
		if (item !== null && typeof item !== 'string' && typeof item !== 'number' && typeof item !== 'boolean') throw new ChatContractError('usage metadata must be scalar');
		safeMetadata[key] = item;
	}
	return {
		segment_id: text(component.segment_id, 'segment_id')!,
		kind,
		quantity: decimal(component.quantity, 'quantity'),
		unit: enumValue(component.unit, ['token', 'request', 'context', 'image', 'second', 'usd'] as const, 'usage unit'),
		unit_price_usd: decimal(component.unit_price_usd, 'unit_price_usd'),
		cost_usd: decimal(component.cost_usd, 'cost_usd', kind === 'provider_adjustment'),
		source: enumValue(component.source, ['executor', 'advisor', 'search', 'fetch', 'memory', 'media', 'sandbox', 'system'] as const, 'usage source'),
		model_name: text(component.model_name, 'model_name')!,
		metadata: safeMetadata
	};
}

export function parseChatRunEvent(value: unknown): ChatRunEvent {
	const event = record(value, 'chat run event');
	exact(event, ['event_id', 'run_id', 'seq', 'type', 'created_at', 'payload'], 'chat run event');
	const type = text(event.type, 'event type')!;
	const runId = text(event.run_id, 'run_id')!;
	const seq = integer(event.seq, 'seq');
	const eventId = text(event.event_id, 'event_id')!;
	const createdAt = text(event.created_at, 'created_at')!;
	if (seq < 1 || eventId !== `${runId}:${seq}` || Number.isNaN(Date.parse(createdAt))) throw new ChatContractError('invalid event cursor');
	const payload = record(event.payload, 'event payload');
	const base = { event_id: eventId, run_id: runId, seq, created_at: createdAt };

	switch (type) {
		case 'run.started': {
			exact(payload, ['conversation_id', 'temp_thread_id', 'model_name', 'effective_features', 'run_kind'], 'run.started payload');
			return {
				...base,
				type,
				payload: {
					conversation_id: nullableText(payload.conversation_id, 'conversation_id'),
					temp_thread_id: nullableText(payload.temp_thread_id, 'temp_thread_id'),
					model_name: text(payload.model_name, 'model_name')!,
					effective_features: record(payload.effective_features, 'effective_features'),
					run_kind: enumValue(payload.run_kind, ['completion', 'compaction'] as const, 'run kind')
				}
			};
		}
		case 'run.stage.changed': {
			exact(payload, ['stage', 'tool_name'], 'run.stage.changed payload');
			const stage = enumValue(payload.stage, ['queued', 'model_request', 'model_response', 'tool_execution', 'response_writing', 'awaiting_input', 'finalizing'] as const, 'run stage');
			const toolName = nullableText(payload.tool_name, 'tool_name');
			if ((stage === 'tool_execution') !== (toolName !== null)) throw new ChatContractError('tool stage and tool name differ');
			return { ...base, type, payload: { stage, tool_name: toolName } };
		}
		case 'run.warning': {
			exact(payload, ['code', 'safe_message'], 'run.warning payload');
			return { ...base, type, payload: { code: text(payload.code, 'warning code')!, safe_message: text(payload.safe_message, 'safe message')! } };
		}
		case 'message.created': {
			exact(payload, ['message_id', 'role', 'parent_id'], 'message.created payload');
			return { ...base, type, payload: { message_id: text(payload.message_id, 'message_id')!, role: enumValue(payload.role, ['assistant', 'tool'] as const, 'message role'), parent_id: nullableText(payload.parent_id, 'parent_id') } };
		}
		case 'context.updated':
			return { ...base, type, payload: parseContextUpdatedPayload(payload) };
		case 'part.delta': {
			exact(payload, ['message_id', 'part_index', 'part_type', 'delta'], 'part.delta payload');
			return { ...base, type, payload: { message_id: text(payload.message_id, 'message_id')!, part_index: integer(payload.part_index, 'part_index'), part_type: enumValue(payload.part_type, ['text', 'reasoning'] as const, 'part_type'), delta: text(payload.delta, 'delta')! } };
		}
		case 'part.completed': {
			exact(payload, ['message_id', 'part_index', 'part'], 'part.completed payload');
			return { ...base, type, payload: { message_id: text(payload.message_id, 'message_id')!, part_index: integer(payload.part_index, 'part_index'), part: parseChatPartsStrict([payload.part])[0] } };
		}
		case 'tool.call.started': {
			exactOptional(payload, ['call_id', 'name', 'arguments'], ['source', 'category'], 'tool.call.started payload');
			const source = payload.source === undefined
				? 'builtin'
				: enumValue(payload.source, ['builtin', 'managed', 'custom_http', 'mcp', 'workspace', 'agent'] as const, 'tool source');
			return {
				...base,
				type,
				payload: {
					call_id: text(payload.call_id, 'call_id')!,
					name: text(payload.name, 'tool name')!,
					arguments: record(payload.arguments, 'tool arguments'),
					source,
					category: payload.category === undefined ? '기본 도구' : text(payload.category, 'tool category')!
				}
			};
		}
		case 'tool.call.completed': {
			exactOptional(payload, ['call_id', 'name', 'content', 'status'], ['error_code', 'source', 'category'], 'tool.call.completed payload');
			const errorCode = payload.error_code === undefined || payload.error_code === null ? null : text(payload.error_code, 'tool error code')!;
			const source = payload.source === undefined
				? 'builtin'
				: enumValue(payload.source, ['builtin', 'managed', 'custom_http', 'mcp', 'workspace', 'agent'] as const, 'tool source');
			return {
				...base,
				type,
				payload: {
					call_id: text(payload.call_id, 'call_id')!,
					name: text(payload.name, 'tool name')!,
					content: parseChatPartsStrict(payload.content),
					status: enumValue(payload.status, ['completed', 'failed'] as const, 'tool status'),
					error_code: errorCode,
					source,
					category: payload.category === undefined ? '기본 도구' : text(payload.category, 'tool category')!
				}
			};
		}
		case 'tool.approval_required': {
			exact(payload, ['call_id', 'name', 'source', 'effect', 'destination', 'redacted_arguments', 'preview', 'expected_state_revision', 'writer_fence', 'expires_at'], 'tool.approval_required payload');
			const expiresAt = text(payload.expires_at, 'expires_at')!;
			if (Number.isNaN(Date.parse(expiresAt))) throw new ChatContractError('invalid approval expiry');
			const nullableInteger = (value: unknown, label: string): number | null => value === null ? null : integer(value, label);
			return {
				...base,
				type,
				payload: {
					call_id: text(payload.call_id, 'call_id')!,
					name: text(payload.name, 'tool name')!,
					source: enumValue(payload.source, ['builtin', 'managed', 'custom_http', 'mcp', 'workspace', 'agent'] as const, 'tool source'),
					effect: enumValue(payload.effect, ['read', 'workspace_write', 'process', 'external_mutation'] as const, 'tool effect'),
					destination: nullableText(payload.destination, 'tool destination'),
					redacted_arguments: record(payload.redacted_arguments, 'redacted tool arguments'),
					preview: parseChatPartsStrict(payload.preview),
					expected_state_revision: nullableInteger(payload.expected_state_revision, 'expected state revision'),
					writer_fence: nullableInteger(payload.writer_fence, 'writer fence'),
					expires_at: expiresAt
				}
			};
		}
		case 'tool.approval_resolved': {
			exact(payload, ['call_id', 'decision', 'decided_by_user_id', 'decided_at'], 'tool.approval_resolved payload');
			const decidedAt = text(payload.decided_at, 'approval decision time')!;
			if (Number.isNaN(Date.parse(decidedAt))) throw new ChatContractError('invalid approval decision time');
			return {
				...base,
				type,
				payload: {
					call_id: text(payload.call_id, 'call_id')!,
					decision: enumValue(payload.decision, ['approve', 'deny'] as const, 'approval decision'),
					decided_by_user_id: nullableText(payload.decided_by_user_id, 'approval deciding user'),
					decided_at: decidedAt
				}
			};
		}
		case 'interaction.resolved': {
			exact(payload, ['interaction_id', 'status', 'response'], 'interaction.resolved payload');
			const response = payload.response === null ? null : record(payload.response, 'interaction response');
			const interactionStatus = enumValue(payload.status, ['answered', 'timeout', 'canceled'] as const, 'interaction status');
			if (response !== null) {
				if (
					!Array.isArray(response.option_ids) ||
					response.option_ids.length > 5 ||
					response.option_ids.some((optionId) => !text(optionId, 'interaction option id')) ||
					new Set(response.option_ids).size !== response.option_ids.length
				) {
					throw new ChatContractError('invalid interaction option ids');
				}
				exact(response, ['option_ids', 'text'], 'interaction response');
				if (response.text !== null && (typeof response.text !== 'string' || response.text.length > 4000)) {
					throw new ChatContractError('invalid interaction text');
				}
			}
			if ((interactionStatus === 'answered') !== (response !== null)) {
				throw new ChatContractError('interaction status and response differ');
			}
			return {
				...base,
				type,
				payload: {
					interaction_id: text(payload.interaction_id, 'interaction id')!,
					status: interactionStatus,
					response: response === null ? null : { option_ids: response.option_ids as string[], text: response.text as string | null }
				}
			};
		}
		case 'usage.updated': {
			exact(payload, ['components', 'prompt_tokens', 'completion_tokens', 'raw_cost', 'credited_cost'], 'usage.updated payload');
			if (!Array.isArray(payload.components) || payload.components.length > 256) throw new ChatContractError('invalid usage components');
			return { ...base, type, payload: { components: payload.components.map(usageComponent), prompt_tokens: integer(payload.prompt_tokens, 'prompt_tokens'), completion_tokens: integer(payload.completion_tokens, 'completion_tokens'), raw_cost: decimal(payload.raw_cost, 'raw_cost'), credited_cost: decimal(payload.credited_cost, 'credited_cost') } };
		}
		case 'run.completed': {
			exact(payload, ['status', 'message_id'], 'run.completed payload');
			if (payload.status !== 'completed') throw new ChatContractError('terminal event and payload status differ');
			return { ...base, type, payload: { status: 'completed', message_id: nullableText(payload.message_id, 'message_id') } };
		}
		case 'run.failed': {
			exact(payload, ['status', 'message_id', 'error_code', 'safe_message'], 'run.failed payload');
			if (payload.status !== 'failed') throw new ChatContractError('terminal event and payload status differ');
			return { ...base, type, payload: { status: 'failed', message_id: nullableText(payload.message_id, 'message_id'), error_code: text(payload.error_code, 'error_code')!, safe_message: text(payload.safe_message, 'safe_message')! } };
		}
		case 'run.canceled': {
			exact(payload, ['status', 'message_id', 'error_code', 'safe_message'], 'run.canceled payload');
			if (payload.status !== 'canceled') throw new ChatContractError('terminal event and payload status differ');
			return { ...base, type, payload: { status: 'canceled', message_id: nullableText(payload.message_id, 'message_id'), error_code: text(payload.error_code, 'error_code')!, safe_message: text(payload.safe_message, 'safe_message')! } };
		}
		default:
			throw new ChatContractError(`unsupported event type: ${type}`);
	}
}
