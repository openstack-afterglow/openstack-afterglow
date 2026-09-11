<script lang="ts">
	import type { ChatUsage } from '$lib/api/chatTree';
	import ChatUsageWidget from './ChatUsageWidget.svelte';

	interface Props {
		open: boolean;
		username: string | null;
		usage: ChatUsage | null;
		onClose: () => void;
		onSettings: () => void;
	}
	let { open, username, usage, onClose, onSettings }: Props = $props();

	const initials = $derived((username ?? '?').slice(0, 2).toUpperCase());
</script>

{#if open}
	<div
		class="scrim"
		role="button"
		tabindex="-1"
		aria-label="닫기"
		onclick={onClose}
		onkeydown={(e) => e.key === 'Escape' && onClose()}
	></div>
	<div class="menu" role="menu" aria-label="사용자 메뉴">
		<div class="user">
			<span class="avatar">{initials}</span>
			<span class="name truncate">{username || '사용자'}</span>
		</div>

		{#if usage}
			<div class="usage-block">
				<ChatUsageWidget {usage} />
			</div>
		{/if}

		<button
			type="button"
			class="entry"
			role="menuitem"
			onclick={() => {
				onClose();
				onSettings();
			}}
		>
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" stroke-linecap="round" stroke-linejoin="round" /></svg>
			설정
		</button>
	</div>
{/if}

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 44;
		border: none;
		background: transparent;
		cursor: default;
	}
	.menu {
		position: absolute;
		bottom: calc(100% + 0.4rem);
		left: 0;
		right: 0;
		z-index: 45;
		background: var(--color-surface-raised);
		border: 1px solid var(--color-line);
		border-radius: 0.7rem;
		box-shadow: 0 12px 32px color-mix(in oklab, var(--color-ink-0) 22%, transparent);
		padding: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.user {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0.4rem 0.5rem;
	}
	.avatar {
		flex-shrink: 0;
		width: 1.9rem;
		height: 1.9rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		background: var(--color-accent);
		color: var(--color-action-on-accent);
		font-size: 0.72rem;
		font-weight: 700;
	}
	.name {
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--color-ink-0);
	}
	.usage-block {
		padding: 0.5rem 0.6rem;
		border-top: 1px solid var(--color-line);
		border-bottom: 1px solid var(--color-line);
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.entry {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.6rem;
		border: none;
		border-radius: 0.5rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.82rem;
		cursor: pointer;
		text-align: left;
		width: 100%;
	}
	.entry:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
