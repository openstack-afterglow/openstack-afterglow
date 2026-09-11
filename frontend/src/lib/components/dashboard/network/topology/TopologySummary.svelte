<script lang="ts">
	let {
		visibleNetworkCount,
		projectRouterCount,
		instanceCount,
		projectFipCount,
		projectLbCount,
	}: {
		visibleNetworkCount: number;
		projectRouterCount: number;
		instanceCount: number;
		projectFipCount: number;
		projectLbCount: number;
	} = $props();
</script>

<div class="mt-4 flex gap-6 text-xs text-ink-3 px-1">
	<span>네트워크 {visibleNetworkCount}개</span>
	<span>라우터 {projectRouterCount}개</span>
	<span>인스턴스 {instanceCount}개</span>
	<span>Floating IP {projectFipCount}개</span>
	<span>로드밸런서 {projectLbCount}개</span>
</div>
