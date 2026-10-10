<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';

	interface Props {
		showHost?: boolean;
	}

	let { showHost = false }: Props = $props();

	const s = useInstanceDetailController();

	const githubLogin = $derived(s.instance!.ssh_access_mode === 'github' ? s.instance!.github_login : null);
</script>

<div class="motion-enter bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('info.title')}</h2>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">ID</dt>
			<dd class="text-sm text-ink-2 font-mono">{s.instance!.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('info.createdAt')}</dt>
			<dd class="text-sm text-ink-2">{s.formatDate(s.instance!.created_at)}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('info.image')}</dt>
			<dd class="text-sm text-ink-2">{s.instance!.image_name ?? s.instance!.image_id ?? t('info.bootFromVolume')}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t('info.flavor')}</dt>
			<dd class="text-sm text-ink-2">{s.instance!.flavor_name ?? s.instance!.flavor_id ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-2 mb-0.5">{t(githubLogin ? 'info.githubSsh' : 'info.keyPair')}</dt>
			<dd class="text-sm text-ink-2 font-mono [overflow-wrap:anywhere]">{#if githubLogin}@{githubLogin}{:else}{s.instance!.key_name ?? '-'}{/if}</dd>
		</div>
		{#if showHost && s.instance!.host}
			<div>
				<dt class="text-xs text-ink-2 mb-0.5">{t('info.host')}</dt>
				<dd class="text-sm text-ink-2 font-mono">{s.instance!.host}</dd>
			</div>
		{/if}
		{#if s.ownerDisplay}
			<div class="overflow-hidden">
				<dt class="text-xs text-ink-2 mb-0.5">{t('info.creator')}</dt>
				<dd class="text-sm text-ink-2 font-mono truncate max-w-full" title={s.ownerDisplay}>{s.ownerDisplay}</dd>
			</div>
		{/if}
		<div class="col-span-2">
			<dt class="text-xs text-ink-2 mb-1.5">{t('info.ipAddress')}</dt>
			<dd class="flex flex-col gap-1.5">
				{#if s.fixedIpsList.length === 0 && s.floatingIpsList.length === 0}
					<span class="text-sm text-ink-2">-</span>
				{/if}
				{#each s.fixedIpsList as fip}
					{@const paired = s.floatingIpsList.find(fl => fl.network_name === fip.network_name)}
					<div class="flex items-center gap-1.5 flex-wrap">
						<span class="text-sm font-mono text-ink-2 bg-surface-sunken px-2 py-0.5 rounded">{fip.addr}</span>
						<span class="text-xs text-ink-2 bg-surface-sunken px-1.5 py-0.5 rounded">{t('info.fixed')}</span>
						{#if paired}
							<span class="text-sm font-mono text-green-300 bg-surface-sunken px-2 py-0.5 rounded">{paired.addr}</span>
							<span class="text-xs text-green-500 bg-green-900/20 px-1.5 py-0.5 rounded">{t('info.floating')}</span>
						{/if}
						{#if fip.network_name}
							<span class="text-xs text-ink-2">{fip.network_name}</span>
						{/if}
					</div>
				{/each}
			</dd>
		</div>
	</dl>
</div>
