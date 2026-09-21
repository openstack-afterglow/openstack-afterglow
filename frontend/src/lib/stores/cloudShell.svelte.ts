import { api, ApiError, getWebSocketUrl } from '$lib/api/client';

export type CloudShellPhase =
	| 'closed'
	| 'consent'
	| 'ticketing'
	| 'provisioning'
	| 'authorizing'
	| 'ready'
	| 'ending'
	| 'error';
export type CloudShellView = 'normal' | 'minimized' | 'maximized';
export type CloudShellWorkspaceState = 'unknown' | 'absent' | 'available' | 'busy' | 'error';
export type CloudShellCloseReason = 'user' | 'project-switch' | 'logout' | 'identity-lost' | 'destroy';

export interface CloudShellIdentity {
	token: string;
	projectId: string;
	projectName: string;
}

interface TicketResponse {
	ticket: string;
	websocket_path: string;
	expires_at: number;
}

interface ServerControl {
	type: 'status' | 'warning' | 'ready' | 'exit' | 'error';
	phase?: string;
	reason?: string;
	code?: string;
	expires_at?: number;
	idle_timeout_seconds?: number;
}

interface WebSocketLike {
	binaryType: BinaryType;
	readyState: number;
	onopen: ((event: Event) => void) | null;
	onmessage: ((event: MessageEvent) => void) | null;
	onerror: ((event: Event) => void) | null;
	onclose: ((event: CloseEvent) => void) | null;
	send(data: string | ArrayBufferLike | ArrayBufferView): void;
	close(code?: number, reason?: string): void;
}

interface TerminalSink {
	write(data: Uint8Array): void;
	clear(): void;
	focus(): void;
	fit(): void;
}

interface CloudShellDependencies {
	issueTicket(identity: CloudShellIdentity): Promise<TicketResponse>;
	deleteWorkspace(identity: CloudShellIdentity): Promise<void>;
	webSocketUrl(path: string): string;
	createWebSocket(url: string): WebSocketLike;
}

export interface CloudShellController {
	readonly phase: CloudShellPhase;
	readonly phaseLabel: string;
	readonly view: CloudShellView;
	readonly visible: boolean;
	readonly statusStep: string;
	readonly error: string;
	readonly resetError: string;
	readonly errorCode: string;
	readonly expiresAt: number | null;
	readonly idleTimeoutSeconds: number | null;
	readonly workspaceState: CloudShellWorkspaceState;
	readonly homeSizeGiB: number;
	readonly resetting: boolean;
	readonly terminalEpoch: number;
	readonly identity: CloudShellIdentity | null;
	readonly active: boolean;
	bindIdentity(identity: CloudShellIdentity | null): void;
	openConsent(): void;
	cancelConsent(): void;
	approve(): Promise<void>;
	close(reason?: CloudShellCloseReason, options?: { keepDock?: boolean }): Promise<void>;
	dismiss(): void;
	retry(): void;
	minimize(): void;
	toggleMaximized(): void;
	restore(): void;
	sendInput(data: string): void;
	resize(cols: number, rows: number): void;
	setTerminalSink(sink: TerminalSink | null): void;
	resetWorkspace(): Promise<boolean>;
}

const defaultDependencies: CloudShellDependencies = {
	issueTicket: (identity) =>
		api.post<TicketResponse>('/api/v1/cloud-shell/tickets', {}, identity.token, identity.projectId),
	deleteWorkspace: (identity) =>
		api.delete('/api/v1/cloud-shell/workspace', identity.token, identity.projectId),
	webSocketUrl: (path) => getWebSocketUrl(path),
	createWebSocket: (url) => new WebSocket(url),
};

const ACTIVE_PHASES = new Set<CloudShellPhase>([
	'ticketing',
	'provisioning',
	'authorizing',
	'ready',
	'ending',
]);
const PHASE_LABEL: Record<CloudShellPhase, string> = {
	closed: '종료됨',
	consent: '승인 대기',
	ticketing: '준비 중',
	provisioning: '준비 중',
	authorizing: '인증 중',
	ready: '연결됨',
	ending: '종료 중',
	error: '오류',
};
const STEP_LABEL: Record<string, string> = {
	provisioning: '홈 확인',
	workspace: '홈 확인',
	container: '컨테이너 준비',
	terminal: '터미널 연결',
	authorizing: '세션 인증',
	ready: '연결됨',
};
const CLOSE_ERROR: Record<number, string> = {
	4401: '승인 티켓 또는 로그인 세션이 만료되었습니다.',
	4403: 'Cloud Shell 연결 권한 또는 origin 검증에 실패했습니다.',
	4408: '20분 동안 입출력이 없어 세션이 종료되었습니다.',
	4410: '다른 탭이나 프로젝트에서 Cloud Shell이 이미 실행 중입니다.',
	4419: '최대 세션 시간 또는 Keystone 토큰 수명이 끝났습니다.',
	4500: 'Cloud Shell 인프라 준비 또는 연결에 실패했습니다.',
};
const ERROR_CODE_MESSAGE: Record<string, string> = {
	active_session: '다른 탭이나 프로젝트에서 Cloud Shell이 이미 실행 중입니다.',
	reservation_exists: 'Cloud Shell 승인이 이미 진행 중입니다. 잠시 후 다시 시도해 주세요.',
	token_expiring: 'Keystone 토큰 만료가 가까워 새 Cloud Shell을 시작할 수 없습니다.',
	workspace_busy: '영구 홈이 사용 중입니다. 활성 Cloud Shell을 먼저 닫아 주세요.',
	workspace_error: '영구 홈 볼륨이 오류 상태입니다. 운영자 확인이 필요합니다.',
	quota_exceeded: 'Cloud Shell 서비스 프로젝트의 할당량이 부족합니다.',
	image_pull_failed: 'Cloud Shell 이미지를 Zun compute에서 가져오지 못했습니다.',
	cinder_unavailable: 'Cloud Shell 영구 홈 스토리지를 확인할 수 없습니다.',
	zun_unavailable: 'Zun Cloud Shell 런타임을 사용할 수 없습니다.',
	coordination_lost: 'Cloud Shell 세션 조정 연결이 끊겼습니다.',
	cleanup_pending: '세션 정리가 아직 끝나지 않았습니다. 잠시 후 다시 시도해 주세요.',
};

function extractApiCode(error: unknown): string | null {
	if (!(error instanceof ApiError)) return null;
	try {
		const parsed = JSON.parse(error.message) as { code?: unknown };
		return typeof parsed.code === 'string' ? parsed.code : null;
	} catch {
		return null;
	}
}

function apiErrorMessage(error: unknown, fallback: string): string {
	const code = extractApiCode(error);
	if (code && ERROR_CODE_MESSAGE[code]) return ERROR_CODE_MESSAGE[code];
	if (error instanceof ApiError && error.status === 409) {
		return 'Cloud Shell 세션 또는 영구 홈이 현재 사용 중입니다.';
	}
	if (error instanceof ApiError && error.status === 503) {
		return 'Cloud Shell 인프라를 현재 사용할 수 없습니다.';
	}
	return fallback;
}

export function createCloudShellController(
	dependencies: CloudShellDependencies = defaultDependencies,
): CloudShellController {
	let phase = $state<CloudShellPhase>('closed');
	let view = $state<CloudShellView>('normal');
	let visible = $state(false);
	let statusStep = $state('');
	let error = $state('');
	let errorCode = $state('');
	let expiresAt = $state<number | null>(null);
	let idleTimeoutSeconds = $state<number | null>(null);
	let resetError = $state('');
	let workspaceState = $state<CloudShellWorkspaceState>('unknown');
	let homeSizeGiB = $state(5);
	let resetting = $state(false);
	let terminalEpoch = $state(0);
	let identity = $state<CloudShellIdentity | null>(null);
	let socket: WebSocketLike | null = null;
	let terminalSink: TerminalSink | null = null;
	let connectionSerial = 0;

	function setError(message: string, code = '') {
		phase = 'error';
		visible = true;
		error = message;
		errorCode = code;
		statusStep = '';
	}

	function clearSessionState() {
		expiresAt = null;
		idleTimeoutSeconds = null;
		terminalEpoch += 1;
		terminalSink?.clear();
	}

	function disconnectSocket(reason: CloudShellCloseReason) {
		connectionSerial += 1;
		const active = socket;
		socket = null;
		if (active && active.readyState < 2) active.close(1000, reason);
	}

	function bindIdentity(next: CloudShellIdentity | null) {
		if (
			(identity === null && next === null) ||
			(identity !== null &&
				next !== null &&
				identity.token === next.token &&
				identity.projectId === next.projectId &&
				identity.projectName === next.projectName)
		) {
			return;
		}
		const projectChanged = identity && next && identity.projectId !== next.projectId;
		const lost = identity && !next;
		if ((projectChanged || lost) && (visible || phase !== 'closed')) {
			void close(projectChanged ? 'project-switch' : 'identity-lost', { keepDock: false });
		}
		identity = next;
	}

	function openConsent() {
		if (!identity) return;
		if (ACTIVE_PHASES.has(phase)) {
			visible = true;
			view = 'normal';
			return;
		}
		error = '';
		errorCode = '';
		phase = 'consent';
		view = 'normal';
	}

	function cancelConsent() {
		if (phase !== 'consent') return;
		phase = 'closed';
		if (!visible) statusStep = '';
	}

	function handleControl(control: ServerControl) {
		if (control.type === 'status') {
			const serverPhase = control.phase ?? '';
			statusStep = STEP_LABEL[serverPhase] ?? 'Cloud Shell 준비';
			phase = serverPhase === 'authorizing' ? 'authorizing' : 'provisioning';
			return;
		}
		if (control.type === 'ready') {
			phase = 'ready';
			statusStep = STEP_LABEL.ready;
			error = '';
			errorCode = '';
			expiresAt = typeof control.expires_at === 'number' ? control.expires_at : null;
			idleTimeoutSeconds =
				typeof control.idle_timeout_seconds === 'number' ? control.idle_timeout_seconds : null;
			workspaceState = 'available';
			queueMicrotask(() => {
				terminalSink?.fit();
				terminalSink?.focus();
			});
			return;
		}
		if (control.type === 'warning') {
			statusStep = control.reason === 'idle_timeout' ? '입출력 유휴 시간 만료' : '세션 종료 예정';
			return;
		}
		if (control.type === 'exit') {
			phase = 'ending';
			statusStep = control.reason === 'idle_timeout' ? '유휴 시간으로 종료 중' : '세션 종료 중';
			return;
		}
		if (control.type === 'error') {
			const code = control.code ?? 'terminal_failed';
			setError(ERROR_CODE_MESSAGE[code] ?? 'Cloud Shell 세션에서 오류가 발생했습니다.', code);
			disconnectSocket('destroy');
		}
	}

	async function handleMessage(data: unknown) {
		if (typeof data === 'string') {
			try {
				handleControl(JSON.parse(data) as ServerControl);
			} catch {
				setError('Cloud Shell 제어 메시지가 올바르지 않습니다.', 'protocol_error');
				disconnectSocket('destroy');
			}
			return;
		}
		if (data instanceof ArrayBuffer) {
			terminalSink?.write(new Uint8Array(data));
			return;
		}
		if (ArrayBuffer.isView(data)) {
			terminalSink?.write(new Uint8Array(data.buffer, data.byteOffset, data.byteLength));
			return;
		}
		if (typeof Blob !== 'undefined' && data instanceof Blob) {
			terminalSink?.write(new Uint8Array(await data.arrayBuffer()));
		}
	}

	async function approve() {
		if (phase !== 'consent' || !identity) return;
		const approvedIdentity = { ...identity };
		phase = 'ticketing';
		visible = true;
		view = 'normal';
		statusStep = '승인 티켓 발급';
		error = '';
		errorCode = '';
		resetError = '';
		terminalEpoch += 1;
		terminalSink?.clear();
		try {
			const ticket = await dependencies.issueTicket(approvedIdentity);
			if (!identity || identity.projectId !== approvedIdentity.projectId || phase !== 'ticketing') return;
			const separator = ticket.websocket_path.includes('?') ? '&' : '?';
			const url = dependencies.webSocketUrl(
				`${ticket.websocket_path}${separator}ticket=${encodeURIComponent(ticket.ticket)}`,
			);
			const nextSocket = dependencies.createWebSocket(url);
			nextSocket.binaryType = 'arraybuffer';
			socket = nextSocket;
			const serial = ++connectionSerial;
			phase = 'provisioning';
			statusStep = '홈 확인';
			nextSocket.onopen = () => {
				if (socket !== nextSocket || serial !== connectionSerial) return;
				phase = 'provisioning';
			};
			nextSocket.onmessage = (event) => {
				if (socket !== nextSocket || serial !== connectionSerial) return;
				void handleMessage(event.data);
			};
			nextSocket.onerror = () => {
				if (socket !== nextSocket || serial !== connectionSerial || phase === 'ending') return;
				setError('Cloud Shell WebSocket 연결에 실패했습니다.', 'websocket_error');
				disconnectSocket('destroy');
			};
			nextSocket.onclose = (event) => {
				if (socket !== nextSocket || serial !== connectionSerial) return;
				socket = null;
				if (phase === 'ending') {
					phase = 'closed';
					statusStep = '세션 종료됨 · 영구 홈 유지';
					clearSessionState();
					return;
				}
				if (event.code === 1000 || event.code === 1001) {
					phase = 'closed';
					statusStep = '세션 종료됨 · 영구 홈 유지';
					clearSessionState();
					return;
				}
				setError(CLOSE_ERROR[event.code] ?? 'Cloud Shell 연결이 예기치 않게 종료되었습니다.', errorCode);
			};
		} catch (caught) {
			setError(apiErrorMessage(caught, 'Cloud Shell 승인에 실패했습니다.'), extractApiCode(caught) ?? '');
		}
	}

	async function close(
		reason: CloudShellCloseReason = 'user',
		options: { keepDock?: boolean } = {},
	) {
		const keepDock = options.keepDock ?? reason === 'user';
		if (phase !== 'closed') {
			phase = 'ending';
			statusStep = '세션 종료 중';
		}
		disconnectSocket(reason);
		clearSessionState();
		phase = 'closed';
		statusStep = keepDock ? '세션 종료됨 · 영구 홈 유지' : '';
		visible = keepDock;
		view = 'normal';
		await Promise.resolve();
	}

	function dismiss() {
		if (ACTIVE_PHASES.has(phase)) return;
		visible = false;
	}

	function retry() {
		if (phase !== 'error' && phase !== 'closed') return;
		openConsent();
	}

	function minimize() {
		if (!visible) return;
		view = 'minimized';
	}

	function toggleMaximized() {
		if (!visible) return;
		view = view === 'maximized' ? 'normal' : 'maximized';
	}

	function restore() {
		if (!visible) return;
		view = 'normal';
	}

	function sendInput(data: string) {
		if (phase !== 'ready' || !socket || socket.readyState !== 1) return;
		const bytes = new TextEncoder().encode(data);
		for (let offset = 0; offset < bytes.length; offset += 64 * 1024) {
			socket.send(bytes.subarray(offset, offset + 64 * 1024));
		}
	}

	function resize(cols: number, rows: number) {
		if (phase !== 'ready' || !socket || socket.readyState !== 1) return;
		const boundedCols = Math.max(20, Math.min(500, Math.trunc(cols)));
		const boundedRows = Math.max(5, Math.min(200, Math.trunc(rows)));
		socket.send(JSON.stringify({ type: 'resize', cols: boundedCols, rows: boundedRows }));
	}

	function setTerminalSink(next: TerminalSink | null) {
		terminalSink = next;
		if (next && phase === 'ready') {
			queueMicrotask(() => {
				next.fit();
				next.focus();
			});
		}
	}

	async function resetWorkspace() {
		if (!identity || resetting) return false;
		resetting = true;
		error = '';
		resetError = '';
		try {
			await dependencies.deleteWorkspace(identity);
			workspaceState = 'absent';
			statusStep = '영구 홈 초기화 완료';
			return true;
		} catch (caught) {
			const message = apiErrorMessage(caught, 'Cloud Shell 영구 홈 초기화에 실패했습니다.');
			if (ACTIVE_PHASES.has(phase)) resetError = message;
			else setError(message, extractApiCode(caught) ?? '');
			return false;
		} finally {
			resetting = false;
		}
	}

	return {
		get phase() { return phase; },
		get phaseLabel() { return PHASE_LABEL[phase]; },
		get view() { return view; },
		get visible() { return visible; },
		get statusStep() { return statusStep; },
		get error() { return error; },
		get errorCode() { return errorCode; },
		get expiresAt() { return expiresAt; },
		get idleTimeoutSeconds() { return idleTimeoutSeconds; },
		get workspaceState() { return workspaceState; },
		get homeSizeGiB() { return homeSizeGiB; },
		get resetting() { return resetting; },
		get terminalEpoch() { return terminalEpoch; },
		get identity() { return identity; },
		get resetError() { return resetError; },
		get active() { return ACTIVE_PHASES.has(phase); },
		bindIdentity,
		openConsent,
		cancelConsent,
		approve,
		close,
		dismiss,
		retry,
		minimize,
		toggleMaximized,
		restore,
		sendInput,
		resize,
		setTerminalSink,
		resetWorkspace,
	};
}

export const cloudShell = createCloudShellController();
