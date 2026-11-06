// 타입 전용 import 라 빌드 시 지워지며 런타임 결합을 만들지 않는다.
import type { ButtonVariant } from '$lib/components/ui/Button.svelte';

export interface ConfirmDialogOptions {
	/** 긍정 버튼 문구. 트리거가 쓴 동사를 그대로 재사용한다. 기본값은 현재 언어의 확인. */
	confirmLabel?: string;
	/** 긍정 버튼 variant. 기본값 danger 라 기존 파괴적 흐름은 그대로다. */
	confirmVariant?: ButtonVariant;
	/** 지정한 문자열과 정확히 일치하는 입력이 있어야 확인할 수 있다. */
	requiredText?: string;
	/** 필수 입력의 표시 레이블. 생략하면 requiredText 를 사용한다. */
	requiredTextLabel?: string;
}

let _resolve: ((v: boolean) => void) | null = null;
let _open = $state(false);
let _message = $state('');
let _confirmLabel = $state<string | undefined>(undefined);
let _confirmVariant = $state<ButtonVariant>('danger');
let _requiredText = $state<string | undefined>(undefined);
let _requiredTextLabel = $state<string | undefined>(undefined);
let _requestId = $state(0);

export function confirmDialog(message: string, options: ConfirmDialogOptions = {}): Promise<boolean> {
	return new Promise(resolve => {
		_message = message;
		// 매 호출마다 되돌린다. 모듈 수준 $state 는 대화상자 사이에 남으므로, 되돌리지 않으면
		// 한 번 쓴 accent variant 가 다음 삭제 확인으로 새어 들어간다.
		_confirmLabel = options.confirmLabel;
		_confirmVariant = options.confirmVariant ?? 'danger';
		_requiredText = options.requiredText;
		_requiredTextLabel = options.requiredTextLabel;
		_requestId += 1;
		_open = true;
		_resolve = resolve;
	});
}

export const dialogState = {
	get open() { return _open; },
	get message() { return _message; },
	get confirmLabel() { return _confirmLabel; },
	get confirmVariant() { return _confirmVariant; },
	get requiredText() { return _requiredText; },
	get requiredTextLabel() { return _requiredTextLabel; },
	get requestId() { return _requestId; },
	accept(value?: string) {
		if (_requiredText !== undefined && value !== _requiredText) return;
		_open = false;
		_resolve?.(true);
		_resolve = null;
	},
	reject() { _open = false; _resolve?.(false); _resolve = null; },
};
