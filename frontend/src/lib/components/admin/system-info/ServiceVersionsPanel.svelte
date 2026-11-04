<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { Alert, CompactResourceCard, LoadingState, ResponsiveTable, TableShell } from '$lib/components/ui';
	import type { ServiceVersion, ServiceVersions } from '$lib/types/adminOverview';

	let { data, loading, failure }: {
		data: ServiceVersions | null;
		loading: boolean;
		failure: 'unavailable' | 'failed' | null;
	} = $props();
	const names: Record<ServiceVersion['service'], string> = {
		nova: 'Nova', neutron: 'Neutron', palimpsest: 'Palimpsest', drover: 'Drover', lumen: 'Lumen', waygate: 'Waygate',
	};
	const version = (row: ServiceVersion) => row.status === 'available' && row.version && row.version_kind
		? row.version : t('systemInfo.services.unknown');
	const kind = (row: ServiceVersion) => row.status === 'available' && row.version && row.version_kind
		? t(`systemInfo.services.kind.${row.version_kind}`) : t('systemInfo.services.notReported');
</script>

<section aria-labelledby="service-versions-heading" class="min-w-0 space-y-3">
	<div>
		<h2 id="service-versions-heading" class="text-base font-semibold text-ink-0">{t('systemInfo.services.title')}</h2>
		<p class="mt-1 max-w-prose text-sm text-ink-2">{t('systemInfo.services.description')}</p>
	</div>
	{#if failure}
		<Alert tone={failure === 'unavailable' ? 'info' : 'danger'}>{t(`systemInfo.services.${failure === 'unavailable' ? 'endpointUnavailable' : 'loadFailed'}`)}</Alert>
	{/if}
	{#if loading}<LoadingState variant={data ? 'inline' : 'section'} label={t('systemInfo.services.loading')} />{/if}
	{#if data?.services.length}
		<ResponsiveTable>
			{#snippet cards()}
				{#each data.services as row (row.service)}
					<CompactResourceCard>
						<h3 class="text-sm font-semibold text-ink-0">{names[row.service]}</h3>
						<p class="text-ink-2">{t(`systemInfo.services.status.${row.status}`)}</p>
						<dl>
							<div><dt>{t('systemInfo.services.version')}</dt><dd class="break-all">{version(row)}</dd></div>
							<div><dt>{t('systemInfo.services.kind')}</dt><dd>{kind(row)}</dd></div>
						</dl>
					</CompactResourceCard>
				{/each}
			{/snippet}
			<TableShell>
				<table aria-labelledby="service-versions-heading">
					<thead><tr>
						<th scope="col">{t('systemInfo.services.service')}</th>
						<th scope="col">{t('systemInfo.services.status')}</th>
						<th scope="col">{t('systemInfo.services.version')}</th>
						<th scope="col">{t('systemInfo.services.kind')}</th>
					</tr></thead>
					<tbody>{#each data.services as row (row.service)}<tr>
						<th scope="row" class="text-ink-0">{names[row.service]}</th>
						<td class="text-ink-2">{t(`systemInfo.services.status.${row.status}`)}</td>
						<td class="break-all text-ink-1">{version(row)}</td>
						<td class="text-ink-2">{kind(row)}</td>
					</tr>{/each}</tbody>
				</table>
			</TableShell>
		</ResponsiveTable>
	{:else if data && !loading && !failure}
		<p class="text-sm text-ink-2">{t('systemInfo.services.empty')}</p>
	{/if}
</section>
