<script lang="ts">
	import Pill from '$lib/components/ui/Pill.svelte';

	let { status = 'unverified', size = 'xs' }: {
		status?: 'verified' | 'unverified' | 'unavailable' | null;
		size?: 'xs' | 'sm';
	} = $props();

	const presentation = $derived(status === 'verified'
		? { tone: 'success' as const, label: '검증됨' }
		: status === 'unavailable'
			? { tone: 'neutral' as const, label: '검증 불가' }
			: { tone: 'warning' as const, label: '미검증' });
</script>

<Pill tone={presentation.tone} {size}>{presentation.label}</Pill>
