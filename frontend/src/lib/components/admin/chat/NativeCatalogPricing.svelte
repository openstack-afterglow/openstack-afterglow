<script lang="ts">
	import type { NativeMediaPricing, NativeMediaRateKey, NativeTokenPricing } from '$lib/api/nativeCatalog';
	import { t } from '$lib/i18n/ns/native-providers';
	import { t as adminT } from '$lib/i18n/ns/admin-chat';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import type { BillingBasis } from './modelPricing';

	let { tokens, media }: { tokens: NativeTokenPricing | null; media: NativeMediaPricing | null } = $props();
	const tokenColumns = $derived([
		{ key: 'input' as const, label: adminT('configuration.input') },
		{ key: 'output' as const, label: adminT('configuration.output') },
		{ key: 'cache_read' as const, label: adminT('configuration.cacheRead') },
		{ key: 'cache_write' as const, label: `${t('price.cacheWrite')} (TTL ${tokens?.cache_write_ttl ?? '—'})` },
		{ key: 'cache_write_long' as const, label: `${t('price.cacheWriteLong')} (TTL ${tokens?.cache_write_long_ttl ?? '—'})` }
	]);
	const tokenRows = $derived(tokens ? [
		{ label: t('pricing.default'), rates: tokens },
		...(tokens.long_context ? [{ label: t('pricing.longContext', { threshold: tokens.long_context.threshold_tokens }), rates: tokens.long_context }] : [])
	] : []);
	const mediaRows = $derived.by(() => {
		const rows: { label: string; value: string; unit: string }[] = [];
		const pricing = media;
		if (!pricing) return rows;
		const add = (key: NativeMediaRateKey, label: string, unit: string) => {
			if (Object.hasOwn(pricing, key)) rows.push({ label, value: pricing[key] ?? '—', unit });
		};
		add('image_per_unit', adminT('pricing.imageBaseRate'), t('media.usdPerImage'));
		add('audio_per_character', adminT('configuration.speechGenerationCharacterRate'), adminT('configuration.usdPerCharacter'));
		for (const unit of ['second', 'minute', 'hour'] as const) {
			const priceUnit = t('media.usdPerTime', { unit: adminT(`pricing.${unit}`) });
			for (const [prefix, label] of [
				['audio_input', t('media.audioInput')], ['audio_output', t('media.audioOutput')],
				['realtime_input', t('media.realtimeInput')], ['realtime_output', t('media.realtimeOutput')],
				['realtime_session', t('media.realtimeSession')]
			] as const) add(`${prefix}_per_${unit}`, label, priceUnit);
			if (unit !== 'hour') add(`audio_per_${unit}`, `${unit === 'minute' ? t('media.audioInput') : t('media.audioOutput')} · ${t('media.audioLegacy')}`, priceUnit);
		}
		for (const [variant, value] of Object.entries(pricing.image_variants ?? {})) {
			rows.push({ label: t('media.variant', { variant }), value, unit: t('media.usdPerImage') });
		}
		for (const modality of ['image', 'audio'] as const) {
			const rates = pricing.token_rates?.[modality];
			if (!rates) continue;
			const modalityLabel = modality === 'image' ? adminT('configuration.image') : adminT('pricing.audio');
			for (const [key, direction] of [
				['input_per_million', adminT('configuration.input')],
				['output_per_million', adminT('configuration.output')],
				['cache_read_per_million', adminT('configuration.cacheRead')]
			] as const) {
				rows.push({ label: adminT('pricing.modalityDirection', { modality: modalityLabel, direction }), value: rates[key] ?? '—', unit: adminT('configuration.usd1mTokens') });
			}
		}
		return rows;
	});
	const basisKeys = { unit: 'pricing.imageUnit', duration: 'pricing.audioDuration', characters: 'pricing.characters', tokens: 'pricing.tokens', session: 'pricing.sessionDuration' } as const satisfies Record<BillingBasis, string>;
	const basisLabel = $derived(media?.billing_basis ? adminT(basisKeys[media.billing_basis]) : '—');
</script>

{#if tokens}
	<section class="mt-3 min-w-0" aria-label={t('pricing.tokens')} data-testid="catalog-token-pricing">
		<h5 class="mb-2 text-xs font-medium text-ink-1">{t('pricing.tokens')} · {adminT('configuration.usd1mTokens')}</h5>
		<ResponsiveTable embedded>
			{#snippet cards()}
				{#each tokenRows as row (row.label)}
					<div class="min-w-0 border-t border-line py-2">
						<h6 class="mb-2 text-xs font-medium text-ink-1">{row.label}</h6>
						<dl class="price-facts">
							{#each tokenColumns as column (column.key)}
								<div><dt>{column.label}</dt><dd>{row.rates[column.key] ?? '—'}</dd></div>
							{/each}
						</dl>
					</div>
				{/each}
			{/snippet}
			<TableShell density="compact">
				<table aria-label={t('pricing.tokens')}>
					<thead><tr><th scope="col">{t('pricing.tier')}</th>{#each tokenColumns as column (column.key)}<th scope="col">{column.label}</th>{/each}</tr></thead>
					<tbody>{#each tokenRows as row (row.label)}<tr><th scope="row">{row.label}</th>{#each tokenColumns as column (column.key)}<td>{row.rates[column.key] ?? '—'}</td>{/each}</tr>{/each}</tbody>
				</table>
			</TableShell>
		</ResponsiveTable>
	</section>
{/if}
{#if media}
	<section class="mt-3 min-w-0" aria-label={t('pricing.media')} data-testid="catalog-media-pricing">
		<h5 class="mb-2 text-xs font-medium text-ink-1">{t('pricing.media')}</h5>
		<dl class="price-facts mb-2">
			<div><dt>{t('media.basis')}</dt><dd>{basisLabel}</dd></div>
			{#if Object.hasOwn(media, 'reservation_usd')}<div><dt>{adminT('pricing.reservationCap')}</dt><dd>{media.reservation_usd ?? '—'} USD</dd></div>{/if}
		</dl>
		{#if Object.hasOwn(media, 'reservation_usd')}<p class="mb-2 text-xs text-ink-2">{adminT('pricing.reservationHelp')}</p>{/if}
		{#if mediaRows.length}
			<ResponsiveTable embedded>
				{#snippet cards()}
					{#each mediaRows as row, index (index)}
						<dl class="price-facts min-w-0 border-t border-line py-2"><div><dt>{row.label}</dt><dd>{row.value} <span>{row.unit}</span></dd></div></dl>
					{/each}
				{/snippet}
				<TableShell density="compact">
					<table aria-label={t('pricing.media')}>
						<thead><tr><th scope="col">{t('media.field')}</th><th scope="col">{t('media.rate')}</th><th scope="col">{t('media.unit')}</th></tr></thead>
						<tbody>{#each mediaRows as row, index (index)}<tr><th scope="row">{row.label}</th><td>{row.value}</td><td>{row.unit}</td></tr>{/each}</tbody>
					</table>
				</TableShell>
			</ResponsiveTable>
		{/if}
	</section>
{/if}

<style>
	.price-facts { display: grid; gap: 0.375rem; min-width: 0; font-size: var(--type-support); color: var(--color-ink-2); }
	.price-facts > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.25rem 1rem; min-width: 0; }
	dt { overflow-wrap: anywhere; }
	dd { margin: 0; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; color: var(--color-ink-1); }
	dd span { color: var(--color-ink-2); }
	th, td { overflow-wrap: anywhere; }
</style>
