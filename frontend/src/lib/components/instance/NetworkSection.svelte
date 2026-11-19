<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import type { PortInfo } from '$lib/types/networks';
	import { t } from '$lib/i18n/ns/instance';
	import SecurityGroupUnion from './SecurityGroupUnion.svelte';
	import { buildSecurityGroupUnion } from '$lib/utils/securityGroupUnion';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { StatusChip } from '$lib/components/ui';
	import Alert from '$lib/components/ui/Alert.svelte';
	import IsoGridView from '$lib/components/iso/IsoGridView.svelte';
	import IsoViewToggle from '$lib/components/iso/IsoViewToggle.svelte';
	import type { IsoViewMode } from '$lib/components/iso/types';
	import { buildInstanceIsoScene } from './instanceIsoScene';

	const s = useInstanceDetailController();
	const lockTitle = $derived(s.waygateLocked ? t('waygate.managedNote') : undefined);
	const inspectorHeading = $props.id();
	let viewMode = $state<IsoViewMode>('grid');
	let selection = $state<{ instanceId: string; id: string } | null>(null);
	const selectedId = $derived(selection?.instanceId === s.instance?.id ? selection?.id ?? null : null);
	const grid = $derived.by(() => {
		if (viewMode !== 'grid' || !s.instance) return null;
		const savedByPort = new Map(s.securityGroupPorts.map(port => [port.id, port.security_group_ids]));
		const policy = !s.securityGroupsLoading && !s.securityGroupsError && savedByPort.size === s.interfaces.length
			&& s.interfaces.every(port => savedByPort.get(port.id) != null)
			? { groups: s.allSecurityGroups, portGroupIds: new Map(s.interfaces.map(port => [port.id, savedByPort.get(port.id)!])) }
			: null;
		return buildInstanceIsoScene({
			instance: s.instance, ports: s.interfaces, networks: s.availableNetworks,
			floatingIps: s.floatingIps, policy, waygateLocked: s.waygateLocked,
			volumes: s.volumesKnown ? s.volumes : null, shares: s.storageAttachments,
			expandedSecurityGroup: selectedId,
		});
	});
	const detail = $derived(selectedId ? grid?.details.get(selectedId) : undefined);

	function associationLabel(state: string) {
		switch (state) {
			case 'tracked': return t('network.iso.association.tracked');
			case 'untracked': return t('network.iso.association.untracked');
			case 'mismatch': return t('network.iso.association.mismatch');
			default: return t('network.iso.association.unknown');
		}
	}
	let showAddInterface = $state(false);
	let selectedNetId = $state('');
	let sgEditPortId = $state<string | null>(null);
	let sgEditSelected = $state<string[]>([]);
	let expandedSgRules = $state<Set<string>>(new Set());

	function toggleSgRules(sgId: string) {
		const next = new Set(expandedSgRules);
		next.has(sgId) ? next.delete(sgId) : next.add(sgId);
		expandedSgRules = next;
	}

	function toggleSg(sgId: string) {
		if (s.waygateLocked) return;
		if (sgEditSelected.includes(sgId)) {
			sgEditSelected = sgEditSelected.filter(id => id !== sgId);
		} else {
			sgEditSelected = [...sgEditSelected, sgId];
		}
	}

	function openSgEdit(port: PortInfo) {
		if (s.waygateLocked) return;
		sgEditPortId = port.id;
		sgEditSelected = [...s.securityGroupIdsForPort(port)];
	}

	async function handleSaveSgEdit() {
		if (!sgEditPortId) return;
		await s.saveSgEdit(sgEditPortId, sgEditSelected);
		sgEditPortId = null;
	}

	async function handleAttachInterface() {
		await s.attachInterface(selectedNetId);
		showAddInterface = false;
		selectedNetId = '';
	}
</script>

<div class="min-w-0 bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-2">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">{t('network.title')}</h2>
		<IsoViewToggle value={viewMode} onchange={mode => { viewMode = mode; }} storageKey="instance.network.view" />
	</div>

	{#if grid && s.instance}
		<div class="min-w-0 @max-md/panel:-mx-2">
			<IsoGridView scene={grid.scene} label={t('network.iso.label')}
				caption={[t('network.iso.caption'), grid.scene.nodes.some(node => node.kind === 'volume' || node.kind === 'file-share') ? t('network.iso.storageNote') : ''].filter(Boolean).join(' ')}
				height="clamp(17rem, 51dvh, 26.5rem)" fitKey={s.instance.id}
				selectedId={detail ? selectedId : null}
				onselect={id => { if (s.instance) selection = { instanceId: s.instance.id, id }; }}
				onclear={() => { selection = null; }} />
		</div>
		{#if s.interfaces.length === 0}
			<p class="mt-3 text-sm text-ink-2">{t('network.empty')}</p>
		{:else if s.securityGroupsLoading}
			<LoadingState variant="section" label={t('securityGroupUnion.loading')} />
		{:else if s.securityGroupsError}
			<Alert flat tone="danger" class="mt-3">
				{t('securityGroupUnion.error', { error: s.securityGroupsError })}
			</Alert>
		{:else if grid.missingGroupIds.length}
			<Alert flat tone="warning" class="mt-3">
				<p>{t('securityGroupUnion.missingGroups')}</p>
				<ul class="font-mono break-all">
					{#each grid.missingGroupIds as id (id)}<li>{id}</li>{/each}
				</ul>
			</Alert>
		{:else if !grid.policyKnown}
			<Alert flat tone="warning" class="mt-3">{t('network.iso.policyUnknown')}</Alert>
		{/if}
		{#if detail}
			<section aria-labelledby={inspectorHeading} class="mt-4 min-w-0 space-y-2 border-t border-line pt-3">
				<h3 id={inspectorHeading} class="break-words text-sm font-semibold text-ink-1">{detail.label}</h3>
				{#if detail.kind === 'port'}
					<dl class="space-y-2 text-xs text-ink-2">
						<div><dt>{t('network.portId')}</dt><dd class="break-all font-mono">{detail.port.id}</dd></div>
						{#if detail.network}<div><dt>{t('network.network')}</dt><dd class="break-words">{detail.network}</dd></div>{/if}
						{#if detail.port.mac_address}<div><dt>{t('network.macAddress')}</dt><dd class="font-mono">{detail.port.mac_address}</dd></div>{/if}
						<div><dt>{t('network.status')}</dt><dd><StatusChip status={detail.port.status} /></dd></div>
						{#if detail.port.fixed_ips.length}
							<div><dt>{t('network.ipAddress')}</dt><dd class="break-words font-mono">{detail.port.fixed_ips.map(ip => ip.ip_address).join(', ')}</dd></div>
						{/if}
						{#if detail.securityGroups}
							<div><dt>{t('network.securityGroups')}</dt><dd class="break-words">{detail.securityGroups.join(', ') || t('network.none')}</dd></div>
						{/if}
					</dl>
				{:else if detail.kind === 'security-group'}
					<dl class="space-y-2 text-xs text-ink-2">
						<div><dt>{t('network.iso.detail.id')}</dt><dd class="break-all font-mono">{detail.groupId}</dd></div>
						{#each detail.ports as port (port.id)}
							<div><dt>{t('network.iso.detail.groupPorts')}</dt><dd class="break-all font-mono">{port.id}</dd></div>
						{/each}
					</dl>
					{#if detail.missing}
						<p class="text-xs text-state-warning-text">{t('network.iso.groupMissing')}</p>
					{:else if detail.rules.length === 0}
						<p class="text-xs text-ink-2">{t('network.iso.detail.noRules')}</p>
					{:else}
						<ul class="space-y-1 text-xs text-ink-2">
							{#each detail.rules as rule (rule.key)}
								<li class="break-words">{t(rule.direction === 'ingress' ? 'securityGroupUnion.direction.ingress' : 'securityGroupUnion.direction.egress')} · {rule.ethertype} · {rule.protocolLabel} · {rule.portLabel} · {rule.remoteLabel}</li>
							{/each}
						</ul>
					{/if}
				{:else if detail.kind === 'volume'}
					<dl class="space-y-2 text-xs text-ink-2">
						<div><dt>{t('network.iso.detail.id')}</dt><dd class="break-all font-mono">{detail.volume.volume_id}</dd></div>
						{#if detail.volume.device}<div><dt>{t('network.iso.detail.device')}</dt><dd class="font-mono">{detail.volume.device}</dd></div>{/if}
						{#if detail.volume.size}<div><dt>{t('network.iso.detail.size')}</dt><dd>{t('network.iso.sizeGb', { size: detail.volume.size })}</dd></div>{/if}
						{#if detail.volume.status}<div><dt>{t('network.status')}</dt><dd><StatusChip status={detail.volume.status} /></dd></div>{/if}
						{#if detail.volume.delete_on_termination !== undefined}
							<div><dt>{t('volumes.title')}</dt><dd>{detail.volume.delete_on_termination ? t('volumes.deleteOnTermination') : t('volumes.keep')}</dd></div>
						{/if}
					</dl>
				{:else if detail.kind === 'share'}
					<dl class="space-y-2 text-xs text-ink-2">
						<div><dt>{t('network.iso.detail.id')}</dt><dd class="break-all font-mono">{detail.share.file_storage_id}</dd></div>
						{#if detail.share.share_proto}<div><dt>{t('network.iso.detail.protocol')}</dt><dd>{detail.share.share_proto.toUpperCase()}</dd></div>{/if}
						<div><dt>{t('network.status')}</dt><dd><StatusChip status={detail.share.status} /></dd></div>
						{#if detail.share.access_level}<div><dt>{t('network.iso.detail.accessLevel')}</dt><dd>{detail.share.access_level}</dd></div>{/if}
						{#if detail.share.access_to}<div><dt>{t('network.iso.detail.accessTo')}</dt><dd class="break-all font-mono">{detail.share.access_to}</dd></div>{/if}
						{#if detail.share.association_state}<div><dt>{t('network.iso.detail.association')}</dt><dd>{associationLabel(detail.share.association_state)}</dd></div>{/if}
					</dl>
				{:else if detail.kind === 'network'}
					<ul class="space-y-2 text-xs text-ink-2">
						{#each detail.ports as port (port.id)}
							<li class="flex flex-wrap items-center gap-2">
								<span class="break-all font-mono">{port.id}</span><StatusChip status={port.status} />
								{#each port.fixed_ips as ip}<span class="break-all font-mono">{ip.ip_address}</span>{/each}
							</li>
						{/each}
					</ul>
				{:else if detail.kind === 'rules'}
					<ul class="space-y-1 text-xs text-ink-2">
						{#each detail.rules as rule (rule.key)}
							<li class="break-words">{t(rule.direction === 'ingress' ? 'securityGroupUnion.direction.ingress' : 'securityGroupUnion.direction.egress')} · {rule.ethertype} · {rule.protocolLabel} · {rule.portLabel} · {rule.remoteLabel}</li>
						{/each}
					</ul>
				{:else if detail.kind === 'floating'}
					<ul class="space-y-1 text-xs text-ink-2">
						{#each detail.addresses as ip (ip.id)}
							<li class="flex flex-wrap items-center gap-2"><span class="break-all font-mono">{ip.floating_ip_address}</span><StatusChip status={ip.status} /></li>
						{/each}
					</ul>
				{/if}
			</section>
		{/if}
	{:else if viewMode === 'list'}
		<div class="mb-3 flex justify-end">
			<button
				onclick={() => { showAddInterface = !showAddInterface; selectedNetId = ''; }}
				disabled={s.waygateLocked}
				title={lockTitle}
				class="text-xs text-warm-text hover:text-warm-text-hover transition-colors disabled:text-ink-3"
			>
				{showAddInterface ? t('network.close') : t('network.addInterface')}
			</button>
		</div>

	{#if showAddInterface && !s.waygateLocked}
		<div class="motion-enter mb-4 border-y border-line py-4">
			<p class="text-xs text-ink-2 mb-2">{t('network.selectNetworkLabel')}</p>
			<div class="flex gap-2">
				<select
					bind:value={selectedNetId}
					class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
				>
					<option value="">{t('network.selectNetworkPlaceholder')}</option>
					{#each s.availableNetworks as net}
						<option value={net.id}>{net.name || net.id.slice(0, 12)}</option>
					{/each}
				</select>
				<button
					onclick={handleAttachInterface}
					disabled={!selectedNetId || s.actioning === 'attach-iface'}
					class="text-xs text-warm-text hover:text-warm-text-hover px-3 py-1.5 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3 disabled:border-line-2"
				>
					{#if s.actioning === 'attach-iface'}<LoadingState variant="control" label={t('network.adding')} />{:else}{t('network.add')}{/if}
				</button>
			</div>
		</div>
	{/if}

	{#if s.interfaces.length === 0}
		<p class="text-sm text-ink-2">{t('network.empty')}</p>
	{:else}
		<div class="divide-y divide-line border-t border-line">
			{#each s.interfaces as iface (iface.id)}
				{@const ifaceFip = s.floatingIps.find(f => f.port_id === iface.id)}
				{@const appliedGroupIds = s.securityGroupIdsForPort(iface)}
				<div class="min-w-0 py-4 last:pb-0">
					<div class="flex items-start justify-between mb-3">
						<div class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-2 flex-1 min-w-0">
							<div>
								<dt class="text-xs text-ink-2 mb-0.5">{t('network.portId')}</dt>
								<dd class="text-xs text-ink-2 font-mono break-all">{iface.id}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-2 mb-0.5">{t('network.macAddress')}</dt>
								<dd class="text-xs text-ink-2 font-mono">{iface.mac_address}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-2 mb-0.5">{t('network.network')}</dt>
								<dd class="text-xs text-ink-2">{iface.network_id ? s.networkNameById(iface.network_id) : '-'}</dd>
							</div>
							<div>
								<dt class="text-xs text-ink-2 mb-0.5">{t('network.status')}</dt>
								<dd><StatusChip status={iface.status} /></dd>
							</div>
							<div class="@3xl/panel:col-span-2">
								<dt class="text-xs text-ink-2 mb-1">{t('network.ipAddress')}</dt>
								<dd class="flex flex-wrap gap-1.5 items-center">
									{#each iface.fixed_ips as fip}
										<span class="text-xs font-mono text-ink-2 bg-surface-selected px-1.5 py-0.5 rounded">{fip.ip_address}</span>
									{/each}
									{#if ifaceFip}
										<span class="text-xs font-mono text-green-300 bg-green-900/20 px-1.5 py-0.5 rounded">{ifaceFip.floating_ip_address}</span>
									{/if}
								</dd>
							</div>
						</div>
						<div class="ml-4 flex flex-col gap-1.5 shrink-0">
							{#if ifaceFip}
								<button
									onclick={() => s.releaseFloatingIp(ifaceFip.id)}
									disabled={!!s.actioning || s.waygateLocked}
									title={lockTitle}
									class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3"
								>
									{#if s.actioning === 'fip-release-' + ifaceFip.id}<LoadingState variant="control" label={t('network.releasing')} />{:else}{t('network.releaseFloatingIp')}{/if}
								</button>
							{:else}
								<button
									onclick={() => s.assignFloatingIp(iface.id)}
									disabled={!!s.actioning || s.waygateLocked}
									title={lockTitle}
									class="text-xs text-warm-text hover:text-warm-text-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3"
								>
									{#if s.actioning === 'fip-assign-' + iface.id}<LoadingState variant="control" label={t('network.assigning')} />{:else}{t('network.addFloatingIp')}{/if}
								</button>
							{/if}
							<button
								onclick={() => s.detachInterface(iface.id)}
								disabled={!!s.actioning || s.waygateLocked}
								title={lockTitle}
								class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3"
							>
								{#if s.actioning === 'detach-iface-' + iface.id}<LoadingState variant="control" label={t('network.removing')} />{:else}{t('network.remove')}{/if}
							</button>
						</div>
					</div>
					<!-- 보안 그룹 -->
					<div>
						<div class="flex items-center justify-between mb-1.5">
							<dt class="text-xs text-ink-2">{t('network.securityGroups')}</dt>
							<button
								onclick={() => openSgEdit(iface)}
								disabled={s.securityGroupsLoading || !!s.securityGroupsError || s.waygateLocked}
								title={lockTitle}
								class="text-xs text-warm-text hover:text-warm-text-hover transition-colors disabled:text-ink-3"
							>
								{t('network.edit')}
							</button>
						</div>
						{#if sgEditPortId === iface.id && !s.waygateLocked}
							<div class="motion-enter border-y border-line py-3 mt-2">
								<p class="text-xs text-ink-2 mb-2">{t('network.projectSecurityGroups')}</p>
								<div class="space-y-1.5 mb-3 max-h-56 overflow-y-auto">
									{#each s.allSecurityGroups as sg}
										<div>
											<label class="flex items-center gap-2 cursor-pointer">
												<input
													type="checkbox"
													checked={sgEditSelected.includes(sg.id)}
													onchange={() => toggleSg(sg.id)}
													class="accent-blue-500"
												/>
												<span class="text-xs text-ink-2">{sg.name}</span>
												{#if sg.description}
													<span class="text-xs text-ink-2 truncate max-w-[100px]">— {sg.description}</span>
												{/if}
												<button
													type="button"
													onclick={() => toggleSgRules(sg.id)}
													class="text-xs text-ink-2 hover:text-ink-2 ml-auto shrink-0 transition-colors"
												>
													{t('network.ruleCount', { indicator: expandedSgRules.has(sg.id) ? '▾' : '▸', count: sg.rules.length })}
												</button>
											</label>
											{#if expandedSgRules.has(sg.id)}
												{@const groupUnion = buildSecurityGroupUnion(s.allSecurityGroups, [sg.id])}
												<div class="ml-5 mt-1 mb-1 space-y-0.5 pl-2 border-l border-line-2">
													{#each groupUnion.rows as rule (rule.key)}
														<div class="text-xs text-ink-2 break-words">{t(rule.direction === 'ingress' ? 'securityGroupUnion.direction.ingress' : 'securityGroupUnion.direction.egress')} · {rule.ethertype} · {rule.protocolLabel} {rule.portLabel} · {rule.remoteLabel}</div>
													{/each}
													{#if sg.rules.length === 0}
														<div class="text-xs text-ink-2 italic">{t('network.noRules')}</div>
													{/if}
												</div>
											{/if}
										</div>
									{/each}
								</div>
								<div class="flex gap-2">
									<button
										onclick={handleSaveSgEdit}
										disabled={s.actioning === 'sg-' + iface.id || s.securityGroupsLoading || !!s.securityGroupsError}
										class="text-xs text-warm-text hover:text-warm-text-hover px-2 py-1 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3"
									>
										{#if s.actioning === 'sg-' + iface.id}<LoadingState variant="control" label={t('network.saving')} />{:else}{t('network.save')}{/if}
									</button>
									<button
										onclick={() => { sgEditPortId = null; }}
										class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors"
									>
										{t('network.cancel')}
									</button>
								</div>
							</div>
						{:else}
							<dd class="flex flex-wrap gap-1.5">
								{#if appliedGroupIds.length === 0}
									<span class="text-xs text-ink-2">{t('network.none')}</span>
								{:else}
									{#each appliedGroupIds as sgId}
										<span class="text-xs text-purple-300 bg-purple-900/30 px-1.5 py-0.5 rounded">{s.sgNameById(sgId)}</span>
									{/each}
								{/if}
							</dd>
						{/if}
					</div>
					<SecurityGroupUnion
						groupIds={appliedGroupIds}
						groups={s.allSecurityGroups}
						loading={s.securityGroupsLoading}
						error={s.securityGroupsError}
					/>
				</div>
			{/each}
		</div>
	{/if}
	{/if}
</div>
