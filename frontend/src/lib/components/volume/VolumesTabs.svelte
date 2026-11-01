<script lang="ts">
	import { t } from '$lib/i18n/ns/volume';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	let {
		tab = $bindable<'volumes' | 'snapshots'>(),
		volumeCount,
		snapshotCount,
		showSnapshots = true,
		onChange,
	}: {
		tab: 'volumes' | 'snapshots';
		volumeCount: number | null;
		snapshotCount: number | null;
		showSnapshots?: boolean;
		onChange?: (tab: 'volumes' | 'snapshots') => void;
	} = $props();
</script>

<Tabs
	id="volume-resource-tabs"
	value={tab}
	items={[
		{ value: 'volumes', label: volumeCount === null ? t('tabs.volumesUnknown') : t('tabs.volumes', { count: volumeCount }), panelId: 'volume-resource-panel' },
		...(showSnapshots
			? [{ value: 'snapshots', label: snapshotCount === null ? t('tabs.snapshotsUnknown') : t('tabs.snapshots', { count: snapshotCount }), panelId: 'snapshot-resource-panel' }]
			: []),
	]}
	onchange={(next) => { if (onChange) onChange(next as typeof tab); else tab = next as typeof tab; }}
	ariaLabel={t('tabs.resources')}
/>
