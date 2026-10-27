<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { projectManagement, refreshProjectManagement, type ProjectManagementState } from '$lib/stores/projectManagement';
	import type { IamSession } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import IamProjects from './IamProjects.svelte';

	let capabilityState = $state.raw<ProjectManagementState>({ scope: null, capability: null, checking: false, error: '' });
	let session = $state.raw<IamSession | null>(null);
	let domainManager = $state(false);
	let revision = $state(0);
	let denied = $state(false);
	let entryVerified = $state(false);
	let live = true;
	function acceptCapability(next: ProjectManagementState) {
		const allowed = entryVerified && next.scope && next.capability && next.capability.domain_kind !== 'personal' && (next.capability.is_domain_manager || next.capability.can_create_project);
		const changed = capabilityState.scope !== next.scope || domainManager !== (next.capability?.is_domain_manager === true);
		capabilityState = next;
		if (!allowed || changed) { session = null; revision++; }
		domainManager = next.capability?.is_domain_manager === true;
		if (!next.checking && !next.error) denied = false;
		if (allowed && !next.checking && !next.error && !session) {
			const scope = next.scope!;
			const manager = domainManager;
			const target: IamSession = {
				token: scope.token, domainId: scope.domainId, userId: scope.userId,
				isCurrent: () => capabilityState.scope === scope && session === target && capabilityState.capability !== null && domainManager === manager,
				canSubmit: () => target.isCurrent() && !capabilityState.checking && !capabilityState.error && !denied
			};
			session = target;
		}
	}
	const unsubscribe = projectManagement.subscribe(acceptCapability);
	onMount(() => {
		// Navigation may retain an old snapshot. Never mount project/delegation
		// consumers until this route has completed a fresh authority read.
		void refreshProjectManagement().then(() => {
			if (!live) return;
			entryVerified = true;
			acceptCapability(capabilityState);
		});
	});
	function recheck() { denied = true; void refreshProjectManagement(); }
	onDestroy(() => { live = false; unsubscribe(); session = null; });
</script>

<PageShell>
	<PageHeader breadcrumb={t('title')} title={t('projectsTitle')} subtitle={t('projectsSubtitle')}>
		{#snippet actions()}<Button variant="secondary" disabled={capabilityState.checking || !capabilityState.scope} onclick={() => { void refreshProjectManagement(); }}>{t('refresh')}</Button>{/snippet}
	</PageHeader>
	{#if !entryVerified || capabilityState.checking}<ActivityIndicator label={t('projectsVerifying')} />
	{:else if capabilityState.error}<Alert tone="danger">{t('loadFailed')}</Alert>
	{:else if !session}<Alert tone="warning">{t('projectsDenied')}</Alert>{/if}
	{#if session}
		<p class="mb-4 break-all text-sm text-ink-2">{t('domain')} · {session.domainId}</p>
		{#key revision}<IamProjects {session} {domainManager} canCreate={capabilityState.capability?.can_create_project === true} blocked={capabilityState.checking || !!capabilityState.error || denied} onDenied={recheck} />{/key}
	{/if}
</PageShell>
