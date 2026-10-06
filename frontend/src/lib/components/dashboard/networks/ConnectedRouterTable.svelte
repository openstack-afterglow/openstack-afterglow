<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { NetworkRouterInfo, RouterListItem } from '$lib/types/networks';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

	let {
		routers,
		subnets = [],
		availableRouters = [],
		canManage = false,
		connecting = false,
		projectId,
		isSystemAdmin = false,
		onConnect,
		onDisconnect,
	}: {
		routers: NetworkRouterInfo[];
		subnets?: { id: string; name: string; cidr: string; gateway_ip?: string | null }[];
		availableRouters?: RouterListItem[];
		canManage?: boolean;
		connecting?: boolean;
		projectId?: string | null;
		isSystemAdmin?: boolean;
		onConnect?: (routerId: string, subnetId: string) => Promise<boolean>;
		onDisconnect?: (routerId: string, subnetId: string) => Promise<boolean>;
	} = $props();
	let showConnectForm = $state(false);
	let selectedRouterId = $state('');
	let selectedSubnetId = $state('');
	const pending = createPendingAction();
	const connectingRouter = $derived(pending.isActive('connect', connecting));

	function openConnect() {
		selectedRouterId = availableRouters[0]?.id ?? '';
		selectedSubnetId = subnets[0]?.id ?? '';
		showConnectForm = true;
	}

	async function handleConnect() {
		const connect = onConnect;
		if (!selectedRouterId || !selectedSubnetId || !connect) return;
		const ok = await pending.run('connect', () => connect(selectedRouterId, selectedSubnetId));
		if (ok) {
			showConnectForm = false;
			selectedRouterId = '';
			selectedSubnetId = '';
		}
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">{t('network.routers.titleCount', { count: routers.length })}</h2>
		{#if canManage && onConnect && subnets.length > 0 && availableRouters.length > 0}
			<Button
				variant="subtle"
				size="xs"
				onclick={() => { if (showConnectForm) { showConnectForm = false; } else { openConnect(); } }}
			>
				{showConnectForm ? t('network.actions.close') : t('network.routers.connectAdd')}
			</Button>
		{/if}
	</div>

	{#if showConnectForm && canManage}
		<div class="motion-enter mb-4 bg-surface-sunken rounded-lg p-4 space-y-3">
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1">{t('network.routers.select')}
						<select
							bind:value={selectedRouterId}
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
						>
							<option value="">{t('network.routers.select')}</option>
							{#each availableRouters as r}
								<option value={r.id}>{r.name || r.id.slice(0, 12)}</option>
							{/each}
						</select>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">{t('network.subnets.select')}
						<select
							bind:value={selectedSubnetId}
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
						>
							<option value="">{t('network.subnets.select')}</option>
							{#each subnets as s}
								<option value={s.id}>{!s.gateway_ip ? t('network.subnets.autoGatewayOption', { name: s.name || s.cidr }) : s.name || s.cidr}</option>
							{/each}
						</select>
					</label>
				</div>
			</div>
			<div class="flex justify-end gap-2">
				<Button
					size="xs"
					variant="ghost"
					onclick={() => { showConnectForm = false; }}
				>{t('network.actions.cancel')}</Button>
				<Button
					size="xs"
					variant="accent"
					onclick={handleConnect}
					disabled={!selectedRouterId || !selectedSubnetId || connecting}
					ariaBusy={connectingRouter}
				>{#if connectingRouter}<ActivityIndicator size="xs" tone="ink" />{/if}{connectingRouter ? t('network.actions.connecting') : t('network.actions.connect')}</Button>
			</div>
		</div>
	{/if}

	{#if routers.length > 0}
		<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="text-left py-2 pr-6">{t('network.labels.name')}</th>
					<th class="text-left py-2 pr-6">{t('network.routers.externalGateway')}</th>
					<th class="text-left py-2 pr-6">{t('network.routers.connectedSubnets')}</th>
					{#if canManage && onDisconnect}
						<th class="text-right py-2">{t('network.labels.actions')}</th>
					{/if}
				</tr>
			</thead>
			<tbody>
				{#each routers as router}
					<tr class="border-b border-line/50">
						<td class="py-2 pr-6 text-ink-2"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={router.name || router.id}>{router.name || router.id.slice(0, 12) + '…'}</span></td>
						<td class="py-2 pr-6">
							{#if router.external_gateway_network_id}
								<span class="text-orange-300 text-xs font-mono">{router.external_gateway_network_id.slice(0, 12)}…</span>
							{:else}
								<span class="text-ink-2 text-xs">-</span>
							{/if}
						</td>
						<td class="py-2 pr-6 text-ink-2 text-xs">
							{#if router.connected_subnet_ids.length > 0}
								<div class="flex flex-wrap gap-1">
									{#each router.connected_subnet_ids as sid}
										{@const sub = subnets.find(s => s.id === sid)}
										<span class="px-1.5 py-0.5 rounded text-xs bg-surface-selected/50 border border-line text-ink-1">
											{sub?.name || sid.slice(0, 8)}
										</span>
									{/each}
								</div>
							{:else}
								<span>-</span>
							{/if}
						</td>
						{#if canManage && onDisconnect}
							<td class="py-2 text-right">
								{#if isSystemAdmin || (router.project_id && router.project_id === projectId)}
									<div class="flex items-center justify-end gap-1">
										{#each router.connected_subnet_ids as sid}
											{@const disconnecting = pending.isActive(`disconnect:${router.id}:${sid}`, connecting)}
											<Button
												variant="danger-outline"
												size="xs"
												onclick={() => pending.run(`disconnect:${router.id}:${sid}`, () => onDisconnect?.(router.id, sid))}
												disabled={connecting}
												ariaBusy={disconnecting}
											>
												{#if disconnecting}<ActivityIndicator size="xs" tone="danger" />{/if}{disconnecting ? tc('state.processing') : router.connected_subnet_ids.length > 1 ? t('network.routers.disconnectNamed', { name: subnets.find((s) => s.id === sid)?.name || sid.slice(0, 6) }) : t('network.actions.disconnect')}
											</Button>
										{/each}
									</div>
								{:else}
									<span class="text-ink-3 text-xs">-</span>
								{/if}
							</td>
						{/if}
					</tr>
				{/each}
			</tbody>
		</table>
		</div>
	{:else}
		<p class="text-sm text-ink-2">{t('network.routers.emptySentence')}</p>
	{/if}
</div>
