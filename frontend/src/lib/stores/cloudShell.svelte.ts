import { api, ApiError, getWebSocketUrl } from '$lib/api/client';
import { t } from '$lib/i18n/ns/containers-shell';

type MessageKey = Parameters<typeof t>[0];

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
const PHASE_LABEL: Record<CloudShellPhase, MessageKey> = {
	closed: 'shell.phase.closed',
	consent: 'shell.phase.consent',
	ticketing: 'shell.phase.ticketing',
	provisioning: 'shell.phase.provisioning',
	authorizing: 'shell.phase.authorizing',
	ready: 'shell.phase.ready',
	ending: 'shell.phase.ending',
	error: 'shell.phase.error',
};
const STEP_LABEL: Partial<Record<string, MessageKey>> = {
	provisioning: 'shell.step.home',
	workspace: 'shell.step.home',
	container: 'shell.step.container',
	terminal: 'shell.step.terminal',
	authorizing: 'shell.step.authorizing',
	ready: 'shell.step.ready',
};
const CLOSE_ERROR: Partial<Record<number, MessageKey>> = {
	4401: 'shell.error.ticketExpired',
	4403: 'shell.error.permission',
	4408: 'shell.error.idleTimeout',
	4410: 'shell.error.activeSession',
	4419: 'shell.error.maxLifetime',
	4500: 'shell.error.infrastructure',
};
const ERROR_CODE_MESSAGE: Partial<Record<string, MessageKey>> = {
	active_session: 'shell.error.activeSession',
	reservation_exists: 'shell.error.reservationExists',
	token_expiring: 'shell.error.tokenExpiring',
	workspace_busy: 'shell.error.workspaceBusy',
	workspace_error: 'shell.error.workspaceError',
	quota_exceeded: 'shell.error.quotaExceeded',
	image_pull_failed: 'shell.error.imagePullFailed',
	cinder_unavailable: 'shell.error.cinderUnavailable',
	zun_unavailable: 'shell.error.zunUnavailable',
	coordination_lost: 'shell.error.coordinationLost',
	cleanup_pending: 'shell.error.cleanupPending',
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

function apiErrorKey(error: unknown, fallback: MessageKey): MessageKey {
	const code = extractApiCode(error);
	const messageKey = code ? ERROR_CODE_MESSAGE[code] : undefined;
	if (messageKey) return messageKey;
	if (error instanceof ApiError && error.status === 409) {
		return 'shell.error.busy';
	}
	if (error instanceof ApiError && error.status === 503) {
		return 'shell.error.unavailable';
	}
	return fallback;
}

export function createCloudShellController(
	dependencies: CloudShellDependencies = defaultDependencies,
): CloudShellController {
	let phase = $state<CloudShellPhase>('closed');
	let view = $state<CloudShellView>('normal');
	let visible = $state(false);
	let statusStep = $state<MessageKey | ''>('');
	let error = $state<MessageKey | ''>('');
	let errorCode = $state('');
	let expiresAt = $state<number | null>(null);
	let idleTimeoutSeconds = $state<number | null>(null);
	let resetError = $state<MessageKey | ''>('');
	let workspaceState = $state<CloudShellWorkspaceState>('unknown');
	let homeSizeGiB = $state(5);
	let resetting = $state(false);
	let terminalEpoch = $state(0);
	let identity = $state<CloudShellIdentity | null>(null);
	let socket: WebSocketLike | null = null;
	let terminalSink: TerminalSink | null = null;
	let connectionSerial = 0;

	function setError(message: MessageKey, code = '') {
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
			statusStep = STEP_LABEL[serverPhase] ?? 'shell.step.preparing';
			phase = serverPhase === 'authorizing' ? 'authorizing' : 'provisioning';
			return;
		}
		if (control.type === 'ready') {
			phase = 'ready';
			statusStep = 'shell.step.ready';
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
			statusStep = control.reason === 'idle_timeout' ? 'shell.step.idleExpired' : 'shell.step.endingSoon';
			return;
		}
		if (control.type === 'exit') {
			phase = 'ending';
			statusStep = control.reason === 'idle_timeout' ? 'shell.step.endingIdle' : 'shell.step.ending';
			return;
		}
		if (control.type === 'error') {
			const code = control.code ?? 'terminal_failed';
			setError(ERROR_CODE_MESSAGE[code] ?? 'shell.error.session', code);
			disconnectSocket('destroy');
		}
	}

	async function handleMessage(data: unknown) {
		if (typeof data === 'string') {
			try {
				handleControl(JSON.parse(data) as ServerControl);
			} catch {
				setError('shell.error.protocol', 'protocol_error');
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
		statusStep = 'shell.step.ticket';
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
			statusStep = 'shell.step.home';
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
				setError('shell.error.websocket', 'websocket_error');
				disconnectSocket('destroy');
			};
			nextSocket.onclose = (event) => {
				if (socket !== nextSocket || serial !== connectionSerial) return;
				socket = null;
				if (phase === 'ending') {
					phase = 'closed';
					statusStep = 'shell.step.closed';
					clearSessionState();
					return;
				}
				if (event.code === 1000 || event.code === 1001) {
					phase = 'closed';
					statusStep = 'shell.step.closed';
					clearSessionState();
					return;
				}
				setError(CLOSE_ERROR[event.code] ?? 'shell.error.unexpectedClose', errorCode);
			};
		} catch (caught) {
			setError(apiErrorKey(caught, 'shell.error.approval'), extractApiCode(caught) ?? '');
		}
	}

	async function close(
		reason: CloudShellCloseReason = 'user',
		options: { keepDock?: boolean } = {},
	) {
		const keepDock = options.keepDock ?? reason === 'user';
		if (phase !== 'closed') {
			phase = 'ending';
			statusStep = 'shell.step.ending';
		}
		disconnectSocket(reason);
		clearSessionState();
		phase = 'closed';
		statusStep = keepDock ? 'shell.step.closed' : '';
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
			statusStep = 'shell.step.homeReset';
			return true;
		} catch (caught) {
			const message = apiErrorKey(caught, 'shell.error.reset');
			if (ACTIVE_PHASES.has(phase)) resetError = message;
			else setError(message, extractApiCode(caught) ?? '');
			return false;
		} finally {
			resetting = false;
		}
	}

	return {
		get phase() { return phase; },
		get phaseLabel() { return t(PHASE_LABEL[phase]); },
		get view() { return view; },
		get visible() { return visible; },
		get statusStep() { return statusStep ? t(statusStep) : ''; },
		get error() { return error ? t(error) : ''; },
		get errorCode() { return errorCode; },
		get expiresAt() { return expiresAt; },
		get idleTimeoutSeconds() { return idleTimeoutSeconds; },
		get workspaceState() { return workspaceState; },
		get homeSizeGiB() { return homeSizeGiB; },
		get resetting() { return resetting; },
		get terminalEpoch() { return terminalEpoch; },
		get identity() { return identity; },
		get resetError() { return resetError ? t(resetError) : ''; },
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
