<script lang="ts">
	import { isAvatarUrl, type Agent } from '$lib/api/chatAgents';

	interface Props {
		agents: Agent[];
		activeAgent: Agent | null;
		disabled?: boolean;
		onBind: (agent: Agent) => void;
		onUnbind: () => void;
		onManage: () => void;
		onHub: () => void;
	}
	let { agents, activeAgent, disabled = false, onBind, onUnbind, onManage, onHub }: Props = $props();

	let open = $state(false);
	let root = $state<HTMLDivElement | null>(null);

	function toggle() {
		if (disabled) return;
		open = !open;
	}
	function pick(a: Agent) {
		open = false;
		onBind(a);
	}
	function onWindowClick(e: MouseEvent) {
		if (root && !root.contains(e.target as Node)) open = false;
	}
	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') open = false;
	}
</script>

<svelte:window onclick={onWindowClick} onkeydown={onKeydown} />

<div class="agent-picker" bind:this={root}>
	{#if activeAgent}
		<div class="badge" class:disabled>
			<button type="button" class="badge-main" {disabled} onclick={toggle} title="에이전트 변경">
				<span class="avatar">
					{#if isAvatarUrl(activeAgent.avatar)}
						<img src={activeAgent.avatar} alt="" />
					{:else}
						{activeAgent.avatar || '🤖'}
					{/if}
				</span>
				<span class="badge-name">{activeAgent.name}</span>
			</button>
			<button type="button" class="unbind" onclick={onUnbind} title="에이전트 해제" aria-label="에이전트 해제">
				<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" /></svg>
			</button>
		</div>
	{:else}
		<button type="button" class="trigger" {disabled} aria-haspopup="menu" aria-expanded={open} onclick={toggle} title="에이전트 선택">
			<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="7" width="16" height="12" rx="2" /><path d="M9 7V4h6v3M9 13h.01M15 13h.01" stroke-linecap="round" /></svg>
			<span class="agent-label">에이전트</span>
			<svg class="chev" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" /></svg>
		</button>
	{/if}

	{#if open}
		<div class="menu" role="menu">
			<div class="menu-scroll">
				{#if agents.length === 0}
					<p class="menu-empty">저장된 에이전트가 없습니다</p>
				{:else}
					{#each agents as a (a.id)}
						<button type="button" role="menuitem" class="menu-item" class:active={activeAgent?.id === a.id} onclick={() => pick(a)}>
							<span class="mi-avatar">
								{#if isAvatarUrl(a.avatar)}<img src={a.avatar} alt="" />{:else}{a.avatar || '🤖'}{/if}
							</span>
							<span class="mi-text truncate">{a.name}</span>
							{#if activeAgent?.id === a.id}
								<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>
							{/if}
						</button>
					{/each}
				{/if}
			</div>
			<div class="menu-foot">
				{#if activeAgent}
					<button type="button" class="foot-item" onclick={() => { open = false; onUnbind(); }}>바인딩 해제</button>
				{/if}
				<button type="button" class="foot-item" onclick={() => { open = false; onManage(); }}>에이전트 관리</button>
				<button type="button" class="foot-item accent" onclick={() => { open = false; onHub(); }}>허브 탐색</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.agent-picker {
		position: relative;
		display: inline-block;
	}
	.trigger {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.4rem 0.6rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		cursor: pointer;
		white-space: nowrap;
		flex-shrink: 0;
		transition: background 0.15s, color 0.15s, border-color 0.15s;
	}
	/* 모바일: 라벨 숨겨 아이콘만(줄바꿈·과밀 방지) */
	@media (max-width: 640px) {
		.agent-label {
			display: none;
		}
	}
	.trigger:hover:not(:disabled) {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
		border-color: var(--color-line-2);
	}
	.trigger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.chev {
		color: var(--color-ink-2);
	}
	.badge {
		display: inline-flex;
		align-items: center;
		border-radius: 0.5rem;
		border: 1px solid color-mix(in oklab, var(--color-accent) 40%, var(--color-line));
		background: color-mix(in oklab, var(--color-accent) 10%, transparent);
	}
	.badge-main {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.3rem 0.4rem 0.3rem 0.45rem;
		border: none;
		background: transparent;
		color: var(--color-ink-0);
		font-size: 0.8125rem;
		cursor: pointer;
	}
	.badge-main:disabled {
		cursor: default;
	}
	.avatar {
		width: 1.35rem;
		height: 1.35rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.35rem;
		font-size: 0.85rem;
		overflow: hidden;
	}
	.avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.badge-name {
		max-width: 9rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.unbind {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.75rem;
		border: none;
		border-left: 1px solid color-mix(in oklab, var(--color-accent) 25%, var(--color-line));
		background: transparent;
		color: var(--color-ink-2);
		cursor: pointer;
		border-radius: 0 0.5rem 0.5rem 0;
	}
	.unbind:hover {
		color: var(--color-state-danger);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
	}
	.menu {
		position: absolute;
		z-index: 30;
		top: calc(100% + 0.35rem);
		right: 0;
		width: 15rem;
		display: flex;
		flex-direction: column;
		border-radius: 0.6rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		box-shadow: var(--shadow-popover);
		overflow: hidden;
	}
	.menu-scroll {
		max-height: 14rem;
		overflow-y: auto;
		padding: 0.3rem;
	}
	.menu-empty {
		padding: 0.6rem 0.5rem;
		font-size: 0.8rem;
		color: var(--color-ink-2);
	}
	.menu-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.4rem 0.5rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		text-align: left;
		cursor: pointer;
	}
	.menu-item:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.menu-item.active {
		color: var(--color-accent);
	}
	.mi-avatar {
		flex-shrink: 0;
		width: 1.5rem;
		height: 1.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.35rem;
		background: var(--color-surface-sunken);
		font-size: 0.9rem;
		overflow: hidden;
	}
	.mi-avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.mi-text {
		flex: 1;
		min-width: 0;
	}
	.menu-foot {
		display: flex;
		flex-direction: column;
		border-top: 1px solid var(--color-line);
		padding: 0.25rem;
	}
	.foot-item {
		padding: 0.45rem 0.55rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		text-align: left;
		cursor: pointer;
	}
	.foot-item:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.foot-item.accent {
		color: var(--color-accent);
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
