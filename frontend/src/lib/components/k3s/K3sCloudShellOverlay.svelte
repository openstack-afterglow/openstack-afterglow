<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import { createShellTicket } from '$lib/api/k3sResources';
  import { auth } from '$lib/stores/auth';
  import { getBaseUrl } from '$lib/api/client';

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
    closeAll();
  });

  function sendResize(cols: number, rows: number) {
    if (ws?.readyState !== WebSocket.OPEN) return;
    const resizeJson = JSON.stringify({ Width: cols, Height: rows });
    const encoded = new TextEncoder().encode(resizeJson);
    const frame = new Uint8Array(1 + encoded.length);
    frame[0] = CH_RESIZE;
    frame.set(encoded, 1);
    ws.send(frame);
  }

  async function initTerminal() {
    if (!terminalEl) return;
    const { Terminal } = await import('@xterm/xterm');
    const { FitAddon } = await import('@xterm/addon-fit');

    terminal = new Terminal({
      theme: {
        background: '#0f172a',
        foreground: '#e2e8f0',
        cursor: '#60a5fa',
        selectionBackground: '#334155',
      },
      fontFamily: "'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace",
      fontSize: 13,
      cursorBlink: true,
      convertEol: true,
    });
    fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(terminalEl);
    fitAddon.fit();

    terminal.onData((data) => {
      if (ws?.readyState === WebSocket.OPEN) {
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
    if (connecting || !terminal || !s.cluster) return;
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
      errorMsg = 'Shell 티켓 발급 실패 — 클러스터 연결을 확인하세요';
      connecting = false;
      terminal?.write('\r\n\x1b[31m티켓 발급 실패\x1b[0m\r\n');
      return;
    }

    const baseUrl = getBaseUrl();
    const proto = baseUrl.startsWith('https') ? 'wss:' : 'ws:';
    const host = new URL(baseUrl || window.location.origin).host;
    const url = `${proto}//${host}/api/v1/k3s/clusters/${s.cluster.id}/shell?ticket=${encodeURIComponent(ticket)}`;

    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';
    ws = socket;

    terminal.write('\r\n\x1b[33mCloud Shell 연결 중...\x1b[0m\r\n');

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
      errorMsg = '연결 오류가 발생했습니다';
      connecting = false;
      connected = false;
    };

    socket.onclose = (event: CloseEvent) => {
      connecting = false;
      connected = false;
      ws = null;
      if (event.code === 4408) {
        idleTimedOut = true;
        terminal?.write('\r\n\x1b[33m[15분 idle timeout — 세션 종료됨]\x1b[0m\r\n');
      } else if (event.code !== 1000 && event.code !== 1001) {
        terminal?.write(`\r\n\x1b[33m연결 종료 (${event.code})\x1b[0m\r\n`);
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

<div class="fixed inset-0 z-50 bg-surface-canvas flex flex-col">
  <!-- 헤더 -->
  <div class="flex items-center justify-between px-4 py-2 border-b border-line shrink-0">
    <div class="flex items-center gap-3">
      <span class="text-sm font-medium text-ink-1">
        Cloud Shell — <span class="text-action-warm">{s.cluster?.name}</span>
      </span>
      {#if connected}
        <span class="text-xs text-green-400 flex items-center gap-1">
          <span class="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse inline-block"></span>
          연결됨
        </span>
      {:else if connecting}
        <span class="text-xs text-yellow-400">연결 중...</span>
      {:else}
        <span class="text-xs text-ink-3">연결 끊김</span>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      {#if !connected && !connecting}
        <button
          onclick={reconnect}
          class="text-xs text-action-warm hover:text-action-warm-hover px-3 py-1 border border-action-warm hover:border-action-warm rounded transition-colors"
        >재연결</button>
      {/if}
      <button
        onclick={handleClose}
        class="text-ink-2 hover:text-ink-0 text-xl leading-none px-2 transition-colors"
        aria-label="닫기"
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
      <span>15분 동안 활동이 없어 세션이 종료되었습니다.</span>
      <button onclick={reconnect} class="text-action-warm hover:text-action-warm-hover underline">재연결</button>
    </div>
  {/if}
</div>
