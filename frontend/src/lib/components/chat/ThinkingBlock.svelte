<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-studio';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	interface Props {
		text: string;
		/** 추론이 진행 중(본문 시작 전)이면 자동 펼침 + "추론 중…" 라벨. 본문이 시작되거나 완료되면 false. */
		active?: boolean;
		animate?: boolean;
	}
	let { text, active = false, animate = active }: Props = $props();

	// 추론 진행 중엔 펼쳐 보여주고, 끝나면 자동으로 접되 사용자가 토글하면 그 상태 유지.
	let userToggled = $state<boolean | null>(null);
	const open = $derived(userToggled ?? active);
</script>

<div class="think" class:active>
	<button
		type="button"
		class="think-head"
		onclick={() => (userToggled = !open)}
		aria-expanded={open}
	>
		{#if active}
			<ActivityIndicator variant="orbit" size="xs" label={t('thinkingBlock.active')} />
		{:else}
			<svg class="ic" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
				<path d="M9.5 21h5M12 3a6 6 0 0 1 4 10.5c-.6.6-1 1.4-1 2.2V17H9v-1.3c0-.8-.4-1.6-1-2.2A6 6 0 0 1 12 3z" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
			<span class="think-label">{t('thinkingBlock.process')}</span>
		{/if}
		<svg class="chevron" class:open viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
			<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
		</svg>
	</button>

	{#if open}
		<div class="think-body" class:motion-enter={animate && active}>{text}</div>
	{/if}
</div>

<style>
	.think {
		border: 1px solid var(--color-line);
		border-radius: 0.6rem;
		background: var(--color-surface-sunken);
		overflow: hidden;
		margin-bottom: 0.6rem;
	}
	.think-head {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		width: 100%;
		padding: 0.45rem 0.6rem;
		background: transparent;
		border: none;
		color: var(--color-ink-2);
		cursor: pointer;
		text-align: left;
		font-size: 0.76rem;
	}
	.think-head:hover {
		background: var(--color-surface-raised);
	}
	.ic {
		flex-shrink: 0;
		color: var(--color-accent);
	}
	.think-label {
		font-weight: 600;
		color: var(--color-ink-1);
	}
	.chevron {
		margin-left: auto;
		color: var(--color-ink-2);
		transition: transform var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.chevron.open {
		transform: rotate(180deg);
	}
	.think-body {
		border-top: 1px solid var(--color-line);
		padding: 0.55rem 0.7rem;
		font-size: 0.78rem;
		line-height: 1.6;
		color: var(--color-ink-2);
		white-space: pre-wrap;
		word-break: break-word;
		overflow-wrap: anywhere;
		max-height: 22rem;
		overflow-y: auto;
	}
</style>
