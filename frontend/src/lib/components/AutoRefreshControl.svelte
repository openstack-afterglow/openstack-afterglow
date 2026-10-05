<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import ToggleGroup, { type ToggleOption } from '$lib/components/ui/ToggleGroup.svelte';
	import { t } from '$lib/i18n/ns/shared';

	interface Props {
		active: boolean;
		intervalSeconds: number;
		intervalOptions?: readonly number[];
		refreshing?: boolean;
		onManualRefresh: () => void;
	}

	let {
		active = $bindable(),
		intervalSeconds = $bindable(),
		intervalOptions = [10, 15, 30, 60],
		refreshing = false,
		onManualRefresh,
	}: Props = $props();

	const toggleValue = $derived(active ? String(intervalSeconds) : 'off');
	const options: ToggleOption[] = $derived([
		{ value: 'off', label: t('autoRefresh.off') },
		...intervalOptions.map((opt) => ({ value: String(opt), label: `${opt}s` })),
	]);

	function handleChange(value: string) {
		if (value === 'off') {
			active = false;
			return;
		}
		active = true;
		intervalSeconds = parseInt(value, 10);
	}
</script>

<div class="auto-refresh-control">
	<Button
		type="button"
		onclick={onManualRefresh}
		disabled={refreshing}
		title={refreshing ? t('autoRefresh.loading') : t('autoRefresh.refreshNow')}
		variant="subtle"
		size="sm"
	>
		<svg
			class="refresh-icon {refreshing ? 'animate-spin' : ''}"
			style={refreshing ? 'animation-direction: reverse' : ''}
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			viewBox="0 0 24 24"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M4 4v5h5M20 20v-5h-5M4 9a8 8 0 0114.93-3M20 15a8 8 0 01-14.93 3"
			/>
		</svg>
		<span class="refresh-label">{t('autoRefresh.refresh')}</span>
	</Button>
	<ToggleGroup value={toggleValue} {options} onchange={handleChange} size="xs" />
</div>

<style>
	.auto-refresh-control {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}
	.refresh-icon {
		width: 0.875rem;
		height: 0.875rem;
	}
	.refresh-label { display: none; }
	@media (min-width: 768px) {
		.refresh-label { display: inline; }
	}
</style>
