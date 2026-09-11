<script lang="ts">
	import type { TopologyLoadBalancer } from '$lib/types/topology';

	let {
		lb,
		onClose,
	}: {
		lb: TopologyLoadBalancer;
		onClose: () => void;
	} = $props();
</script>

<div class="p-6 space-y-5">
	<div class="flex items-start justify-between">
		<div>
			<h2 class="text-lg font-semibold text-ink-0">{lb.name || '로드밸런서'}</h2>
			<p class="text-xs text-ink-2 mt-0.5 font-mono">{lb.id}</p>
		</div>
		<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
	</div>
	<div class="grid grid-cols-2 gap-3 text-sm">
		<div class="bg-surface-sunken rounded-lg p-3">
			<p class="text-ink-2 text-xs mb-1">VIP 주소</p>
			<p class="text-ink-0 font-mono">{lb.vip_address ?? '-'}</p>
		</div>
		<div class="bg-surface-sunken rounded-lg p-3">
			<p class="text-ink-2 text-xs mb-1">프로비저닝 상태</p>
			<p class="font-medium" style="color:{lb.provisioning_status === 'ACTIVE' ? '#22c55e' : '#f59e0b'}">{lb.provisioning_status}</p>
		</div>
		<div class="bg-surface-sunken rounded-lg p-3">
			<p class="text-ink-2 text-xs mb-1">운영 상태</p>
			<p class="font-medium" style="color:{lb.operating_status === 'ONLINE' ? '#22c55e' : '#94a3b8'}">{lb.operating_status}</p>
		</div>
	</div>
	{#if lb.listeners.length > 0}
		<div>
			<h3 class="text-sm font-medium text-ink-2 mb-2">리스너</h3>
			<div class="space-y-1.5">
				{#each lb.listeners as li}
					<div class="bg-surface-sunken rounded-lg px-3 py-2 text-sm flex items-center gap-3">
						<span class="text-cyan-400 font-mono text-xs">{li.protocol}:{li.protocol_port}</span>
						<span class="text-ink-2 truncate">{li.name || li.id}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
	{#if lb.members.length > 0}
		<div>
			<h3 class="text-sm font-medium text-ink-2 mb-2">멤버 ({lb.members.length}개)</h3>
			<div class="space-y-1.5">
				{#each lb.members as m}
					<div class="bg-surface-sunken rounded-lg px-3 py-2 text-sm flex items-center gap-3">
						<span class="w-2 h-2 rounded-full flex-shrink-0" style="background:{m.status === 'ACTIVE' ? '#22c55e' : m.status === 'ERROR' ? '#ef4444' : '#64748b'}"></span>
						<span class="text-ink-0 font-mono text-xs">{m.address}:{m.protocol_port}</span>
						<span class="text-ink-3 text-xs">{m.status}</span>
						{#if !m.server_id}
							<span class="text-xs text-yellow-600">외부 호스트</span>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
