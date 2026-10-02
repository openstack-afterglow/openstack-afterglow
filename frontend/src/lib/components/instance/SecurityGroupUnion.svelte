<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import { buildSecurityGroupUnion } from '$lib/utils/securityGroupUnion';
	import type { SecurityGroupUnionGroup, SecurityGroupUnionRow } from '$lib/utils/securityGroupUnion';

	interface Props {
		groupIds: readonly string[];
		groups: readonly SecurityGroupUnionGroup[];
		loading?: boolean;
		error?: string;
	}

	let { groupIds, groups, loading = false, error = '' }: Props = $props();
	let union = $derived(buildSecurityGroupUnion(groups, groupIds));
	let inbound = $derived(union.rows.filter((row) => row.direction === 'ingress'));
	let outbound = $derived(union.rows.filter((row) => row.direction === 'egress'));
	let inboundOpen = $state(false);
	let outboundOpen = $state(false);

	function toggleInbound() { inboundOpen = !inboundOpen; }
	function toggleOutbound() { outboundOpen = !outboundOpen; }
</script>

{#snippet directionTable(rows: SecurityGroupUnionRow[], label: string, remoteHeading: string, expanded: boolean, onToggle: () => void)}
	<div class="min-w-0 max-w-full space-y-2">
		<h4>
			<Button variant="ghost" size="sm" class="w-full min-h-11" ariaExpanded={expanded} ariaLabel="{label} 허용 규칙 {expanded ? '접기' : '펼치기'}" onclick={onToggle}>
				<span class="flex w-full items-center justify-between gap-2">
					<span class="text-ink-1">{label}</span>
					<span class="flex items-center gap-1 text-ink-2">
						<span>{expanded ? '접기' : '펼치기'}</span>
						<svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={expanded ? 'M19 15l-7-7-7 7' : 'M5 9l7 7 7-7'} />
						</svg>
					</span>
				</span>
			</Button>
		</h4>
		{#if expanded}
			<TableShell density="compact" class="min-w-0 max-w-full">
				<table aria-label="{label} 허용 규칙">
					<thead>
						<tr>
							<th scope="col">IP 버전</th>
							<th scope="col">프로토콜</th>
							<th scope="col">포트 / ICMP</th>
							<th scope="col">{remoteHeading}</th>
						</tr>
					</thead>
					<tbody>
						{#each rows as row (row.key)}
							<tr>
								<td>{row.ethertype}</td>
								<td>{row.protocolLabel}</td>
								<td>{row.portLabel}</td>
								<td title={row.remote.kind === 'group' ? row.remote.value : undefined}>{row.remoteLabel}</td>
							</tr>
						{:else}
							<tr><td colspan="4" class="text-ink-2">{label} 허용 규칙이 없습니다.</td></tr>
						{/each}
					</tbody>
				</table>
			</TableShell>
		{/if}
	</div>
{/snippet}

<section aria-label="적용된 허용 규칙" class="mt-3 min-w-0 max-w-full space-y-3">
	<h3 class="text-xs font-semibold text-ink-1">적용된 허용 규칙</h3>
	<p class="text-xs leading-relaxed text-ink-2 break-words">
		저장된 보안 그룹의 허용 규칙입니다. 실제 연결은 게스트 서비스, OS 방화벽, 라우팅에서도 허용되어야 합니다.
	</p>

	{#if loading}
		<p role="status" class="text-xs text-ink-2">보안 그룹 허용 규칙을 불러오는 중입니다.</p>
	{:else if error}
		<p role="alert" class="text-xs leading-relaxed text-state-danger-text break-words">
			보안 그룹 허용 규칙을 확인하지 못했습니다. {error} 적용된 허용 규칙 전체를 표시할 수 없습니다.
		</p>
	{:else if groupIds.length === 0}
		<p class="text-xs leading-relaxed text-ink-2">이 인터페이스에 적용된 보안 그룹이 없습니다.</p>
	{:else if union.missingGroupIds.length > 0}
		<div role="alert" class="min-w-0 space-y-1 text-xs leading-relaxed text-state-warning-text">
			<p>다음 보안 그룹을 조회할 수 없어 적용된 허용 규칙 전체를 표시할 수 없습니다.</p>
			<ul class="space-y-1">
				{#each union.missingGroupIds as id (id)}
					<li class="font-mono break-all">{id}</li>
				{/each}
			</ul>
		</div>
	{:else if union.rows.length === 0}
		<p class="text-xs leading-relaxed text-ink-2">적용된 보안 그룹에 허용 규칙이 없습니다.</p>
	{:else}
		{@render directionTable(inbound, '인바운드', '출발지', inboundOpen, toggleInbound)}
		{@render directionTable(outbound, '아웃바운드', '대상', outboundOpen, toggleOutbound)}
	{/if}
</section>
