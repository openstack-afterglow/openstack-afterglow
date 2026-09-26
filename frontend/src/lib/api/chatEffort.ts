/**
 * thinking(추론) effort 선택 — 순수 함수.
 *
 * 선택지는 모델의 `reasoning_options`(models.dev 유래)에서만 도출한다.
 * 명시적 해제(none)는 Lumen `GET /v1/chat/models`의 `reasoning_none_supported`가 true일 때만 노출한다.
 * Lumen은 끄기를 광고하지 않는 모델(gpt-5, o3, gemini-2.5-pro 등)의 none을 422로 거부하므로,
 * 규칙을 여기서 복제하지 않고 서버 판정을 그대로 따른다. 값이 없으면(구버전 Lumen) 숨긴다.
 */
import type { ModelCapabilities } from './chatContracts';

const _SUPPORTED_NAMED_EFFORTS = new Set([
	'minimal',
	'low',
	'medium',
	'high',
	'xhigh',
	'max',
	'ultra'
]);
const _LABELS: Record<string, string> = {
	auto: '자동',
	none: '없음',
	minimal: '최소',
	low: '낮음',
	medium: '중간',
	high: '높음',
	xhigh: '매우 높음',
	max: '최대',
	ultra: '울트라'
};

/** 모델별 선택지. auto 는 provider 기본, none 은 모델이 지원할 때만 명시적인 추론 비활성화다. */
export function effortOptionsFor(
	caps: ModelCapabilities | null | undefined,
	noneSupported: boolean | null | undefined = false
): string[] {
	if (!caps?.reasoning) return [];
	const opt = caps.reasoning_options?.find((o) => o.type === 'effort');
	const values =
		opt?.values?.filter(
			(value) => typeof value === 'string' && _SUPPORTED_NAMED_EFFORTS.has(value)
		) ?? [];
	return noneSupported === true ? ['auto', 'none', ...values] : ['auto', ...values];
}

/** effort 값 → 표시 라벨(한국어). 매핑 없으면 원문. */
export function effortLabel(value: string): string {
	return _LABELS[value] ?? value;
}

/**
 * 현재 effort가 모델에서 유효한지 확인하고, 아니면 auto(=provider 기본) 반환.
 * 모델을 바꾸면 이전 effort가 새 모델에 없을 수 있으므로 정규화에 사용.
 */
export function normalizeEffort(
	effort: string | null,
	caps: ModelCapabilities | null | undefined,
	noneSupported: boolean | null | undefined = false
): string {
	const selected = effort ?? 'auto';
	return effortOptionsFor(caps, noneSupported).includes(selected) ? selected : 'auto';
}

/**
 * 실제로 실행될 모델 기준으로 effort를 정규화한다. 재생성처럼 composer 모델과 다른 모델로
 * 보내는 경로에서, 그 모델이 지원하지 않는 값(예: gpt-5의 none)을 auto로 바꿔 422를 막는다.
 */
export function effortForModel(
	effort: string | null,
	models: readonly {
		model_name: string;
		capabilities?: ModelCapabilities | null;
		reasoning_none_supported?: boolean;
	}[],
	modelName: string | null | undefined
): string {
	const target = models.find((m) => m.model_name === modelName);
	return normalizeEffort(effort, target?.capabilities, target?.reasoning_none_supported);
}
