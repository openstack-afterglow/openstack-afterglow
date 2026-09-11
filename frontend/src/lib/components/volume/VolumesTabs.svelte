<script lang="ts">
	import Tabs from '$lib/components/ui/Tabs.svelte';
	let {
		tab = $bindable<'volumes' | 'snapshots'>(),
		volumeCount,
		snapshotCount,
		showSnapshots = true,
	}: {
		tab: 'volumes' | 'snapshots';
		volumeCount: number;
		snapshotCount: number;
		showSnapshots?: boolean;
	} = $props();
</script>

<Tabs
	id="volume-resource-tabs"
	value={tab}
	items={[
		{ value: 'volumes', label: `볼륨 ${volumeCount}`, panelId: 'volume-resource-panel' },
		...(showSnapshots
			? [{ value: 'snapshots', label: `스냅샷 ${snapshotCount}`, panelId: 'snapshot-resource-panel' }]
			: []),
	]}
	onchange={(next) => { tab = next as typeof tab; }}
	ariaLabel="볼륨 리소스"
/>
