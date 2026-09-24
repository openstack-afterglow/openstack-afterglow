import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api/errors';
import {
	createCloudShellController,
	type CloudShellController,
	type CloudShellIdentity,
} from './cloudShell.svelte';

class FakeSocket {
	binaryType: BinaryType = 'blob';
	readyState = 0;
	onopen: ((event: Event) => void) | null = null;
	onmessage: ((event: MessageEvent) => void) | null = null;
	onerror: ((event: Event) => void) | null = null;
	onclose: ((event: CloseEvent) => void) | null = null;
	sent: Array<string | ArrayBufferLike | ArrayBufferView> = [];
	closed: Array<{ code?: number; reason?: string }> = [];

	send(data: string | ArrayBufferLike | ArrayBufferView) {
		this.sent.push(data);
	}

	close(code?: number, reason?: string) {
		this.closed.push({ code, reason });
		this.readyState = 3;
	}

	open() {
		this.readyState = 1;
		this.onopen?.(new Event('open'));
	}

	message(data: unknown) {
		this.onmessage?.(new MessageEvent('message', { data }));
	}

	serverClose(code: number) {
		this.readyState = 3;
		this.onclose?.(new CloseEvent('close', { code }));
	}
}

const identity: CloudShellIdentity = {
	token: 'token-a',
	projectId: 'project-a',
	projectName: 'Project A',
};

function buildController() {
	const issueTicket = vi.fn().mockResolvedValue({
		ticket: 'ticket value',
		websocket_path: '/api/v1/cloud-shell/ws',
		expires_at: 2_000_000_000,
	});
	const deleteWorkspace = vi.fn().mockResolvedValue(undefined);
	const socket = new FakeSocket();
	const createWebSocket = vi.fn(() => socket);
	const controller = createCloudShellController({
		issueTicket,
		deleteWorkspace,
		webSocketUrl: (path: string) => `wss://afterglow.example${path}`,
		createWebSocket,
	});
	return { controller, issueTicket, deleteWorkspace, socket, createWebSocket };
}

describe('Cloud Shell singleton controller contract', () => {
	let controller: CloudShellController;

	beforeEach(() => {
		({ controller } = buildController());
		controller.bindIdentity(identity);
	});

	it('does not call the backend when consent is opened and canceled', () => {
		const fixture = buildController();
		fixture.controller.bindIdentity(identity);
		fixture.controller.openConsent();

		expect(fixture.controller.phase).toBe('consent');
		fixture.controller.cancelConsent();

		expect(fixture.issueTicket).not.toHaveBeenCalled();
		expect(fixture.createWebSocket).not.toHaveBeenCalled();
		expect(fixture.controller.phase).toBe('closed');
	});

	it('does not churn the bound identity when auth emits an unchanged snapshot', () => {
		const boundIdentity = controller.identity;

		controller.bindIdentity({ ...identity });

		expect(controller.identity).toBe(boundIdentity);
	});

	it('transitions through server phases and relays binary terminal frames', async () => {
		const fixture = buildController();
		fixture.controller.bindIdentity(identity);
		const write = vi.fn();
		const clear = vi.fn();
		const focus = vi.fn();
		const fit = vi.fn();
		fixture.controller.setTerminalSink({ write, clear, focus, fit });
		fixture.controller.openConsent();

		await fixture.controller.approve();
		expect(fixture.issueTicket).toHaveBeenCalledWith(identity);
		expect(fixture.createWebSocket).toHaveBeenCalledWith(
			'wss://afterglow.example/api/v1/cloud-shell/ws?ticket=ticket%20value',
		);
		expect(fixture.socket.binaryType).toBe('arraybuffer');
		expect(fixture.controller.phase).toBe('provisioning');

		fixture.socket.open();
		fixture.socket.message(JSON.stringify({ type: 'status', phase: 'container' }));
		expect(fixture.controller.statusStep).toBe('컨테이너 준비');
		fixture.socket.message(JSON.stringify({ type: 'status', phase: 'authorizing' }));
		expect(fixture.controller.phase).toBe('authorizing');
		fixture.socket.message(JSON.stringify({
			type: 'ready',
			expires_at: 2_000_000_000,
			idle_timeout_seconds: 1200,
		}));
		await Promise.resolve();

		expect(fixture.controller.phase).toBe('ready');
		expect(fixture.controller.workspaceState).toBe('available');
		expect(focus).toHaveBeenCalled();
		expect(fit).toHaveBeenCalled();

		const output = new Uint8Array([104, 105]);
		fixture.socket.message(output.buffer);
		expect(write).toHaveBeenCalledWith(expect.objectContaining({ byteLength: 2 }));

		fixture.controller.sendInput('openstack project list\r');
		fixture.controller.resize(120, 34);
		expect(ArrayBuffer.isView(fixture.socket.sent[0])).toBe(true);
		expect(new TextDecoder().decode(fixture.socket.sent[0] as Uint8Array)).toBe('openstack project list\r');
		expect(fixture.socket.sent[1]).toBe(JSON.stringify({ type: 'resize', cols: 120, rows: 34 }));
	});

	it('closes and discards the shell before rebinding to another project', async () => {
		const fixture = buildController();
		fixture.controller.bindIdentity(identity);
		fixture.controller.openConsent();
		await fixture.controller.approve();
		fixture.socket.open();

		fixture.controller.bindIdentity({ ...identity, projectId: 'project-b', projectName: 'Project B' });
		await Promise.resolve();

		expect(fixture.socket.closed).toContainEqual({ code: 1000, reason: 'project-switch' });
		expect(fixture.controller.phase).toBe('closed');
		expect(fixture.controller.visible).toBe(false);
		expect(fixture.controller.identity?.projectId).toBe('project-b');
	});

	it('maps fixed WebSocket close codes to actionable errors', async () => {
		const fixture = buildController();
		fixture.controller.bindIdentity(identity);
		fixture.controller.openConsent();
		await fixture.controller.approve();
		fixture.socket.open();

		fixture.socket.serverClose(4410);

		expect(fixture.controller.phase).toBe('error');
		expect(fixture.controller.error).toContain('다른 탭이나 프로젝트');
	});

	it('reports workspace reset success only after the delete call resolves', async () => {
		const fixture = buildController();
		fixture.controller.bindIdentity(identity);

		await expect(fixture.controller.resetWorkspace()).resolves.toBe(true);
		expect(fixture.deleteWorkspace).toHaveBeenCalledWith(identity);
		expect(fixture.controller.workspaceState).toBe('absent');
	});

	it('keeps an active terminal connected when workspace reset returns busy', async () => {
		const fixture = buildController();
		fixture.deleteWorkspace.mockRejectedValue(
			new ApiError(409, JSON.stringify({ code: 'workspace_busy', message: 'busy' })),
		);
		fixture.controller.bindIdentity(identity);
		fixture.controller.openConsent();
		await fixture.controller.approve();
		fixture.socket.open();
		fixture.socket.message(JSON.stringify({ type: 'ready' }));

		await expect(fixture.controller.resetWorkspace()).resolves.toBe(false);
		expect(fixture.controller.phase).toBe('ready');
		expect(fixture.controller.resetError).toContain('활성 Cloud Shell');
		expect(fixture.socket.closed).toEqual([]);
	});

	it('keeps reset failures fail-closed and distinguishes a busy home', async () => {
		const fixture = buildController();
		fixture.deleteWorkspace.mockRejectedValue(
			new ApiError(409, JSON.stringify({ code: 'workspace_busy', message: 'busy' })),
		);
		fixture.controller.bindIdentity(identity);

		await expect(fixture.controller.resetWorkspace()).resolves.toBe(false);
		expect(fixture.controller.phase).toBe('error');
		expect(fixture.controller.error).toContain('활성 Cloud Shell');
	});
});
