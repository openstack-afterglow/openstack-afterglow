<script lang="ts">
	import { t } from '$lib/i18n/ns/images-keys';
	import Pill from '$lib/components/ui/Pill.svelte';

	let { status = 'unverified', size = 'xs' }: {
		status?: 'verified' | 'unverified' | 'unavailable' | null;
		size?: 'xs' | 'sm';
	} = $props();

	const presentation = $derived(status === 'verified'
		? { tone: 'success' as const, label: t('verificationBadge.verified') }
		: status === 'unavailable'
			? { tone: 'neutral' as const, label: t('verificationBadge.unavailable') }
			: { tone: 'warning' as const, label: t('verificationBadge.unverified') });
</script>

<Pill tone={presentation.tone} {size}>{presentation.label}</Pill>
