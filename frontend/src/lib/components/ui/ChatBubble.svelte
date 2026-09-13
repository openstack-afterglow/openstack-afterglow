<script lang="ts">
	import type { Snippet } from 'svelte';

	export type ChatBubbleAlignment = 'start' | 'end';

	interface Props {
		align: ChatBubbleAlignment;
		label: string;
		ariaLabel: string;
		metadata?: string | null;
		timestamp?: string | null;
		timestampLabel?: string | null;
		footer?: Snippet;
		footerVisible?: boolean;
		children: Snippet;
	}

	let {
		align,
		label,
		ariaLabel,
		metadata = null,
		timestamp = null,
		timestampLabel = null,
		footer,
		footerVisible = false,
		children
	}: Props = $props();
</script>

<article class="chat chat-message chat-{align}" aria-label={ariaLabel}>
	<header class="chat-header">
		<span>{label}</span>
		{#if metadata}
			<span class="chat-model">{metadata}</span>
		{/if}
		{#if timestamp && timestampLabel}
			<time datetime={timestamp}>{timestampLabel}</time>
		{/if}
	</header>

	<div class="chat-bubble">
		{@render children()}
	</div>

	{#if footer && footerVisible}
		<footer class="chat-footer">
			{@render footer()}
		</footer>
	{/if}
</article>

<style>
	.chat-message {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: var(--chat-message-gap);
		max-width: 100%;
	}
	.chat-start {
		justify-items: start;
	}
	.chat-end {
		justify-items: end;
	}
	.chat-header,
	.chat-footer {
		display: flex;
		align-items: center;
		gap: var(--chat-message-meta-gap);
		padding: 0 var(--chat-message-meta-inset);
		font-size: var(--chat-message-meta-size);
		line-height: 1.2;
		color: var(--color-ink-3);
	}
	.chat-header {
		font-weight: 600;
	}
	.chat-header time {
		font-weight: 400;
		font-variant-numeric: tabular-nums;
	}
	.chat-model {
		max-width: 14rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-weight: 400;
	}
	.chat-bubble {
		min-width: 0;
		max-width: min(92%, var(--chat-message-assistant-max-inline));
		border: 1px solid var(--color-line);
		border-radius: var(--chat-message-radius);
		padding: var(--chat-message-padding-block) var(--chat-message-padding-inline);
		background: var(--color-surface-raised);
	}
	.chat-start .chat-bubble {
		border-bottom-left-radius: var(--chat-message-directional-corner);
	}
	.chat-end .chat-bubble {
		max-width: min(82%, var(--chat-message-user-max-inline));
		border-color: var(--color-accent);
		border-bottom-right-radius: var(--chat-message-directional-corner);
		background: var(--color-accent);
		color: var(--color-action-on-accent);
		white-space: pre-wrap;
		word-break: break-word;
		overflow-wrap: anywhere;
	}
</style>
