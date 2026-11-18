/**
 * 채팅 에이전트 타입 + 폼 ↔ 페이로드 순수 변환.
 *
 * 에이전트 = 프롬프트(instructions) + 모델 + 파라미터 + MCP/툴 묶음.
 * 폼 상태(문자열 입력 · 체크박스 Record)와 API 페이로드(숫자 · int[]) 사이의 왕복은
 * 순수 함수로 격리해 유닛 테스트한다(빈 params 키 생략, id Record↔int[] 매핑).
 */

export type AgentVisibility = 'private' | 'public';

export interface AgentParams {
	temperature?: number;
	max_tokens?: number;
}

export interface Agent {
	id: number;
	owner_user_id?: string;
	name: string;
	description?: string | null;
	avatar?: string | null;
	instructions?: string | null;
	model_name?: string | null;
	model_row_id?: number | null;
	params?: AgentParams | null;
	mcp_ids: number[];
	tool_ids: number[];
	visibility: AgentVisibility;
	cloned_from_id?: number | null;
	clone_count?: number;
	is_owner?: boolean;
	created_at?: string | null;
	updated_at?: string | null;
}

/** 바인딩 대상 확장(MCP 서버 / 커스텀 툴) 공통 표시 형태. */
export interface AgentExtension {
	id: number;
	name: string;
}

/** 폼 상태(입력값은 문자열, 다중선택은 Record). */
export interface AgentForm {
	name: string;
	description: string;
	avatar: string;
	instructions: string;
	model_name: string;
	/** Undefined is an untouched legacy value; null clears the pinned route. */
	model_row_id?: number | null;
	temperature: string;
	max_tokens: string;
	mcp_ids: Record<number, boolean>;
	tool_ids: Record<number, boolean>;
	visibility: AgentVisibility;
}

/** API 페이로드(POST/PATCH 공통). undefined 키는 전송에서 생략된다. */
export interface AgentPayload {
	name: string;
	description?: string;
	avatar?: string;
	instructions?: string;
	model_name?: string | null;
	model_row_id?: number | null;
	params?: AgentParams;
	mcp_ids: number[];
	tool_ids: number[];
	visibility: AgentVisibility;
}

export function emptyAgentForm(): AgentForm {
	return {
		name: '',
		description: '',
		avatar: '',
		instructions: '',
		model_name: '',
		temperature: '',
		max_tokens: '',
		mcp_ids: {},
		tool_ids: {},
		visibility: 'private'
	};
}

function idsToRecord(ids: readonly number[]): Record<number, boolean> {
	const rec: Record<number, boolean> = {};
	for (const id of ids) rec[id] = true;
	return rec;
}

/** 체크박스 Record 에서 선택된 id 만 오름차순 int[] 로. */
export function idsFromRecord(rec: Record<number, boolean>): number[] {
	return Object.keys(rec)
		.filter((k) => rec[Number(k)])
		.map(Number)
		.sort((a, b) => a - b);
}

/** 편집 진입: 서버 Agent → 폼 상태(체크박스 Record 되채움, 숫자 → 문자열). */
export function agentToForm(a: Agent): AgentForm {
	return {
		name: a.name ?? '',
		description: a.description ?? '',
		avatar: a.avatar ?? '',
		instructions: a.instructions ?? '',
		model_name: a.model_name ?? '',
		model_row_id: a.model_row_id ?? undefined,
		temperature:
			a.params?.temperature === undefined || a.params?.temperature === null
				? ''
				: String(a.params.temperature),
		max_tokens:
			a.params?.max_tokens === undefined || a.params?.max_tokens === null
				? ''
				: String(a.params.max_tokens),
		mcp_ids: idsToRecord(a.mcp_ids ?? []),
		tool_ids: idsToRecord(a.tool_ids ?? []),
		visibility: a.visibility ?? 'private'
	};
}

/**
 * 폼 → 페이로드. 빈 문자열 필드는 생략(undefined), params 는 유효한 숫자가 있을 때만
 * 해당 키를 포함하고, 둘 다 없으면 params 자체를 생략한다.
 */
export function buildAgentPayload(form: AgentForm): AgentPayload {
	const params: AgentParams = {};
	const t = Number(form.temperature);
	if (form.temperature.trim() !== '' && Number.isFinite(t)) params.temperature = t;
	const mt = Number(form.max_tokens);
	if (form.max_tokens.trim() !== '' && Number.isInteger(mt) && mt > 0) params.max_tokens = mt;

	const payload: AgentPayload = {
		name: form.name.trim(),
		mcp_ids: idsFromRecord(form.mcp_ids),
		tool_ids: idsFromRecord(form.tool_ids),
		visibility: form.visibility
	};
	const desc = form.description.trim();
	if (desc) payload.description = desc;
	const avatar = form.avatar.trim();
	if (avatar) payload.avatar = avatar;
	const instr = form.instructions.trim();
	if (instr) payload.instructions = instr;
	const model = form.model_name.trim();
	if (form.model_row_id !== undefined) {
		payload.model_row_id = form.model_row_id;
		payload.model_name = model || null;
	} else if (model) {
		payload.model_name = model;
	}
	if (params.temperature !== undefined || params.max_tokens !== undefined) payload.params = params;

	return payload;
}

/** avatar 문자열이 이미지 URL 인지(그 외는 이모지/텍스트로 취급). */
export function isAvatarUrl(avatar: string | null | undefined): boolean {
	if (!avatar) return false;
	return /^https?:\/\//i.test(avatar.trim());
}
