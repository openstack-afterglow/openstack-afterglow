<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import IsoGridView from '$lib/components/iso/IsoGridView.svelte';
	import IsoViewToggle from '$lib/components/iso/IsoViewToggle.svelte';
	import type { IsoViewMode } from '$lib/components/iso/types';
	import { Button, LoadingState, StatusChip } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/drover';
	import { t as ti } from '$lib/i18n/ns/instance';
	import { t as tc } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import type { SecurityGroupUnionRow } from '$lib/utils/securityGroupUnion';
	import type { ServiceInfo } from '$lib/types/k3s';
	import { buildK3sIsoScene, K3S_GRID_PAGE_SIZE, k3sSecurityGroupNodeOf, listK3sGridNodes, type K3sGridRate, type K3sGridTraffic, type K3sIsoDetail } from './k3sIsoScene';

	let { list }: { list: Snippet } = $props();
	const s = useK3sClusterDetailController();
	const heading = $props.id();
	const inspectorHeading = `${heading}-inspector`;
	let mode = $state<IsoViewMode>('grid');
	let selectedId = $state<string | null>(null);
	let page = $state(0);
	const clusterId = $derived(s.cluster?.id);
	const vmNodes = $derived(s.cluster ? listK3sGridNodes(s.cluster, s.gridNodegroups ?? []) : []);
	const pageCount = $derived(Math.max(1, Math.ceil(vmNodes.length / K3S_GRID_PAGE_SIZE)));
	const visiblePage = $derived(Math.min(page, pageCount - 1));
	const pageNodes = $derived(vmNodes.slice(visiblePage * K3S_GRID_PAGE_SIZE, (visiblePage + 1) * K3S_GRID_PAGE_SIZE));
	const pageKey = $derived(JSON.stringify(pageNodes.map(node => node.id)));
	const expandedSecurityGroup = $derived(k3sSecurityGroupNodeOf(selectedId));

	$effect(() => {
		if (mode !== 'grid' || !clusterId) return;
		void s.isActive;
		untrack(() => { void s.loadGridInventory(); });
		return () => s.stopGridReads();
	});
	$effect(() => {
		if (mode !== 'grid' || !clusterId) return;
		void pageKey;
		void s.isActive;
		untrack(() => { void s.loadGridNodes(pageNodes.map(node => node.id)); });
	});

	const unknown = $derived(t('grid.unknown'));
	const numberFormat = $derived(new Intl.NumberFormat(intlLocale(), { maximumSignificantDigits: 3 }));
	const dateFormat = $derived(new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }));
	const volumeLabels = $derived({ boot: t('grid.boot'), csi: t('grid.csi'), attached: t('grid.attached') });
	function rateLabel(traffic: K3sGridTraffic) {
		return t('grid.rate', {
			rx: traffic.rx ? numberFormat.format(traffic.rx.value) : unknown,
			tx: traffic.tx ? numberFormat.format(traffic.tx.value) : unknown,
		});
	}
	const grid = $derived(mode === 'grid' && s.cluster ? buildK3sIsoScene({
		cluster: s.cluster,
		nodes: pageNodes,
		nodeData: s.gridNodeData,
		networks: s.gridNetworks,
		floating: s.gridFloating,
		services: s.gridServices,
		expandedSecurityGroup,
		labels: { server: t('grid.controlPlane'), agent: t('grid.worker'), api: t('grid.api'), services: t('grid.services'),
			volume: volumeLabels, csiShare: t('grid.csi'), rate: rateLabel,
			ruleCount: count => ti('network.iso.rulesCount', { count }),
			moreSources: count => ti('network.iso.moreSources', { count }),
			missingGroup: ti('network.iso.groupMissing'),
			ingress: ti('securityGroupUnion.direction.ingress'), egress: ti('securityGroupUnion.direction.egress') },
	}) : null);
	const detail = $derived(selectedId ? grid?.details.get(selectedId) : undefined);

	type Port = NonNullable<Extract<K3sIsoDetail, { kind: 'vm' }>['ports']>[number];
</script>

{#snippet field(label: string, value: string | number | null | undefined)}
	<div><dt>{label}</dt><dd class="break-all text-ink-1">{value ?? unknown}</dd></div>
{/snippet}

{#snippet ruleList(rows: SecurityGroupUnionRow[] | null)}
	{#if rows}
		<ul class="space-y-1">
			{#each rows as rule (rule.key)}
				<li class="break-words">{rule.direction === 'ingress' ? ti('securityGroupUnion.direction.ingress') : rule.direction === 'egress' ? ti('securityGroupUnion.direction.egress') : rule.direction} · {rule.ethertype} · {rule.protocolLabel} · {rule.portLabel} · {rule.remoteLabel}</li>
			{:else}
				<li>{ti('network.noRules')}</li>
			{/each}
		</ul>
	{:else}
		<p>{unknown}</p>
	{/if}
{/snippet}

{#snippet portInfo(port: Port)}
	<dl class="grid gap-2 sm:grid-cols-2">
		{@render field(t('overview.info.id'), port.id)}
		{@render field(t('networks.network'), port.networkId)}
		{@render field(t('grid.fixedIps'), port.fixedIps.join(', ') || null)}
		{@render field(t('grid.floatingIps'), port.floating?.map(ip => ip.floating_ip_address).join(', ') || (port.floating ? t('grid.none') : null))}
		{#if port.status}<div><dt>{tc('table.status')}</dt><dd><StatusChip status={port.status} /></dd></div>{/if}
		{#if port.primary}<div><dt>{t('networks.port')}</dt><dd>{t('networks.primary')}</dd></div>{/if}
	</dl>
	<p class="mt-2 font-medium text-ink-1">{t('grid.securityGroups')}</p>
	{#if port.groups}
		<ul class="space-y-1">
			{#each port.groups as group (group.id)}
				<li><details class="mt-1">
					<summary class="cursor-pointer break-all">{group.name}</summary>
					<div class="ml-4 mt-1">{@render ruleList(group.rules)}</div>
				</details></li>
			{:else}
				<li>{t('grid.none')}</li>
			{/each}
		</ul>
	{:else}
		<p>{unknown}</p>
	{/if}
{/snippet}

{#snippet serviceInfo(item: ServiceInfo)}
	<dl class="grid gap-2 sm:grid-cols-2">
		{@render field(t('services.type'), item.type)}
		{@render field(t('services.clusterIp'), item.cluster_ip)}
		{@render field(t('grid.externalIps'), item.external_ips.join(', ') || t('grid.none'))}
	</dl>
	<p class="mt-2 font-medium text-ink-1">{t('services.ports')}</p>
	<ul class="space-y-1">
		{#each item.ports as port}
			<li class="break-words">{port.name ? `${port.name} · ` : ''}{t('grid.servicePort', { port: port.port, protocol: port.protocol, target: port.target_port ?? unknown })}{port.node_port != null ? ` · ${t('grid.nodePort', { port: port.node_port })}` : ''}</li>
		{:else}<li>{t('grid.none')}</li>{/each}
	</ul>
{/snippet}

{#snippet measurement(label: string, rate: K3sGridRate | null | undefined)}
	{@render field(label, rate && t('grid.sample', { value: numberFormat.format(rate.value), time: dateFormat.format(rate.ts * 1000) }))}
{/snippet}

<section aria-labelledby={heading} class="mb-3 min-w-0 rounded-lg border border-line bg-surface-base p-4">
	<div class="flex flex-wrap items-center justify-between gap-2">
		<h2 id={heading} class="text-sm font-semibold text-ink-1">{t('grid.title')}</h2>
		<div class="flex flex-wrap items-center gap-2">
			{#if mode === 'grid'}
				<Button variant="secondary" size="sm" disabled={s.gridLoading} onclick={() => {
					void s.loadGridInventory(true);
					void s.loadGridNodes(pageNodes.map(node => node.id), true);
				}}>{t('grid.refresh')}</Button>
			{/if}
			<IsoViewToggle value={mode} onchange={value => { mode = value; selectedId = null; }} storageKey="drover.cluster.view" />
		</div>
	</div>

	{#if grid}
		{#if pageCount > 1}
			<div class="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-2">
				<Button variant="secondary" size="sm" disabled={visiblePage === 0} onclick={() => { page = visiblePage - 1; selectedId = null; }}>{t('grid.previous')}</Button>
				<span>{t('grid.page', { page: visiblePage + 1, total: pageCount })}</span>
				<Button variant="secondary" size="sm" disabled={visiblePage >= pageCount - 1} onclick={() => { page = visiblePage + 1; selectedId = null; }}>{t('grid.next')}</Button>
			</div>
		{/if}
		<div class="mt-3 min-w-0 @max-md/panel:-mx-2">
			<IsoGridView scene={grid.scene} label={t('grid.title')} caption={t('grid.caption')}
				height="clamp(19rem, 59dvh, 26rem)" fitKey={`${clusterId}:${visiblePage}`}
				selectedId={detail ? selectedId : null} onselect={id => { selectedId = id; }} onclear={() => { selectedId = null; }} />
		</div>
		<p class="mt-2 text-xs text-ink-2">{t('grid.storageNote')}</p>
		{#if s.gridLoading}
			<LoadingState variant="inline" label={t('grid.loading')} class="mt-2 text-xs" />
		{:else if s.gridNodegroups === null}
			<p class="mt-2 text-xs text-ink-2">{t('grid.nodegroupsUnknown')}</p>
		{/if}
		{#if !vmNodes.length}<p class="mt-2 text-xs text-ink-2">{t('overview.vms.empty')}</p>{/if}
		{#if grid.hiddenResources > 0}<p class="mt-2 text-xs text-ink-2">{t('grid.moreInDetails')}</p>{/if}

		{#if detail}
			<section aria-labelledby={inspectorHeading} class="mt-4 min-w-0 space-y-2 border-t border-line pt-3 text-xs text-ink-2">
				<h3 id={inspectorHeading} class="break-words text-sm font-semibold text-ink-1">{detail.label}</h3>
				{#if detail.kind === 'vm'}
					<dl class="grid gap-2 sm:grid-cols-2">
						{@render field(t('overview.info.id'), detail.vm.id)}
						{@render field(tc('table.type'), detail.vm.role === 'server' ? t('grid.controlPlane') : t('grid.worker'))}
						{@render measurement(t('grid.rx'), detail.traffic?.rx)}
						{@render measurement(t('grid.tx'), detail.traffic?.tx)}
					</dl>
					<h4 class="font-medium text-ink-1">{t('networks.title')}</h4>
					{#each detail.ports ?? [] as port (port.id)}
						<details>
							<summary class="cursor-pointer break-all">{port.fixedIps.join(', ') || port.id}</summary>
							<div class="ml-4 mt-2">{@render portInfo(port)}</div>
						</details>
					{:else}<p>{detail.ports ? t('networks.noInterfaces') : unknown}</p>{/each}
					<h4 class="font-medium text-ink-1">{t('grid.volumes')}</h4>
					<ul class="space-y-1">
						{#each detail.volumes ?? [] as { item, classification } (item.volume_id)}
							<li class="break-words">{item.name || item.volume_id} · {volumeLabels[classification]}{item.device ? ` · ${item.device}` : ''}{item.size != null ? ` · ${t('grid.volumeSize', { size: item.size })}` : ''}</li>
						{:else}<li>{detail.volumes ? t('grid.none') : unknown}</li>{/each}
					</ul>
					<h4 class="font-medium text-ink-1">{t('grid.shares')}</h4>
					<ul class="space-y-1">
						{#each detail.shares ?? [] as { item, csiHint } (item.file_storage_id)}
							<li class="break-words">{[item.name || item.file_storage_id, item.share_proto, item.association_state, csiHint ? t('grid.csi') : null].filter(Boolean).join(' · ')}</li>
						{:else}<li>{detail.shares ? t('grid.none') : unknown}</li>{/each}
					</ul>
					<Button variant="link" size="xs" onclick={() => { if (detail?.kind === 'vm') s.setViewingInstance(detail.vm.id); }}>{t('overview.vms.viewInstance')}</Button>
				{:else if detail.kind === 'port'}
					<p class="break-words">{detail.vm}{detail.network ? ` · ${detail.network}` : ''}</p>
					{@render portInfo(detail.port)}
				{:else if detail.kind === 'group'}
					<dl class="grid gap-2 sm:grid-cols-2">
						{@render field(t('overview.info.id'), detail.group.id)}
						{@render field(t('networks.port'), detail.portId)}
					</dl>
					{@render ruleList(detail.group.rules)}
				{:else if detail.kind === 'rules'}
					{@render ruleList(detail.rules)}
				{:else if detail.kind === 'network'}
					<dl>{@render field(t('overview.info.id'), detail.id)}</dl>
					<ul class="space-y-1">
						{#each detail.members as { vm, vmLabel, port } (`${vm.id}:${port.id}`)}
							<li class="break-words">{vmLabel} · {port.id}{port.fixedIps.length ? ` · ${port.fixedIps.join(', ')}` : ''}</li>
						{/each}
					</ul>
				{:else if detail.kind === 'floating'}
					<dl class="grid gap-2 sm:grid-cols-2">
						{@render field(t('grid.fixedIps'), detail.item.fixed_ip_address)}
						{@render field(t('networks.port'), detail.item.port_id)}
						<div><dt>{tc('table.status')}</dt><dd><StatusChip status={detail.item.status} /></dd></div>
					</dl>
				{:else if detail.kind === 'api'}
					<dl class="grid gap-2 sm:grid-cols-2">
						{@render field(t('grid.api'), detail.address)}
						{@render field(t('grid.serverIp'), detail.serverIp)}
					</dl>
					{#if !detail.matchesPort}<p>{t('grid.apiNoMatch')}</p>{/if}
				{:else if detail.kind === 'volume'}
					<dl class="grid gap-2 sm:grid-cols-2">
						{@render field(t('overview.info.id'), detail.volume.item.volume_id)}
						{@render field(t('grid.vm'), detail.vm)}
						{@render field(tc('table.type'), volumeLabels[detail.volume.classification])}
						{@render field(t('grid.device'), detail.volume.item.device)}
						{@render field(t('grid.size'), detail.volume.item.size != null ? t('grid.volumeSize', { size: detail.volume.item.size }) : null)}
						{@render field(tc('table.status'), detail.volume.item.status)}
					</dl>
				{:else if detail.kind === 'share'}
					<dl class="grid gap-2 sm:grid-cols-2">
						{@render field(t('overview.info.id'), detail.share.item.file_storage_id)}
						{@render field(t('grid.vm'), detail.vm)}
						{@render field(t('grid.protocol'), detail.share.item.share_proto)}
						{@render field(t('grid.association'), detail.share.item.association_state)}
						{@render field(tc('table.status'), detail.share.item.status)}
						{@render field(t('grid.exports'), detail.share.item.exports?.join(', ') || null)}
					</dl>
				{:else if detail.kind === 'service'}
					{@render serviceInfo(detail.item)}
				{:else if detail.kind === 'services'}
					{#if detail.catalog}
						{#if detail.catalog.failedNamespaces.length}
							<p class="break-words">{t('grid.servicesPartial', { namespaces: detail.catalog.failedNamespaces.join(', ') })}</p>
						{/if}
						{#each detail.catalog.items as item (`${item.namespace}/${item.name}`)}
							<details>
								<summary class="cursor-pointer break-all">{item.namespace}/{item.name} · {item.type}</summary>
								<div class="ml-4 mt-2">{@render serviceInfo(item)}</div>
							</details>
						{:else}<p>{detail.catalog.failedNamespaces.length ? unknown : t('services.empty')}</p>{/each}
					{:else}<p>{unknown}</p>{/if}
				{/if}
			</section>
		{/if}
	{/if}
</section>

{#if mode === 'list'}{@render list()}{/if}
