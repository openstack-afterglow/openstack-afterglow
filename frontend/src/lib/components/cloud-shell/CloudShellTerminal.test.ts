import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const terminalInstances: FakeTerminal[] = [];
let activeSocket: FakeSocket | null = null;

class FakeTerminal {
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
			ticket: 'ticket',
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
			constructor() {
				activeSocket = new FakeSocket();
				return activeSocket;
			}
		});
	});

	afterEach(async () => {
		const { cloudShell } = await import('$lib/stores/cloudShell.svelte');
		await cloudShell.close('destroy', { keepDock: false });
		cloudShell.bindIdentity(null);
		vi.unstubAllGlobals();
	});

	it('enables real input after ready and preserves the mounted terminal while minimized', async () => {
		const { cloudShell } = await import('$lib/stores/cloudShell.svelte');
		const { default: CloudShellDock } = await import('./CloudShellDock.svelte');
		cloudShell.bindIdentity({ token: 'token', projectId: 'project', projectName: 'Project' });
		cloudShell.openConsent();
		await cloudShell.approve();

		render(CloudShellDock);
		await waitFor(() => expect(terminalInstances).toHaveLength(1));
		const terminal = terminalInstances[0];
		expect(terminal.options.disableStdin).toBe(true);
		expect(activeSocket).not.toBeNull();

		activeSocket!.open();
		activeSocket!.message(JSON.stringify({ type: 'ready' }));
		await waitFor(() => expect(terminal.options.disableStdin).toBe(false));

		terminal.emitData('a');
		expect(activeSocket!.sent).toHaveLength(1);
		expect(ArrayBuffer.isView(activeSocket!.sent[0])).toBe(true);
		expect(new TextDecoder().decode(activeSocket!.sent[0] as Uint8Array)).toBe('a');

		activeSocket!.message(new TextEncoder().encode('before-minimize'));
		await waitFor(() => expect(terminal.writes).toHaveLength(1));
		await fireEvent.click(screen.getByRole('button', { name: 'Cloud Shell 최소화' }));
		activeSocket!.message(new TextEncoder().encode('while-minimized'));
		await waitFor(() => expect(terminal.writes).toHaveLength(2));

		expect(terminalInstances).toHaveLength(1);
		expect(terminal.disposed).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: 'Cloud Shell 복원' }));
		expect(terminal.writes.map((value) => new TextDecoder().decode(value))).toEqual([
			'before-minimize',
			'while-minimized',
		]);
	});
});
