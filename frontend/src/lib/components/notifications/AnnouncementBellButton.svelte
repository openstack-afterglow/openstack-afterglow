<script lang="ts">
	interface Props {
		count: number;
		open: boolean;
		element?: HTMLButtonElement | null;
		onclick: () => void;
	}

	let { count, open, element = $bindable(null), onclick }: Props = $props();
</script>

<button
	bind:this={element}
	{onclick}
	class="relative flex size-11 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-surface-sunken hover:text-ink-0 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] lg:size-8"
	title="알림"
	aria-label={count > 0 ? `알림, 읽지 않은 공지 ${count}개` : '알림'}
	aria-haspopup="true"
	aria-expanded={open}
>
	<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
	{#if count > 0}
		<span class="absolute right-2 top-2 size-2 lg:right-0.5 lg:top-0.5" data-unread-indicator aria-hidden="true">
			<span class="absolute inset-0 rounded-full bg-[var(--color-state-danger)] opacity-75 animate-ping motion-reduce:animate-none"></span>
			<span class="absolute inset-0 rounded-full bg-[var(--color-state-danger)]"></span>
		</span>
	{/if}
</button>
