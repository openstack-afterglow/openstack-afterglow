<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { DbInstance } from '$lib/types/database';

	let {
		instance,
		rootInfo,
		enablingRoot,
		onEnableRoot,
	}: {
		instance: DbInstance;
		rootInfo: { name: string; password: string } | null;
		enablingRoot: boolean;
		onEnableRoot: () => Promise<void>;
	} = $props();

	const dsType = $derived(instance?.datastore?.type ?? '');
	const dbPort = $derived(
		dsType === 'postgresql' ? '5432'
		: dsType === 'redis' ? '6379'
		: dsType === 'mongodb' ? '27017'
		: '3306'
	);
	const connectCmd = $derived(
		instance
			? dsType === 'postgresql'
				? `psql -h ${instance.ip || instance.hostname || '<host>'} -p ${dbPort} -U <user> -d <database>`
				: dsType === 'redis'
					? `redis-cli -h ${instance.ip || instance.hostname || '<host>'} -p ${dbPort}`
					: `mysql -h ${instance.ip || instance.hostname || '<host>'} -P ${dbPort} -u <user> -p`
			: ''
	);
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
	<h2 class="text-sm font-semibold text-ink-0 mb-3">{tr('connection.title')}</h2>
	<div class="space-y-2 text-sm">
		<div class="flex gap-4">
			<div><div class="text-ink-2 text-xs mb-0.5">{tr('labels.host')}</div><div class="text-ink-0 font-mono">{instance.ip || instance.hostname || '-'}</div></div>
			<div><div class="text-ink-2 text-xs mb-0.5">{tr('labels.port')}</div><div class="text-ink-0 font-mono">{dbPort}</div></div>
		</div>
		{#if connectCmd}
			<div>
				<div class="text-ink-2 text-xs mb-1">{tr('connection.example')}</div>
				<code class="block bg-surface-sunken rounded px-3 py-2 text-xs text-green-400 font-mono break-all">{connectCmd}</code>
			</div>
		{/if}
		{#if rootInfo}
			<div class="bg-amber-950/30 border border-action-warm rounded-lg px-3 py-2">
				<div class="text-warm-text text-xs font-medium mb-1">{tr('connection.rootAccount')}</div>
				<div class="font-mono text-xs text-ink-0">{tr('connection.credentials', { name: rootInfo.name, password: rootInfo.password })}</div>
			</div>
		{:else}
			<button onclick={onEnableRoot} disabled={enablingRoot}
				class="text-xs text-warm-text border border-action-warm hover:border-action-warm px-3 py-1.5 rounded transition-colors">
				{#if enablingRoot}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{tr('state.enablingRoot')}</span></span>{:else}{tr('actions.enableRoot')}{/if}
			</button>
		{/if}
	</div>
</div>
