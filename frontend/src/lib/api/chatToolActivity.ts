/**
 * 도구(tool) 사용 시각화 — 저장/스트림의 tool_calls 필드를 카드용 아이템으로 정규화(순수 함수).
 *
 * 두 가지 저장 형태를 방어적으로 파싱한다:
 * - assistant 호출 스텝: `[{id, type:'function', function:{name, arguments}}]` (litellm/OpenAI 형태)
 *   또는 라이브 SSE 형태 `[{id, name, args}]`.
 * - role=tool 결과 메타: `[{tool_call_id, name}]` (어떤 툴의 결과인지 식별용).
 *
 * UI 위험 로직이라 순수 함수로 격리해 단위 테스트한다.
 */

export interface ToolActivityFile {
	assetId: string;
	name: string;
	mimeType: string;
	sizeBytes: number;
}


export interface ToolActivityItem {
	/** tool_call_id — 호출과 결과를 잇는 키. 없을 수 있음. */
	id: string | null;
	/** 툴 이름 */
	name: string;
	/** 호출 인자(JSON 문자열). 없으면 null. */
	args?: string | null;
	/** 실행 결과 텍스트. 진행 중이면 null. */
	result?: string | null;
	/** 실행 중(결과 대기)인지 여부 */
	running: boolean;
	/** 완료 상태. 레거시 기록에 없으면 성공 완료로 표시한다. */
	status?: 'completed' | 'failed';
	/** 서버가 안전하게 공개한 실패 코드. */
	errorCode?: string | null;
	/** 실행 경과 시간(ms). 라이브와 durable 기록 모두에서 제공될 수 있다. */
	durationMs?: number | null;
	/** Durable generated files owned by the current run principal. */
	files?: ToolActivityFile[];
}

function asArray(value: unknown): unknown[] {
	return Array.isArray(value) ? value : [];
}

function str(value: unknown): string | null {
	return typeof value === 'string' && value.length > 0 ? value : null;
}

/**
 * assistant 호출 스텝의 tool_calls → 호출 아이템 목록(인자 포함, 결과는 아직 없음).
 * 두 형태(function.{name,arguments} / {name,args}) 모두 처리.
 */
export function parseAssistantToolCalls(toolCalls: unknown): ToolActivityItem[] {
	const items: ToolActivityItem[] = [];
	for (const raw of asArray(toolCalls)) {
		if (!raw || typeof raw !== 'object') continue;
		const tc = raw as Record<string, unknown>;
		const fn = (tc.function as Record<string, unknown> | undefined) ?? undefined;
		const name = str(fn?.name) ?? str(tc.name);
		if (!name) continue;
		const args = str(fn?.arguments) ?? str(tc.args);
		const id = str(tc.id) ?? str(tc.tool_call_id);
		items.push({ id, name, args, result: null, running: true });
	}
	return items;
}

/**
 * role=tool 결과 메시지의 tool_calls 메타 → 툴 이름. 식별 불가 시 null.
 */
export function toolNameFromResultMeta(toolCalls: unknown): string | null {
	for (const raw of asArray(toolCalls)) {
		if (!raw || typeof raw !== 'object') continue;
		const tc = raw as Record<string, unknown>;
		const name = str(tc.name);
		if (name) return name;
	}
	return null;
}

/**
 * 인자(JSON 문자열)를 사람이 읽기 좋게 정규화. 빈 객체("{}")·공백은 빈 문자열로.
 * 파싱되면 2-스페이스 pretty, 실패하면 원문 유지.
 */
export function formatToolArgs(args: string | null | undefined): string {
	if (!args) return '';
	const trimmed = args.trim();
	if (trimmed === '' || trimmed === '{}') return '';
	try {
		const parsed = JSON.parse(trimmed);
		if (parsed && typeof parsed === 'object' && Object.keys(parsed).length === 0) return '';
		return JSON.stringify(parsed, null, 2);
	} catch {
		return trimmed;
	}
}


/** Canonical persisted parts → reloaded tool cards, preserving call/result linkage. */
export function toolActivityFromCanonicalParts(value: unknown): ToolActivityItem[] {
	const parts = asArray(value);
	const items = new Map<string, ToolActivityItem>();
	for (const raw of parts) {
		if (!raw || typeof raw !== 'object') continue;
		const part = raw as Record<string, unknown>;
		const type = str(part.type);
		const id = str(part.call_id);
		const name = str(part.name);
		if (!id || !name) continue;
		if (type === 'tool_call') {
			const argumentsValue = part.arguments;
			let args: string | null = null;
			try {
				args = argumentsValue === undefined ? null : JSON.stringify(argumentsValue);
			} catch {
				args = null;
			}
			items.set(id, { id, name, args, result: null, running: part.status === 'running' || part.status === 'pending' });
		} else if (type === 'tool_result') {
			const resultParts = asArray(part.content);
			const content = resultParts
				.filter((entry) => entry && typeof entry === 'object' && (entry as Record<string, unknown>).type === 'text')
				.map((entry) => String((entry as Record<string, unknown>).text ?? ''))
				.join('\n');
			const files = resultParts.flatMap((entry): ToolActivityFile[] => {
				if (!entry || typeof entry !== 'object') return [];
				const resultPart = entry as Record<string, unknown>;
				if (
					resultPart.type !== 'file' ||
					typeof resultPart.asset_id !== 'string' ||
					typeof resultPart.name !== 'string' ||
					typeof resultPart.mime_type !== 'string' ||
					typeof resultPart.size_bytes !== 'number'
				) return [];
				return [{
					assetId: resultPart.asset_id,
					name: resultPart.name,
					mimeType: resultPart.mime_type,
					sizeBytes: resultPart.size_bytes
				}];
			});
			const existing = items.get(id);
			items.set(id, {
				id,
				name,
				args: existing?.args ?? null,
				result: content || null,
				running: false,
				...(files.length > 0 ? { files } : {})
			});
		}
	}
	return [...items.values()];
}

/** Merge a chronological set of tool observations into one card per call. */
export function mergeToolActivity(items: readonly ToolActivityItem[]): ToolActivityItem[] {
	const merged = new Map<string, ToolActivityItem>();
	const order: string[] = [];
	for (const [index, item] of items.entries()) {
		const key = item.id ?? `${item.name}:${index}`;
		const previous = merged.get(key);
		if (!previous) {
			merged.set(key, { ...item });
			order.push(key);
			continue;
		}
		merged.set(key, {
			...previous,
			...item,
			args: item.args ?? previous.args ?? null,
			result: item.result ?? previous.result ?? null,
			status: item.status ?? previous.status,
			durationMs: item.durationMs ?? previous.durationMs ?? null,
			files: item.files ?? previous.files
		});
	}
	return order.map((key) => merged.get(key)!);
}
