<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
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
		{ value: 'inherit', label: '서버 기본값 사용', disabled },
		{ value: 'custom', label: '직접 지정', disabled },
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
		<Field label="이름" for="{id}-name" error={errors.name} help={mode === 'server-create' ? '비워두면 자동 생성됩니다. 영문/숫자로 시작, 최대 63자' : '영문/숫자로 시작, 최대 63자'} required={mode !== 'server-create'}>
			<TextInput id="{id}-name" bind:element={elements.name} bind:value={draft.name} placeholder={mode === 'server-create' ? 'waygate-gateway' : 'my-laptop'} {disabled} required={mode !== 'server-create'} maxlength={63} ariaInvalid={!!errors.name} />
		</Field>
	{/if}
	{#if clientMode}
		<div class="space-y-2">
			<p class="text-xs font-medium text-ink-1">DNS 설정 방식</p>
			<ToggleGroup value={draft.inheritDns ? 'inherit' : 'custom'} options={inheritOptions} onchange={(value) => { draft.inheritDns = value === 'inherit'; }} ariaLabel="DNS 설정 방식" />
		</div>
	{/if}
	{#if clientMode && draft.inheritDns}
		<Field label="DNS" help="서버 기본값 변경 시 함께 적용됩니다.">
			<p class="break-all rounded-md border border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] px-3 py-2 text-sm text-ink-1">{defaults?.dns || '설정 안 함'}</p>
		</Field>
	{:else}
		<Field label="DNS" for="{id}-dns" error={errors.dns} help="쉼표로 최대 두 개. 비우면 설정에 DNS를 넣지 않습니다.">
			<TextInput id="{id}-dns" bind:element={elements.dns} bind:value={draft.dns} placeholder="1.1.1.1, 8.8.8.8" {disabled} maxlength={255} ariaInvalid={!!errors.dns} />
		</Field>
	{/if}
	{#if clientMode}
		<Field label="MTU" for="{id}-mtu" error={errors.mtu} help={`${WAYGATE_MTU_MIN}–${WAYGATE_MTU_MAX}. 비우면 WireGuard 자동값`}>
			<TextInput id="{id}-mtu" bind:element={elements.mtu} bind:value={draft.mtu} inputmode="numeric" placeholder="자동" {disabled} ariaInvalid={!!errors.mtu} />
		</Field>
		<div class="space-y-2">
			<p class="text-xs font-medium text-ink-1">PersistentKeepalive 설정 방식</p>
			<ToggleGroup value={draft.inheritPersistentKeepalive ? 'inherit' : 'custom'} options={inheritOptions} onchange={(value) => { draft.inheritPersistentKeepalive = value === 'inherit'; }} ariaLabel="PersistentKeepalive 설정 방식" />
		</div>
	{/if}
	{#if clientMode && draft.inheritPersistentKeepalive}
		<Field label="PersistentKeepalive (초)" help="서버 기본값 변경 시 함께 적용됩니다.">
			<p class="rounded-md border border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] px-3 py-2 text-sm text-ink-1">{(defaults?.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT) === 0 ? '비활성화 (0초)' : `${defaults?.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT}초`}</p>
		</Field>
	{:else}
		<Field label="PersistentKeepalive (초)" for="{id}-keepalive" error={errors.persistentKeepalive} help={`0–${WAYGATE_KEEPALIVE_MAX}. 0이면 비활성화`} required>
			<TextInput id="{id}-keepalive" bind:element={elements.persistentKeepalive} bind:value={draft.persistentKeepalive} inputmode="numeric" {disabled} required ariaInvalid={!!errors.persistentKeepalive} />
		</Field>
	{/if}
	{#if mode === 'server-create' || mode === 'server-edit'}
		<Alert tone="info">상속 중인 클라이언트와 새 클라이언트의 DNS·Keepalive 기본값입니다. 직접 지정한 값은 유지됩니다. 변경 후 기기에서 <code>.conf</code> 또는 QR을 다시 가져오세요.</Alert>
	{:else if pskEnabled === undefined}
		<p class="text-xs leading-relaxed text-ink-2">
			사전 공유 키(PSK)는 이 클라이언트 전용 32바이트 난수로 자동 생성되어 암호화 저장되며, 발급된 <code>.conf</code>와 QR에 함께 포함됩니다.
		</p>
	{:else}
		<p class="text-xs leading-relaxed text-ink-2">
			사전 공유 키(PSK): {pskEnabled ? '사용 중 · 저장 시 기존 키를 유지합니다.' : '없음 · 기존 연결이 끊기지 않도록 자동으로 추가하지 않습니다.'}
		</p>
		<Alert tone="info">저장한 값은 이 기기에 설정을 다시 가져와야 적용됩니다. 저장 후 <code>.conf</code>를 다시 받거나 QR을 다시 스캔하세요.</Alert>
	{/if}
</div>
