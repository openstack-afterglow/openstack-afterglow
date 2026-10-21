<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
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

<div class="motion-enter border-t border-line-2">
	{#if rules.length === 0}
		<p class="text-xs text-ink-2 px-4 py-3 italic">{t('securityGroup.rules.empty')}</p>
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each rules as rule (rule.id)}
					<CompactResourceCard>
						<p class="font-medium">{rule.direction === 'ingress' ? t('securityGroup.rules.inbound') : t('securityGroup.rules.outbound')} · {rule.protocol?.toUpperCase() ?? t('securityGroup.rules.anyProtocol')}</p>
						<dl><div><dt>{t('securityGroup.rules.port')}</dt><dd>{rule.port_range_min != null && rule.port_range_max != null ? rule.port_range_min === rule.port_range_max ? rule.port_range_min : `${rule.port_range_min}-${rule.port_range_max}` : '-'}</dd></div><div><dt>{t('securityGroup.rules.remoteIp')}</dt><dd>{rule.remote_ip_prefix ?? '-'}</dd></div></dl>
						{#snippet actions()}<button class="text-state-danger-text" onclick={() => onDelete(rule.id)}>{t('network.actions.delete')}</button>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<table class="w-full text-xs">
			<thead>
				<tr class="text-ink-2 uppercase tracking-wide border-b border-line-2/50">
					<th class="text-left px-4 py-2">{t('securityGroup.rules.direction')}</th>
					<th class="text-left px-4 py-2">{t('securityGroup.rules.protocol')}</th>
					<th class="text-left px-4 py-2">{t('securityGroup.rules.port')}</th>
					<th class="text-left px-4 py-2">{t('securityGroup.rules.remoteIp')}</th>
					<th class="text-right px-4 py-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each rules as rule (rule.id)}
					<tr class="border-b border-line/50 hover:bg-surface-sunken/30">
						<td class="px-4 py-2 text-ink-2">{rule.direction === 'ingress' ? t('securityGroup.rules.inbound') : t('securityGroup.rules.outbound')}</td>
						<td class="px-4 py-2 text-ink-2 font-mono">{rule.protocol?.toUpperCase() ?? t('securityGroup.rules.anyProtocol')}</td>
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
		</ResponsiveTable>
	{/if}
</div>
