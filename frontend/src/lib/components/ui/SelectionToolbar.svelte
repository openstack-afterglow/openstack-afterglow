<script lang="ts">
	import SelectionCheckbox from './SelectionCheckbox.svelte';
	import { t } from '$lib/i18n/ns/common';

	interface Props {
		label: string;
		ariaLabel: string;
		checked: boolean;
		indeterminate: boolean;
		selectedCount: number;
		disabled?: boolean;
		onToggle: () => void;
	}

	let {
		label,
		ariaLabel,
		checked,
		indeterminate,
		selectedCount,
		disabled = false,
		onToggle,
	}: Props = $props();
</script>

<div class="selection-toolbar" role="group" aria-label={ariaLabel}>
	<SelectionCheckbox
		checked={checked}
		indeterminate={indeterminate}
		disabled={disabled}
		ariaLabel={t('selection.selectAllOf', { label })}
		onclick={(event) => {
			event.stopPropagation();
			onToggle();
		}}
	/>
	<span class="selection-toolbar-label">{t('selection.selectAll')}</span>
	<span class="selection-toolbar-count" aria-live="polite">{t('selection.count', { count: selectedCount })}</span>
</div>

<style>
	.selection-toolbar {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 2rem;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		font-weight: 700;
	}

	.selection-toolbar-label {
		white-space: nowrap;
	}

	.selection-toolbar-count {
		color: var(--color-ink-2);
		font-weight: 600;
		white-space: nowrap;
	}
</style>
