import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { installExperienceCollector } from '$lib/utils/experience';
import { cloudShell } from '$lib/stores/cloudShell.svelte';
import CloudShellDock from './CloudShellDock.svelte';

const terminalInstances: FakeTerminal[] = [];
let activeSocket: FakeSocket | null = null;

class FakeTerminal {
	static strings = { promptLabel: 'Terminal input', tooMuchOutput: 'Too much output to announce, navigate to rows manually to read' };
	options: Record<string, unknown>;
	writes: Uint8Array[] = [];
	disposed = false;
	private dataHandler: ((data: string) => void) | null = null;

	constructor(options: Record<string, unknown>) {
		this.options = { ...options };
		terminalInstances.push(this);
	}

	loadAddon() {}
	open() {}
	focus() {}
	reset() {}
	write(data: Uint8Array) { this.writes.push(data); }
	dispose() { this.disposed = true; }
	onData(handler: (data: string) => void) {
		this.dataHandler = handler;
		return { dispose: () => { this.dataHandler = null; } };
	}
	onResize() { return { dispose: () => {} }; }
	emitData(data: string) { this.dataHandler?.(data); }
}

class FakeFitAddon {
	fit() {}
}

class FakeWebLinksAddon {}

class FakeSocket {
	binaryType: BinaryType = 'blob';
	readyState: number = WebSocket.CONNECTING;
	onopen: ((event: Event) => void) | null = null;
	onmessage: ((event: MessageEvent) => void) | null = null;
	onerror: ((event: Event) => void) | null = null;
	onclose: ((event: CloseEvent) => void) | null = null;
	sent: Array<string | ArrayBufferLike | ArrayBufferView> = [];
	constructor(readonly url: string) {}

	send(data: string | ArrayBufferLike | ArrayBufferView) { this.sent.push(data); }
	close() { this.readyState = WebSocket.CLOSED; }
	open() {
		this.readyState = WebSocket.OPEN;
		this.onopen?.(new Event('open'));
	}
	message(data: unknown) { this.onmessage?.({ data } as MessageEvent); }
}

vi.mock('@xterm/xterm', () => ({ Terminal: FakeTerminal }));
vi.mock('@xterm/addon-fit', () => ({ FitAddon: FakeFitAddon }));
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: FakeWebLinksAddon }));
vi.mock('$lib/utils/terminalTheme', () => ({ getTerminalTheme: () => ({ background: 'transparent' }) }));
vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: {
		post: vi.fn().mockResolvedValue({
			ticket: 'CLOUD_SHELL_TICKET_CANARY_7b2d',
			websocket_path: '/api/v1/cloud-shell/ws',
			expires_at: 2_000_000_000,
		}),
		delete: vi.fn().mockResolvedValue(undefined),
	},
	getWebSocketUrl: (path: string) => `wss://afterglow.example${path}`,
}));

class ResizeObserverStub {
	observe() {}
	disconnect() {}
}

describe('CloudShellTerminal lifecycle', () => {
	beforeEach(() => {
		terminalInstances.length = 0;
		activeSocket = null;
		vi.stubGlobal('ResizeObserver', ResizeObserverStub);
		vi.stubGlobal('WebSocket', class {
			static CONNECTING = 0;
			static OPEN = 1;
			static CLOSING = 2;
			static CLOSED = 3;
			constructor(url: string) {
				activeSocket = new FakeSocket(url);
				return activeSocket;
			}
		});
	});

	afterEach(async () => {
		await cloudShell.close('destroy', { keepDock: false });
		cloudShell.bindIdentity(null);
		vi.unstubAllGlobals();
	});

	it('keeps binary terminal content out of non-empty semantic diagnostics across ready, minimize, error and close', async () => {
		const canaries = {
			token: 'CLOUD_SHELL_TOKEN_CANARY_9c1a',
			ticket: 'CLOUD_SHELL_TICKET_CANARY_7b2d',
			command: 'printf "SHELL_COMMAND_CANARY_8ea1_비밀"\\n\r',
			output: 'SHELL_OUTPUT_CANARY_4f2e_비밀',
			kubeconfig: 'apiVersion: v1\nusers:\n- name: SHELL_KUBECONFIG_CANARY_6d3b\n  user:\n    token: SHELL_KUBE_TOKEN_CANARY_2c7f',
		};
		const originalFetch = window.fetch;
		const wire: string[] = [];
		const rows: { event_type: string; component: string; payload: { state?: string; stage?: string; reason?: string } }[] = [];
		window.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
			if (String(input).endsWith('/experience-contract')) return Response.json({ schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 });
			if (!String(input).endsWith('/experience-events')) throw new Error('Unexpected cloud shell replay transport');
			const body = String(init?.body);
			wire.push(body);
			const batch = JSON.parse(body);
			rows.push(...batch.events);
			return Response.json({ schema_version: 2, accepted: batch.events.length, duplicates: 0 }, { status: 201 });
		});
		const collector = installExperienceCollector({
			getOwner: () => ({ token: canaries.token, sessionId: 'shell-session', userId: 'shell-user', domainId: 'shell-domain', projectId: 'shell-project' }),
			getRoute: () => '/dashboard', getBaseUrl: () => 'http://localhost:8000',
			isEnabled: () => true, isSuppressed: () => false, subscribeOwner: () => () => {},
		});
		let unmount: (() => void) | undefined;
		try {
			cloudShell.bindIdentity({ token: canaries.token, userId: 'shell-user', sessionId: 'shell-session', projectId: 'shell-project', projectName: 'Project' });
			cloudShell.openConsent();
			await cloudShell.approve();

			// xterm and the remote WebSocket are fixtures; the dock, store and collector are real.
			const view = render(CloudShellDock);
			unmount = view.unmount;
			await waitFor(() => expect(terminalInstances).toHaveLength(1));
			const terminal = terminalInstances[0];
			const socket = activeSocket!;
			expect(terminal.options.disableStdin).toBe(true);
			expect(socket).not.toBeNull();
			expect(socket.url).toContain(`/api/v1/cloud-shell/ws?ticket=${canaries.ticket}`);
			expect(socket.binaryType).toBe('arraybuffer');
			socket.open();
			socket.message(JSON.stringify({ type: 'ready' }));
			await waitFor(() => expect(terminal.options.disableStdin).toBe(false));
			await tick();
			await collector.flush();
			expect(rows).toEqual(expect.arrayContaining([
				expect.objectContaining({ event_type: 'view.state_changed', component: 'shared.stream', payload: { state: 'ready', step: 1 } }),
				expect.objectContaining({ event_type: 'result.committed', payload: { stage: 'dom' } }),
			]));

			terminal.emitData(canaries.command);
			expect(socket.sent).toHaveLength(1);
			expect(ArrayBuffer.isView(socket.sent[0])).toBe(true);
			expect(new TextDecoder().decode(socket.sent[0] as Uint8Array)).toBe(canaries.command);
			const outputBytes = new TextEncoder().encode(canaries.output);
			// WebSocket ArrayBuffers belong to the browser realm, unlike Node's TextEncoder buffer in jsdom.
			const outputBuffer = new window.ArrayBuffer(outputBytes.byteLength);
			new window.Uint8Array(outputBuffer).set(outputBytes);
			expect(outputBuffer).toBeInstanceOf(ArrayBuffer);
			socket.message(outputBuffer);
			await waitFor(() => expect(terminal.writes).toHaveLength(1));
			await fireEvent.click(screen.getByRole('button', { name: 'Cloud Shell 최소화' }));
			socket.message(new TextEncoder().encode(canaries.kubeconfig));
			await waitFor(() => expect(terminal.writes).toHaveLength(2));
			expect(terminalInstances).toHaveLength(1);
			expect(terminal.disposed).toBe(false);
			await fireEvent.click(screen.getByRole('button', { name: 'Cloud Shell 복원' }));
			expect(terminal.writes.map((value) => new TextDecoder().decode(value))).toEqual([canaries.output, canaries.kubeconfig]);

			rows.length = 0;
			// A readiness application superseded before its DOM tick must be discarded by the real owner.
			socket.message(JSON.stringify({ type: 'ready' }));
			socket.message(JSON.stringify({ type: 'error', code: 'terminal_failed' }));
			await waitFor(() => expect(terminal.options.disableStdin).toBe(true));
			await collector.flush();
			expect(rows.some(row => row.event_type === 'view.state_changed' && row.payload.state === 'error')).toBe(true);
			expect(rows.some(row => row.event_type === 'result.discarded' && row.payload.stage === 'dom' && row.payload.reason === 'stale')).toBe(true);
			expect(rows.some(row => row.event_type === 'result.committed')).toBe(false);
			rows.length = 0;
			await cloudShell.close('user');
			await tick();
			await collector.flush();
			expect(rows.some(row => row.event_type === 'view.state_changed' && row.payload.state === 'disabled')).toBe(true);
			expect(rows.some(row => row.event_type === 'result.applied' && row.payload.stage === 'state')).toBe(true);
			expect(wire.length).toBeGreaterThan(0);
			for (const canary of Object.values(canaries)) {
				expect(wire.join('\n')).not.toContain(canary);
				expect(JSON.stringify(rows)).not.toContain(canary);
			}
			expect(wire.join('\n')).not.toMatch(/SHELL_COMMAND_CANARY|SHELL_OUTPUT_CANARY|SHELL_KUBECONFIG_CANARY|SHELL_KUBE_TOKEN_CANARY/);
		} finally {
			unmount?.();
			await cloudShell.close('destroy', { keepDock: false });
			collector.destroy();
			window.fetch = originalFetch;
		}
	});
});
