import { render, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { installExperienceCollector } from '$lib/utils/experience';
import ContainerTerminalPanel from './ContainerTerminalPanel.svelte';

const terminalInstances: FakeTerminal[] = [];

class FakeTerminal {
  static strings = { promptLabel: '', tooMuchOutput: '' };
  options = {};
  writes: (string | Uint8Array)[] = [];
  private dataHandler: ((data: string) => void) | undefined;
  constructor() { terminalInstances.push(this); }
  loadAddon() {}
  open() {}
  onData(handler: (data: string) => void) {
    this.dataHandler = handler;
    return { dispose: () => { this.dataHandler = undefined; } };
  }
  write(data: string | Uint8Array) { this.writes.push(data); }
  dispose() { this.dataHandler = undefined; }
  emitData(data: string) { this.dataHandler?.(data); }
}

vi.mock('$lib/api/client', () => ({
  api: { post: vi.fn(async () => ({ ticket: 'private-terminal-ticket' })) },
  getWebSocketUrl: (path: string) => `ws://localhost${path}`,
}));
vi.mock('@xterm/xterm', () => ({ Terminal: FakeTerminal }));
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit = vi.fn(); } }));
vi.mock('$lib/utils/terminalTheme', () => ({ getTerminalTheme: () => ({ background: 'transparent' }) }));

class Socket {
  static instances: Socket[] = [];
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  sent: string[] = [];
  send(data: string) { this.sent.push(data); }
  constructor(readonly url: string) { Socket.instances.push(this); }
  close() { this.readyState = 3; }
  opened() { this.readyState = 1; this.onopen?.(); }
  closed() { this.readyState = 3; this.onclose?.(); }
  message(data: string | Uint8Array) { this.onmessage?.({ data } as MessageEvent); }
  errored() { this.onerror?.(); }
}

describe('container terminal rendered connection ownership', () => {
  it('omits terminal content from connected, error and late-close discard diagnostic wire while preserving IO', async () => {
    terminalInstances.length = 0;
    Socket.instances = [];
    const canaries = {
      command: 'cat /CONTAINER_COMMAND_CANARY_64a9_비밀\r',
      output: 'CONTAINER_OUTPUT_CANARY_8e32_비밀',
      kubeconfig: 'apiVersion: v1\nusers:\n- name: CONTAINER_KUBECONFIG_CANARY_7a35\n  user:\n    token: CONTAINER_KUBE_TOKEN_CANARY_5b27',
      token: 'private-token',
      ticket: 'private-terminal-ticket',
      container: 'private-container',
    };
    vi.stubGlobal('WebSocket', Socket);
    const originalFetch = window.fetch;
    const wire: string[] = [];
    const rows: { event_type: string; payload: { state?: string; stage?: string; reason?: string } }[] = [];
    window.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/experience-contract')) return Response.json({ schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 });
      if (!String(input).endsWith('/experience-events')) throw new Error('Unexpected terminal replay transport');
      const body = String(init?.body);
      wire.push(body);
      const batch = JSON.parse(body);
      rows.push(...batch.events);
      return Response.json({ schema_version: 2, accepted: batch.events.length, duplicates: 0 }, { status: 201 });
    });
    const collector = installExperienceCollector({
      getOwner: () => ({ token: canaries.token, sessionId: 'session-a', userId: 'user-a', domainId: 'domain-a', projectId: 'project-a' }),
      getRoute: () => '/dashboard/containers/instances/:id', getBaseUrl: () => 'http://localhost:8000',
      isEnabled: () => true, isSuppressed: () => false, subscribeOwner: () => () => {},
    });
    let unmount: (() => void) | undefined;
    try {
      // Only xterm and the remote peer are fixtures; component ownership and wire collection are real.
      const view = render(ContainerTerminalPanel, { open: true, containerId: canaries.container, token: canaries.token, projectId: 'project-a' });
      unmount = view.unmount;
      await waitFor(() => expect(Socket.instances).toHaveLength(1));
      const socket = Socket.instances[0];
      expect(socket.url).toContain(`/containers/${canaries.container}/exec?ticket=${canaries.ticket}`);
      expect(terminalInstances).toHaveLength(1);
      const terminal = terminalInstances[0];
      socket.opened();
      await tick();
      await collector.flush();
      expect(rows.some(row => row.event_type === 'result.committed')).toBe(true);
      expect(rows.some(row => row.event_type === 'view.state_changed' && row.payload.state === 'ready')).toBe(true);
      terminal.emitData(canaries.command);
      expect(socket.sent).toEqual([canaries.command]);
      socket.message(canaries.output);
      const binaryOutput = new TextEncoder().encode(canaries.kubeconfig);
      socket.message(binaryOutput);
      expect(terminal.writes).toEqual([canaries.output, binaryOutput]);
      socket.errored();
      await tick();
      await collector.flush();
      expect(rows.some(row => row.event_type === 'view.state_changed' && row.payload.state === 'error')).toBe(true);
      rows.length = 0;
      view.unmount();
      unmount = undefined;
      socket.closed();
      await tick();
      await collector.flush();
      expect(rows.some(row => row.event_type === 'view.state_changed' && row.payload.state === 'disabled')).toBe(true);
      expect(rows.some(row => row.event_type === 'result.applied' && row.payload.stage === 'state')).toBe(true);
      expect(rows.some(row => row.event_type === 'result.committed')).toBe(false);
      expect(rows.some(row => row.event_type === 'result.discarded' && row.payload.stage === 'dom' && row.payload.reason === 'stale')).toBe(true);
      expect(wire.length).toBeGreaterThan(0);
      for (const canary of Object.values(canaries)) {
        expect(wire.join('\n')).not.toContain(canary);
      }
      expect(wire.join('\n')).not.toMatch(/CONTAINER_COMMAND_CANARY|CONTAINER_OUTPUT_CANARY|CONTAINER_KUBECONFIG_CANARY|CONTAINER_KUBE_TOKEN_CANARY/);
    } finally {
      unmount?.();
      collector.destroy();
      window.fetch = originalFetch;
      vi.unstubAllGlobals();
    }
  });
});
