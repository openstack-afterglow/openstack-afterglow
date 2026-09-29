<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatNumber, formatStorage } from '$lib/utils/format';
	import type { GpuDevice } from '$lib/types/gpu';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';

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

	const OUTCOME_LABEL: Record<HostRelocationItem['outcome'], string> = { requested: '요청됨', failed: '실패', skipped: '건너뜀' };
	const ACTION_LABEL: Record<NonNullable<HostRelocationItem['action']>, string> = {
		'live-migrate': '라이브 마이그레이션',
		'cold-migrate': '콜드 마이그레이션',
		evacuate: '대피',
	};
	function countOutcome(r: HostRelocationResult, outcome: HostRelocationItem['outcome']): number {
		return r.items.filter((item) => item.outcome === outcome).length;
	}

	let intent = $state<'enable' | 'disable' | 'migrate' | 'evacuate' | null>(null);
	let reason = $state('');
	let fenced = $state(false);
	function choose(next: typeof intent) { intent = next; reason = ''; fenced = false; }

	let {
		detail,
		loading,
		projectNameMap,
		gpus = [],
		onClose,
		onMigrate,
		onOpenDetail,
		pending = false,
		error = '',
		result = null,
		onSchedule,
		onRelocate,
	}: {
		detail: HypervisorDetail | null;
		loading: boolean;
		projectNameMap: Map<string, string>;
		gpus?: GpuDevice[];
		onClose: () => void;
		onMigrate: (serverId: string, serverName: string, type: 'live' | 'cold') => void;
		onOpenDetail: (serverId: string, projectId: string) => void;
		pending?: boolean;
		error?: string;
		result?: HostRelocationResult | null;
		onSchedule: (enabled: boolean, reason?: string) => Promise<boolean>;
		onRelocate: (mode: 'migrate' | 'evacuate', fenced: boolean) => Promise<boolean>;
	} = $props();

	async function submitIntent() {
		const current = intent;
		if (pending || current === null) return;
		const accepted = current === 'enable' || current === 'disable'
			? await onSchedule(current === 'enable', reason.trim())
			: await onRelocate(current, fenced);
		if (accepted) choose(null);
	}
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
				<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">기본 정보</h3>
				<dl class="space-y-2 text-xs">
					<div class="flex justify-between">
						<dt class="text-ink-2">연결 상태</dt>
						<dd class={detail.state === 'up' ? 'text-[var(--color-state-success-text)]' : 'text-[var(--color-state-danger-text)]'}>{detail.state === 'up' ? '정상 (up)' : '중단 (down)'}</dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">스케줄링</dt>
						<dd class={detail.status === 'enabled' ? 'text-[var(--color-state-success-text)]' : 'text-[var(--color-state-warning-text)]'}>{detail.status === 'enabled' ? '허용 (enabled)' : '차단 (disabled)'}</dd>
					</div>
					{#if detail.status === 'disabled' && detail.disabled_reason}
					<div class="flex justify-between gap-4">
						<dt class="text-ink-2 flex-shrink-0">비활성화 사유</dt>
						<dd class="text-ink-2 text-right break-all">{detail.disabled_reason}</dd>
					</div>
					{/if}
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

			<section class="bg-surface-base border border-line rounded-xl p-4 space-y-3" aria-label="호스트 운영 작업">
				<h3 class="text-xs text-ink-2 uppercase tracking-wide">호스트 운영 작업</h3>
				<p class="text-xs text-ink-2">스케줄링 변경은 인스턴스를 이동시키지 않습니다.</p>
				{#if detail.status === 'enabled'}
					<Button variant="secondary" size="sm" disabled={pending} onclick={() => choose('disable')}>스케줄링 비활성화</Button>
				{:else}
					<Button variant="secondary" size="sm" disabled={pending} onclick={() => choose('enable')}>스케줄링 활성화</Button>
				{/if}
				{#if detail.servers.length > 0 && detail.state === 'up' && detail.status === 'disabled'}
					<Button variant="outline" size="sm" disabled={pending} onclick={() => choose('migrate')}>모든 인스턴스 마이그레이션</Button>
				{:else if detail.servers.length > 0 && detail.state === 'down'}
					<Button variant="danger-outline" size="sm" disabled={pending} onclick={() => choose('evacuate')}>모든 인스턴스 대피</Button>
				{:else if detail.servers.length > 0 && detail.state === 'up'}
					<p class="text-xs text-ink-2">전체 인스턴스 마이그레이션은 스케줄링을 비활성화한 뒤에만 요청할 수 있습니다.</p>
				{/if}
				{#if intent}
					<div class="border border-line rounded-lg p-3 space-y-3 text-xs" role="group" aria-label="호스트 작업 확인">
						{#if intent === 'disable'}
							<p>이 호스트에 새 인스턴스가 배치되지 않도록 스케줄링을 중지합니다. 기존 인스턴스는 이동하지 않습니다.</p>
							<label class="block text-ink-2" for="host-disable-reason">비활성화 사유 (필수)</label>
							<input id="host-disable-reason" class="w-full bg-surface-sunken border border-line rounded-md p-2 text-ink-0" bind:value={reason} disabled={pending} />
						{:else if intent === 'enable'}
							<p>스케줄링을 활성화하여 새 인스턴스의 배치를 다시 허용하시겠습니까? 호스트의 연결 상태는 별개입니다.</p>
						{:else if intent === 'migrate'}
							<p>이 호스트의 모든 인스턴스에 마이그레이션을 요청하시겠습니까? ACTIVE는 라이브, SHUTOFF는 콜드 마이그레이션을 요청하고 그 외 상태는 건너뜁니다. 목적지는 Nova 스케줄러가 선택하며, 각 요청은 비동기이고 완료를 보장하지 않습니다.</p>
						{:else}
							<Alert tone="warning" title="split-brain 위험">호스트가 down으로 표시되어도 실제로 정지된 것은 아닙니다. 원본 호스트가 전원 차단 또는 펜싱되지 않았다면 동일 인스턴스가 두 호스트에서 동시에 실행되어 디스크가 손상될 수 있습니다 (split-brain). 먼저 원본 호스트의 전원 차단 또는 펜싱을 직접 확인하세요.</Alert>
							<p>목적지는 Nova 스케줄러가 선택하며, 각 대피 요청은 비동기이고 완료를 보장하지 않습니다.</p>
							<label class="flex gap-2 items-start"><input type="checkbox" bind:checked={fenced} disabled={pending} /> 원본 호스트가 펜싱되어 실행되지 않음을 확인했습니다</label>
						{/if}
						<div class="flex gap-2">
							<Button variant={intent === 'evacuate' ? 'danger' : 'accent'} size="sm" disabled={pending || (intent === 'disable' && !reason.trim()) || (intent === 'evacuate' && !fenced)} onclick={submitIntent}>{pending ? '요청 중...' : intent === 'enable' ? '스케줄링 활성화 확인' : intent === 'disable' ? '스케줄링 비활성화 확인' : intent === 'migrate' ? '마이그레이션 요청' : '대피 요청'}</Button>
							<Button variant="ghost" size="sm" disabled={pending} onclick={() => choose(null)}>취소</Button>
						</div>
					</div>
				{/if}
				{#if error}<Alert tone="danger">{error}</Alert>{/if}
				{#if result}
					<div role="status" aria-label="호스트 이동 요청 결과" class="text-xs space-y-2">
						<p>{result.source_host} {result.mode === 'migrate' ? '마이그레이션' : '대피'} 요청 결과 · 요청 {countOutcome(result, 'requested')}건 · 실패 {countOutcome(result, 'failed')}건 · 건너뜀 {countOutcome(result, 'skipped')}건</p>
						<p class="text-ink-2">요청은 비동기입니다. '요청됨'은 Nova가 요청을 접수했다는 뜻이며 인스턴스 이동 완료를 의미하지 않습니다.</p>
						<ul class="space-y-1">
							{#each result.items as item (item.id)}
								<li class={item.outcome === 'failed' ? 'text-[var(--color-state-danger-text)]' : item.outcome === 'skipped' ? 'text-ink-2' : 'text-ink-0'}>
									{item.name || item.id} ({item.id}): {OUTCOME_LABEL[item.outcome]}{item.action ? ` · ${ACTION_LABEL[item.action]}` : ''}{item.detail ? ` · ${item.detail}` : ''}
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			</section>

			<!-- 리소스 현황 -->
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">리소스 현황</h3>
				<dl class="space-y-2 text-xs">
					<div class="flex justify-between">
						<dt class="text-ink-2">vCPU</dt>
						<dd class="text-ink-2">{detail.vcpus_used} / {detail.vcpus_allowed || detail.vcpus} <span class="text-ink-2 text-xs">(물리 {detail.vcpus})</span></dd>
					</div>
					<div class="flex justify-between">
						<dt class="text-ink-2">RAM</dt>
						<dd class="text-ink-2">{formatNumber(Math.round(detail.memory_mb_used/1024))} / {formatNumber(Math.round((detail.memory_allowed_mb || detail.memory_mb)/1024))} GB <span class="text-ink-2 text-xs">(물리 {formatNumber(Math.round(detail.memory_mb/1024))} GB)</span></dd>
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
					<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">GPU 장치 ({gpus.length})</h3>
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
					<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">VM 목록 ({detail.servers.length})</h3>
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
