<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/waygate';
	import type { WaygateServer } from '$lib/types/waygate';
	import {
		WAYGATE_KEEPALIVE_DEFAULT,
		WAYGATE_KEEPALIVE_MAX,
		WAYGATE_MTU_MAX,
		WAYGATE_MTU_MIN,
		type WaygateClientDraft,
		type WaygateClientDraftErrors,
	} from '$lib/utils/waygateClientSettings';

	interface Props {
		draft: WaygateClientDraft;
		errors: WaygateClientDraftErrors;
		disabled?: boolean;
		mode?: 'client-edit' | 'issue' | 'server-create' | 'server-edit';
		defaults?: WaygateServer;
		/** Omitted for issuance: the service generates a unique PSK for every new client. */
		pskEnabled?: boolean;
	}
	let { draft = $bindable(), errors, disabled = false, pskEnabled, mode = 'client-edit', defaults }: Props = $props();
	const id = $props.id();
	const clientMode = $derived(mode === 'issue' || mode === 'client-edit');
	const inheritOptions = $derived([
		{ value: 'inherit', label: t('settings.inherit'), disabled },
		{ value: 'custom', label: t('settings.custom'), disabled },
	]);
	const fields = ['name', 'dns', 'mtu', 'persistentKeepalive'] as const;
	const elements = $state<Record<(typeof fields)[number], HTMLInputElement | null>>({
		name: null, dns: null, mtu: null, persistentKeepalive: null,
	});

	export function focusFirstError() {
		const first = fields.find((field) => errors[field] && elements[field]);
		if (first) elements[first]?.focus();
	}
</script>

<div class="space-y-4">
	{#if mode !== 'server-edit'}
		<Field label={t('settings.name')} for="{id}-name" error={errors.name} help={mode === 'server-create' ? t('settings.nameHelpAutomatic') : t('settings.nameHelp')} required={mode !== 'server-create'}>
			<TextInput id="{id}-name" bind:element={elements.name} bind:value={draft.name} placeholder={mode === 'server-create' ? 'waygate-gateway' : 'my-laptop'} {disabled} required={mode !== 'server-create'} maxlength={63} ariaInvalid={!!errors.name} />
		</Field>
	{/if}
	{#if clientMode}
		<div class="space-y-2">
			<p class="text-xs font-medium text-ink-1">{t('settings.dnsMode')}</p>
			<ToggleGroup value={draft.inheritDns ? 'inherit' : 'custom'} options={inheritOptions} onchange={(value) => { draft.inheritDns = value === 'inherit'; }} ariaLabel={t('settings.dnsMode')} />
		</div>
	{/if}
	{#if clientMode && draft.inheritDns}
		<Field label="DNS" help={t('settings.inheritedHelp')}>
			<p class="break-all rounded-md border border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] px-3 py-2 text-sm text-ink-1">{defaults?.dns || t('settings.dnsUnset')}</p>
		</Field>
	{:else}
		<Field label="DNS" for="{id}-dns" error={errors.dns} help={t('settings.dnsHelp')}>
			<TextInput id="{id}-dns" bind:element={elements.dns} bind:value={draft.dns} placeholder="1.1.1.1, 8.8.8.8" {disabled} maxlength={255} ariaInvalid={!!errors.dns} />
		</Field>
	{/if}
	{#if clientMode}
		<Field label="MTU" for="{id}-mtu" error={errors.mtu} help={t('settings.mtuHelp', { min: WAYGATE_MTU_MIN, max: WAYGATE_MTU_MAX })}>
			<TextInput id="{id}-mtu" bind:element={elements.mtu} bind:value={draft.mtu} inputmode="numeric" placeholder={t('settings.automatic')} {disabled} ariaInvalid={!!errors.mtu} />
		</Field>
		<div class="space-y-2">
			<p class="text-xs font-medium text-ink-1">{t('settings.keepaliveMode')}</p>
			<ToggleGroup value={draft.inheritPersistentKeepalive ? 'inherit' : 'custom'} options={inheritOptions} onchange={(value) => { draft.inheritPersistentKeepalive = value === 'inherit'; }} ariaLabel={t('settings.keepaliveMode')} />
		</div>
	{/if}
	{#if clientMode && draft.inheritPersistentKeepalive}
		<Field label={t('settings.keepaliveLabel')} help={t('settings.inheritedHelp')}>
			<p class="rounded-md border border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] px-3 py-2 text-sm text-ink-1">{(defaults?.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT) === 0 ? t('settings.keepaliveDisabled') : t('settings.keepaliveSeconds', { seconds: defaults?.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT })}</p>
		</Field>
	{:else}
		<Field label={t('settings.keepaliveLabel')} for="{id}-keepalive" error={errors.persistentKeepalive} help={t('settings.keepaliveHelp', { max: WAYGATE_KEEPALIVE_MAX })} required>
			<TextInput id="{id}-keepalive" bind:element={elements.persistentKeepalive} bind:value={draft.persistentKeepalive} inputmode="numeric" {disabled} required ariaInvalid={!!errors.persistentKeepalive} />
		</Field>
	{/if}
	{#if mode === 'server-create' || mode === 'server-edit'}
		<Alert tone="info"><RichText segments={t.rich('settings.serverDefaultsHelp')} /></Alert>
	{:else if pskEnabled === undefined}
		<p class="text-xs leading-relaxed text-ink-2">
			<RichText segments={t.rich('settings.generatedPskHelp')} />
		</p>
	{:else}
		<p class="text-xs leading-relaxed text-ink-2">
			{pskEnabled ? t('settings.pskEnabledHelp') : t('settings.pskDisabledHelp')}
		</p>
		<Alert tone="info"><RichText segments={t.rich('settings.savedSettingsHelp')} /></Alert>
	{/if}
</div>
