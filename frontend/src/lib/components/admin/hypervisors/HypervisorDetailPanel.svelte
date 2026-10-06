<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatNumber, formatStorage } from '$lib/utils/format';
	import type { GpuDevice } from '$lib/types/gpu';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t } from '$lib/i18n/ns/admin-compute';
	import RichText from '$lib/i18n/RichText.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import HypervisorRemovalReview from './HypervisorRemovalReview.svelte';
	import type { RemovalInspection, RemovalApproval, RemovalResult } from './removal';

	export interface HypervisorDetail {
		id: string;
		hypervisor_hostname: string;
		state: string;
		status: string;
		disabled_reason?: string | null;
		hypervisor_type: string;
		hypervisor_version: number;
		host_ip: string;
		host_time: string;
		uptime: string;
		uptime_observed_at?: string | null;
		service_host: string;
		service_id?: string;
		service_updated_at?: string | null;
		service_state?: string | null;
		forced_down?: boolean | null;
		vcpus: number;
		vcpus_used: number;
		vcpus_allowed: number;
		memory_mb: number;
		memory_mb_used: number;
		memory_allowed_mb: number;
		local_gb: number;
		local_gb_used: number;
		running_vms: number;
		cpu_info: string | null;
		cpu_model: string | null;
		servers: { id: string; name: string; status: string; project_id: string; flavor: string }[];
	}

	export interface HostRelocationItem {
		id: string;
		name: string;
		action: 'live-migrate' | 'cold-migrate' | 'evacuate' | null;
		outcome: 'requested' | 'failed' | 'skipped';
		detail?: string;
	}

	export interface HostRelocationResult {
		source_host: string;
		mode: 'migrate' | 'evacuate';
		items: HostRelocationItem[];
	}

	const OUTCOME_KEY = { requested: 'hypervisors.outcome.requested', failed: 'hypervisors.outcome.failed', skipped: 'hypervisors.outcome.skipped' } as const;
	const ACTION_KEY = {
		'live-migrate': 'hypervisors.action.liveMigrate',
		'cold-migrate': 'hypervisors.action.coldMigrate',
		evacuate: 'hypervisors.action.evacuate',
	} as const;
	function countOutcome(r: HostRelocationResult, outcome: HostRelocationItem['outcome']): number {
		return r.items.filter((item) => item.outcome === outcome).length;
	}

	let intent = $state<'enable' | 'disable' | 'migrate' | 'evacuate' | null>(null);
	let reason = $state('');
	let fenced = $state(false);
	function choose(next: typeof intent) {
		if (pending && next !== null) return;
		intent = next; reason = ''; fenced = false;
	}

	let {
		detail,
		loading,
		projectNameMap,
		gpus = [],
		onMigrate,
		onOpenDetail,
		pending = false,
		error = '',
		result = null,
		onSchedule,
		onRelocate,
		inspection = null,
		removalResult = null,
		approvalRevision = 0,
		invalidReason = '',
		detailError = '',
		onCheckRemoval,
		onRemove,
	}: {
		detail: HypervisorDetail | null;
		loading: boolean;
		projectNameMap: Map<string, string>;
		gpus?: GpuDevice[];
		onMigrate: (serverId: string, serverName: string, type: 'live' | 'cold') => void;
		onOpenDetail: (serverId: string, projectId: string) => void;
		pending?: boolean;
		error?: string;
		result?: HostRelocationResult | null;
		onSchedule: (enabled: boolean, reason?: string) => Promise<boolean>;
		onRelocate: (mode: 'migrate' | 'evacuate', fenced: boolean) => Promise<boolean>;
		inspection?: RemovalInspection | null;
		removalResult?: RemovalResult | null;
		approvalRevision?: number;
		invalidReason?: string;
		detailError?: string;
		onCheckRemoval: () => Promise<void>;
		onRemove: (approval: RemovalApproval) => Promise<void>;
	} = $props();

	async function submitIntent() {
		const current = intent;
		if (pending || current === null) return;
		const accepted = current === 'enable' || current === 'disable'
			? await onSchedule(current === 'enable', reason.trim())
			: await onRelocate(current, fenced);
		if (accepted) choose(null);
	}

	let lastOperationStatus: string | undefined;
	$effect(() => {
		const status = JSON.stringify([detail?.id, detail?.state, detail?.status, detail?.service_state, detail?.forced_down, detail?.running_vms, detail?.servers.map((server) => [server.id, server.status])]);
		if (lastOperationStatus !== undefined && status !== lastOperationStatus) choose(null);
		lastOperationStatus = status;
	});
</script>

<div class="w-full min-w-0 bg-surface-canvas flex flex-col">
	<div class="flex items-center justify-between px-4 py-3 border-b border-line">
		<h2 class="text-sm font-semibold text-ink-0 truncate">{detail?.hypervisor_hostname ?? (loading ? t('hypervisors.loading') : t('hypervisors.detail.title'))}</h2>
	</div>
	{#if detailError}<div class="p-4"><Alert tone="danger">{detailError} {t('hypervisors.detail.retryHelp')}</Alert></div>{/if}

	{#if loading}
		<div class="p-4"><LoadingSkeleton variant="table" rows={4} /></div>
	{:else if detail}
		<div class="min-w-0 p-4 space-y-4">
			<!-- 기본 정보 -->
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('hypervisors.detail.basicInfo')}</h3>
				<dl class="space-y-2 text-xs">
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.connection.label')}</dt>
						<dd class={detail.state === 'up' ? 'text-[var(--color-state-success-text)]' : 'text-[var(--color-state-danger-text)]'}>{t(detail.state === 'up' ? 'hypervisors.connection.up' : 'hypervisors.connection.down')}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.scheduling.label')}</dt>
						<dd class={detail.status === 'enabled' ? 'text-[var(--color-state-success-text)]' : 'text-[var(--color-state-warning-text)]'}>{t(detail.status === 'enabled' ? 'hypervisors.scheduling.enabled' : 'hypervisors.scheduling.disabled')}</dd>
					</div>
					{#if detail.status === 'disabled' && detail.disabled_reason}
					<div class="flex justify-between gap-4">
						<dt class="text-ink-2 flex-shrink-0">{t('hypervisors.detail.disabledReason')}</dt>
						<dd class="text-ink-2 text-right break-all">{detail.disabled_reason}</dd>
					</div>
					{/if}
					<div class="flex justify-between gap-4">
						<dt class="text-ink-2">{t('hypervisors.detail.serviceId')}</dt>
						<dd class="font-mono text-right break-all">{detail.service_id || t('hypervisors.detail.unavailable')}</dd>
					</div>
					<div class="flex justify-between gap-4">
						<dt class="text-ink-2">{t('hypervisors.detail.serviceUpdatedAt')}</dt>
						<dd class="text-right break-all">{detail.service_updated_at || t('hypervisors.detail.unavailable')}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.detail.hostIp')}</dt>
						<dd class="text-ink-2 font-mono">{detail.host_ip || '-'}</dd>
					</div>
					{#if detail.host_time}
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.detail.hostTime')}</dt>
						<dd class="text-ink-2 font-mono">{detail.host_time}</dd>
					</div>
					{/if}
					<div class="flex justify-between gap-4">
						<dt class="text-ink-2 flex-shrink-0">{t('hypervisors.detail.uptimeRaw')}</dt>
						<dd class="text-ink-2 text-right text-xs leading-relaxed break-all">{detail.uptime || t('hypervisors.detail.uptimeUnavailable')}</dd>
					</div>
					{#if detail.uptime && detail.uptime_observed_at}
					<div class="flex justify-between gap-4">
						<dt class="text-ink-2 flex-shrink-0">{t('hypervisors.detail.uptimeObservedAt')}</dt>
						<dd class="text-ink-2 text-right font-mono break-all">{detail.uptime_observed_at}</dd>
					</div>
					{/if}
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.detail.type')}</dt>
						<dd class="text-ink-2">{detail.hypervisor_type}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.detail.version')}</dt>
						<dd class="text-ink-2">{detail.hypervisor_version}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.detail.serviceHost')}</dt>
						<dd class="text-ink-2 font-mono">{detail.service_host || '-'}</dd>
					</div>
					{#if detail.cpu_model}
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.cpuModel')}</dt>
						<dd class="text-ink-2 font-mono text-right">{detail.cpu_model}</dd>
					</div>
					{/if}
				</dl>
			</div>

			<section class="bg-surface-base border border-line rounded-xl p-4 space-y-3" aria-label={t('hypervisors.operations.title')}>
				<h3 class="text-xs text-ink-2 uppercase tracking-wide">{t('hypervisors.operations.title')}</h3>
				<p class="text-xs text-ink-2">{t('hypervisors.operations.schedulingHelp')}</p>
				{#if detail.status === 'enabled'}
					<Button variant="secondary" size="sm" disabled={pending} onclick={() => choose('disable')}>{t('hypervisors.operations.disableScheduling')}</Button>
				{:else}
					<Button variant="secondary" size="sm" disabled={pending} onclick={() => choose('enable')}>{t('hypervisors.operations.enableScheduling')}</Button>
				{/if}
				{#if detail.servers.length > 0 && detail.state === 'up' && detail.status === 'disabled'}
					<Button variant="outline" size="sm" disabled={pending} onclick={() => choose('migrate')}>{t('hypervisors.operations.migrateAll')}</Button>
				{:else if detail.servers.length > 0 && detail.state === 'down'}
					<Button variant="danger-outline" size="sm" disabled={pending} onclick={() => choose('evacuate')}>{t('hypervisors.operations.evacuateAll')}</Button>
				{:else if detail.servers.length > 0 && detail.state === 'up'}
					<p class="text-xs text-ink-2">{t('hypervisors.operations.migrateHelp')}</p>
				{/if}
				{#if intent}
					<div class="border border-line rounded-lg p-3 space-y-3 text-xs" role="group" aria-label={t('hypervisors.operations.confirmLabel')}>
						{#if intent === 'disable'}
							<p>{t('hypervisors.operations.disableConfirm')}</p>
							<Field for="host-disable-reason" label={t('hypervisors.operations.requiredReason')} required>
								<TextInput id="host-disable-reason" bind:value={reason} disabled={pending} />
							</Field>
						{:else if intent === 'enable'}
							<p>{t('hypervisors.operations.enableConfirm')}</p>
						{:else if intent === 'migrate'}
							<p>{t('hypervisors.operations.migrateConfirm')}</p>
						{:else}
							<Alert tone="warning" title={t('hypervisors.operations.splitBrainTitle')}>{t('hypervisors.operations.splitBrainWarning')}</Alert>
							<p>{t('hypervisors.operations.evacuateHelp')}</p>
							<label class="flex gap-2 items-start"><input type="checkbox" bind:checked={fenced} disabled={pending} /> {t('hypervisors.operations.fencedConfirm')}</label>
						{/if}
						<div class="flex gap-2">
							<Button variant={intent === 'evacuate' ? 'danger' : 'accent'} size="sm" disabled={pending || (intent === 'disable' && !reason.trim()) || (intent === 'evacuate' && !fenced)} onclick={submitIntent}>{t(pending ? 'hypervisors.operations.requesting' : intent === 'enable' ? 'hypervisors.operations.confirmEnable' : intent === 'disable' ? 'hypervisors.operations.confirmDisable' : intent === 'migrate' ? 'hypervisors.operations.requestMigrate' : 'hypervisors.operations.requestEvacuate')}</Button>
							<Button variant="ghost" size="sm" disabled={pending} onclick={() => choose(null)}>{t('hypervisors.cancel')}</Button>
						</div>
					</div>
				{/if}
				{#if error}<Alert tone="danger">{error}</Alert>{/if}
				{#if result}
					<div role="status" aria-label={t('hypervisors.result.label')} class="text-xs space-y-2">
						<p>{t(result.mode === 'migrate' ? 'hypervisors.result.migrateSummary' : 'hypervisors.result.evacuateSummary', { host: result.source_host, requested: countOutcome(result, 'requested'), failed: countOutcome(result, 'failed'), skipped: countOutcome(result, 'skipped') })}</p>
						<p class="text-ink-2">{t('hypervisors.result.asyncHelp')}</p>
						<ul class="space-y-1">
							{#each result.items as item (item.id)}
								<li class={item.outcome === 'failed' ? 'text-[var(--color-state-danger-text)]' : item.outcome === 'skipped' ? 'text-ink-2' : 'text-ink-0'}>
									{t('hypervisors.result.item', { name: item.name || item.id, id: item.id, outcome: t(OUTCOME_KEY[item.outcome]), action: item.action ? 'present' : 'none', actionLabel: item.action ? t(ACTION_KEY[item.action]) : '', detail: item.detail ? 'present' : 'none', detailText: item.detail ?? '' })}
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			</section>

			<HypervisorRemovalReview
				{inspection}
				result={removalResult}
				{approvalRevision}
				{invalidReason}
				{pending}
				onCheck={onCheckRemoval}
				{onRemove}
			/>

			<!-- 리소스 현황 -->
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('hypervisors.detail.resources')}</h3>
				{#snippet physical(text: string)}<span class="text-ink-2 text-xs">{text}</span>{/snippet}
				<dl class="space-y-2 text-xs">
					<div class="flex justify-between">
						<dt class="text-ink-2">vCPU</dt>
						<dd class="text-ink-2"><RichText segments={t.rich('hypervisors.detail.vcpuUsage', { used: detail.vcpus_used, allowed: detail.vcpus_allowed || detail.vcpus, physical: detail.vcpus })} tags={{ physical }} /></dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.ram')}</dt>
						<dd class="text-ink-2"><RichText segments={t.rich('hypervisors.detail.ramUsage', { used: formatNumber(Math.round(detail.memory_mb_used/1024)), allowed: formatNumber(Math.round((detail.memory_allowed_mb || detail.memory_mb)/1024)), physical: formatNumber(Math.round(detail.memory_mb/1024)) })} tags={{ physical }} /></dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.detail.localDisk')}</dt>
						<dd class="text-ink-2">{formatStorage(detail.local_gb_used)} / {formatStorage(detail.local_gb)}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">{t('hypervisors.detail.runningVms')}</dt>
						<dd class="text-ink-2">{detail.running_vms}</dd>
					</div>
				</dl>
			</div>

			<!-- GPU 장치 -->
			{#if gpus.length > 0}
				<div class="bg-surface-base border border-line rounded-xl p-4">
					<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('hypervisors.detail.gpuDevices', { count: gpus.length })}</h3>
					<div class="space-y-1.5">
						{#each gpus as gpu (gpu.provider_uuid)}
							<div class="flex items-center justify-between bg-surface-sunken/50 border border-line-2/50 rounded-lg px-3 py-2">
								<div class="flex-1 min-w-0">
									<div class="text-xs text-ink-2">
										<span class="text-ink-2">{gpu.vendor_name}</span>
										{#if gpu.device_name}
											<span class="text-ink-2 ml-1">{gpu.device_name}</span>
										{:else if gpu.device_id}
											<span class="text-ink-2 ml-1">({gpu.device_id})</span>
										{/if}
									</div>
									<div class="text-xs text-ink-2 font-mono">{gpu.pci_address} · {gpu.resource_class}</div>
								</div>
								<span class="ml-2 px-1.5 py-0.5 rounded text-xs font-medium shrink-0 {gpu.used > 0 ? 'bg-red-900/30 text-red-400' : 'bg-green-900/30 text-green-400'}">
									{t(gpu.used > 0 ? 'hypervisors.gpu.inUse' : 'hypervisors.gpu.available')}
								</span>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- VM 목록 -->
			{#if detail.servers.length > 0}
				<div class="bg-surface-base border border-line rounded-xl p-4">
					<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('hypervisors.detail.vmList', { count: detail.servers.length })}</h3>
					<div class="space-y-1.5">
						{#each detail.servers as s}
							<div class="flex items-center justify-between py-1.5 border-b border-line/50 last:border-0">
								<div class="flex-1 min-w-0">
									<button
										type="button"
										onclick={() => onOpenDetail(s.id, s.project_id)}
										class="text-xs text-ink-2 hover:text-warm-text-hover transition-colors truncate block w-full text-left"
									>{s.name || s.id.slice(0, 12)}</button>
									<div class="text-xs text-ink-2">{projectNameMap.get(s.project_id) || s.project_id.slice(0, 8)} · {s.flavor}</div>
								</div>
								<div class="flex items-center gap-1 ml-2 flex-shrink-0">
									<StatusChip status={s.status} />
									{#if s.status === 'ACTIVE'}
										<Button variant="outline" size="sm" disabled={pending} onclick={() => onMigrate(s.id, s.name, 'live')}>{t('hypervisors.detail.move')}</Button>
									{:else if s.status === 'SHUTOFF'}
										<Button variant="outline" size="sm" disabled={pending} onclick={() => onMigrate(s.id, s.name, 'cold')}>{t('hypervisors.detail.move')}</Button>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>
