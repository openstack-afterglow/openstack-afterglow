/**
 * 채팅 프로젝트(workspace) + 사용자 메모리 타입 및 폼 ↔ 페이로드 순수 변환.
 *
 * workspace = 대화 묶음 + 프로젝트 공통 지침(instructions).
 * memory = 사용자 장기 기억 항목(content, 활성 토글).
 * 폼 상태(문자열 입력)와 API 페이로드 사이의 왕복은 순수 함수로 격리해 유닛 테스트한다
 * (빈 문자열 필드 생략). chatAgents.ts 의 스타일을 그대로 따른다.
 */

export interface Workspace {
	id: number;
	owner_user_id?: string;
	name: string;
	description?: string | null;
	instructions?: string | null;
	created_at?: string | null;
	updated_at?: string | null;
}

/** 폼 상태(입력값은 문자열). */
export interface WorkspaceForm {
	name: string;
	description: string;
	instructions: string;
}

/** API 페이로드(POST/PATCH 공통). undefined 키는 전송에서 생략된다. */
export interface WorkspacePayload {
	name: string;
	description?: string;
	instructions?: string;
}

export function emptyWorkspaceForm(): WorkspaceForm {
	return {
		name: '',
		description: '',
		instructions: ''
	};
}

/** 편집 진입: 서버 Workspace → 폼 상태(null → 빈 문자열). */
export function workspaceToForm(w: Workspace): WorkspaceForm {
	return {
		name: w.name ?? '',
		description: w.description ?? '',
		instructions: w.instructions ?? ''
	};
}

/**
 * 폼 → 페이로드. 빈 문자열 필드는 생략(undefined)한다.
 * (chatAgents.buildAgentPayload 와 동일하게, PATCH 로 기존 값을 빈 문자열로 되돌릴 수는 없다.)
 */
export function buildWorkspacePayload(form: WorkspaceForm): WorkspacePayload {
	const payload: WorkspacePayload = {
		name: form.name.trim()
	};
	const desc = form.description.trim();
	if (desc) payload.description = desc;
	const instr = form.instructions.trim();
	if (instr) payload.instructions = instr;
	return payload;
}

/** 대화 수 계산에 필요한 최소 형태(workspace_id 만 참조). */
export interface ConversationRef {
	workspace_id: number | null;
}

/**
 * 특정 프로젝트에 소속된 대화 수. `c.workspace_id === workspaceId` 인 대화만 센다.
 * (프로젝트 카드/상세의 "소속 대화 수" 배지에 사용.)
 */
export function countConversationsInWorkspace(
	conversations: ConversationRef[],
	workspaceId: number
): number {
	return conversations.filter((c) => c.workspace_id === workspaceId).length;
}
