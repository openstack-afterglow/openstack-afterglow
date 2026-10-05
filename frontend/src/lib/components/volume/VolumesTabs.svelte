<script lang="ts">
	import { t } from '$lib/i18n/ns/volume';
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
		{ value: 'volumes', label: t('tabs.volumes', { count: volumeCount }), panelId: 'volume-resource-panel' },
		...(showSnapshots
			? [{ value: 'snapshots', label: t('tabs.snapshots', { count: snapshotCount }), panelId: 'snapshot-resource-panel' }]
			: []),
	]}
	onchange={(next) => { tab = next as typeof tab; }}
	ariaLabel={t('tabs.resources')}
/>
