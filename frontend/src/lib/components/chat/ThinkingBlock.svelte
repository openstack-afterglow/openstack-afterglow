<script lang="ts">
	interface Props {
		text: string;
		/** 추론이 진행 중(본문 시작 전)이면 자동 펼침 + "추론 중…" 라벨. 본문이 시작되거나 완료되면 false. */
		active?: boolean;
	}
	let { text, active = false }: Props = $props();

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
		<svg class="ic" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
			<path d="M9.5 21h5M12 3a6 6 0 0 1 4 10.5c-.6.6-1 1.4-1 2.2V17H9v-1.3c0-.8-.4-1.6-1-2.2A6 6 0 0 1 12 3z" stroke-linecap="round" stroke-linejoin="round" />
		</svg>
		<span class="think-label">{active ? '추론 중…' : '추론 과정'}</span>
		{#if active}
			<span class="dots" aria-hidden="true"><span></span><span></span><span></span></span>
		{/if}
		<svg class="chevron" class:open viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
			<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
		</svg>
	</button>

	{#if open}
		<div class="think-body">{text}</div>
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
		transition: transform 0.15s;
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
	.dots {
		display: inline-flex;
		gap: 0.2rem;
	}
	.dots span {
		width: 0.32rem;
		height: 0.32rem;
		border-radius: 50%;
		background: var(--color-ink-3);
		animation: blink 1.2s infinite ease-in-out both;
	}
	.dots span:nth-child(2) {
		animation-delay: 0.16s;
	}
	.dots span:nth-child(3) {
		animation-delay: 0.32s;
	}
	@keyframes blink {
		0%,
		80%,
		100% {
			opacity: 0.25;
		}
		40% {
			opacity: 1;
		}
	}
</style>
