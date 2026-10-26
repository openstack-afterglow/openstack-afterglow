<script lang="ts">
	import { onMount } from 'svelte';
	import { derived, get } from 'svelte/store';
	import { t } from '$lib/i18n/ns/workspace-selector';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { api, ApiError } from '$lib/api/client';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';

	let { domainId = $auth.domainId ?? '', domainName = $auth.domainName ?? '', submitting = $bindable(false), submitDisabled = false, onCreate, onClose, onSuccess }: {
		domainId?: string; domainName?: string; submitting?: boolean; submitDisabled?: boolean;
		onCreate?: (name: string, description: string) => Promise<{ id: string; name: string }>;
		onClose: () => void; onSuccess: (project: { id: string; name: string }) => void;
	} = $props();
	let open = $state(true);
	let name = $state('');
	let description = $state('');
	let checking = $state(true);
	let allowed = $state(false);
	let authorizedDomain = $state('');
	let error = $state<'loadFailed' | 'createRejected' | 'createUncertain' | ''>('');
	let uncertain = $state(false);
	let active = false;
	let epoch = 0;
	let request: AbortController | null = null;
	const componentId = $props.id();
	let personal = $state(false);
	const canSubmit = $derived(!submitDisabled && allowed && authorizedDomain === domainId && !checking && !submitting && !uncertain && (personal || !!name.trim()) && $authReady && !$logoutInProgress && !$projectSwitching);
	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	}

	onMount(() => {
		active = true;
		let previous = '';
		const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching], ([state, ready, loggingOut, switching]) => ({ state, ready, loggingOut, switching })).subscribe(({ state, ready, loggingOut, switching }) => {
			const key = JSON.stringify([sessionScopeKey(state), !!state.token, ready, loggingOut, switching]);
			if (key === previous) return;
			const first = previous === ''; previous = key;
			epoch++; request?.abort(); allowed = false; personal = false; submitting = false;
			if (!first) { onClose(); return; }
			if (ready && state.token && !loggingOut && !switching && domainId) void checkCapability();
			else checking = false;
		});
		return () => { active = false; epoch++; request?.abort(); unsubscribe(); submitting = false; };
	});
	async function checkCapability() {
		const version = epoch; const target = domainId;
		request = new AbortController(); const signal = request.signal;
		try {
			const result = await api.get<{ domain_id: string; domain_kind?: 'personal' | 'organization' | 'legacy'; can_create_project: boolean }>(`/api/v1/projects/capabilities?domain_id=${encodeURIComponent(target)}`, get(auth).token!, undefined, { refresh: true, suppressAuthRedirect: true, signal });
			if (!active || version !== epoch || domainId !== target || signal.aborted) return;
			allowed = result.domain_id === target && result.can_create_project === true;
			personal = result.domain_id === target && result.domain_kind === 'personal';
			authorizedDomain = target;
		} catch { if (active && version === epoch && !signal.aborted) error = 'loadFailed'; }
		finally { if (active && version === epoch) checking = false; }
	}
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!canSubmit) return;
		const version = epoch; const target = domainId;
		request = new AbortController(); const signal = request.signal;
		submitting = true; error = '';
		try {
			const result = onCreate
				? await onCreate(name.trim(), description.trim())
				: await api.post<{ id: string; name: string }>('/api/v1/projects', { ...(!personal && name.trim() ? { name: name.trim() } : {}), description: description.trim(), domain_id: target }, get(auth).token!, undefined, { signal, replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' });
			if (!active || version !== epoch || domainId !== target || signal.aborted) return;
			if (!result?.id || typeof result.name !== 'string') throw new Error('Invalid project response');
			submitting = false;
			onSuccess(result);
		} catch (cause) {
			if (active && version === epoch && !signal.aborted) {
				uncertain = !(cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 408);
				error = uncertain ? 'createUncertain' : 'createRejected';
			}
		} finally { if (active && version === epoch) submitting = false; }
	}
</script>

<div use:portal>
<FormModal bind:open title={t('newProject')} {onClose} {submitting}>
	<form class="space-y-4" onsubmit={submit}>
		<p class="break-all text-sm text-ink-2">{domainName} · {domainId}</p>
		{#if error}<Alert tone="warning">{t(error)}</Alert>{/if}
		{#if !checking && !allowed && !error}<Alert tone="neutral">{t('createDenied')}</Alert>{/if}
		{#if personal}<p class="text-sm text-ink-2">{t('personalProjectNameHelp')}</p>
		{:else}<Field label={t('projectName')} for={`${componentId}-name`} required><TextInput id={`${componentId}-name`} bind:value={name} required maxlength={64} disabled={submitting || uncertain || !allowed} /></Field>{/if}
		<Field label={t('description')} for={`${componentId}-description`}><TextInput id={`${componentId}-description`} bind:value={description} maxlength={255} disabled={submitting || uncertain || !allowed} /></Field>
		<div class="flex flex-wrap justify-end gap-2">
			<Button variant="secondary" onclick={onClose} disabled={submitting}>{t('cancel')}</Button>
			<Button type="submit" disabled={!canSubmit} ariaBusy={submitting}>{t('create')}</Button>
		</div>
	</form>
	{#snippet actions()}{/snippet}
</FormModal>
</div>
