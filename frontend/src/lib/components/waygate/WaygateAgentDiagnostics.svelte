<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/ns/waygate';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { ApiError } from '$lib/api/client';
	import * as waygateApi from '$lib/api/waygate';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import type { DesignTone } from '$lib/design/tokens';
	import type { WaygateDiagnosticsHint, WaygateDiagnosticsVerdict, WaygateServerDiagnostics } from '$lib/types/waygate';

	/**
	 * Read-only agent connection diagnostics for one selected gateway. The parent keys
	 * this component by server and scope, drives refresh() from its panel auto-refresh
	 * and passes the scope liveness check; nothing here mutates Waygate or Nova.
	 */
	let { serverId, serverVmId, token, projectId, isCurrent }: {
		serverId: string;
		serverVmId: string | null;
		token: string;
		projectId: string;
		isCurrent: () => boolean;
	} = $props();

	const CONSOLE_LOG_LINES = 200;
	const VERDICT_TONES: Record<WaygateDiagnosticsVerdict, DesignTone> = {
		ok: 'success',
		never_connected: 'danger',
		not_polling: 'danger',
		not_reporting: 'warning',
		peer_mismatch: 'warning',
	};
	const HINTS: readonly WaygateDiagnosticsHint[] = ['agent_not_polling', 'agent_never_reported', 'agent_status_stale', 'peers_mismatch', 'image_agent_outdated'];

	let destroyed = false;
	onDestroy(() => { destroyed = true; });
	const live = () => !destroyed && isCurrent();

	let diagnostics = $state<WaygateServerDiagnostics | null>(null);
	const hints = $derived(diagnostics ? [...new Set(diagnostics.hints)] : []);
	// unsupported: an older Waygate without the endpoint (404/405); stop asking for this panel.
	let phase = $state<'loading' | 'ready' | 'unsupported' | 'error'>('loading');
	let loadError = $state('');
	let request = 0;
	let inFlight: Promise<void> | null = null;

	export function refresh(): Promise<void> {
		if (!live() || phase === 'unsupported') return Promise.resolve();
		if (inFlight) return inFlight;
		const id = ++request;
		const pending = (async () => {
			try {
				const next = await waygateApi.getServerDiagnostics(serverId, token, projectId);
				if (!live() || id !== request) return;
				diagnostics = next;
				loadError = '';
				phase = 'ready';
			} catch (e) {
				if (!live() || id !== request) return;
				if (e instanceof ApiError && (e.status === 404 || e.status === 405)) {
					diagnostics = null;
					phase = 'unsupported';
					return;
				}
				loadError = e instanceof ApiError ? e.message : t('project.error.server');
				// Keep the last good verdict visible; a transient failure only adds a note.
				if (!diagnostics) phase = 'error';
			}
		})();
		inFlight = pending;
		return pending.finally(() => { if (inFlight === pending) inFlight = null; });
	}

	onMount(() => { void refresh(); });

	function isKnownVerdict(verdict: string): verdict is WaygateDiagnosticsVerdict {
		return Object.hasOwn(VERDICT_TONES, verdict);
	}
	function isKnownHint(hint: string): hint is WaygateDiagnosticsHint {
		return (HINTS as readonly string[]).includes(hint);
	}
	function verdictLabel(verdict: string): string {
		return isKnownVerdict(verdict) ? t(`project.diagnostics.verdict.${verdict}`) : t('project.diagnostics.verdict.unknown', { verdict });
	}
	function hintText(hint: string): string {
		return isKnownHint(hint) ? t(`project.diagnostics.hint.${hint}`) : t('project.diagnostics.hint.unknown', { code: hint });
	}

	function formatAbsolute(iso: string): string {
		const value = new Date(iso);
		return Number.isFinite(value.getTime()) ? value.toLocaleString(intlLocale()) : iso;
	}
	/** Age relative to Waygate's own checked_at, so a skewed browser clock cannot distort it. */
	function formatRelative(iso: string, checkedAt: string): string {
		const at = Date.parse(iso);
		if (!Number.isFinite(at)) return iso;
		const checked = Date.parse(checkedAt);
		const seconds = Math.max(0, Math.round(((Number.isFinite(checked) ? checked : Date.now()) - at) / 1000));
		const format = new Intl.RelativeTimeFormat(intlLocale(), { numeric: 'auto' });
		if (seconds < 60) return format.format(-seconds, 'second');
		if (seconds < 3600) return format.format(-Math.floor(seconds / 60), 'minute');
		if (seconds < 86_400) return format.format(-Math.floor(seconds / 3600), 'hour');
		return format.format(-Math.floor(seconds / 86_400), 'day');
	}
	function selfCheckState(value: boolean | null | undefined, yes: string, no: string): string {
		return value === true ? yes : value === false ? no : 'unknown';
	}

	// ---- Gateway VM console log (existing project-scoped Nova endpoint) ----
	let consoleOpen = $state(false);
	let consoleLog = $state('');
	let consoleLoaded = $state(false);
	let consoleLoading = $state(false);
	let consoleError = $state('');
	let consoleRequest = 0;
	let consolePre = $state<HTMLPreElement | null>(null);

	async function loadConsoleLog() {
		const vmId = serverVmId;
		if (!live() || !vmId) return;
		const id = ++consoleRequest;
		const current = () => live() && id === consoleRequest && vmId === serverVmId;
		consoleOpen = true;
		consoleLoading = true;
		consoleError = '';
		try {
			const output = await waygateApi.getGatewayConsoleLog(vmId, CONSOLE_LOG_LINES, token, projectId);
			if (!current()) return;
			consoleLog = output;
			consoleLoaded = true;
			await tick();
			if (current() && consolePre) consolePre.scrollTop = consolePre.scrollHeight;
		} catch (e) {
			if (!current()) return;
			// The console-log endpoint maps Nova 403/404/409 to console_log_unavailable.
			consoleError = e instanceof ApiError && [403, 404, 409].includes(e.status)
				? t('project.diagnostics.console.unavailable')
				: t('project.diagnostics.console.error', { error: e instanceof ApiError ? e.message : t('project.error.server') });
		} finally {
			if (current()) consoleLoading = false;
		}
	}
	function hideConsoleLog() {
		consoleRequest += 1;
		consoleOpen = false;
		consoleLoading = false;
	}
</script>

<section class="mb-8 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4" aria-labelledby="waygate-agent-diagnostics-heading">
	<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
		<h3 id="waygate-agent-diagnostics-heading" class="text-sm font-medium text-[var(--color-ink-1)]">{t('project.diagnostics.heading')}</h3>
		{#if phase === 'ready' && diagnostics}
			<Pill tone={isKnownVerdict(diagnostics.verdict) ? VERDICT_TONES[diagnostics.verdict] : 'neutral'} dot>
				<span data-testid="waygate-diagnostics-verdict">{verdictLabel(diagnostics.verdict)}</span>
			</Pill>
		{/if}
	</div>

	{#if phase === 'loading'}
		<LoadingState variant="section" label={t('project.diagnostics.loading')} />
	{:else if phase === 'unsupported'}
		<p class="break-keep text-xs text-[var(--color-ink-3)]">{t('project.diagnostics.unsupported')}</p>
	{:else if phase === 'error'}
		<p class="break-keep text-xs text-[var(--color-ink-2)]">{t('project.diagnostics.error', { error: loadError })}</p>
	{:else if diagnostics}
		{@const checkedAt = diagnostics.checked_at}
		{@const selfCheck = diagnostics.last_status?.diagnostics}
		<dl class="grid grid-cols-1 gap-3 text-xs lg:grid-cols-2">
			{#each [
				{ key: 'register', label: t('project.diagnostics.label.register'), at: diagnostics.last_register_at },
				{ key: 'desired', label: t('project.diagnostics.label.desiredState'), at: diagnostics.last_desired_state_at },
				{ key: 'status', label: t('project.diagnostics.label.statusReport'), at: diagnostics.last_status_at },
			] as row (row.key)}
				<div>
					<dt class="text-[var(--color-ink-3)]">{row.label}</dt>
					<dd class="mt-0.5 break-keep text-[var(--color-ink-1)]">
						{#if row.at}
							<time datetime={row.at} title={row.at}>{formatRelative(row.at, checkedAt)}</time>
							<span class="text-[var(--color-ink-3)]"> · {formatAbsolute(row.at)}</span>
						{:else}
							{t('project.diagnostics.never')}
						{/if}
					</dd>
				</div>
			{/each}
			<div>
				<dt class="text-[var(--color-ink-3)]">{t('project.diagnostics.label.peers')}</dt>
				<!-- wg_interface_up=false means the agent could not observe peers, not an empty peer set. -->
				<dd class="mt-0.5 text-[var(--color-ink-1)]">{t('project.diagnostics.peersValue', { reported: diagnostics.last_status && selfCheck?.wg_interface_up !== false ? String(diagnostics.last_status.peers) : '-', expected: diagnostics.expected.enabled_clients })}</dd>
			</div>
			<div>
				<dt class="text-[var(--color-ink-3)]">{t('project.diagnostics.label.agent')}</dt>
				<dd class="mt-0.5 break-all text-[var(--color-ink-1)]">{t('project.diagnostics.agentValue', {
					mode: diagnostics.agent.install_mode ?? '-',
					intervalKnown: diagnostics.agent.report_interval_seconds == null ? 'no' : 'yes',
					interval: diagnostics.agent.report_interval_seconds ?? 0,
				})}</dd>
				{#if diagnostics.agent.image_id}
					<dd class="mt-0.5 break-all font-mono text-[var(--color-ink-3)]">{t('project.diagnostics.agentImage', { image: diagnostics.agent.image_id })}</dd>
				{/if}
			</div>
			{#if selfCheck}
				<div>
					<dt class="text-[var(--color-ink-3)]">{t('project.diagnostics.label.selfCheck')}</dt>
					<dd class="mt-0.5 text-[var(--color-ink-1)]">{t('project.diagnostics.selfCheck.reconcile', { state: selfCheckState(selfCheck.reconcile_ok, 'ok', 'failed') })}</dd>
					<dd class="mt-0.5 text-[var(--color-ink-1)]">{t('project.diagnostics.selfCheck.interface', { state: selfCheckState(selfCheck.wg_interface_up, 'up', 'down') })}</dd>
					{#if selfCheck.error}
						<dd class="mt-0.5 break-all font-mono text-[var(--color-ink-2)]">{t('project.diagnostics.selfCheck.error', { error: selfCheck.error })}</dd>
					{/if}
				</div>
			{/if}
		</dl>
		{#if hints.length}
			<ul class="mt-3 space-y-2" aria-label={t('project.diagnostics.hintsLabel')}>
				{#each hints as hint (hint)}
					<li><Alert tone={diagnostics.verdict === 'ok' ? 'info' : 'warning'}><span data-hint={hint}>{hintText(hint)}</span></Alert></li>
				{/each}
			</ul>
		{/if}
		{#if loadError}
			<p class="mt-2 break-keep text-xs text-[var(--color-ink-3)]">{t('project.diagnostics.staleError', { error: loadError })}</p>
		{/if}
		<p class="mt-2 text-xs text-[var(--color-ink-3)]">{t('project.diagnostics.checkedAt', { time: formatAbsolute(checkedAt) })}</p>
	{/if}

	<div class="mt-4 border-t border-[var(--color-line)] pt-3">
		{#if !serverVmId}
			<p class="break-keep text-xs text-[var(--color-ink-3)]">{t('project.diagnostics.console.noVm')}</p>
		{:else}
			<div class="flex flex-wrap items-center gap-2">
				{#if consoleOpen}
					<Button variant="secondary" size="sm" onclick={() => void loadConsoleLog()} disabled={consoleLoading} ariaBusy={consoleLoading}>{t('project.diagnostics.console.refresh')}</Button>
					<Button variant="ghost" size="sm" onclick={hideConsoleLog} ariaExpanded={true}>{t('project.diagnostics.console.hide')}</Button>
				{:else}
					<Button variant="secondary" size="sm" onclick={() => void loadConsoleLog()} ariaExpanded={false}>{t('project.diagnostics.console.open')}</Button>
				{/if}
			</div>
			{#if consoleOpen}
				<p class="mt-3 text-xs text-[var(--color-ink-3)]">{t('project.diagnostics.console.title', { lines: CONSOLE_LOG_LINES })}</p>
				{#if consoleError}
					<Alert tone="danger" class="mt-2">{consoleError}</Alert>
				{/if}
				{#if consoleLoading && !consoleLoaded}
					<LoadingState variant="section" label={t('project.diagnostics.console.loading')} />
				{:else if consoleLoaded}
					<pre
						bind:this={consolePre}
						aria-busy={consoleLoading}
						aria-label={t('project.diagnostics.console.label')}
						class="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded border border-[var(--color-line)] bg-[var(--color-surface-canvas)] p-3 font-mono text-xs text-[var(--color-ink-2)]"
					>{consoleLog || t('project.diagnostics.console.empty')}</pre>
				{/if}
			{/if}
		{/if}
	</div>
</section>
