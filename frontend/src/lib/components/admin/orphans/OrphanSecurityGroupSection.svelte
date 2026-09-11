<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanSecurityGroupInfo } from '$lib/types/orphan';

	let {
		items,
		selected = $bindable(new Set<string>()),
		onCleanup,
	}: {
		items: OrphanSecurityGroupInfo[];
		selected: Set<string>;
		onCleanup: () => void;
	} = $props();
</script>

<OrphanSection
	title="고아 Security Group"
	{items}
	bind:selected
	emptyMessage="afterglow-managed marker가 있는 미부착 SG 없음."
	{onCleanup}
>
	{#snippet headerNote()}
		<div class="text-xs text-ink-3 mb-2">
			※ description에 <code class="text-ink-2">[afterglow-managed]</code> 마커가 있고 어떤 port에도 attach되지 않은 SG만 후보.
		</div>
	{/snippet}
	{#snippet headers()}
		<th class="text-left py-2 pr-4">이름</th>
		<th class="text-left py-2 pr-4">설명</th>
		<th class="text-left py-2 pr-4">프로젝트</th>
		<th class="text-left py-2 pr-4">생성일</th>
		<th class="text-left py-2 pr-4">연령(일)</th>
		<th class="text-left py-2 pr-4">ID</th>
	{/snippet}
	{#snippet row(g)}
		<td class="py-2 pr-4 text-ink-1">{g.name}</td>
		<td class="py-2 pr-4 text-ink-2 max-w-md truncate" title={g.description ?? ''}>{g.description ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{g.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{g.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-action-warm">{g.age_days}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{g.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
