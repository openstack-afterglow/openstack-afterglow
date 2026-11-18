<script lang="ts">
	import { onMount } from 'svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import { t } from '$lib/i18n/ns/iso-view';
	import type { IsoViewMode } from './types';

	let { value = 'grid', onchange, storageKey }: {
		value?: IsoViewMode;
		onchange: (mode: IsoViewMode) => void;
		storageKey: string;
	} = $props();

	const options = $derived([
		{ value: 'grid', label: t('view.grid') },
		{ value: 'list', label: t('view.list') },
	]);

	onMount(() => {
		let saved: string | null = null;
		try { saved = localStorage.getItem(storageKey); } catch { /* Keep the host default. */ }
		if ((saved === 'grid' || saved === 'list') && saved !== value) onchange(saved);
	});

	function choose(mode: string) {
		if (mode !== 'grid' && mode !== 'list') return;
		try { localStorage.setItem(storageKey, mode); } catch { /* Keep the in-session choice. */ }
		onchange(mode);
	}
</script>

<ToggleGroup {value} {options} onchange={choose} ariaLabel={t('view.label')} />
