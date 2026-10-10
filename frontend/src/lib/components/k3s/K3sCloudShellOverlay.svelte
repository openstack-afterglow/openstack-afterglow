<script lang="ts">
  import { t } from '$lib/i18n/ns/drover';
  import RichText from '$lib/i18n/RichText.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { prefersReducedMotion } from '$lib/utils/motion';
  import { onDestroy, onMount, tick } from 'svelte';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import { createShellTicket } from '$lib/api/k3sResources';
  import { auth } from '$lib/stores/auth';
  import { k3sPermissions } from '$lib/stores/k3sPermissions';
  import { projectPermissions } from '$lib/stores/servicePermissions';
  import { getBaseUrl } from '$lib/api/client';
  import '@xterm/xterm/css/xterm.css';
  import { resolvedTheme } from '$lib/stores/theme';
  import { getTerminalTheme } from '$lib/utils/terminalTheme';
  import { getLocale } from '$lib/i18n/runtime.svelte';
  import { localizeTerminal } from '$lib/utils/terminalLocale';

  const s = useK3sClusterDetailController();

  let terminalEl: HTMLDivElement | undefined = $state();
  let terminal: import('@xterm/xterm').Terminal | null = null;
  let fitAddon: import('@xterm/addon-fit').FitAddon | null = null;
  let ws: WebSocket | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let connected = $state(false);
  let connecting = $state(false);
  let errorMsg = $state('');
  let idleTimedOut = $state(false);
  let disposed = false;

  // K8s exec v4.channel.k8s.io 채널 ID
  const CH_STDIN = 0;
  const CH_STDOUT = 1;
  const CH_STDERR = 2;
  const CH_RESIZE = 4;

  onMount(async () => {
    await tick();
    await initTerminal();
  });

  onDestroy(() => {
    disposed = true;
    closeAll();
  });

  // Pending permission reloads (token refresh) only pause input; a loaded grant set without the leaf closes the session.
  $effect(() => {
    if ($projectPermissions.permissions && !$k3sPermissions.workloads) { closeAll(); s.closeShell(); }
  });

  function sendResize(cols: number, rows: number) {
    if (!$k3sPermissions.workloads || ws?.readyState !== WebSocket.OPEN) return;
    const resizeJson = JSON.stringify({ Width: cols, Height: rows });
    const encoded = new TextEncoder().encode(resizeJson);
    const frame = new Uint8Array(1 + encoded.length);
    frame[0] = CH_RESIZE;
    frame.set(encoded, 1);
    ws.send(frame);
  }

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

  async function initTerminal() {
    if (disposed || !$k3sPermissions.workloads || !terminalEl) return;
    const { Terminal } = await import('@xterm/xterm');
    const { FitAddon } = await import('@xterm/addon-fit');
    if (disposed || !$k3sPermissions.workloads || !terminalEl) return;

    terminal = new Terminal({
      theme: getTerminalTheme(),
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      cursorBlink: !prefersReducedMotion(),
      convertEol: true,
    });
    localizeTerminal(terminal);
    fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(terminalEl);
    fitAddon.fit();

    terminal.onData((data) => {
      if ($k3sPermissions.workloads && ws?.readyState === WebSocket.OPEN) {
        const encoded = new TextEncoder().encode(data);
        const frame = new Uint8Array(1 + encoded.length);
        frame[0] = CH_STDIN;
        frame.set(encoded, 1);
        ws.send(frame);
      }
    });

    terminal.onResize(({ cols, rows }) => {
      sendResize(cols, rows);
    });

    // ResizeObserver로 컨테이너 크기 변경 감지
    resizeObserver = new ResizeObserver(() => fitAddon?.fit());
    resizeObserver.observe(terminalEl);

    await connectWs();
  }

  async function connectWs() {
    if (disposed || !$k3sPermissions.workloads || connecting || !terminal || !s.cluster) return;
    const userId = $auth.userId;
    const projectId = $auth.projectId;
    const clusterId = s.cluster.id;
    connecting = true;
    errorMsg = '';
    idleTimedOut = false;

    let ticket: string;
    try {
      const res = await createShellTicket(
        s.cluster.id,
        $auth.token ?? undefined,
        $auth.projectId ?? undefined
      );
      ticket = res.ticket;
    } catch {
      errorMsg = t('cloudShell.ticketFailed');
      connecting = false;
      terminal?.write(`\r\n\x1b[31m${t('cloudShell.terminalTicketFailed')}\x1b[0m\r\n`);
      return;
    }
    if (disposed || !terminal || $auth.userId !== userId || $auth.projectId !== projectId || s.cluster?.id !== clusterId) { connecting = false; return; }

    const baseUrl = getBaseUrl();
    const proto = baseUrl.startsWith('https') ? 'wss:' : 'ws:';
    const host = new URL(baseUrl || window.location.origin).host;
    const url = `${proto}//${host}/api/v1/k3s/clusters/${s.cluster.id}/shell?ticket=${encodeURIComponent(ticket)}`;

    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';
    ws = socket;

    terminal.write(`\r\n\x1b[33m${t('cloudShell.terminalConnecting')}\x1b[0m\r\n`);

    socket.onopen = () => {
      connecting = false;
      connected = true;
      // 현재 터미널 크기 전송
      if (terminal) {
        sendResize(terminal.cols, terminal.rows);
      }
    };

    socket.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        const view = new Uint8Array(event.data);
        if (view.length === 0) return;
        const channel = view[0];
        const payload = view.subarray(1);
        if ((channel === CH_STDOUT || channel === CH_STDERR) && payload.length > 0) {
          terminal?.write(payload);
        }
      }
    };

    socket.onerror = () => {
      errorMsg = t('cloudShell.connectionError');
      connecting = false;
      connected = false;
    };

    socket.onclose = (event: CloseEvent) => {
      connecting = false;
      connected = false;
      ws = null;
      if (event.code === 4408) {
        idleTimedOut = true;
        terminal?.write(`\r\n\x1b[33m${t('cloudShell.terminalIdleTimeout')}\x1b[0m\r\n`);
      } else if (event.code !== 1000 && event.code !== 1001) {
        terminal?.write(`\r\n\x1b[33m${t('cloudShell.terminalClosed', { code: event.code })}\x1b[0m\r\n`);
      }
    };
  }

  function closeAll() {
    resizeObserver?.disconnect();
    resizeObserver = null;
    ws?.close();
    ws = null;
    terminal?.dispose();
    terminal = null;
    fitAddon = null;
  }

  function handleClose() {
    closeAll();
    s.closeShell();
  }

  async function reconnect() {
    if (!terminal) {
      await initTerminal();
      return;
    }
    terminal.clear();
    await connectWs();
  }
</script>

{#snippet clusterName(text: string)}<span class="text-warm-text">{text}</span>{/snippet}

<div class="motion-fade fixed inset-0 z-50 bg-surface-canvas flex flex-col">
  <!-- 헤더 -->
  <div class="flex items-center justify-between px-4 py-2 border-b border-line shrink-0">
    <div class="flex items-center gap-3">
      <span class="text-sm font-medium text-ink-1">
        <RichText segments={t.rich('cloudShell.title', { name: s.cluster?.name ?? '' })} tags={{ name: clusterName }} />
      </span>
      {#if connected}
        <ActivityIndicator variant="pulse" tone="success" size="xs" label={t('cloudShell.connected')} class="text-xs" />
      {:else if connecting}
        <ActivityIndicator size="xs" label={t('cloudShell.connecting')} class="text-xs" />
      {:else}
        <span class="text-xs text-ink-2">{t('cloudShell.disconnected')}</span>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      {#if !connected && !connecting}
        <button
          onclick={reconnect}
          class="text-xs text-warm-text hover:text-warm-text-hover px-3 py-1 border border-action-warm hover:border-action-warm rounded transition-colors"
        >{t('cloudShell.reconnect')}</button>
      {/if}
      <button
        onclick={handleClose}
        class="text-ink-2 hover:text-ink-0 text-xl leading-none px-2 transition-colors"
        aria-label={t('cloudShell.close')}
      >&times;</button>
    </div>
  </div>

  {#if errorMsg}
    <div class="px-4 py-2 bg-red-900/30 border-b border-red-800 text-xs text-red-400 shrink-0">
      {errorMsg}
    </div>
  {/if}

  <!-- 터미널 영역 -->
  <div class="flex-1 overflow-hidden p-2">
    <div bind:this={terminalEl} class="w-full h-full"></div>
  </div>

  <!-- idle timeout 안내 -->
  {#if idleTimedOut}
    <div class="shrink-0 px-4 py-2 bg-yellow-900/30 border-t border-yellow-800 text-xs text-yellow-400 flex items-center justify-between">
      <span>{t('cloudShell.idleTimeout')}</span>
      <button onclick={reconnect} class="text-warm-text hover:text-warm-text-hover underline">{t('cloudShell.reconnect')}</button>
    </div>
  {/if}
</div>
