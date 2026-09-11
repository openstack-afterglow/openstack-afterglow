<script lang="ts">
  import { tick, type Snippet } from 'svelte';

  interface Props {
    open: boolean;
    onopen: () => void;
    onclose: () => void;
    children: Snippet;
    buttonClass?: string;
    ariaLabel?: string;
  }

  let {
    open,
    onopen,
    onclose,
    children,
    buttonClass = '',
    ariaLabel = '리소스 작업 메뉴',
  }: Props = $props();

  const id = $props.id();
  const menuId = `${id}-actions`;
  let triggerEl = $state<HTMLButtonElement | null>(null);
  let menuEl = $state<HTMLDivElement | null>(null);
  let pos = $state<null | { top: number; left: number }>(null);

  function computePosition() {
    if (!triggerEl) return;
    const rect = triggerEl.getBoundingClientRect();
    const menuWidth = menuEl?.offsetWidth ?? 160;
    const menuHeight = menuEl?.offsetHeight ?? 160;
    const margin = 8;
    const gap = 4;
    const spaceBelow = window.innerHeight - rect.bottom;
    const openDown = spaceBelow >= menuHeight + gap || spaceBelow >= rect.top;
    pos = {
      top: Math.min(
        Math.max(margin, openDown ? rect.bottom + gap : rect.top - menuHeight - gap),
        Math.max(margin, window.innerHeight - menuHeight - margin),
      ),
      left: Math.min(
        Math.max(margin, rect.right - menuWidth),
        Math.max(margin, window.innerWidth - menuWidth - margin),
      ),
    };
  }

  function firstEnabledAction(): HTMLElement | null {
    return menuEl?.querySelector<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? null;
  }

  async function prepareOpen() {
    await tick();
    computePosition();
    await tick();
    firstEnabledAction()?.focus();
  }

  function handleTriggerClick(event: MouseEvent) {
    event.stopPropagation();
    if (open) onclose();
    else onopen();
  }

  function handleMenuFocusOut(event: FocusEvent) {
    const next = event.relatedTarget;
    if (next instanceof Node && (menuEl?.contains(next) || triggerEl?.contains(next))) return;
    onclose();
  }

  function handleMenuKeyDown(event: KeyboardEvent) {
    event.stopPropagation();
    if (event.key !== 'Escape') return;
    event.preventDefault();
    onclose();
    triggerEl?.focus();
  }

  $effect(() => {
    if (!open) {
      pos = null;
      return;
    }
    void prepareOpen();
  });

  $effect(() => {
    if (!open) return;
    const reposition = () => computePosition();
    function handleClick(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerEl?.contains(target) || menuEl?.contains(target)) return;
      onclose();
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      onclose();
      triggerEl?.focus();
    }
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
      document.removeEventListener('click', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  });
</script>

<button
  bind:this={triggerEl}
  type="button"
  onclick={handleTriggerClick}
  class="action-trigger {buttonClass}"
  aria-label={ariaLabel}
  aria-expanded={open}
  aria-controls={menuId}
>
  <svg class="size-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
    <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z"/>
  </svg>
</button>

{#if open}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -- delegated click containment prevents resource-row activation -->
  <div
    bind:this={menuEl}
    id={menuId}
    class="action-menu"
    role="group"
    aria-label={`${ariaLabel} 옵션`}
    style:left={pos ? `${pos.left}px` : '-9999px'}
    style:top={pos ? `${pos.top}px` : '-9999px'}
    onfocusout={handleMenuFocusOut}
    onkeydown={handleMenuKeyDown}
    onclick={(event) => event.stopPropagation()}
  >
    {@render children()}
  </div>
{/if}

<style>
  .action-trigger {
    width: 1.75rem;
    height: 1.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.375rem;
    color: var(--color-ink-2);
    background: transparent;
    transition: background var(--motion-duration-fast) var(--motion-ease-standard), color var(--motion-duration-fast) var(--motion-ease-standard);
  }
  .action-trigger:hover {
    color: var(--color-ink-0);
    background: color-mix(in oklab, var(--color-surface-sunken) 65%, transparent);
  }
  .action-menu {
    position: fixed;
    z-index: var(--z-popover);
    min-width: 8.75rem;
    padding-block: 0.25rem;
    border: 1px solid var(--color-line-2);
    border-radius: 0.5rem;
    background: var(--color-surface-raised);
    box-shadow: var(--shadow-restraint);
  }
  @media (pointer: coarse) {
    .action-trigger {
      width: 2.75rem;
      height: 2.75rem;
    }
  }
</style>
