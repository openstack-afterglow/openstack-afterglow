<script lang="ts">
	import { Alert, Field, TextInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/usage-schedule';
	import type { UsageScheduleDraft } from '$lib/types/instanceUsage';
	import { usageDraftError, toLocalDateTime } from '$lib/utils/instanceUsage';
	let { value, onchange, disabled = false, currentExpiry, idPrefix = 'usage-schedule' }: {
		value: UsageScheduleDraft; onchange: (value: UsageScheduleDraft) => void;
		disabled?: boolean; currentExpiry?: string; idPrefix?: string;
	} = $props();
	const error = $derived(usageDraftError(value, currentExpiry));
	const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
	const extended = $derived(value.expiresLocal > toLocalDateTime(currentExpiry ?? value.defaultExpiresAt));
	const reasonBytes = $derived(new TextEncoder().encode(value.reason.trim()).length);
</script>

<div class="min-w-0 space-y-4">
	<Field label={t('expires')} for="{idPrefix}-expires" required help={t('timezone', { zone })}>
		<input id="{idPrefix}-expires" type="datetime-local" value={value.expiresLocal} {disabled} required
			aria-describedby="{idPrefix}-expires-message" aria-invalid={error === 'invalidDate' || error === 'pastDate' || error === 'shorterDate'}
			oninput={(event) => onchange({ ...value, expiresLocal: event.currentTarget.value })}
			class="min-w-0 w-full rounded-md border border-line-2 bg-surface-sunken px-3 py-2 text-sm text-ink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" />
	</Field>
	{#if !currentExpiry && value.expiresLocal === toLocalDateTime(value.defaultExpiresAt)}
		<p class="text-xs leading-relaxed text-ink-2">{t('defaultDate')}</p>
	{/if}
	<Field label={t('action')} for="{idPrefix}-action">
		<select id="{idPrefix}-action" value={value.expiryAction} {disabled}
			onchange={(event) => onchange({ ...value, expiryAction: event.currentTarget.value as 'shelve' | 'delete', deleteVolumes: false })}
			class="min-w-0 w-full rounded-md border border-line-2 bg-surface-sunken px-3 py-2 text-sm text-ink-0">
			<option value="shelve">{t('shelve')}</option>
			<option value="delete">{t('delete')}</option>
		</select>
	</Field>
	{#if value.expiryAction === 'delete'}
		<Alert tone="warning">{t('destructive')}</Alert>
		<label class="flex min-h-11 items-start gap-3 text-sm text-ink-1">
			<input type="checkbox" checked={value.deleteVolumes} {disabled} class="mt-1 shrink-0"
				onchange={(event) => onchange({ ...value, deleteVolumes: event.currentTarget.checked })} />
			<span class="min-w-0 break-words">{t('deleteVolumes')}</span>
		</label>
		{#if !value.deleteVolumes}<p class="text-sm text-ink-2">{t('retain')}</p>{/if}
		<p class="text-xs leading-relaxed text-ink-2">{t('storageScope')}</p>
	{:else}
		<p class="text-sm text-ink-2">{t('retain')}</p>
	{/if}
	<Field label={t('reason')} for="{idPrefix}-reason" required={extended} help={t('reasonHelp')}>
		<TextInput id="{idPrefix}-reason" value={value.reason} {disabled} required={extended} ariaInvalid={error === 'reasonInvalid' || error === 'reasonRequired'}
			oninput={(event) => onchange({ ...value, reason: (event.target as HTMLInputElement).value })} />
		<span class="text-xs tabular-nums text-ink-2">{reasonBytes} / 255 UTF-8</span>
	</Field>
	{#if error}<Alert tone="danger">{t(error)}</Alert>{/if}
</div>
