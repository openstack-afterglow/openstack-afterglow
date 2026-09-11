<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatNumber, formatStorage } from '$lib/utils/format';
	import type { GpuDevice } from '$lib/types/gpu';

	export interface HypervisorDetail {
		id: string;
		hypervisor_hostname: string;
		state: string;
		status: string;
		hypervisor_type: string;
		hypervisor_version: number;
		host_ip: string;
		host_time: string;
		uptime: string;
		service_host: string;
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

	let {
		detail,
		loading,
		projectNameMap,
		gpus = [],
		onClose,
		onMigrate,
		onOpenDetail,
	}: {
		detail: HypervisorDetail | null;
		loading: boolean;
		projectNameMap: Map<string, string>;
		gpus?: GpuDevice[];
		onClose: () => void;
		onMigrate: (serverId: string, serverName: string, type: 'live' | 'cold') => void;
		onOpenDetail: (serverId: string, projectId: string) => void;
	} = $props();
</script>

<div class="w-96 border-l border-line bg-surface-canvas flex flex-col overflow-hidden flex-shrink-0">
	<div class="flex items-center justify-between px-4 py-3 border-b border-line">
		<h2 class="text-sm font-semibold text-ink-0 truncate">{detail?.hypervisor_hostname ?? '로딩 중...'}</h2>
		<button onclick={onClose} class="text-ink-2 hover:text-ink-0 text-lg leading-none">×</button>
	</div>

	{#if loading}
		<div class="p-4"><LoadingSkeleton variant="table" rows={4} /></div>
	{:else if detail}
		<div class="flex-1 overflow-y-auto p-4 space-y-4">
			<!-- 기본 정보 -->
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">기본 정보</h3>
				<dl class="space-y-2 text-xs">
					<div class="flex justify-between">
						<dt class="text-ink-2">상태</dt>
						<dd class="{detail.state === 'up' && detail.status === 'enabled' ? 'text-green-400' : 'text-red-400'}">{detail.state}/{detail.status}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">호스트 IP</dt>
						<dd class="text-ink-2 font-mono">{detail.host_ip || '-'}</dd>
					</div>
					{#if detail.host_time}
					<div class="flex justify-between">
						<dt class="text-ink-2">호스트 시간</dt>
						<dd class="text-ink-2 font-mono">{detail.host_time}</dd>
					</div>
					{/if}
					{#if detail.uptime}
					<div class="flex justify-between gap-4">
						<dt class="text-ink-2 flex-shrink-0">업타임</dt>
						<dd class="text-ink-2 text-right text-xs leading-relaxed break-all">{detail.uptime}</dd>
					</div>
					{/if}
					<div class="flex justify-between">
						<dt class="text-ink-2">타입</dt>
						<dd class="text-ink-2">{detail.hypervisor_type}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">버전</dt>
						<dd class="text-ink-2">{detail.hypervisor_version}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">서비스 호스트</dt>
						<dd class="text-ink-2 font-mono">{detail.service_host || '-'}</dd>
					</div>
					{#if detail.cpu_model}
					<div class="flex justify-between">
						<dt class="text-ink-2">CPU 모델</dt>
						<dd class="text-ink-2 font-mono text-right">{detail.cpu_model}</dd>
					</div>
					{/if}
				</dl>
			</div>

			<!-- 리소스 현황 -->
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">리소스 현황</h3>
				<dl class="space-y-2 text-xs">
					<div class="flex justify-between">
						<dt class="text-ink-2">vCPU</dt>
						<dd class="text-ink-2">{detail.vcpus_used} / {detail.vcpus_allowed || detail.vcpus} <span class="text-ink-3 text-xs">(물리 {detail.vcpus})</span></dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">RAM</dt>
						<dd class="text-ink-2">{formatNumber(Math.round(detail.memory_mb_used/1024))} / {formatNumber(Math.round((detail.memory_allowed_mb || detail.memory_mb)/1024))} GB <span class="text-ink-3 text-xs">(물리 {formatNumber(Math.round(detail.memory_mb/1024))} GB)</span></dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">로컬 디스크</dt>
						<dd class="text-ink-2">{formatStorage(detail.local_gb_used)} / {formatStorage(detail.local_gb)}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">실행 중 VM</dt>
						<dd class="text-ink-2">{detail.running_vms}</dd>
					</div>
				</dl>
			</div>

			<!-- GPU 장치 -->
			{#if gpus.length > 0}
				<div class="bg-surface-base border border-line rounded-xl p-4">
					<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">GPU 장치 ({gpus.length})</h3>
					<div class="space-y-1.5">
						{#each gpus as gpu (gpu.provider_uuid)}
							<div class="flex items-center justify-between bg-surface-sunken/50 border border-line-2/50 rounded-lg px-3 py-2">
								<div class="flex-1 min-w-0">
									<div class="text-xs text-ink-2">
										<span class="text-ink-2">{gpu.vendor_name}</span>
										{#if gpu.device_name}
											<span class="text-ink-2 ml-1">{gpu.device_name}</span>
										{:else if gpu.device_id}
											<span class="text-ink-3 ml-1">({gpu.device_id})</span>
										{/if}
									</div>
									<div class="text-xs text-ink-3 font-mono">{gpu.pci_address} · {gpu.resource_class}</div>
								</div>
								<span class="ml-2 px-1.5 py-0.5 rounded text-xs font-medium shrink-0 {gpu.used > 0 ? 'bg-red-900/30 text-red-400' : 'bg-green-900/30 text-green-400'}">
									{gpu.used > 0 ? '사용 중' : '사용 가능'}
								</span>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- VM 목록 -->
			{#if detail.servers.length > 0}
				<div class="bg-surface-base border border-line rounded-xl p-4">
					<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">VM 목록 ({detail.servers.length})</h3>
					<div class="space-y-1.5">
						{#each detail.servers as s}
							<div class="flex items-center justify-between py-1.5 border-b border-line/50 last:border-0">
								<div class="flex-1 min-w-0">
									<button
										type="button"
										onclick={() => onOpenDetail(s.id, s.project_id)}
										class="text-xs text-ink-2 hover:text-action-warm-hover transition-colors truncate block w-full text-left"
									>{s.name || s.id.slice(0, 12)}</button>
									<div class="text-xs text-ink-3">{projectNameMap.get(s.project_id) || s.project_id.slice(0, 8)} · {s.flavor}</div>
								</div>
								<div class="flex items-center gap-1 ml-2 flex-shrink-0">
									<span class="text-xs {s.status === 'ACTIVE' ? 'text-green-400' : s.status === 'ERROR' ? 'text-red-400' : 'text-ink-2'}">{s.status}</span>
									{#if s.status === 'ACTIVE'}
										<button onclick={() => onMigrate(s.id, s.name, 'live')} class="px-1.5 py-0.5 text-xs bg-cyan-900/30 hover:bg-cyan-900/60 text-cyan-400 rounded">이동</button>
									{:else if s.status === 'SHUTOFF'}
										<button onclick={() => onMigrate(s.id, s.name, 'cold')} class="px-1.5 py-0.5 text-xs bg-teal-900/30 hover:bg-teal-900/60 text-teal-400 rounded">이동</button>
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
