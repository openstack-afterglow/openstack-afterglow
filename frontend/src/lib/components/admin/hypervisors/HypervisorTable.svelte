<script lang="ts">
	import { formatNumber } from '$lib/utils/format';
	import HypervisorUsageBar from './HypervisorUsageBar.svelte';

	export interface HypervisorRow {
		id: string;
		name: string;
		state: string;
		status: string;
		vcpus: number;
		vcpus_used: number;
		vcpus_allowed: number;
		memory_size_mb: number;
		memory_used_mb: number;
		memory_allowed_mb: number;
		local_disk_gb: number;
		local_disk_used_gb: number;
		running_vms: number;
		gpu_total?: number;
		gpu_used?: number;
		gpu_model?: string | null;
		cpu_model?: string | null;
	}

	let {
		hypervisors,
		selectedId,
		sortColumn,
		sortAsc,
		onSort,
		onSelect,
	}: {
		hypervisors: HypervisorRow[];
		selectedId: string | null;
		sortColumn: string;
		sortAsc: boolean;
		onSort: (col: string) => void;
		onSelect: (id: string) => void;
	} = $props();

	function sortIcon(col: string): string {
		if (sortColumn !== col) return '↕';
		return sortAsc ? '↑' : '↓';
	}
</script>

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">
					<button onclick={() => onSort('name')} class="hover:text-ink-0 transition-colors flex items-center gap-1">
						호스트명 <span class="text-ink-3">{sortIcon('name')}</span>
					</button>
				</th>
				<th class="text-left py-2 pr-4">상태</th>
				<th class="text-left py-2 pr-4">
					<button onclick={() => onSort('running_vms')} class="hover:text-ink-0 transition-colors flex items-center gap-1">
						VM 수 <span class="text-ink-3">{sortIcon('running_vms')}</span>
					</button>
				</th>
				<th class="text-left py-2 pr-4 max-lg:hidden">
					<button onclick={() => onSort('cpu_model')} class="hover:text-ink-0 transition-colors flex items-center gap-1">
						CPU 모델 <span class="text-ink-3">{sortIcon('cpu_model')}</span>
					</button>
				</th>
				<th class="text-left py-2 pr-4">
					<button onclick={() => onSort('vcpus_used')} class="hover:text-ink-0 transition-colors flex items-center gap-1">
						vCPU <span class="text-ink-3">{sortIcon('vcpus_used')}</span>
					</button>
				</th>
				<th class="text-left py-2 pr-4">
					<button onclick={() => onSort('memory_used_mb')} class="hover:text-ink-0 transition-colors flex items-center gap-1">
						RAM (GB) <span class="text-ink-3">{sortIcon('memory_used_mb')}</span>
					</button>
				</th>
				<th class="text-left py-2 pr-4">
					<button onclick={() => onSort('gpu_model')} class="hover:text-ink-0 transition-colors flex items-center gap-1">
						GPU 모델 <span class="text-ink-3">{sortIcon('gpu_model')}</span>
					</button>
				</th>
				<th class="text-left py-2">
					<button onclick={() => onSort('gpu_used')} class="hover:text-ink-0 transition-colors flex items-center gap-1">
						GPU 수 <span class="text-ink-3">{sortIcon('gpu_used')}</span>
					</button>
				</th>
			</tr>
		</thead>
		<tbody>
			{#each hypervisors as h (h.id)}
				<tr
					class="border-b border-line/50 text-xs transition-colors {selectedId === h.id ? 'bg-surface-sunken/70' : ''}"
				>
					<td class="p-0">
						<button type="button" onclick={() => onSelect(h.id)} class="block w-full py-2 pr-4 font-mono text-ink-0 hover:text-action-warm-hover transition-colors text-left" title={h.name}>{h.name}</button>
					</td>
					<td class="py-2 pr-4">
						<span class="{h.state === 'up' && h.status === 'enabled' ? 'text-green-400' : 'text-red-400'}">{h.state}/{h.status}</span>
					</td>
					<td class="py-2 pr-4 text-ink-2">{formatNumber(h.running_vms)}</td>
					<td class="py-2 pr-4 text-ink-2 font-mono text-xs max-lg:hidden">{h.cpu_model ?? '-'}</td>
					<td class="py-2 pr-4">
						<HypervisorUsageBar
							used={h.vcpus_used}
							total={h.vcpus_allowed || h.vcpus}
							label="{formatNumber(h.vcpus_used)}/{formatNumber(h.vcpus_allowed || h.vcpus)}"
						/>
					</td>
					<td class="py-2 pr-4">
						<HypervisorUsageBar
							used={h.memory_used_mb}
							total={h.memory_allowed_mb || h.memory_size_mb}
							label="{formatNumber(Math.round(h.memory_used_mb/1024))}/{formatNumber(Math.round((h.memory_allowed_mb || h.memory_size_mb)/1024))}"
						/>
					</td>
					<td class="py-2 pr-4 text-xs {h.gpu_model ? 'text-ink-2 font-mono' : 'text-ink-3'}">{h.gpu_model ?? '-'}</td>
					<td class="py-2">
						{#if (h.gpu_total ?? 0) > 0}
							<HypervisorUsageBar
								used={h.gpu_used ?? 0}
								total={h.gpu_total ?? 0}
								label="{formatNumber(h.gpu_used ?? 0)}/{formatNumber(h.gpu_total ?? 0)}"
							/>
						{:else}
							<span class="text-ink-3">-</span>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
