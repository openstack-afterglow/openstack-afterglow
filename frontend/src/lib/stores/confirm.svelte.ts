// 타입 전용 import 라 빌드 시 지워지며 런타임 결합을 만들지 않는다.
import type { ButtonVariant } from '$lib/components/ui/Button.svelte';

export interface ConfirmDialogOptions {
	/** 긍정 버튼 문구. 트리거가 쓴 동사를 그대로 재사용한다. 기본값은 확인. */
	confirmLabel?: string;
	/** 긍정 버튼 variant. 기본값 danger 라 기존 파괴적 흐름은 그대로다. */
	confirmVariant?: ButtonVariant;
}

let _resolve: ((v: boolean) => void) | null = null;
let _open = $state(false);
let _message = $state('');
let _confirmLabel = $state('확인');
let _confirmVariant = $state<ButtonVariant>('danger');

export function confirmDialog(message: string, options: ConfirmDialogOptions = {}): Promise<boolean> {
	return new Promise(resolve => {
		_message = message;
		// 매 호출마다 되돌린다. 모듈 수준 $state 는 대화상자 사이에 남으므로, 되돌리지 않으면
		// 한 번 쓴 accent variant 가 다음 삭제 확인으로 새어 들어간다.
		_confirmLabel = options.confirmLabel ?? '확인';
		_confirmVariant = options.confirmVariant ?? 'danger';
		_open = true;
		_resolve = resolve;
	});
}

export const dialogState = {
	get open() { return _open; },
	get message() { return _message; },
	get confirmLabel() { return _confirmLabel; },
	get confirmVariant() { return _confirmVariant; },
	accept() { _open = false; _resolve?.(true); _resolve = null; },
	reject() { _open = false; _resolve?.(false); _resolve = null; },
};
