<script lang="ts">
	import { useNetworkDetailController } from '$lib/stores/networkDetailController.svelte';

	const s = useNetworkDetailController();
</script>

{#if s.network!.subnet_details.length > 0}
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">서브넷 ({s.network!.subnet_details.length})</h3>
		<div class="space-y-3">
			{#each s.network!.subnet_details as subnet}
				<div class="border-b border-line/50 pb-2 last:border-0 last:pb-0">
					<div class="text-xs text-ink-0 font-medium">{subnet.name || subnet.id.slice(0, 8)}</div>
					<dl class="mt-1 space-y-1 text-xs">
						<div class="flex justify-between">
							<dt class="text-ink-3">CIDR</dt>
							<dd class="text-ink-2 font-mono">{subnet.cidr}</dd>
						</div>
						<div class="flex justify-between">
							<dt class="text-ink-3">게이트웨이</dt>
							<dd class="text-ink-2 font-mono">{subnet.gateway_ip || '-'}</dd>
						</div>
						<div class="flex justify-between">
							<dt class="text-ink-3">DHCP</dt>
							<dd class="{subnet.dhcp_enabled ? 'text-green-400' : 'text-ink-3'}">{subnet.dhcp_enabled ? '활성' : '비활성'}</dd>
						</div>
					</dl>
				</div>
			{/each}
		</div>
	</div>
{:else}
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-2">서브넷</h3>
		<p class="text-xs text-ink-3">서브넷이 없습니다</p>
	</div>
{/if}
