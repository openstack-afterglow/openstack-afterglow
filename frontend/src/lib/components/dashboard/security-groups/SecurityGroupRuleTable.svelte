<script lang="ts">
	interface SecurityGroupRule {
		id: string;
		direction: string;
		protocol: string | null;
		port_range_min: number | null;
		port_range_max: number | null;
		remote_ip_prefix: string | null;
		ethertype: string;
	}

	let {
		rules,
		onDelete,
	}: {
		rules: SecurityGroupRule[];
		onDelete: (ruleId: string) => Promise<void>;
	} = $props();
</script>

<div class="border-t border-line-2">
	{#if rules.length === 0}
		<p class="text-xs text-ink-3 px-4 py-3 italic">규칙 없음</p>
	{:else}
		<table class="w-full text-xs">
			<thead>
				<tr class="text-ink-3 uppercase tracking-wide border-b border-line-2/50">
					<th class="text-left px-4 py-2">방향</th>
					<th class="text-left px-4 py-2">프로토콜</th>
					<th class="text-left px-4 py-2">포트</th>
					<th class="text-left px-4 py-2">원격 IP</th>
					<th class="text-right px-4 py-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each rules as rule (rule.id)}
					<tr class="border-b border-line/50 hover:bg-surface-sunken/30">
						<td class="px-4 py-2 text-ink-2">{rule.direction === 'ingress' ? '인바운드' : '아웃바운드'}</td>
						<td class="px-4 py-2 text-ink-2 font-mono">{rule.protocol?.toUpperCase() ?? 'ANY'}</td>
						<td class="px-4 py-2 text-ink-2 font-mono">
							{#if rule.port_range_min != null && rule.port_range_max != null}
								{rule.port_range_min === rule.port_range_max ? rule.port_range_min : `${rule.port_range_min}-${rule.port_range_max}`}
							{:else}-{/if}
						</td>
						<td class="px-4 py-2 text-ink-2 font-mono">{rule.remote_ip_prefix ?? '-'}</td>
						<td class="px-4 py-2 text-right">
							<button
								onclick={() => onDelete(rule.id)}
								class="text-red-400 hover:text-red-300 transition-colors"
							>✕</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>
