<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/common';
	import { mobileViewport } from '$lib/utils/mobileViewport';

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

	const componentId = $props.id();
	const selectedInterval = $derived(active ? String(intervalSeconds) : 'off');
	const options = $derived([...new Set([...intervalOptions, intervalSeconds])].filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b));
	const refreshLabel = $derived(refreshing ? t('autoRefresh.loading') : t('autoRefresh.refreshNow'));

	function handleChange(value: string) {
		if (value === 'off') {
			active = false;
			return;
		}
		active = true;
		intervalSeconds = parseInt(value, 10);
	}
</script>

{#snippet refreshGlyph()}
	{#if refreshing}
		<LoadingState variant="control" label="" aria-hidden="true" />
	{:else}
		<svg
			class="refresh-icon"
			aria-hidden="true"
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
	{/if}
{/snippet}

{#if mobileViewport.current}
	<!-- Mobile keeps the bound polling preference as-is and exposes only one explicit refresh. -->
	<div class="auto-refresh-control mobile">
		<Button
			type="button"
			onclick={onManualRefresh}
			disabled={refreshing}
			ariaBusy={refreshing}
			ariaLabel={refreshLabel}
			title={refreshLabel}
			variant="subtle"
			size="icon"
			class="refresh-round"
		>
			{@render refreshGlyph()}
		</Button>
	</div>
{:else}
	<div class="auto-refresh-control">
		<div class="refresh-frequency">
			<Field label={t('autoRefresh.label')} for={`${componentId}-interval`} class="min-w-0 max-w-full [overflow-wrap:anywhere]">
				<SelectInput id={`${componentId}-interval`} value={selectedInterval} ariaLabel={t('autoRefresh.label')} onchange={(event) => handleChange((event.currentTarget as HTMLSelectElement).value)}>
					<option value="off">{t('autoRefresh.off')}</option>
					{#each options as seconds (seconds)}
						<option value={String(seconds)}>{t('autoRefresh.seconds', { seconds })}</option>
					{/each}
				</SelectInput>
			</Field>
		</div>
		<Button
			type="button"
			onclick={onManualRefresh}
			disabled={refreshing}
			ariaBusy={refreshing}
			ariaLabel={refreshLabel}
			title={refreshLabel}
			variant="subtle"
			size="sm"
			class="max-w-full !whitespace-normal"
		>
			{@render refreshGlyph()}
			<span class="refresh-label">{t('autoRefresh.refresh')}</span>
		</Button>
	</div>
{/if}

<style>
	.auto-refresh-control {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
		max-width: 100%;
	}
	.auto-refresh-control.mobile { flex-wrap: nowrap; flex: 0 0 auto; }
	.auto-refresh-control.mobile :global(.btn.refresh-round) { border-radius: 9999px; }
	.refresh-icon {
		width: 0.875rem;
		flex-shrink: 0;
		height: 0.875rem;
	}
	.auto-refresh-control.mobile .refresh-icon { width: 1.125rem; height: 1.125rem; }
	.refresh-frequency { min-width: 0; max-width: 100%; }
	.refresh-frequency :global(.field) { flex-direction: row; align-items: center; }
	.refresh-frequency :global(select) { width: auto; max-width: 100%; }
	.refresh-label { overflow-wrap: anywhere; }
</style>
