<script lang="ts">
	import { untrack } from 'svelte';
	import { auth, canWrite } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { Volume } from '$lib/types/volume';
	import { t } from '$lib/i18n/ns/volume';
	import { Alert, Button, Field, FormModal, TextInput } from '$lib/components/ui';
	import { toast } from '$lib/stores/toast';

	let { volume, projectId, adminInstanceId, onclose, onsuccess }: {
		volume: Volume | null;
		projectId: string | undefined;
		adminInstanceId?: string;
		onclose: () => void;
		onsuccess: () => void;
	} = $props();

	const inputId = $props.id();
	const maxSize = 2147483647;
	let newSize = $state('');
	let extending = $state(false);
	let error = $state('');
	let invalidated = $state(false);
	let session = $state<{ id: string; projectId: string; token: string; adminInstanceId: string | undefined; transportProjectId: string | undefined } | null>(null);
	let targetId: string | null = null;
	let generation = 0;

	$effect.pre(() => {
		const id = volume?.id ?? null;
		const size = volume?.size;
		const token = $auth.token;
		const scope = projectId;
		const writable = $canWrite;
		const parentId = adminInstanceId;
		const transportProjectId = parentId ? $auth.projectId ?? undefined : scope;
		untrack(() => {
			if (id !== targetId) {
				targetId = id;
				generation++;
				newSize = String(Math.min((size ?? 0) + 10, maxSize));
				error = '';
				extending = false;
				session = id && token && scope ? { id, projectId: scope, token, adminInstanceId: parentId, transportProjectId } : null;
				invalidated = !session || !writable;
			} else if (!writable || !session || session.token !== token || session.projectId !== scope
				|| session.adminInstanceId !== parentId || session.transportProjectId !== transportProjectId) {
				generation++;
				invalidated = true;
			}
		});
	});

	function eligible(target: Volume | null): target is Volume {
		return !!target && Number.isSafeInteger(target.size) && target.size > 0 && target.size < maxSize
			&& Array.isArray(target.attachments)
			&& ((target.status === 'available' && target.attachments.length === 0)
				|| (target.status === 'in-use' && target.attachments.length > 0));
	}
	const sizeValid = $derived(!!volume && Number.isSafeInteger(Number(newSize))
		&& Number(newSize) > volume.size && Number(newSize) <= maxSize);
	const ready = $derived(!invalidated && !!session && $canWrite && !!$auth.token
		&& session.token === $auth.token && session.projectId === projectId && session.adminInstanceId === adminInstanceId && eligible(volume));

	function close() { if (!extending) onclose(); }
	function ownsRequest(scope: NonNullable<typeof session>, requestGeneration: number) {
		return requestGeneration === generation && !invalidated && $canWrite
			&& volume?.id === scope.id && projectId === scope.projectId && $auth.token === scope.token
			&& adminInstanceId === scope.adminInstanceId
			&& (scope.adminInstanceId ? $auth.projectId ?? undefined : projectId) === scope.transportProjectId;
	}

	async function confirmExtend() {
		const target = volume;
		const scope = session;
		if (!target || !scope || extending || !ready) return;
		const requestedSize = Number(newSize);
		if (!sizeValid) {
			error = t('extendModal.invalidSize', { maxSize });
			return;
		}
		const requestGeneration = generation;
		extending = true;
		error = '';
		try {
			const volumePath = scope.adminInstanceId
				? `/api/v1/admin/instances/${encodeURIComponent(scope.adminInstanceId)}/volumes/${encodeURIComponent(scope.id)}`
				: `/api/v1/volumes/${encodeURIComponent(scope.id)}`;
			const current = await api.get<Volume>(volumePath, scope.token, scope.transportProjectId, { refresh: true });
			if (!ownsRequest(scope, requestGeneration)) return;
			if (current.id !== scope.id || !eligible(current) || current.size !== target.size) {
				error = t('extendModal.targetUnavailable');
				return;
			}
			for (const attachment of scope.adminInstanceId ? [] : current.attachments) {
				const serverId = attachment.server_id;
				if (typeof serverId !== 'string' || !serverId) {
					error = t('extendModal.offlineRequired');
					return;
				}
				const server = await api.get<{ id: string; project_id?: string; status: string }>(
					`/api/v1/instances/${encodeURIComponent(serverId)}`, scope.token, scope.projectId, { refresh: true },
				);
				if (!ownsRequest(scope, requestGeneration)) return;
				if (server.id !== serverId || server.project_id !== scope.projectId || server.status !== 'SHUTOFF') {
					error = t('extendModal.offlineRequired');
					return;
				}
			}
			if (!ownsRequest(scope, requestGeneration) || !eligible(volume) || volume.size !== current.size) return;
			const accepted = await api.post<Volume>(
				`${volumePath}/extend`,
				{ new_size: requestedSize }, scope.token, scope.transportProjectId,
			);
			if (!ownsRequest(scope, requestGeneration)) return;
			toast.info(t('extendModal.accepted', { size: accepted.size, status: accepted.status }));
			onsuccess();
		} catch (e) {
			if (ownsRequest(scope, requestGeneration)) error = e instanceof ApiError ? e.message : t('extendModal.extendFailed');
		} finally {
			if (volume?.id === scope.id && requestGeneration === generation) extending = false;
			else if (volume?.id === scope.id && invalidated) extending = false;
		}
	}
</script>

{#if volume}
	<FormModal open={true} title={t('extendModal.title')} submitting={extending} onClose={close}>
		<form onsubmit={(event) => { event.preventDefault(); void confirmExtend(); }} class="space-y-4">
			<Field label={t('extendModal.volumeLabel')}>
				<p class="text-sm text-ink-1 break-all">{volume.name || volume.id} {t('extendModal.statusSummary', { status: volume.status })}</p>
			</Field>
			<Field label={t('extendModal.currentSizeLabel')}>
				<p class="text-sm font-mono text-ink-1">{t('extendModal.currentSize', { size: volume.size })}</p>
			</Field>
			<Alert tone="warning">{t('extendModal.offlineRequired')}</Alert>
			<Alert tone="info">{t('extendModal.guestBoundary')}</Alert>
			<Field label={t('extendModal.newSizeLabel', { minSize: volume.size + 1 })} for={inputId} help={t('extendModal.noShrink')} required>
				<TextInput id={inputId} type="number" inputmode="numeric" bind:value={newSize} disabled={extending || !ready} required ariaInvalid={!sizeValid} />
			</Field>
			{#if invalidated}<Alert tone="warning">{t('extendModal.scopeChanged')}</Alert>
			{:else if !eligible(volume)}<Alert tone="warning">{t('extendModal.targetUnavailable')}</Alert>{/if}
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
		</form>
		{#snippet actions()}
			<Button variant="secondary" onclick={close} disabled={extending}>{t('extendModal.cancel')}</Button>
			<Button onclick={confirmExtend} disabled={extending || !ready || !sizeValid} ariaBusy={extending}>
				{extending ? t('extendModal.extending') : t('extendModal.extend')}
			</Button>
		{/snippet}
	</FormModal>
{/if}
