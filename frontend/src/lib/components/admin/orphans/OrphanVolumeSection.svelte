<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanVolumeInfo } from '$lib/types/orphan';

	let {
		items,
		selected = $bindable(new Set<string>()),
		minAgeDays,
		onCleanup,
	}: {
		items: OrphanVolumeInfo[];
		selected: Set<string>;
		minAgeDays: number;
		onCleanup: () => void;
	} = $props();

	const emptyMessage = $derived(`임계치(${minAgeDays}일) 이상의 장기 미사용 volume 없음.`);
</script>

<OrphanSection
	title="장기 미사용 Volumes"
	{items}
	bind:selected
	{emptyMessage}
	{onCleanup}
>
	{#snippet headers()}
		<th class="text-left py-2 pr-4">이름</th>
		<th class="text-left py-2 pr-4">크기(GB)</th>
		<th class="text-left py-2 pr-4">상태</th>
		<th class="text-left py-2 pr-4">프로젝트</th>
		<th class="text-left py-2 pr-4">생성일</th>
		<th class="text-left py-2 pr-4">연령(일)</th>
		<th class="text-left py-2 pr-4">ID</th>
	{/snippet}
	{#snippet row(v)}
		<td class="py-2 pr-4 text-ink-1">{v.name ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{v.size_gb}</td>
		<td class="py-2 pr-4 text-green-400">{v.status}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{v.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{v.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-action-warm">{v.age_days}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{v.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
