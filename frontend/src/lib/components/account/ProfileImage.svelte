<script lang="ts">
	import { profileImage } from '$lib/stores/profileImage';
	let { name = '', label, large = false }: { name?: string; label: string; large?: boolean } = $props();
	let failed = $state(false);
	const source = $derived($profileImage.image?.url ?? '');
	const safeSource = $derived(/^https:\/\/www\.gravatar\.com\/avatar\/[a-f0-9]{64}\?s=128&d=404$/.test(source) || /^data:image\/png;base64,[A-Za-z0-9+/]+=*$/.test(source) ? source : '');
	const initials = $derived((name.trim() || '?').slice(0, 2).toUpperCase());
	$effect(() => { void safeSource; failed = false; });
</script>

<span class="flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-line-2 bg-surface-sunken text-xs font-semibold text-ink-2 {large ? 'size-16' : 'size-8'}">
	{#if safeSource && !failed}
		<img src={safeSource} alt={label} referrerpolicy="no-referrer" class="size-full object-cover" width={large ? 64 : 32} height={large ? 64 : 32} onerror={() => { failed = true; }} />
	{:else}
		<span role="img" aria-label={label}>{initials}</span>
	{/if}
</span>
