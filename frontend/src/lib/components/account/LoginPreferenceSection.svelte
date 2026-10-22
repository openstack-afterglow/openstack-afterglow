<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { api } from '$lib/api/client';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { t } from '$lib/i18n/ns/account';
	import { Alert, Button, Card, ActivityIndicator } from '$lib/components/ui';
	let mounted = false;
	let epoch = 0;
	let loaded = $state(false);
	let enabled = $state(false);
	let busy = $state(false);
	let error = $state('');
	let saved = $state(false);
	const blocked = $derived(!$authReady || $logoutInProgress || $projectSwitching || !$auth.token || !loaded || busy);
	function capture() {
		const state = get(auth), ticket = epoch;
		if (!mounted || !state.token || !get(authReady) || get(logoutInProgress) || get(projectSwitching)) return null;
		return { token: state.token, project: state.projectId ?? undefined,
			current: () => mounted && epoch === ticket && get(authReady) && !get(logoutInProgress) && !get(projectSwitching) };
	}
	async function load() {
		const owner = capture(); if (!owner) return;
		busy = true; loaded = false; error = ''; saved = false;
		try {
			const result = await api.get<{ remember_last_workspace: boolean }>('/api/v1/profile/login-preference', owner.token, owner.project, { refresh: true, cache: 'no-store', replayOnUnauthorized: false });
			if (owner.current()) { enabled = result.remember_last_workspace; loaded = true; }
		} catch { if (owner.current()) error = t('loginPreference.failed'); }
		finally { if (owner.current()) busy = false; }
	}
	async function save() {
		if (blocked) return;
		const owner = capture(); if (!owner) return;
		busy = true; error = ''; saved = false;
		try {
			await api.put('/api/v1/profile/login-preference', { remember_last_workspace: enabled }, owner.token, owner.project, { cache: 'no-store', replayOnUnauthorized: false });
			if (owner.current()) saved = true;
		} catch { if (owner.current()) { error = t('loginPreference.failed'); loaded = false; } }
		finally { if (owner.current()) busy = false; }
	}
	onMount(() => {
		mounted = true; let previous = '';
		const changed = () => {
			const state = get(auth);
			const next = JSON.stringify([sessionScopeKey(state), get(authReady), get(logoutInProgress), get(projectSwitching)]);
			if (next === previous) return;
			previous = next; epoch++; enabled = false; loaded = false; busy = false; error = ''; saved = false;
			void load();
		};
		const unsubscribers = [auth.subscribe(changed), authReady.subscribe(changed), logoutInProgress.subscribe(changed), projectSwitching.subscribe(changed)];
		return () => { mounted = false; epoch++; unsubscribers.forEach(unsubscribe => unsubscribe()); };
	});
</script>

<Card class="p-5 space-y-4">
	<h3 class="text-sm font-semibold text-ink-0">{t('loginPreference.title')}</h3>
	<p class="text-sm text-ink-2">{t('loginPreference.help')}</p>
	{#if busy}<ActivityIndicator label={t('loginPreference.loading')} />{/if}
	{#if error}<Alert tone="danger">{error} <Button variant="secondary" disabled={busy || !$authReady || $logoutInProgress || $projectSwitching} onclick={load}>{t('loginPreference.reload')}</Button></Alert>{/if}
	{#if saved}<Alert tone="success">{t('loginPreference.saved')}</Alert>{/if}
	<label class="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" bind:checked={enabled} disabled={blocked} />{t('loginPreference.remember')}</label>
	<Button variant="secondary" disabled={blocked || (enabled && !$auth.projectId)} onclick={save}>{t('loginPreference.save')}</Button>
</Card>
