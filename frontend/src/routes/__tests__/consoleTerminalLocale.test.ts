import { cleanup, render, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import type * as StoreModule from 'svelte/store';
import type { Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from '$app/stores';
import { initLocale, setLocale } from '$lib/i18n/runtime.svelte';
import Harness from './_ConsoleTerminalLocaleHarness.svelte';

// Mock factories run before imports; their terminal/socket state must exist at that boundary.
const { TestTerminal, TestSocket, terminals, sockets } = vi.hoisted(() => {
	const terminals: TestTerminal[] = [];
	const sockets: TestSocket[] = [];
	class TestTerminal {
		static strings = { promptLabel: 'Terminal input', tooMuchOutput: 'Too much output' };
		options: Record<string, unknown>;
		writes: Array<string | Uint8Array> = [];
		disposed = false;
		private input: ((data: string) => void) | null = null;
		constructor(options: Record<string, unknown>) { this.options = { ...options }; terminals.push(this); }
		loadAddon() {}
		open() {}
		write(data: string | Uint8Array) { this.writes.push(data); }
		dispose() { this.disposed = true; }
		onData(handler: (data: string) => void) { this.input = handler; return { dispose() {} }; }
		onResize() { return { dispose() {} }; }
		emitData(data: string) { this.input?.(data); }
	}
	class TestSocket {
		static CONNECTING = 0;
		static OPEN = 1;
		static CLOSED = 3;
		readyState = TestSocket.CONNECTING;
		binaryType = 'blob';
		onopen: (() => void) | null = null;
		onmessage: ((event: { data: unknown }) => void) | null = null;
		onclose: ((event: { code: number }) => void) | null = null;
		onerror: (() => void) | null = null;
		sent: Array<string | Uint8Array> = [];
		constructor() { sockets.push(this); }
		open() { this.readyState = TestSocket.OPEN; this.onopen?.(); }
		message(data: unknown) { this.onmessage?.({ data }); }
		send(data: string | Uint8Array) { this.sent.push(data); }
		close() { this.readyState = TestSocket.CLOSED; this.onclose?.({ code: 1000 }); }
	}
	return { TestTerminal, TestSocket, terminals, sockets };
});

vi.mock('@xterm/xterm', () => ({ Terminal: TestTerminal }));
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }));
vi.mock('$lib/utils/terminalTheme', () => ({ getTerminalTheme: () => ({ background: 'transparent' }) }));
// Load the substitute through Vitest's actual-module boundary, not the mocked component.
vi.mock('$lib/components/Sidebar.svelte', () => vi.importActual('$lib/components/LoadingSkeleton.svelte'));
vi.mock('$lib/components/AdminSidebar.svelte', () => vi.importActual('$lib/components/LoadingSkeleton.svelte'));
vi.mock('$lib/components/VmCreatePanel.svelte', () => vi.importActual('$lib/components/LoadingSkeleton.svelte'));
vi.mock('$lib/tutorial/status', () => ({ loadTutorialStatuses() {} }));
vi.mock('$lib/stores/projectList', () => ({ projectList: { prefetch() {} } }));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await vi.importActual<typeof StoreModule>('svelte/store');
	return {
		auth: writable({ token: 'synthetic-token', projectId: 'project', userId: 'user', roles: ['admin'], isSystemAdmin: true }),
		isAdmin: writable(true),
		authReady: writable(true),
		projectSwitching: writable(false),
	};
});
vi.mock('$app/stores', async () => {
	const { writable } = await vi.importActual<typeof StoreModule>('svelte/store');
	return { page: writable({ url: new URL('http://localhost/dashboard'), route: { id: '/dashboard' } }) };
});
vi.mock('$lib/api/client', () => ({
	ApiError: class extends Error {},
	api: {
		get: vi.fn().mockImplementation(async (path: string) => path === '/api/v1/projects/current/permissions'
			? { is_owner: false, is_manager: false, can_write: false, service_permissions: { drover: ['drover-inventory_reader', 'drover-workloads_editor'] } }
			: { id: 'cluster', name: 'Cluster', is_system_admin: true, roles: ['admin'] }),
		post: vi.fn().mockResolvedValue({ ticket: 'ticket' }),
	},
	getBaseUrl: () => 'http://localhost',
	getWebSocketUrl: (path: string) => `ws://localhost${path}`,
}));

// The SvelteKit mock supplies a writable store; the public API intentionally exposes Readable.
const routePage = page as unknown as Writable<{ url: URL; route: { id: string } }>;

async function mountTerminal(route: string, kind: 'container' | 'k3s') {
	routePage.set({ url: new URL(`http://localhost${route.replace('[id]', 'resource')}`), route: { id: route } });
	render(Harness, { kind, admin: route.startsWith('/admin/') });
	await waitFor(() => expect(sockets).toHaveLength(1));
	sockets[0].open();
	await tick();
	return { terminal: terminals[0], socket: sockets[0] };
}

function output(kind: 'container' | 'k3s', text: string) {
	if (kind === 'container') return text;
	const bytes = new TextEncoder().encode(text);
	const frame = new Uint8Array(bytes.length + 1);
	frame[0] = 1;
	frame.set(bytes, 1);
	return frame.buffer;
}

describe('console terminal lifetime across language changes', () => {
	beforeEach(() => {
		initLocale('ko');
		terminals.length = 0;
		sockets.length = 0;
		vi.stubGlobal('WebSocket', TestSocket);
		vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
	});

	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
		initLocale('ko');
	});

	it.each([
		['/dashboard/containers/instances/[id]', 'container'],
		['/dashboard/drover', 'k3s'],
		['/dashboard/drover/[id]', 'k3s'],
		['/admin/drover', 'k3s'],
	] as const)('preserves input, socket and remote output on %s', async (route, kind) => {
		const { terminal, socket } = await mountTerminal(route, kind);
		socket.message(output(kind, 'before-language-change\n'));
		for (const locale of ['en', 'ja', 'zh-CN', 'ko'] as const) {
			setLocale(locale);
			await tick();
			expect(terminal.disposed).toBe(false);
			expect(socket.readyState).toBe(TestSocket.OPEN);
		}
		socket.message(output(kind, 'after-language-change\n'));
		const text = terminal.writes.map(value => typeof value === 'string' ? value : new TextDecoder().decode(value)).join('');
		expect(text).toContain('before-language-change\nafter-language-change\n');
		terminal.emitData('echo still-connected\n');
		const sent = socket.sent.at(-1)!;
		expect(typeof sent === 'string' ? sent : new TextDecoder().decode(sent.subarray(1))).toBe('echo still-connected\n');
		cleanup();
		expect(socket.readyState).toBe(TestSocket.CLOSED);
		expect(terminal.disposed).toBe(true);
	});

	it.each(['/dashboard/account', '/admin/settings'])('retains locale remount cleanup for ordinary pages at %s', async route => {
		const { terminal, socket } = await mountTerminal(route, 'container');
		setLocale('en');
		await tick();
		expect(socket.readyState).toBe(TestSocket.CLOSED);
		expect(terminal.disposed).toBe(true);
	});
});
