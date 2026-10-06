<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/ns/chat-panel';
	import ChatMessage from './ChatMessage.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import ProgressTrack from '$lib/components/ui/ProgressTrack.svelte';
	import { messageEntrance, type MessageEntrance } from './messageMotion';
	import { activityIsRunning, visibleActivityItems } from './chatActivityPresentation';
	import { type AvailableModel, type ChatMessage as ChatMsg } from '$lib/api/chatTree';
	import { projectMessagesForDisplay } from '$lib/api/chatTree';
	import type { StreamMetrics } from '$lib/api/chatMetrics';
	import { toolActivityFromCanonicalParts, type ToolActivityItem } from '$lib/api/chatToolActivity';
	import type { RunActivityItem } from '$lib/api/chatRunReducer';

	type DisplayMessage = ChatMsg & {
		streaming?: boolean;
		metrics?: StreamMetrics | null;
		toolItems?: ToolActivityItem[];
		reasoning?: string | null;
		activityItems?: RunActivityItem[];
		sessionEntrance?: MessageEntrance;
	};

	type AgentActivity = {
		label: string;
		startedAt: string;
	};
	type StarterPrompt = {
		label: string;
		prompt: string;
	};

	interface Props {
		activePath: DisplayMessage[];
		models: AvailableModel[];
		busy?: boolean;
		loading?: boolean;
		modelLocked?: boolean;
		/** 메시지 id → 생성 속도 계측(런타임, 미저장). 낙관적 draft 는 message.metrics 로 직접 전달. */
		metricsById?: Map<string, StreamMetrics>;
		toolActivity?: string | null;
		agentActivity?: AgentActivity | null;
		manualCompactionActivity?: string | null;
		error?: string | null;
		empty?: boolean;
		starterPrompts?: readonly StarterPrompt[];
		onStarterPrompt?: (prompt: string) => void;
		conversationKey?: string;
		hasBefore?: boolean;
		hasAfter?: boolean;
		loadingHistory?: boolean;
		newHistoryActivity?: boolean;
		onLoadBefore?: () => Promise<void>;
		onLoadAfter?: () => Promise<void>;
		onLoadFirst?: () => Promise<boolean>;
		onLoadLatest?: () => Promise<boolean>;
		onCopy: (text: string) => void;
		onRegenerate: (messageId: string, modelName: string) => void;
		onRetry: (messageId: string) => void;
		onFork: (messageId: string) => void;
		onSwitchVersion: (messageId: string, direction: -1 | 1) => void;
	}
	let {
		activePath,
		models,
		busy = false,
		loading = false,
		modelLocked = false,
		metricsById = new Map<string, StreamMetrics>(),
		toolActivity = null,
		agentActivity = null,
		manualCompactionActivity = null,
		error = null,
		empty = false,
		starterPrompts = [],
		onStarterPrompt,
		conversationKey = '',
		hasBefore = false,
		hasAfter = false,
		loadingHistory = false,
		newHistoryActivity = false,
		onLoadBefore,
		onLoadAfter,
		onLoadFirst,
		onLoadLatest,
		onCopy,
		onRegenerate,
		onRetry,
		onFork,
		onSwitchVersion
	}: Props = $props();

	let scrollEl = $state<HTMLDivElement | null>(null);
	let followingLatest = $state(true);
	let navigatingHistory = $state(false);
	let activityNow = $state(Date.now());
	let scrollAfterTickPending = false;

	$effect(() => {
		if (!agentActivity) return;
		activityNow = Date.now();
		const interval = window.setInterval(() => (activityNow = Date.now()), 1_000);
		return () => window.clearInterval(interval);
	});

	function activityElapsed(startedAt: string): string {
		const elapsedSeconds = Math.max(0, Math.floor((activityNow - Date.parse(startedAt)) / 1_000));
		const minutes = Math.floor(elapsedSeconds / 60);
		const seconds = elapsedSeconds % 60;
		return minutes ? t('window.elapsedMinutesSeconds', { minutes, seconds }) : t('window.elapsedSeconds', { seconds });
	}

	function restoredToolItems(message: DisplayMessage): ToolActivityItem[] {
		const toolItems = message.tool_items?.length
			? message.tool_items
			: message.toolItems?.length
				? message.toolItems
				: toolActivityFromCanonicalParts(message.parts);
		const skills =
			message.execution?.skills ??
			(message.execution?.skill_ids ?? []).map((id) => ({ id, name: t('window.skillFallback', { id }) }));
		return [
			...toolItems,
			...skills.map((skill) => ({
				id: `skill:${skill.id}`,
				name: skill.name,
				args: null,
				result: t('window.skillApplied'),
				running: false
			}))
		];
	}


	function modelDisplay(name: string | null | undefined): string | null {
		if (!name) return null;
		return models.find((m) => m.model_name === name)?.display_name ?? name;
	}

	const displayedPath = $derived<DisplayMessage[]>(projectMessagesForDisplay(activePath) as DisplayMessage[]);
	const replyHasProgress = $derived(displayedPath.some((message) => {
		if (!message.streaming) return false;
		const activity = message.activityItems ?? message.execution?.activity ?? [];
		const visible = visibleActivityItems(activity, true);
		return Boolean(message.content.length || visible.some((item) => activityIsRunning(item, activity, true)) ||
			(!visible.length && (message.reasoning || restoredToolItems(message).some((item) => item.running))));
	}));
	const externalProgress = $derived(!replyHasProgress && Boolean(manualCompactionActivity || agentActivity || toolActivity));

	function scrollToLatest() {
		const el = scrollEl;
		if (!el) return;
		el.scrollTop = el.scrollHeight;
		followingLatest = true;
	}
	function scheduleScrollToLatest() {
		if (scrollAfterTickPending) return;
		scrollAfterTickPending = true;
		void tick().then(() => {
			scrollAfterTickPending = false;
			if (followingLatest) scrollToLatest();
		});
	}

	function viewportAnchor(): { id: string; top: number } | null {
		const container = scrollEl;
		if (!container) return null;
		const viewportTop = container.getBoundingClientRect().top;
		for (const element of container.querySelectorAll<HTMLElement>('[data-history-message-id]')) {
			const rect = element.getBoundingClientRect();
			if (rect.bottom >= viewportTop) return { id: element.dataset.historyMessageId ?? '', top: rect.top };
		}
		return null;
	}

	async function moveHistory(direction: 'before' | 'after') {
		const loader = direction === 'before' ? onLoadBefore : onLoadAfter;
		if (!loader || navigatingHistory || loadingHistory) return;
		const anchor = viewportAnchor();
		navigatingHistory = true;
		try {
			await loader();
			await tick();
			if (!anchor || !scrollEl) return;
			const retained = Array.from(scrollEl.querySelectorAll<HTMLElement>('[data-history-message-id]'))
				.find((element) => element.dataset.historyMessageId === anchor.id);
			if (retained) scrollEl.scrollTop += retained.getBoundingClientRect().top - anchor.top;
		} finally {
			navigatingHistory = false;
		}
	}

	async function jumpHistory(anchor: 'first' | 'latest') {
		const loader = anchor === 'first' ? onLoadFirst : onLoadLatest;
		if (!loader || navigatingHistory || loadingHistory) return;
		navigatingHistory = true;
		try {
			const loaded = await loader();
			await tick();
			if (!loaded || !scrollEl) return;
			if (anchor === 'latest') scrollToLatest();
			else {
				scrollEl.scrollTop = 0;
				followingLatest = !hasAfter;
			}
		} finally {
			navigatingHistory = false;
		}
	}

	function onScroll() {
		const el = scrollEl;
		if (!el) return;
		followingLatest = el.scrollHeight - el.clientHeight - el.scrollTop <= 64;
	}
	$effect(() => {
		void conversationKey;
		followingLatest = true;
		scheduleScrollToLatest();
	});

	// Incoming stream deltas must not steal the reader's position after they scroll away.
	$effect(() => {
		void displayedPath.length;
		const last = displayedPath[displayedPath.length - 1];
		if (last) {
			void last.content;
			void last.toolItems;
		}
		if (followingLatest) scheduleScrollToLatest();
	});

	$effect(() => {
		void manualCompactionActivity;
		if (followingLatest) scheduleScrollToLatest();
	});
</script>

<div class="window">
	{#if loading}
		<div class="load-bar" role="status" aria-label={t('window.loading')}><span>{t('window.loading')}</span><ProgressTrack value={null} label={t('window.loading')} size="xs" /></div>
	{/if}
	<div class="scroll" bind:this={scrollEl} onscroll={onScroll}>
		{#if empty}
			<div class="welcome">
				<div class="welcome-mark">
					<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7A8.5 8.5 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z" stroke-linecap="round" stroke-linejoin="round" /></svg>
				</div>
				<h2>{t('window.welcomeTitle')}</h2>
				<p>{t('window.welcomeDescription')}</p>
				{#if starterPrompts.length}
					<div class="starter-prompts" aria-label={t('window.starterSuggestions')}>
						{#each starterPrompts as starter (starter.label)}
							<Button variant="outline" size="xs" onclick={() => onStarterPrompt?.(starter.prompt)}>
								{starter.label}
							</Button>
						{/each}
					</div>
				{/if}
			</div>
		{:else}
			<div class="stream">
				{#if onLoadFirst && onLoadLatest}
					<nav class="history-nav" aria-label={t('window.historyNavigation')}>
						<Button variant="ghost" size="xs" onclick={() => jumpHistory('first')} disabled={!hasBefore || navigatingHistory || loadingHistory}>{t('window.first')}</Button>
						<Button variant="ghost" size="xs" onclick={() => moveHistory('before')} disabled={!hasBefore || navigatingHistory || loadingHistory}>{t('window.previous')}</Button>
						<Button variant="ghost" size="xs" onclick={() => moveHistory('after')} disabled={!hasAfter || navigatingHistory || loadingHistory}>{t('window.next')}</Button>
						<Button variant="ghost" size="xs" onclick={() => jumpHistory('latest')} disabled={!hasAfter || navigatingHistory || loadingHistory}>{t('window.latest')}</Button>
					</nav>
				{/if}
				{#if loadingHistory}
					<div class="history-loading"><ActivityIndicator label={t('window.historyLoading')} /></div>
				{/if}
				{#if newHistoryActivity}
					<div class="history-activity motion-enter" role="status">
						<span>{t('window.newResponse')}</span>
						<Button variant="accent" size="xs" onclick={() => jumpHistory('latest')}>{t('window.viewLatestResponse')}</Button>
					</div>
				{/if}
				{#each displayedPath as msg (msg.sessionEntrance ?? msg.id)}
					<div data-history-message-id={msg.id} use:messageEntrance={{ ticket: msg.sessionEntrance, suppressed: loading || loadingHistory || navigatingHistory }}>
						<ChatMessage
							message={msg}
							{models}
							{busy}
							{modelLocked}
							metrics={msg.metrics ?? metricsById.get(msg.id) ?? null}
							toolItems={restoredToolItems(msg)}
							reasoning={msg.reasoning ?? ''}
							activityItems={msg.activityItems ?? msg.execution?.activity ?? []}
							progressElsewhere={externalProgress}
							liveMotion={Boolean(msg.sessionEntrance)}
							hasPreviousVersion={msg.branch?.previous_id !== null && msg.branch?.previous_id !== undefined}
							hasNextVersion={msg.branch?.next_id !== null && msg.branch?.next_id !== undefined}
							modelDisplayName={modelDisplay(msg.model_name)}
							{onCopy}
							onRegenerate={(model) => onRegenerate(msg.id, model)}
							onRetry={() => onRetry(msg.id)}
							onFork={() => onFork(msg.id)}
							onPrevVersion={() => onSwitchVersion(msg.id, -1)}
							onNextVersion={() => onSwitchVersion(msg.id, 1)}
						/>
					</div>
				{/each}
				{#if externalProgress && manualCompactionActivity}
					<div class="context-activity" role="status" aria-live="polite" aria-atomic="true">
						<ActivityIndicator variant="orbit" />
						<span>{manualCompactionActivity}</span>
					</div>
				{:else if externalProgress && agentActivity}
					<div class="agent-activity" role="status" aria-live="polite" aria-atomic="true">
						<ActivityIndicator variant="orbit" />
						<span>{agentActivity.label}</span>
						<span class="activity-elapsed" aria-hidden="true">· {activityElapsed(agentActivity.startedAt)}</span>
					</div>
				{:else if externalProgress && toolActivity}
					<div class="tool-activity" role="status" aria-live="polite">
						<ActivityIndicator />
						{t('window.toolInProgress', { tool: toolActivity })}
					</div>
				{/if}
			</div>
		{/if}
	</div>

	{#if !empty && !followingLatest}
		<div class="latest-control motion-enter">
			<Button variant="accent" size="sm" onclick={() => hasAfter ? jumpHistory('latest') : scrollToLatest()}>
				{hasAfter ? t('window.goToLatestHistory') : busy ? t('window.followResponse') : t('window.goToLatestMessage')}
			</Button>
		</div>
	{/if}

	{#if error}
		<div class="error-bar" role="alert">{error}</div>
	{/if}
</div>

<style>
	.window {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		min-width: 0;
		position: relative;
	}
	.load-bar {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		color: var(--color-ink-2);
		background: var(--color-surface-base);
		z-index: 5;
	}
	.scroll {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 1.5rem 1rem;
	}
	.stream {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 52rem;
		margin: 0 auto;
	}
	.history-nav {
		position: sticky;
		top: 0;
		z-index: 2;
		align-self: center;
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.25rem;
		padding: 0.25rem;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
	}
	.history-loading {
		align-self: center;
		color: var(--color-ink-2);
		font-size: 0.75rem;
		padding: 0.25rem 0.5rem;
	}
	.history-activity {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.75rem;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-md);
		background: var(--color-surface-sunken);
		color: var(--color-ink-1);
		font-size: 0.8rem;
	}
	.latest-control {
		position: absolute;
		right: 1.25rem;
		bottom: 1.25rem;
		z-index: 2;
	}
	.welcome {
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		gap: 0.4rem;
	}
	.welcome-mark {
		width: 3.5rem;
		height: 3.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 1rem;
		margin-bottom: 0.6rem;
		color: var(--color-accent);
		background: var(--color-surface-sunken);
		border: 1px solid var(--color-line);
	}
	.welcome h2 {
		margin: 0;
		font-size: 1.15rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.welcome p {
		margin: 0;
		font-size: 0.85rem;
		color: var(--color-ink-2);
	}
	.starter-prompts {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.5rem;
		max-width: 34rem;
		margin-top: 0.85rem;
	}
	.tool-activity,
	.agent-activity,
	.context-activity {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.78rem;
		color: var(--color-ink-2);
	}
	.agent-activity,
	.context-activity {
		margin-top: 0.5rem;
		font-size: 0.8125rem;
	}
	.context-activity {
		color: var(--color-accent);
	}
	.activity-elapsed {
		color: var(--color-ink-2);
		font-variant-numeric: tabular-nums;
	}
	.error-bar {
		margin: 0 1rem 0.75rem;
		padding: 0.55rem 0.8rem;
		border-radius: 0.5rem;
		font-size: 0.8rem;
		color: var(--color-state-danger);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
		border: 1px solid color-mix(in oklab, var(--color-state-danger) 35%, transparent);
	}
</style>
