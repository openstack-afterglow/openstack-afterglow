<script lang="ts">
  import { onMount } from 'svelte';
  import { fly, fade } from 'svelte/transition';
  import type { Snippet } from 'svelte';
  import { MOTION_DURATION_MS } from '$lib/design/tokens';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import { motionDuration } from '$lib/utils/motion';

  interface Props {
    onClose: () => void;
    width?: string;
    resizable?: boolean;
    storageKey?: string;
    dataTour?: string;
    ariaLabel?: string;
    labelledBy?: string;
    children: Snippet;
  }

  let {
    onClose,
    width = 'w-full md:w-[75vw] max-w-5xl',
    resizable = true,
    storageKey,
    dataTour,
    ariaLabel,
    labelledBy,
    children,
  }: Props = $props();

  const MIN_PX = 360;

  let widthPx = $state<number | null>(null);
  let panelEl = $state<HTMLElement | null>(null);
  let isDesktop = $state<boolean>(true);
  let viewportWidth = $state(typeof window === 'undefined' ? 0 : window.innerWidth);
  function sidebarWidthPixels(): number {
    const root = getComputedStyle(document.documentElement);
    const value = root.getPropertyValue('--app-sidebar-width').trim();
    if (value.endsWith('rem')) return parseFloat(value) * parseFloat(root.fontSize);
    return parseFloat(value) || 240;
  }

  function maxPanelWidth(): number {
    return Math.max(MIN_PX, viewportWidth - sidebarWidthPixels());
  }

  function clampPanelWidth(value: number): number {
    return Math.max(MIN_PX, Math.min(maxPanelWidth(), value));
  }

  function resolvedKey(): string {
    return storageKey ?? `slidePanel.${window.location.pathname}.width`;
  }

  $effect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const update = () => {
      isDesktop = mq.matches;
      viewportWidth = window.innerWidth;
    };
    update();
    window.addEventListener('resize', update);
    mq.addEventListener('change', update);
    return () => {
      window.removeEventListener('resize', update);
      mq.removeEventListener('change', update);
    };
  });
  onMount(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    queueMicrotask(() => panelEl?.querySelector<HTMLElement>('[data-slide-panel-close]')?.focus());
    return () => {
      if (opener?.isConnected && !opener.inert) opener.focus();
    };
  });

  // 마운트 시 저장된 폭 복원
  $effect(() => {
    const saved = localStorage.getItem(resolvedKey());
    if (saved !== null) {
      const n = parseInt(saved, 10);
      if (!isNaN(n)) widthPx = n;
    }
  });

  // widthPx 변경 시 영속화
  $effect(() => {
    if (widthPx !== null) {
      localStorage.setItem(resolvedKey(), String(widthPx));
    }
  });

  function onHandleMouseDown(e: MouseEvent) {
    e.preventDefault();
    const startX = e.clientX;
    const startW = widthPx ?? panelEl?.offsetWidth ?? 600;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    function onMove(ev: MouseEvent) {
      viewportWidth = window.innerWidth;
      widthPx = clampPanelWidth(startW + (startX - ev.clientX));
    }

    function onUp() {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  function onHandleDblClick() {
    widthPx = null;
    localStorage.removeItem(resolvedKey());
  }
</script>

<!-- Mobile covers the viewport; tablet/desktop preserve shared header/sidebar offsets. -->
<div
  use:dialogFocus={{ enabled: !isDesktop, onEscape: onClose, initialFocus: '[data-slide-panel-close]' }}
  class="app-panel-frame fixed z-[var(--z-modal)] md:z-[var(--z-panel)]"
  role="dialog"
  aria-modal={isDesktop ? undefined : 'true'}
  aria-label={labelledBy ? undefined : ariaLabel}
  aria-labelledby={labelledBy}
  onkeydown={(event) => {
    if (isDesktop && event.key === 'Escape' && !event.defaultPrevented) onClose();
  }}
  tabindex="-1"
>
  <button
    type="button"
    class="absolute inset-0 cursor-default bg-surface-scrim-soft"
    transition:fade={{ duration: motionDuration(MOTION_DURATION_MS.base) }}
    onclick={onClose}
    aria-label="패널 닫기"
    tabindex={isDesktop ? -1 : 0}
  ></button>
  <div
    bind:this={panelEl}
    data-tour={dataTour}
    class="@container/panel absolute inset-y-0 right-0 w-full overflow-y-auto border-l border-line bg-surface-raised shadow-[var(--shadow-restraint)] {width}"
    style={isDesktop && widthPx !== null ? `width: ${clampPanelWidth(widthPx)}px; max-width: 100%` : ''}
    transition:fly={{ x: 400, duration: motionDuration(MOTION_DURATION_MS.panel), opacity: 1 }}
  >
    <button
      type="button"
      data-slide-panel-close
      class="sticky right-3 top-3 z-20 ml-auto mr-3 mt-3 flex size-9 items-center justify-center rounded-md border border-line bg-surface-raised text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
      onclick={onClose}
      aria-label="패널 닫기 버튼"
    >×</button>
    {#if resizable && isDesktop}
      <!-- 폭 조정 핸들: 태블릿/데스크톱에서만 노출, 더블클릭으로 기본값 리셋 -->
      <div
        class="absolute inset-y-0 left-0 z-10 hidden w-1 cursor-col-resize hover:bg-[var(--color-line-2)] md:block"
        aria-hidden="true"
        onmousedown={onHandleMouseDown}
        ondblclick={onHandleDblClick}
      ></div>
    {/if}
    {@render children()}
  </div>
</div>
