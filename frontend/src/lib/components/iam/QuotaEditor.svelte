<script lang="ts">
	import { untrack } from 'svelte';
	import { quotaFields, nativeQuotaKey, type QuotaMap, type ProjectQuotas, type QuotaField, type QuotaSection } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	let { values, native = null, projectMode = false, disabled = false, onSave }: { values: QuotaMap; native?: ProjectQuotas | null; projectMode?: boolean; disabled?: boolean; onSave: (values: QuotaMap) => void } = $props();
	let draft = $state<Record<QuotaField, string>>(untrack(() => Object.fromEntries(Object.values(quotaFields).flat().map(field => [field, values[field] == null ? '' : String(values[field])])) as Record<QuotaField, string>));
	let error = $state('');
	const uid = $props.id();
	function save() {
		if (disabled) return;
		const next: QuotaMap = {};
		for (const [field, input] of Object.entries(draft)) {
			const text = input.trim();
			if (!text) continue;
			if (!/^(?:-1|0|[1-9]\d*)$/.test(text) || !Number.isSafeInteger(Number(text))) { error = t('invalidLimit'); return; }
			if (!projectMode || Number(text) !== values[field as QuotaField]) next[field as QuotaField] = Number(text);
		}
		if (projectMode && !Object.keys(next).length) { error = t('noChanges'); return; }
		error = ''; onSave(next);
	}
</script>

<div class="space-y-3">
	<p class="text-sm text-ink-2">{t(projectMode ? 'projectHelp' : 'policyHelp')}</p>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#each Object.entries(quotaFields) as [section, fields]}
		<section class="space-y-2">
			<h3 class="text-sm font-semibold text-ink-0">{t(`service.${section as QuotaSection}`)}</h3>
			{#if projectMode && !native?.availability[section as QuotaSection]}<Alert tone="warning">{native?.errors[section as QuotaSection] === 'service_disabled' ? t('disabledService') : t('unknownService')}</Alert>{/if}
			<TableShell><table><thead><tr><th>{t('metric')}</th><th>{t('limit')}</th>{#if projectMode}<th>{t('inUse')}</th><th>{t('reserved')}</th>{/if}</tr></thead><tbody>
				{#each fields as field}
					{@const entry = native?.[section as QuotaSection]?.[nativeQuotaKey(field)]}
					<tr><td><label for={`${uid}-${field}`}>{t(`field.${field}`)}</label><code class="block text-xs text-ink-2">{field}</code></td>
						<td>{#if !projectMode || entry}<TextInput id={`${uid}-${field}`} bind:value={draft[field]} disabled={disabled} inputmode="numeric" placeholder={t(projectMode ? 'unchanged' : 'notConfigured')} />{#if entry}<span class="text-xs text-ink-2">{t('observed')}: {entry.limit === -1 ? t('unlimited') : entry.limit}</span>{/if}{:else}<span>{native?.availability[section as QuotaSection] ? t('unsupported') : t('unknown')}</span>{/if}</td>
						{#if projectMode}<td>{entry?.in_use ?? t('unknown')}</td><td>{entry?.reserved ?? t('unknown')}</td>{/if}
					</tr>
				{/each}
			</tbody></table></TableShell>
		</section>
	{/each}
	<Button disabled={disabled} onclick={save}>{t('save')}</Button>
</div>
