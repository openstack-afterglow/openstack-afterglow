<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import Card from '$lib/components/ui/Card.svelte';
	import type { VersionInfo } from '$lib/types/adminOverview';
	import { formatUptime } from '$lib/utils/usageBar';

	let { versionInfo }: { versionInfo: VersionInfo } = $props();
</script>

{#snippet rows(values: { label: string; value: string }[])}
	<dl class="grid min-w-0 grid-cols-1 gap-x-12 md:grid-cols-2">
		{#each values as row}
			<div class="flex min-w-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line py-2">
				<dt class="min-w-0 break-words text-sm text-ink-2">{row.label}</dt>
				<dd class="min-w-0 break-all font-mono text-xs text-ink-1">{row.value}</dd>
			</div>
		{/each}
	</dl>
{/snippet}

<Card>
	<h2 class="mb-4 text-base font-semibold text-ink-0">{t('overview.version.title')}</h2>
	<div class="space-y-6">
		<section>
			<h3 class="mb-1 text-sm font-semibold text-ink-1">{t('overview.version.platform')}</h3>
			{@render rows([
				{ label: t('overview.version.backend'), value: versionInfo.platform.backend_version },
				{ label: t('overview.version.frontend'), value: __APP_VERSION__ },
			])}
		</section>
		<section>
			<h3 class="mb-1 text-sm font-semibold text-ink-1">{t('overview.version.runtime')}</h3>
			{@render rows([
				{ label: 'Python', value: versionInfo.runtime.python_version },
				{ label: t('overview.version.uptime'), value: formatUptime(versionInfo.runtime.uptime_seconds) },
			])}
		</section>
		<section>
			<h3 class="mb-1 text-sm font-semibold text-ink-1">{t('overview.version.dependencies')}</h3>
			{@render rows(Object.entries(versionInfo.dependencies).map(([label, value]) => ({ label, value: value ?? '—' })))}
		</section>
		{#if versionInfo.git.commit}
			<section>
				<h3 class="mb-1 text-sm font-semibold text-ink-1">Git</h3>
				{@render rows([
					{ label: t('overview.version.commit'), value: versionInfo.git.commit },
					...(versionInfo.git.tag ? [{ label: t('overview.version.tag'), value: versionInfo.git.tag }] : []),
					...(versionInfo.git.branch ? [{ label: t('overview.version.branch'), value: versionInfo.git.branch }] : []),
				])}
			</section>
		{/if}
	</div>
</Card>
