<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { ApiError } from '$lib/api/client';
	import { flavorAutomation, parseGpuProfiles, gpuAliasGroup, gpuAliasSelection, type PciDevicesSnapshot, type FlavorAutomationPolicy, type GpuProfileDraft, type AutomationHost } from '$lib/api/flavorAutomation';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { t } from '$lib/i18n/ns/compute-pools';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, Card, Field, TextInput, TextareaInput, SearchSelect } from '$lib/components/ui';
	let { onChanged }: { onChanged?: () => void } = $props();
	const uid = $props.id();
	type ProfileEditor = GpuProfileDraft & { selection?: { primary: string; companions: string[]; confirmUnknown: boolean } };
	let data = $state<FlavorAutomationPolicy | null>(null), drafts = $state<ProfileEditor[]>([]);
	let pci = $state<PciDevicesSnapshot | null>(null), pciError = $state(''), pciLoading = $state(false);
	let loading = $state(false), busy = $state(false), reloadRequired = $state(false), dirty = $state(false);
	let error = $state(''), outcome = $state(''), epoch = $state(0), refresh = $state(0);
	let generation = 0, pciGeneration = 0, live = true, ownerKey = '';
	function allowed() { const state = get(auth); return live && !!state.token && state.isSystemAdmin === true && get(authReady) && !get(projectSwitching) && !get(logoutInProgress); }
	const sync = () => {
		const state = get(auth), next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, !!state.token, get(authReady), get(projectSwitching), get(logoutInProgress)]);
		if (next === ownerKey) return;
		ownerKey = next; ++epoch; ++generation; data = null; pci = null; pciError = ''; pciLoading = false; drafts = []; error = ''; outcome = ''; loading = false; busy = false; reloadRequired = false; dirty = false;
	};
	const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync), logoutInProgress.subscribe(sync)];
	onDestroy(() => { live = false; ++generation; subscriptions.forEach(stop => stop()); });
	function capture() {
		const pending = generation, revision = epoch;
		const current = () => allowed() && pending === generation && revision === epoch;
		return { current, client: flavorAutomation({ token: () => get(auth).token ?? '', projectId: () => get(auth).projectId ?? undefined, isCurrent: current, canSubmit: current }) };
	}
	function accept(snapshot: FlavorAutomationPolicy) {
		data = snapshot;
		drafts = snapshot.gpu_profiles.map(row => ({ name: row.name, display_name: row.display_name, enabled: row.enabled, resource_class: row.resource_class, resources: JSON.stringify(row.resource_requirements, null, 2), specs: JSON.stringify(row.extra_specs, null, 2), aliases: JSON.stringify(row.alias_resource_classes ?? {}, null, 2), selection: pci ? gpuAliasSelection(pci, row) ?? undefined : undefined }));
		dirty = false;
	}
	function fail(cause: unknown) { error = cause instanceof ApiError && cause.status === 409 && /revision|conflict/.test(cause.message) ? t('conflict') : cause instanceof ApiError ? cause.message : t('loadFailed'); }
	function loadPci(owner: ReturnType<typeof capture>) {
		pciLoading = true; pciError = '';
		const pciRequest = ++pciGeneration;
		void owner.client.pciDevices().then(devices => {
			if (!owner.current() || pciRequest !== pciGeneration) return;
			pci = devices;
			if (data && !dirty && !busy) accept(data);
		}).catch(() => {
			if (!owner.current() || pciRequest !== pciGeneration) return;
			pci = null; pciError = t('pciLoadFailed');
			if (data && !dirty && !busy) accept(data);
		}).finally(() => { if (owner.current() && pciRequest === pciGeneration) pciLoading = false; });
	}
	async function load() {
		if (!allowed() || busy) return;
		++generation; const owner = capture(); loading = true; pciLoading = true; data = null; pci = null; pciError = ''; drafts = []; dirty = false; error = ''; outcome = ''; reloadRequired = false;
		loadPci(owner);
		try { const policy = await owner.client.policy(); if (owner.current()) accept(policy); }
		catch (cause) { if (owner.current()) fail(cause); }
		finally { if (owner.current()) loading = false; }
	}
	async function mutate(kind: 'profiles' | 'discover' | 'host', host?: AutomationHost) {
		if (!allowed() || loading || busy || reloadRequired || !data) return;
		const profiles = parsed;
		if (kind === 'profiles' && (!profiles || !dirty || drafts.some(draft => draft.selection && !validSelection(draft)))) return;
		const owner = capture(), revision = data.revision;
		busy = true; error = ''; outcome = '';
		try {
			if (kind === 'host') {
				if (!host || !await confirmDialog(t(host.removed ? 'reincludeConfirm' : 'removeHostConfirm', { name: host.name, id: host.id }), { confirmLabel: t(host.removed ? 'reincludeHost' : 'removeHost'), confirmVariant: host.removed ? 'accent' : 'danger' })) return;
				if (!owner.current()) return;
			}
			const snapshot = kind === 'profiles' ? await owner.client.saveProfiles(revision, profiles!) : kind === 'discover' ? await owner.client.discover() : await owner.client.host(host!.id, revision, !host!.removed);
			if (owner.current()) {
				accept(snapshot); outcome = t('saved'); onChanged?.();
				loadPci(owner);
			}
		} catch (cause) {
			if (owner.current()) { fail(cause); reloadRequired = true; outcome = cause instanceof ApiError && cause.status < 500 ? '' : t('unknownOutcome'); }
		} finally { if (owner.current()) busy = false; }
	}
	function addProfile() { if (locked || !gpuChoices.length) return; drafts = [...drafts, { name: '', display_name: '', enabled: false, resource_class: '', resources: '{}', specs: '{}', aliases: '{}', selection: { primary: '', companions: [], confirmUnknown: false } }]; dirty = true; }
	function validSelection(draft: ProfileEditor) {
		if (!pci || !draft.selection) return false;
		const generated = gpuAliasGroup(pci, draft.selection.primary, draft.selection.companions, draft.selection.confirmUnknown);
		if (!generated || generated.resource_class !== draft.resource_class) return false;
		try {
			for (const field of ['resources', 'specs', 'aliases'] as const) {
				const saved: Record<string, unknown> = JSON.parse(draft[field]), current: Record<string, unknown> = JSON.parse(generated[field]);
				if (Object.keys(saved).length !== Object.keys(current).length || Object.entries(saved).some(([key, value]) => !Object.hasOwn(current, key) || current[key] !== value)) return false;
			}
			return true;
		} catch { return false; }
	}
	function unknownAliases(draft: ProfileEditor) { return draft.selection ? pci?.aliases.filter(alias => alias.kind === 'unknown' && [draft.selection!.primary, ...draft.selection!.companions].includes(alias.name)).map(alias => alias.name) ?? [] : []; }
	function selectAliases(draft: ProfileEditor, primary: string, companions: string[]) {
		if (locked || !pci || !draft.selection) return;
		const group = gpuAliasGroup(pci, primary, companions, true);
		draft.selection = { primary, companions, confirmUnknown: false };
		if (group) Object.assign(draft, group);
		else Object.assign(draft, { resource_class: '', resources: '{}', specs: '{}', aliases: '{}' });
		dirty = true;
	}
	function date(value: string) { const time = Date.parse(value); return Number.isFinite(time) ? new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'medium' }).format(time) : t('unknown'); }
	$effect(() => { void epoch; void refresh; untrack(() => { if (allowed()) void load(); }); });
	const parsed = $derived(drafts.some(draft => draft.selection && !validSelection(draft)) ? null : parseGpuProfiles(drafts.map(draft => draft.selection && !draft.display_name ? { ...draft, display_name: draft.name } : draft)));
	const gpuChoices = $derived(pci?.alias_source.state === 'ready' ? pci.aliases.filter(alias => alias.selectable && ['gpu', 'unknown'].includes(alias.kind)) : []);
	const companionChoices = $derived(pci?.alias_source.state === 'ready' ? pci.aliases.filter(alias => alias.selectable && ['audio', 'unknown'].includes(alias.kind)) : []);
	const locked = $derived(!allowed() || loading || busy || reloadRequired);
</script>

<Card surface="base" class="mb-6 min-w-0">
	<section class="space-y-4" aria-label={t('policyTitle')}>
		<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold">{t('policyTitle')}</h2><Button variant="secondary" disabled={!allowed() || loading || busy} onclick={() => refresh++}>{t('refresh')}</Button></div>
		<Alert tone="info">{t('scopeHelp')}</Alert>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if outcome}<Alert tone={reloadRequired ? 'warning' : 'info'}>{outcome}</Alert>{/if}
		{#if reloadRequired}<Alert tone="warning">{t('reloadRequired')}</Alert>{/if}
		{#if loading}<LoadingState variant="section" label={t('loading')} />{/if}
		{#if data && allowed()}
			<p class="text-sm text-ink-2">{t('revision', { revision: data.revision })}</p>
			<section class="space-y-3" aria-label={t('hostsTitle')}>
				<div class="flex flex-wrap items-center gap-2"><h3 class="mr-auto font-semibold">{t('hostsTitle')}</h3><Button variant="secondary" disabled={locked || dirty} onclick={() => mutate('discover')}>{t('discoverHosts')}</Button></div>
				<p class="text-sm text-ink-2">{t('hostsHelp')}</p>
				{#if !data.hosts.length}<p class="text-sm text-ink-2">{t('hostsEmpty')}</p>{/if}
				<ul class="divide-y divide-line">{#each data.hosts as host (host.id)}
					<li class="space-y-2 py-3"><div class="flex flex-wrap items-start justify-between gap-3"><div class="min-w-0"><h4 class="break-all text-sm font-semibold">{host.name}</h4><code class="block break-all text-xs text-ink-2">{host.id}</code></div><Button variant={host.removed ? 'secondary' : 'danger'} disabled={locked || dirty} onclick={() => mutate('host', host)}>{t(host.removed ? 'reincludeHost' : 'removeHost')}</Button></div>
						<p class="text-sm">{t(host.removed ? 'hostRemoved' : 'hostIncluded')} · {t('observation')}: {host.state === 'up' ? t('hostUp') : host.state === 'down' ? t('hostDown') : host.state === 'missing' ? t('hostMissing') : t('unknown')}{host.status ? ` · ${host.status}` : ''}</p>
						<details><summary class="min-h-11 cursor-pointer py-3 text-sm text-ink-2">{t('supportedInventory')} · {date(host.observed_at)}</summary><dl class="grid min-w-0 grid-cols-1 gap-2 text-xs md:grid-cols-2">{#each [['VCPU', host.cpu], ...(host.pcpu ? [['PCPU', host.pcpu]] : []), ['RAM', host.ram], ['GPU', host.gpu]] as [label, inventory]}<div class="min-w-0"><dt>{label}</dt><dd><code class="whitespace-pre-wrap break-all">{JSON.stringify(inventory, null, 2)}</code></dd></div>{/each}</dl></details>
					</li>
				{/each}</ul>
			</section>
		{/if}
		{#if allowed()}
			<section class="space-y-3 border-t border-line pt-4" aria-label={t('pciTitle')}>
				<h3 class="font-semibold">{t('pciTitle')}</h3><p class="text-sm text-ink-2">{t('pciHelp')}</p>
				{#if pciLoading}<LoadingState variant="section" label={t('loading')} />{/if}
				{#if pciError}<Alert tone="warning">{pciError}</Alert>{/if}
				{#if pci}
					<Alert tone={pci.alias_source.state === 'ready' ? 'info' : 'warning'}>{t('pciAliasState')}: {t(`pciState.${pci.alias_source.state}`)} · {pci.alias_source.observed_at ? date(pci.alias_source.observed_at) : t('unknown')}<p class="mt-1 break-words">{t(`pciAliasHelp.${pci.alias_source.state}`)}</p></Alert>
					{#if !pci.aliases.length}<p class="text-sm text-ink-2">{t('pciAliasesEmpty')}</p>{/if}
					<ul class="divide-y divide-line" aria-label={t('pciConfiguredAliases')}>{#each pci.aliases as alias}
						<li class="min-w-0 space-y-1 py-3"><div class="flex flex-wrap gap-2 text-sm"><code class="break-all font-semibold">{alias.name}</code><span>{t(`pciKind.${alias.kind}`)}</span><span>{t(alias.selectable && pci.alias_source.state === 'ready' ? 'pciSelectable' : 'pciNotSelectable')}</span></div><p class="break-words text-sm text-ink-2">{alias.device_name ?? t('unknown')} · <code class="break-all">{alias.vendor_id ?? '?'}:{alias.product_id ?? '?'} · {alias.resource_class ?? t('unknown')}</code></p><p class="break-words text-sm text-ink-2">{t('pciGroups')}: {alias.mapped_groups.length ? alias.mapped_groups.join(', ') : t('pciUnmapped')}</p></li>
					{/each}</ul>
					<h4 class="text-sm font-semibold">{t('pciInventory')} · {t(`pciState.${pci.inventory.state}`)}</h4>
					{#if pci.inventory.state !== 'ready' || pci.inventory.errors.length}<Alert tone="warning">{t(pci.inventory.state === 'unavailable' ? 'pciInventoryHelp.unavailable' : 'pciInventoryHelp.partial')}</Alert>{/if}
					{#if !pci.inventory.devices.length}<p class="text-sm text-ink-2">{t(pci.inventory.state === 'ready' ? 'pciInventoryEmpty' : 'pciInventoryUnknown')}</p>{/if}
					<ul class="divide-y divide-line" aria-label={t('pciInventory')}>{#each pci.inventory.devices as device}
						<li class="min-w-0 space-y-1 py-3 text-sm"><p class="break-words font-medium">{device.host} · {t(`pciKind.${device.kind}`)}</p><code class="block break-all text-xs text-ink-2">{device.provider_name} · {device.provider_uuid} · {device.pci_address ?? t('unknown')} · {device.resource_class}</code><p class="tabular-nums">{t('pciTotal')}: {device.total} · {t('pciReserved')}: {device.reserved} · {t('pciAllocated')}: {device.used ?? t('unknown')}</p><p class="break-words text-ink-2">{t('pciGroups')}: {device.mapped_groups.length ? device.mapped_groups.join(', ') : t('pciUnmapped')}</p></li>
					{/each}</ul>
				{/if}
			</section>
		{/if}
		{#if data && allowed()}
			<section class="space-y-3 border-t border-line pt-4" aria-label={t('profilesTitle')}>
				<div class="flex flex-wrap items-center gap-2"><h3 class="mr-auto font-semibold">{t('profilesTitle')}</h3><Button variant="secondary" disabled={locked || drafts.length >= 128 || !gpuChoices.length} onclick={addProfile}>{t('addProfile')}</Button></div>
				<p class="text-sm text-ink-2">{t('profilesHelp')}</p><p class="text-sm text-ink-2">{t('scaleHelp')}</p>
				{#if !gpuChoices.length}<Alert tone="warning">{t('pciCreationUnavailable')}</Alert>{/if}
				{#if !drafts.length}<p class="text-sm text-ink-2">{t('profilesEmpty')}</p>{/if}
				<div class="divide-y divide-line" oninput={() => dirty = true} onchange={() => dirty = true} role="group" aria-label={t('profilesTitle')}>
					{#each drafts as draft, index}
						<fieldset disabled={locked} class="min-w-0 space-y-3 py-4"><legend class="break-all text-sm font-semibold">{draft.name || t('newProfile')}</legend>
							<div class="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2"><Field for={`${uid}-name-${index}`} label={t('profileSlug')} help={t('slugHelp')}><TextInput id={`${uid}-name-${index}`} bind:value={draft.name} disabled={locked} /></Field><Field for={`${uid}-display-${index}`} label={t('profileDisplayName')}><TextInput id={`${uid}-display-${index}`} bind:value={draft.display_name} disabled={locked} /></Field><label class="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" bind:checked={draft.enabled} disabled={locked} />{t('approveProfile')}</label></div>
							{#if draft.selection}
								<Field for={`${uid}-gpu-${index}`} label={t('pciPrimaryAlias')}><SearchSelect id={`${uid}-gpu-${index}`} value={draft.selection.primary} options={gpuChoices.map(alias => ({ value: alias.name, label: alias.name, description: `${alias.kind === 'unknown' ? t('pciUnclassified') : alias.device_name ?? t('unknown')} · ${alias.resource_class}` }))} ariaLabel={t('pciPrimaryAlias')} placeholder={t('pciChooseGpu')} disabled={locked} onchange={value => selectAliases(draft, value, draft.selection!.companions.filter(name => name !== value))} /></Field>
								<fieldset class="min-w-0 space-y-2"><legend class="text-sm font-medium">{t('pciCompanions')}</legend><p class="text-sm text-ink-2">{t('pciCompanionHelp')}</p>{#each companionChoices.filter(alias => alias.name !== draft.selection!.primary) as alias}<label class="flex min-h-11 items-start gap-2 py-2 text-sm"><input type="checkbox" class="mt-1" checked={draft.selection.companions.includes(alias.name)} disabled={locked || !draft.selection.primary} onchange={event => selectAliases(draft, draft.selection!.primary, event.currentTarget.checked ? [...draft.selection!.companions, alias.name] : draft.selection!.companions.filter(name => name !== alias.name))} /><span class="min-w-0"><code class="break-all">{alias.name}</code><span class="block break-words text-ink-2">{alias.kind === 'unknown' ? t('pciUnclassified') : alias.device_name ?? t('unknown')} · {alias.resource_class}</span></span></label>{/each}</fieldset>
								{#if unknownAliases(draft).length}<Alert tone="warning"><p class="break-words">{t('pciUnknownRoleHelp')} <code class="break-all">{unknownAliases(draft).join(', ')}</code></p><label class="mt-2 flex min-h-11 items-start gap-2 py-2 text-sm"><input type="checkbox" class="mt-1" bind:checked={draft.selection.confirmUnknown} disabled={locked} />{t('pciConfirmUnknown')}</label></Alert>{/if}
								{#if draft.resource_class}<p class="break-all text-sm text-ink-2">{t('primaryResource')}: <code>{draft.resource_class}</code></p>{/if}
								<details><summary class="min-h-11 cursor-pointer py-3 text-sm text-ink-2">{t('pciGeneratedPayload')}</summary><code class="block whitespace-pre-wrap break-all text-xs">{draft.specs}</code></details>
							{:else}
								<p class="text-sm text-ink-2">{t('pciLegacyHelp')}</p>
								<Field for={`${uid}-rc-${index}`} label={t('primaryResource')}><TextInput id={`${uid}-rc-${index}`} bind:value={draft.resource_class} disabled={locked} /></Field>
								<div class="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2"><Field for={`${uid}-resources-${index}`} label={t('profileResources')} help={t('resourceHelp')}><TextareaInput id={`${uid}-resources-${index}`} bind:value={draft.resources} disabled={locked} /></Field><Field for={`${uid}-specs-${index}`} label={t('profileSpecs')}><TextareaInput id={`${uid}-specs-${index}`} bind:value={draft.specs} disabled={locked} /></Field><Field for={`${uid}-aliases-${index}`} label={t('profileAliases')} help={t('aliasHelp')}><TextareaInput id={`${uid}-aliases-${index}`} bind:value={draft.aliases} disabled={locked} /></Field></div>
							{/if}
							<Button variant="secondary" disabled={locked} onclick={() => { drafts = drafts.filter((_, row) => row !== index); dirty = true; }}>{t('removeProfile')}</Button>
						</fieldset>
					{/each}
				</div>
				{#if parsed === null}<Alert tone="warning">{t('invalidProfile')}</Alert>{/if}
				{#if dirty}<p class="text-sm text-ink-2">{t('unsavedProfiles')}</p>{/if}
				<Button variant="primary" disabled={locked || !dirty || parsed === null} onclick={() => mutate('profiles')}>{#if busy}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{busy ? t('saving') : t('saveProfiles')}</Button>
			</section>
		{/if}
	</section>
</Card>
