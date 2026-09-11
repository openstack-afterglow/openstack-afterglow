<script lang="ts">
	import Tabs from '../Tabs.svelte';

	let value = $state('overview');
	const items = [
		{ value: 'overview', label: '개요', panelId: 'overview-panel' },
		{ value: 'disabled', label: '사용 불가', panelId: 'disabled-panel', disabled: true },
		{ value: 'activity', label: '활동', panelId: 'activity-panel' },
	];
</script>

<Tabs id="project-tabs" {value} {items} onchange={(next) => { value = next; }} ariaLabel="프로젝트 상세" />

{#if value === 'overview'}
	<div id="overview-panel" role="tabpanel" aria-labelledby="project-tabs-overview" tabindex="0">개요 패널</div>
{:else if value === 'activity'}
	<div id="activity-panel" role="tabpanel" aria-labelledby="project-tabs-activity" tabindex="0">활동 패널</div>
{/if}
