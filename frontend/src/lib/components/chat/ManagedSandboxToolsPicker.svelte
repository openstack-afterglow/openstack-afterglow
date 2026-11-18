<script lang="ts">
	import {
		managedSandboxTools, toggleManagedSandboxTool, toggleManagedSandboxProfile,
		setManagedSandboxTools, refreshManagedSandboxTools, managedSandboxIssueMessage,
		type ManagedSandboxProfile
	} from '$lib/stores/managedSandboxTools';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import { t } from '$lib/i18n/ns/mcp-gallery';

	let { menu = false, profileId, summaryOnly = false, showReadiness = true }: {
		menu?: boolean; profileId?: string; summaryOnly?: boolean; showReadiness?: boolean;
	} = $props();
	const uid = $props.id();
	let actionError = $state('');
	const profiles = $derived($managedSandboxTools.profiles.filter((profile) => !profileId || profile.id === profileId));
	const showSummary = $derived(!profileId);
	const needsReset = $derived($managedSandboxTools.issue === 'invalid_saved' || $managedSandboxTools.issue === 'too_many');
	const issue = $derived($managedSandboxTools.issue
		? managedSandboxIssueMessage($managedSandboxTools.issue, $managedSandboxTools.unavailable) : '');

	$effect(() => { void $managedSandboxTools.ownerKey; actionError = ''; });

	function selectedCount(profile: ManagedSandboxProfile) {
		return profile.tools.filter((name) => $managedSandboxTools.selected.includes(name)).length;
	}
	function allSelected(profile: ManagedSandboxProfile) {
		return profile.tools.length > 0 && selectedCount(profile) === profile.tools.length;
	}
	function canAdd(profile: ManagedSandboxProfile) {
		return $managedSandboxTools.canSelect && profile.available === true;
	}
	function change(operation: () => boolean) {
		if (operation()) { actionError = ''; return; }
		actionError = $managedSandboxTools.issue
			? managedSandboxIssueMessage($managedSandboxTools.issue, $managedSandboxTools.unavailable)
			: t('selectionChangeFailed');
	}
	function readiness(profile: ManagedSandboxProfile) {
		if (profile.available === null) return t('managedUnknown');
		if (profile.reason === 'profile_not_in_enabled_sandbox_manifest') return t('profileMissing');
		if (profile.reason === 'execution_protocol_v2_unavailable') return t('protocolMissing');
		return t('unavailable');
	}
</script>

<div class="managed-picker" class:menu class:embedded={!!profileId && !menu} role={menu ? 'group' : undefined} aria-label={menu ? t('selectionTitle') : undefined}>
	{#if showSummary}
		<div class="summary-row">
			<strong>{t('selectionTitle')}</strong>
			<Pill tone="neutral" size="xs">{t('selectionSummary', { count: $managedSandboxTools.selected.length })}</Pill>
		</div>
		<p>{t('selectionLifecycle')}</p>
		{#if !$managedSandboxTools.selected.length && !needsReset}<p>{t('selectionNone')}</p>{/if}
		{#if $managedSandboxTools.preparing}<LoadingState variant="inline" label={t('selectionPreparing')} />
		{:else if $managedSandboxTools.loading}<LoadingState variant="inline" label={t('selectionIssue.loading')} />{/if}
		{#if issue}<Alert tone="warning" flat>{issue}</Alert>
		{:else if $managedSandboxTools.catalogError}<Alert tone="info" flat>{t('selectionReadinessFailed')}</Alert>{/if}
		{#if $managedSandboxTools.storageFailed}<Alert tone="warning" flat>{t('selectionStorageFailed')}</Alert>{/if}
		<div class="actions">
			{#if $managedSandboxTools.selected.length || needsReset}
				{#if menu}<button type="button" class="menu-action" role="menuitem" onclick={() => change(() => setManagedSandboxTools([]))}>{t('selectionClear')}</button>
				{:else}<Button variant="secondary" size="sm" onclick={() => change(() => setManagedSandboxTools([]))}>{t('selectionClear')}</Button>{/if}
			{/if}
			{#if $managedSandboxTools.catalogError || issue}
				{#if menu}<button type="button" class="menu-action" role="menuitem" disabled={$managedSandboxTools.loading} onclick={() => void refreshManagedSandboxTools()}>{t('refresh')}</button>
				{:else}<Button variant="secondary" size="sm" disabled={$managedSandboxTools.loading} onclick={() => void refreshManagedSandboxTools()}>{t('refresh')}</Button>{/if}
			{/if}
		</div>
	{/if}
	{#if !summaryOnly}
		{#each profiles as profile, profileIndex (profile.id)}
			{@const count = selectedCount(profile)}
			{@const all = allSelected(profile)}
			{@const partial = count > 0 && !all}
			{@const profileDisabled = !profile.tools.length || (!canAdd(profile) && !all)}
			<section class="profile" aria-label={profile.name}>
				{#if menu}
					<button type="button" role="menuitemcheckbox" class="menu-option profile-option" aria-checked={partial ? 'mixed' : all} disabled={profileDisabled} onclick={() => change(() => toggleManagedSandboxProfile(profile.id, !all))}>
						{@render check(all || partial, partial)}<span>{t('selectionProfile', { name: profile.name })}</span>
					</button>
				{:else}
					<div class="choice profile-choice">
						<SelectionCheckbox id={`${uid}-profile-${profileIndex}`} checked={all} indeterminate={partial} ariaLabel={t('selectionProfile', { name: profile.name })} disabled={profileDisabled} onclick={() => change(() => toggleManagedSandboxProfile(profile.id, !all))} />
						<label for={`${uid}-profile-${profileIndex}`}>{t('selectionProfile', { name: profile.name })}</label>
					</div>
				{/if}
				{#if showReadiness && profile.available !== true}<p>{readiness(profile)}</p>{/if}
				{#if !profile.tools.length}<p>{t('selectionNoTools')}</p>
				{:else if menu}
					{#each profile.tools as name (name)}
						{@const selected = $managedSandboxTools.selected.includes(name)}
						<button type="button" role="menuitemcheckbox" class="menu-option tool-option" aria-checked={selected} disabled={!selected && !canAdd(profile)} onclick={() => change(() => toggleManagedSandboxTool(name, !selected))}>
							{@render check(selected)}<span class="tool-name">{name}</span>
						</button>
					{/each}
				{:else}
					<details class="tool-list">
						<summary>{t('selectionToolsCount', { selected: count, count: profile.tools.length })}</summary>
						{#each profile.tools as name, toolIndex (name)}
							{@const selected = $managedSandboxTools.selected.includes(name)}
							<div class="choice">
								<SelectionCheckbox id={`${uid}-tool-${profileIndex}-${toolIndex}`} checked={selected} ariaLabel={name} disabled={!selected && !canAdd(profile)} onclick={() => change(() => toggleManagedSandboxTool(name, !selected))} />
								<label class="tool-name" for={`${uid}-tool-${profileIndex}-${toolIndex}`}>{name}</label>
							</div>
						{/each}
					</details>
				{/if}
			</section>
		{:else}
			{#if $managedSandboxTools.loading && profileId}<LoadingState variant="inline" label={t('selectionIssue.loading')} />
			{:else if !profileId && $managedSandboxTools.catalogLoaded}<p>{t('selectionNoTools')}</p>{/if}
		{/each}
	{/if}
	{#if actionError}<Alert tone="warning" flat>{actionError}</Alert>{/if}
</div>

{#snippet check(selected: boolean, partial = false)}
	<span class="menu-check" class:is-selected={selected} aria-hidden="true">
		{#if partial}<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6h8" stroke="currentColor" stroke-width="2" /></svg>
		{:else if selected}<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="m2 6 3 3 5-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>{/if}
	</span>
{/snippet}

<style>
	.managed-picker { display: grid; gap: 0.65rem; min-width: 0; color: var(--color-ink-1); }
	.embedded { margin-block-start: 0.375rem; padding-inline-start: 2.625rem; }
	.embedded .profile { gap: 0; }
	.summary-row, .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
	strong { font-size: var(--type-body); font-weight: 600; color: var(--color-ink-0); }
	p { margin: 0; font-size: var(--type-support); color: var(--color-ink-2); overflow-wrap: anywhere; }
	.profile { display: grid; gap: 0.4rem; min-width: 0; }
	.profile + .profile { padding-block-start: 0.75rem; border-block-start: 1px solid var(--color-line); }
	.choice { display: flex; align-items: center; gap: 0.4rem; min-width: 0; }
	.choice > label { display: flex; flex: 1; align-items: center; min-block-size: var(--control-height); cursor: pointer; font-size: var(--type-body); overflow-wrap: anywhere; }
	.tool-name { font-family: var(--font-mono); font-size: var(--type-identifier); overflow-wrap: anywhere; }
	summary { padding-block: 0.5rem; cursor: pointer; font-size: var(--type-support); color: var(--color-ink-2); }
	summary:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-sm); }
	.tool-list { min-width: 0; }
	.menu { padding: 0.5rem 0.75rem; }
	.menu-option, .menu-action { display: flex; align-items: center; gap: 0.6rem; min-block-size: var(--control-touch-height); width: 100%; border: 0; border-radius: var(--radius-sm); padding: 0.5rem 0.25rem; background: transparent; color: var(--color-ink-1); text-align: start; font-size: var(--type-body); cursor: pointer; }
	.menu-option:hover, .menu-action:hover { background: var(--color-surface-selected); }
	.menu-option:focus-visible, .menu-action:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.menu-option:disabled, .menu-action:disabled { color: var(--color-ink-2); cursor: not-allowed; }
	.menu-option > span:last-child { min-width: 0; overflow-wrap: anywhere; }
	.profile-option { font-weight: 500; }
	.tool-option { padding-inline-start: 0.75rem; }
	.menu-check { display: grid; place-items: center; inline-size: 1rem; block-size: 1rem; flex-shrink: 0; border: 1px solid var(--color-line-2); border-radius: var(--radius-sm); color: var(--color-ink-0); }
	.menu-check.is-selected { background: var(--color-surface-selected); }
	@media (max-width: 767px) { .choice > label, summary { min-block-size: var(--control-touch-height); } }
</style>
