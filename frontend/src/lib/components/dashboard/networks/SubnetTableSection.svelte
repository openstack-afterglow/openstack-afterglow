<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import type { NetworkDetail, RouterListItem } from '$lib/types/networks';

	let {
		network,
		availableRouters = [],
		onAdd,
		onSave,
		onDelete,
		addingSubnet,
		savingSubnet,
		addError,
		saveError,
		onClearAddError,
		onClearSaveError,
		canManage,
	}: {
		network: NetworkDetail;
		availableRouters?: RouterListItem[];
		onAdd: (form: { name: string; cidr: string; gateway: string; dhcp: boolean; routerId?: string }) => Promise<boolean>;
		onSave: (subnetId: string, form: { name: string; gateway: string; dhcp: boolean }) => Promise<boolean>;
		onDelete: (subnetId: string, subnetName: string) => Promise<void>;
		addingSubnet: boolean;
		savingSubnet: boolean;
		addError: string;
		saveError: string;
		onClearAddError: () => void;
		onClearSaveError: () => void;
		canManage: boolean;
	} = $props();

	let showSubnetForm = $state(false);
	let subnetForm = $state({ name: '', cidr: '10.0.0.0/24', gateway: '', dhcp: true, routerId: '' });
	let editingSubnetId = $state<string | null>(null);
	let editSubnetForm = $state({ name: '', gateway: '', dhcp: true });

	function startEditSubnet(subnet: { id: string; name: string; gateway_ip: string | null; dhcp_enabled: boolean }) {
		editingSubnetId = subnet.id;
		editSubnetForm = {
			name: subnet.name || '',
			gateway: subnet.gateway_ip ?? '',
			dhcp: subnet.dhcp_enabled,
		};
		onClearSaveError();
	}

	async function handleAdd() {
		const ok = await onAdd(subnetForm);
		if (ok) {
			showSubnetForm = false;
			onClearAddError();
			subnetForm = { name: '', cidr: '10.0.0.0/24', gateway: '', dhcp: true, routerId: '' };
		}
	}

	async function handleSave() {
		if (!editingSubnetId) return;
		const ok = await onSave(editingSubnetId, editSubnetForm);
		if (ok) editingSubnetId = null;
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">{t('network.subnets.title')}</h2>
		{#if canManage}
			<button
				onclick={() => { showSubnetForm = !showSubnetForm; onClearAddError(); }}
				class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
			>
				{showSubnetForm ? t('network.actions.close') : t('network.subnets.addToggle')}
			</button>
		{/if}
	</div>

	{#if showSubnetForm}
		<div class="mb-4 bg-surface-sunken rounded-lg p-4 space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1">{t('network.subnets.optionalName')}
						<input
							bind:value={subnetForm.name}
							type="text"
							placeholder={t('network.subnets.namePlaceholder')}
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
						/>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">CIDR
						<input
							bind:value={subnetForm.cidr}
							type="text"
							placeholder="10.0.0.0/24"
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
						/>
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">{t('network.subnets.optionalGateway')}
						<input
							bind:value={subnetForm.gateway}
							type="text"
							placeholder="10.0.0.1"
							class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
						/>
					</label>
				</div>
				<div class="flex items-end pb-1.5">
					<label class="flex items-center gap-2 text-sm text-ink-2">
						<input type="checkbox" bind:checked={subnetForm.dhcp} class="rounded border-line-2" />
						{t('network.subnets.enableDhcp')}
					</label>
				</div>
				{#if availableRouters.length > 0}
					<div class="col-span-2">
						<label class="block text-xs text-ink-2 mb-1">{t('network.subnets.optionalRouter')}
							<select
								bind:value={subnetForm.routerId}
								class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
							>
								<option value="">{t('network.subnets.noRouter')}</option>
								{#each availableRouters as r}
									<option value={r.id}>{r.name || r.id.slice(0, 12)}</option>
								{/each}
							</select>
						</label>
					</div>
				{/if}
			</div>
			{#if addError}
				<p class="text-red-400 text-xs">{addError}</p>
			{/if}
			<div class="flex justify-end">
				<button
					onclick={handleAdd}
					disabled={addingSubnet}
					class="text-sm px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm rounded transition-colors"
				>
					{addingSubnet ? t('network.subnets.adding') : t('network.subnets.add')}
				</button>
			</div>
		</div>
	{/if}

	{#if network.subnet_details.length > 0}
		<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="text-left py-2 pr-6">{t('network.labels.name')}</th>
					<th class="text-left py-2 pr-6">CIDR</th>
					<th class="text-left py-2 pr-6">{t('network.labels.gateway')}</th>
					<th class="text-left py-2 pr-4">DHCP</th>
					<th class="text-left py-2 pr-6">{t('network.routers.title')}</th>
					{#if canManage}
						<th class="text-right py-2">{t('network.labels.actions')}</th>
					{/if}
				</tr>
			</thead>
			<tbody>
				{#each network.subnet_details as subnet}
					{@const connected = (network.routers || []).filter((r) => r.connected_subnet_ids.includes(subnet.id))}
					<tr class="border-b border-line/50">
						{#if editingSubnetId === subnet.id}
							<td colspan={canManage ? 6 : 5} class="py-3">
								<div class="bg-surface-sunken rounded-lg p-4 space-y-3">
									<div class="grid grid-cols-2 gap-3">
										<div>
											<label class="block text-xs text-ink-2 mb-1">{t('network.labels.name')}
												<input
													bind:value={editSubnetForm.name}
													type="text"
													class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1"
												/>
											</label>
										</div>
										<div>
											<label class="block text-xs text-ink-2 mb-1">{t('network.labels.gateway')}
												<input
													bind:value={editSubnetForm.gateway}
													type="text"
													placeholder={subnet.gateway_ip ?? t('network.state.none')}
													class="w-full bg-surface-selected border border-line-2 rounded px-2.5 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1"
												/>
											</label>
										</div>
										<div class="flex items-center">
											<label class="flex items-center gap-2 text-sm text-ink-2">
												<input type="checkbox" bind:checked={editSubnetForm.dhcp} class="rounded border-line-2" />
												{t('network.subnets.enableDhcp')}
											</label>
										</div>
									</div>
									{#if saveError}
										<p class="text-red-400 text-xs">{saveError}</p>
									{/if}
									<div class="flex justify-end gap-2">
										<button
											onclick={() => { editingSubnetId = null; }}
											class="text-xs text-ink-2 hover:text-ink-1 px-3 py-1.5 transition-colors"
										>{t('network.actions.cancel')}</button>
										<button
											onclick={handleSave}
											disabled={savingSubnet}
											class="text-xs px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-action-on-warm rounded transition-colors"
										>{savingSubnet ? t('network.actions.saving') : t('network.actions.save')}</button>
									</div>
								</div>
							</td>
						{:else}
							<td class="py-2 pr-6 text-ink-2"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={subnet.name || subnet.id}>{subnet.name || '-'}</span></td>
							<td class="py-2 pr-6 text-ink-2 font-mono text-xs">{subnet.cidr}</td>
							<td class="py-2 pr-6 text-ink-2 font-mono text-xs">{subnet.gateway_ip ?? '-'}</td>
							<td class="py-2 pr-4">
								{#if subnet.dhcp_enabled}
									<span class="px-1.5 py-0.5 bg-green-900/30 text-green-400 rounded text-xs">{t('network.state.enabled')}</span>
								{:else}
									<span class="text-ink-2 text-xs">-</span>
								{/if}
							</td>
							<td class="py-2 pr-6 text-ink-2 text-xs">
								{#if connected.length > 0}
									<div class="flex flex-wrap gap-1">
										{#each connected as r}
											<span class="px-1.5 py-0.5 rounded text-xs bg-surface-selected/50 border border-line text-ink-1">
												{r.name || r.id.slice(0, 8)}
											</span>
										{/each}
									</div>
								{:else}
									<span class="text-ink-3">-</span>
								{/if}
							</td>
							{#if canManage}
								<td class="py-2 text-right">
									<div class="flex items-center justify-end gap-1">
										<button
											onclick={() => startEditSubnet(subnet)}
											class="text-xs text-warm-text hover:text-warm-text-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors"
										>{t('network.actions.edit')}</button>
										<button
											onclick={() => onDelete(subnet.id, subnet.name)}
											class="text-xs text-red-400 hover:text-red-300 px-2 py-1 border border-red-900 hover:border-red-700 rounded transition-colors"
										>{t('network.actions.delete')}</button>
									</div>
								</td>
							{/if}
						{/if}
					</tr>
				{/each}
			</tbody>
		</table>
		</div>
	{:else}
		<p class="text-sm text-ink-2">{t('network.subnets.emptyLabel')}</p>
	{/if}
</div>
