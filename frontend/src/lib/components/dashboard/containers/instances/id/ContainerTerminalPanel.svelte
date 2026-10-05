<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import { onDestroy } from 'svelte';
  import { api, getWebSocketUrl } from '$lib/api/client';
  import '@xterm/xterm/css/xterm.css';
  import { resolvedTheme } from '$lib/stores/theme';
  import { getTerminalTheme } from '$lib/utils/terminalTheme';
  import { getLocale } from '$lib/i18n/runtime.svelte';
  import { localizeTerminal } from '$lib/utils/terminalLocale';

  interface Props {
    open: boolean;
    containerId: string;
    token: string | undefined;
    projectId: string | undefined;
  }

  let { open = $bindable(), containerId, token, projectId }: Props = $props();

  let terminalEl = $state<HTMLDivElement | null>(null);
  let wsConnecting = $state(false);
  let wsConnected = $state(false);

  let terminal: import('@xterm/xterm').Terminal | null = null;
  let fitAddon: import('@xterm/addon-fit').FitAddon | null = null;
  let ws: WebSocket | null = null;

  $effect(() => {
    if (open && terminal === null) {
      openConsole();
    }
  });

  $effect(() => {
    const activeTheme = $resolvedTheme;
    if (!terminal || typeof document === 'undefined') return;
    void activeTheme;
    terminal.options.theme = getTerminalTheme();
  });

  $effect(() => {
    getLocale();
    if (terminal) localizeTerminal(terminal);
  });

  async function openConsole() {
    // DOM이 렌더된 후 터미널 초기화
    await new Promise(r => setTimeout(r, 100));
    if (!terminalEl) return;
    if (terminal) return; // already initialized

    const { Terminal } = await import('@xterm/xterm');
    const { FitAddon } = await import('@xterm/addon-fit');

    terminal = new Terminal({
      theme: getTerminalTheme(),
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      cursorBlink: true,
    });
    localizeTerminal(terminal);
    fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(terminalEl);
    fitAddon.fit();

    connectWs();
  }

  async function connectWs() {
    if (!terminal || wsConnecting) return;
    wsConnecting = true;

    let ticket: string;
    try {
      const res = await api.post<{ ticket: string }>(
        `/api/v1/containers/${containerId}/exec-ticket`,
        {},
        token,
        projectId,
      );
      ticket = res.ticket;
    } catch {
      wsConnecting = false;
      terminal?.write(`\r\n\x1b[31m${t('instances.terminal.ticketFailed')}\x1b[0m\r\n`);
      return;
    }

    const url = getWebSocketUrl(
      `/api/v1/containers/${containerId}/exec?ticket=${encodeURIComponent(ticket)}`,
    );

    const socket = new WebSocket(url);
    ws = socket;

    socket.onopen = () => {
      wsConnecting = false;
      wsConnected = true;
    };

    socket.onmessage = (event) => {
      terminal?.write(event.data);
    };

    socket.onerror = () => {
      terminal?.write(`\r\n\x1b[31m${t('instances.terminal.connectionError')}\x1b[0m\r\n`);
      wsConnected = false;
      wsConnecting = false;
    };

    socket.onclose = () => {
      wsConnected = false;
      wsConnecting = false;
      terminal?.write(`\r\n\x1b[33m${t('instances.terminal.connectionClosed')}\x1b[0m\r\n`);
    };

    terminal!.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(data);
      }
    });
  }

  function closeConsole() {
    open = false;
    ws?.close();
    ws = null;
    terminal?.dispose();
    terminal = null;
    fitAddon = null;
    wsConnected = false;
    wsConnecting = false;
  }

  onDestroy(() => {
    ws?.close();
    terminal?.dispose();
  });
</script>

<div class="bg-surface-base border border-line-2 rounded-xl mb-4 overflow-hidden">
  <div class="flex items-center justify-between px-4 py-2 bg-surface-sunken border-b border-line-2">
    <div class="flex items-center gap-2">
      <span class="text-sm text-ink-0 font-medium">{t('instances.terminal.title')}</span>
      {#if wsConnecting}
        <span class="text-xs text-yellow-400">{t('instances.terminal.connecting')}</span>
      {:else if wsConnected}
        <span class="text-xs text-green-400">{t('instances.terminal.connected')}</span>
      {:else}
        <span class="text-xs text-ink-2">{t('instances.terminal.disconnected')}</span>
      {/if}
    </div>
    <div class="flex gap-2">
      {#if !wsConnected && !wsConnecting}
        <button onclick={connectWs} class="text-xs text-warm-text hover:text-warm-text-hover transition-colors">{t('instances.terminal.reconnect')}</button>
      {/if}
      <button onclick={closeConsole} class="text-xs text-ink-2 hover:text-ink-0 transition-colors">{t('instances.terminal.close')}</button>
    </div>
  </div>
  <div bind:this={terminalEl} class="h-80 w-full bg-surface-canvas"></div>
</div>
