<script lang="ts">
	import { tick } from 'svelte';
	import type { Workspace } from '$lib/api/chatWorkspaces';
	import type { ChatUsage } from '$lib/api/chatTree';
	import { auth } from '$lib/stores/auth';
	import Modal from '$lib/components/ui/Modal.svelte';
	import ChatUserMenu from './ChatUserMenu.svelte';

	interface Conversation {
		id: string;
		title: string | null;
		model_name: string | null;
		workspace_id: number | null;
		updated_at: string | null;
		title_status?: 'idle' | 'pending' | 'ready' | 'failed' | 'unavailable';
	}
	interface Props {
		conversations: Conversation[];
		workspaces: Workspace[];
		activeConvId: string | null;
		newlyCreatedConversationId?: string | null;
		tempMode?: boolean;
		runningConversationIds?: ReadonlySet<string>;
		busy?: boolean;
		/** 사이드바 열림 여부(데스크톱 접기 / 모바일 드로어). */
		open?: boolean;
		/** 사용자 메뉴 팝오버에 표시할 사용량(우상단 위젯 대체). */
		usage?: ChatUsage | null;
		onSelect: (conv: Conversation) => void;
		onNew: () => void;
		onDelete: (conv: Conversation) => void;
		onAssign: (conv: Conversation, workspaceId: number | null) => void;
		onAgents: () => void;
		onWorkspaces: () => void;
		onToggle: () => void;
		onOpenWorkspace: (workspaceId: number) => void;
		onNewInWorkspace: (workspaceId: number) => void;
		onDeleteWorkspace: (workspace: Workspace) => void;
		onSearch: (query: string) => Promise<Conversation[]>;
		onSettings: () => void;
	}
	let {
		conversations,
		workspaces,
		activeConvId,
		newlyCreatedConversationId = null,
		tempMode = false,
		runningConversationIds = new Set<string>(),
		busy = false,
		open = true,
		usage = null,
		onSelect,
		onNew,
		onDelete,
		onAssign,
		onAgents,
		onWorkspaces,
		onOpenWorkspace,
		onToggle,
		onNewInWorkspace,
		onDeleteWorkspace,
		onSearch,
		onSettings
	}: Props = $props();
	let searchOpen = $state(false);
	let searchQuery = $state('');
	let workspaceMenuId = $state<number | null>(null);
	let searchInput = $state<HTMLInputElement | null>(null);
	let searchRequest = 0;
	let serverSearchResults = $state<Conversation[] | null>(null);
	let userMenuOpen = $state(false);

	$effect(() => {
		const closeWorkspaceMenu = (event: PointerEvent) => {
			if (workspaceMenuId === null || !(event.target instanceof Element)) return;
			if (!event.target.closest('.workspace-menu, [data-workspace-menu-trigger]')) workspaceMenuId = null;
		};
		document.addEventListener('pointerdown', closeWorkspaceMenu);
		return () => document.removeEventListener('pointerdown', closeWorkspaceMenu);
	});
	// 접힌 그룹 키 집합(기본 펼침)
	let collapsed = $state<Record<string, boolean>>({});
	function toggle(key: string) {
		collapsed[key] = !collapsed[key];
	}

	let revealedConversationId: string | null = null;
	$effect(() => {
		if (!newlyCreatedConversationId || newlyCreatedConversationId === revealedConversationId) return;
		const conversation = conversations.find((item) => item.id === newlyCreatedConversationId);
		if (!conversation) return;
		revealedConversationId = conversation.id;
		if (conversation.workspace_id !== null) collapsed[`ws-${conversation.workspace_id}`] = false;
	});

	function conversationLabel(conversation: Conversation): string {
		return conversation.title || (conversation.title_status === 'pending' ? '제목 요약 중' : '새 대화');
	}

	// 제목 드래그앤드롭으로 프로젝트 이동 (Codex식). 드래그 중인 대화 id + drop 대상.
	let draggingId = $state<string | null>(null);
	let dropTargetKey = $state<string | null>(null);
	function onDropTo(workspaceId: number | null) {
		const conv = conversations.find((c) => c.id === draggingId);
		draggingId = null;
		dropTargetKey = null;
		if (conv && conv.workspace_id !== workspaceId) onAssign(conv, workspaceId);
	}
	function deleteWorkspace(workspaceId: number) {
		const workspace = workspaces.find((candidate) => candidate.id === workspaceId);
		workspaceMenuId = null;
		if (workspace) onDeleteWorkspace(workspace);
	}

	interface Group {
		key: string;
		id: number | null;
		name: string;
		convs: Conversation[];
		total: number;
	}

	const grouped = $derived.by(() => {
		const knownIds = new Set(workspaces.map((w) => w.id));

		// 프로젝트는 비어 있어도 디렉터리로 항상 표시한다.
		const wsGroups: Group[] = workspaces.map((w) => {
			const workspaceConversations = conversations.filter((c) => c.workspace_id === w.id);
			return {
				key: `ws-${w.id}`,
				id: w.id,
				name: w.name,
				convs: workspaceConversations.slice(0, 5),
				total: workspaceConversations.length
			};
		});

		// workspace_id 가 없거나 알 수 없는(삭제된) 프로젝트를 가리키면 미분류로.
		const unassigned = conversations.filter(
			(c) => c.workspace_id == null || !knownIds.has(c.workspace_id)
		);

		return { wsGroups, unassigned, hasGroups: wsGroups.length > 0, total: conversations.length };
	});
	const searchResults = $derived.by(() => {
		if (serverSearchResults !== null) return serverSearchResults;
		const normalized = searchQuery.trim().toLowerCase();
		if (!normalized) return conversations.slice(0, 12);
		return conversations
			.filter((conversation) => (conversation.title ?? '새 대화').toLowerCase().includes(normalized))
			.slice(0, 20);
	});
	async function openSearch() {
		searchQuery = '';
		serverSearchResults = null;
		searchOpen = true;
		await tick();
		searchInput?.focus();
	}
	function selectSearchResult(conversation: Conversation) {
		searchOpen = false;
		onSelect(conversation);
	}
	function updateSearchQuery(event: Event) {
		searchQuery = (event.currentTarget as HTMLInputElement).value;
		searchRequest += 1;
		serverSearchResults = null;
	}
	$effect(() => {
		if (!searchOpen) return;
		let canceled = false;
		const request = ++searchRequest;
		serverSearchResults = null;
		void onSearch(searchQuery)
			.then((results) => {
				if (!canceled && request === searchRequest) serverSearchResults = results;
			})
			.catch(() => {
				if (!canceled && request === searchRequest) serverSearchResults = [];
			});
		return () => {
			canceled = true;
		};
	});
	$effect(() => {
		const onKeydown = (event: KeyboardEvent) => {
			if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'i') {
				event.preventDefault();
				void openSearch();
			}
		};
		window.addEventListener('keydown', onKeydown);
		return () => window.removeEventListener('keydown', onKeydown);
	});
</script>

<aside class="sidebar" class:closed={!open}>
	<header class="brand">
		<span class="brand-name">Lumen</span>
		<button type="button" class="brand-toggle" onclick={onToggle} aria-label="사이드바 접기" title="사이드바 접기">
			<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3.5" y="4" width="17" height="16" rx="2.5" /><path d="M10 4v16" /></svg>
		</button>
	</header>
	<div class="top">
		<button type="button" class="new-btn" onclick={onNew}>
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" stroke-linecap="round" stroke-linejoin="round" /></svg>
			새 채팅
		</button>
		<button type="button" class="project-hub" onclick={onWorkspaces}>
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" stroke-linejoin="round" /></svg>
			프로젝트
		</button>
	</div>

	<button type="button" class="search-trigger" onclick={openSearch} aria-label="대화 검색">
		<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
		<span>대화 검색</span>
		<kbd>⌘ I</kbd>
	</button>

	<div class="list">
		{#if grouped.total === 0 && !grouped.hasGroups}
			<p class="empty">대화가 없습니다</p>
		{:else if !grouped.hasGroups}
			{#each grouped.unassigned as conv (conv.id)}
				{@render convRow(conv)}
			{/each}
		{:else}
			{#each grouped.wsGroups as g (g.key)}
				{@render groupHeader(g)}
				{#if !collapsed[g.key]}
					{#each g.convs as conv (conv.id)}
						{@render convRow(conv, true)}
					{/each}
					{#if g.total > g.convs.length}
						<button type="button" class="group-more" onclick={() => onOpenWorkspace(g.id!)}>더보기</button>
					{/if}
				{/if}
			{/each}
			{#if grouped.unassigned.length > 0}
				<div class="unassigned-divider" aria-hidden="true"></div>
				{#each grouped.unassigned as conv (conv.id)}
					{@render convRow(conv)}
				{/each}
			{/if}
		{/if}
	</div>

	<div class="entries">
		<button type="button" class="entry" onclick={onAgents}>
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="7" width="16" height="12" rx="2" /><path d="M9 7V4h6v3M9 13h.01M15 13h.01" stroke-linecap="round" /></svg>
			에이전트
		</button>
	</div>

	<!-- 좌하단 사용자 버튼 → 사용량·설정 팝오버 (헤더 우상단 사용량 위젯 대체) -->
	<div class="user-bar">
		<button
			type="button"
			class="user-btn"
			onclick={() => (userMenuOpen = !userMenuOpen)}
			aria-haspopup="menu"
			aria-expanded={userMenuOpen}
		>
			<span class="user-avatar">{($auth.username ?? '?').slice(0, 2).toUpperCase()}</span>
			<span class="user-name truncate">{$auth.username || '사용자'}</span>
			<svg class="dots" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></svg>
		</button>
		<ChatUserMenu
			open={userMenuOpen}
			username={$auth.username}
			{usage}
			onClose={() => (userMenuOpen = false)}
			{onSettings}
		/>
	</div>
</aside>

<Modal open={searchOpen} onClose={() => (searchOpen = false)} ariaLabel="대화 검색">
	<section class="chat-search-dialog" aria-label="대화 검색">
		<div class="chat-search-input">
			<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" stroke-linecap="round" /></svg>
			<input bind:this={searchInput} value={searchQuery} oninput={updateSearchQuery} type="search" placeholder="대화 검색" autocomplete="off" />
			<kbd>Esc</kbd>
		</div>
		<div class="chat-search-results" role="listbox" aria-label="검색 결과">
			{#if searchResults.length === 0}
				<p class="chat-search-empty">일치하는 대화가 없습니다</p>
			{:else}
				{#each searchResults as conversation (conversation.id)}
					<button type="button" role="option" aria-selected={conversation.id === activeConvId} onclick={() => selectSearchResult(conversation)}>
						<span class="truncate">{conversationLabel(conversation)}</span>
						{#if conversation.model_name}
							<small>{conversation.model_name}</small>
						{/if}
					</button>
				{/each}
			{/if}
		</div>
	</section>
</Modal>
{#snippet groupHeader(g: Group)}

	<div class="group-row">
		<button
			type="button"
			class="group-head"
			class:drop-target={draggingId !== null && dropTargetKey === g.key}
			onclick={() => toggle(g.key)}
			ondragover={(e) => {
				if (draggingId !== null) {
					e.preventDefault();
					dropTargetKey = g.key;
				}
			}}
			ondragleave={() => {
				if (dropTargetKey === g.key) dropTargetKey = null;
			}}
			ondrop={(e) => {
				e.preventDefault();
				onDropTo(g.id);
			}}
			aria-expanded={!collapsed[g.key]}
		>
			{#if collapsed[g.key]}
				<svg class="folder" viewBox="0 0 48 48" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M8.5 8C6.032499 8 4 10.032499 4 12.5v23C4 37.967501 6.032499 40 8.5 40h31c2.467501 0 4.5-2.032499 4.5-4.5v-18C44 15.032499 41.967501 13 39.5 13H24.042969l-4.470703-3.724609C18.584055 8.45211 17.339162 8 16.052734 8zM8.5 11h7.552734c.585573 0 1.149821.205358 1.59961.580078l3.503906 2.919922-3.503906 2.919922c-.449789.37472-1.014037.580078-1.59961.580078H7V12.5C7 11.653501 7.653501 11 8.5 11zm15.542969 5H39.5c.846499 0 1.5.653501 1.5 1.5v18c0 .846499-.653501 1.5-1.5 1.5h-31C7.653501 37 7 36.346499 7 35.5V21h9.052734c1.286428 0 2.531321-.452111 3.519532-1.275391z" /></svg>
			{:else}
				<svg class="folder" viewBox="0 0 48 48" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M8.5 8C6.032499 8 4 10.032499 4 12.5v23.90625h.015625C3.986515 38.276932 5.508389 40 7.501953 40h29.044922c1.87 0 3.555905-1.167006 4.212891-2.917969l5.007812-13.332031v-.003906C46.62354 21.501657 44.900814 19 42.498047 19H42v-1.5C42 15.032499 39.967501 13 37.5 13H24.042969l-4.46875-3.724609A1.50015 1.50015 0 0 0 19.572266 9.275391C18.584102 8.45211 17.339162 8 16.052734 8zM8.5 11h7.552734c.585573 0 1.149821.205358 1.59961.580078l4.886718 4.072266A1.50015 1.50015 0 0 0 23.5 16h14c.846499 0 1.5.653501 1.5 1.5V19H13.453125c-1.87 0-3.555905 1.167006-4.212891 2.917969L7 27.882812V12.5C7 11.653501 7.653501 11 8.5 11zm4.953125 11H42.498047c.39986 0 .609397.305152.466797.677734A1.50015 1.50015 0 0 0 42.960938 22.6875L37.951172 36.027344C37.730157 36.616381 37.176875 37 36.546875 37H7.501953c-.397716 0-.60838-.302901-.46875-.673828A1.50015 1.50015 0 0 0 7.035156 36.324219l5.013672-13.351563C12.269843 22.383619 12.823125 22 13.453125 22z" /></svg>
			{/if}
			<span class="group-name truncate">{g.name}</span>
			<span class="group-count">{g.total}</span>
		</button>
		<div class="group-actions">
			<button type="button" class="group-action" class:active={workspaceMenuId === g.id} onclick={() => (workspaceMenuId = workspaceMenuId === g.id ? null : g.id)} title="프로젝트 옵션" aria-label="프로젝트 옵션" aria-expanded={workspaceMenuId === g.id} data-workspace-menu-trigger>
				<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" /></svg>
			</button>
			<button type="button" class="group-action" onclick={() => onNewInWorkspace(g.id!)} title="이 프로젝트에서 새 채팅" aria-label="이 프로젝트에서 새 채팅">
				<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" stroke-linecap="round" stroke-linejoin="round" /></svg>
			</button>
		</div>
		{#if workspaceMenuId === g.id}
			<div class="workspace-menu" role="menu">
				<button type="button" role="menuitem" onclick={() => { workspaceMenuId = null; onOpenWorkspace(g.id!); }}>프로젝트 설정</button>
				<button type="button" role="menuitem" onclick={() => { workspaceMenuId = null; onOpenWorkspace(g.id!); }}>프로젝트 이름 변경</button>
				<button type="button" role="menuitem" class="danger" onclick={() => deleteWorkspace(g.id!)}>프로젝트 제거</button>
			</div>
		{/if}
	</div>
{/snippet}

{#snippet convRow(conv: Conversation, projectChild = false)}
	<div
		class="item-row"
		class:active={!tempMode && activeConvId === conv.id}
		class:dragging={draggingId === conv.id}
		class:project-child={projectChild}
		draggable={true}
		role="listitem"
		ondragstart={() => (draggingId = conv.id)}
		ondragend={() => {
			dropTargetKey = null;
			draggingId = null;
		}}
	>
		<button type="button" class="item" onclick={() => onSelect(conv)}>
			<span class="item-title">{conversationLabel(conv)}</span>
			{#if runningConversationIds.has(conv.id)}
				<span class="run-indicator" title="응답 생성 중" aria-label="응답 생성 중">
					<span class="run-spinner" aria-hidden="true"></span>
					{#if conv.id !== activeConvId}
						<span class="unread-dot" aria-label="확인하지 않은 실행 중 대화"></span>
					{/if}
				</span>
			{/if}
		</button>
		<button
			type="button"
			class="del"
			disabled={busy}
			onclick={() => onDelete(conv)}
			title="대화 삭제"
			aria-label="대화 삭제"
		>
			<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" stroke-linecap="round" stroke-linejoin="round" /></svg>
		</button>
	</div>
{/snippet}

<style>
	.sidebar {
		width: 16rem;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		min-height: 0;
		border-right: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		transition: margin-left 0.22s ease;
	}
	/* 데스크톱: 접으면 왼쪽으로 밀어내 본문이 전체 폭을 차지 */
	.sidebar.closed {
		margin-left: -16rem;
	}
	/* Compact shell: overlay drawer keeps the transcript at full width below desktop. */
	@media (width < 1024px) {
		.sidebar {
			position: absolute;
			top: 0;
			bottom: 0;
			left: 0;
			z-index: 40;
			box-shadow: 2px 0 16px color-mix(in oklab, var(--color-ink-0) 18%, transparent);
		}
		.sidebar.closed {
			margin-left: -17rem; /* 그림자까지 완전히 숨김 */
		}
	}
	.brand {
		display: flex;
		align-items: center;
		justify-content: space-between;
		box-sizing: border-box;
		block-size: 3.75rem;
		padding: 0 0.75rem;
		border-bottom: 1px solid var(--color-line);
	}
	.brand-name {
		color: var(--color-ink-0);
		font-size: 1rem;
		font-weight: 700;
		letter-spacing: 0.02em;
	}
	.brand-toggle {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border: 1px solid transparent;
		border-radius: 0.45rem;
		background: transparent;
		color: var(--color-ink-2);
		cursor: pointer;
	}
	.brand-toggle:hover,
	.brand-toggle:focus-visible {
		border-color: var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-0);
	}
	.top {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		padding: 0.75rem 0.75rem 0.5rem;
	}
	.project-hub {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		width: 100%;
		padding: 0.5rem 0.7rem;
		border: 1px solid transparent;
		border-radius: 0.6rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s, border-color 0.15s, color 0.15s;
	}
	.project-hub:hover,
	.project-hub:focus-visible {
		border-color: var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-0);
	}
	.new-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		width: 100%;
		padding: 0.5rem 0.7rem;
		border: 1px solid transparent;
		border-radius: 0.6rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s, border-color 0.15s, color 0.15s;
	}
	.new-btn:hover,
	.new-btn:focus-visible {
		border-color: var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-0);
	}
	.search-trigger {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		width: calc(100% - 1.5rem);
		margin: 0 0.75rem 0.5rem;
		padding: 0.45rem 0.6rem;
		border: 1px solid transparent;
		border-radius: 0.55rem;
		background: transparent;
		color: var(--color-ink-3);
		font-size: 0.8125rem;
		cursor: pointer;
	}
	.search-trigger:hover,
	.search-trigger:focus-visible {
		border-color: var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-1);
	}
	.search-trigger kbd {
		margin-left: auto;
		padding: 0.1rem 0.3rem;
		border: 1px solid var(--color-line);
		border-radius: 0.3rem;
		color: var(--color-ink-3);
		font-size: 0.65rem;
	}
	.chat-search-dialog {
		width: min(100vw - 2rem, 34rem);
		max-height: min(70vh, 38rem);
		overflow: hidden;
		border: 1px solid var(--color-line);
		border-radius: 0.85rem;
		background: var(--color-surface-raised);
		box-shadow: 0 24px 64px color-mix(in oklab, var(--color-ink-0) 28%, transparent);
	}
	.chat-search-input {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0.8rem 0.9rem;
		border-bottom: 1px solid var(--color-line);
		color: var(--color-ink-2);
	}
	.chat-search-input input {
		flex: 1;
		min-width: 0;
		border: none;
		outline: none;
		background: transparent;
		color: var(--color-ink-0);
		font-size: 0.9rem;
	}
	.chat-search-input input::placeholder {
		color: var(--color-ink-3);
	}
	.chat-search-input kbd {
		padding: 0.12rem 0.35rem;
		border: 1px solid var(--color-line);
		border-radius: 0.3rem;
		color: var(--color-ink-3);
		font-size: 0.65rem;
	}
	.chat-search-results {
		max-height: 24rem;
		overflow-y: auto;
		padding: 0.35rem;
	}
	.chat-search-results button {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		width: 100%;
		padding: 0.6rem 0.65rem;
		border: none;
		border-radius: 0.5rem;
		background: transparent;
		color: var(--color-ink-1);
		text-align: left;
		cursor: pointer;
	}
	.chat-search-results button:hover,
	.chat-search-results button:focus-visible,
	.chat-search-results button[aria-selected='true'] {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.chat-search-results small {
		color: var(--color-ink-3);
		font-size: 0.68rem;
	}
	.chat-search-empty {
		margin: 0;
		padding: 1.25rem 0.65rem;
		color: var(--color-ink-3);
		font-size: 0.8rem;
	}
	.list {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 0 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.empty {
		padding: 1rem 0.75rem;
		font-size: 0.78rem;
		color: var(--color-ink-3);
	}
	.group-row {
		position: relative;
		display: flex;
		align-items: center;
		margin-top: 0.25rem;
		border-radius: 0.5rem;
	}
	.group-row:hover,
	.group-row:focus-within {
		background: var(--color-surface-base);
	}
	.group-head {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex: 1;
		min-width: 0;
		padding: 0.4rem 0.5rem;
		border: none;
		background: transparent;
		color: var(--color-ink-3);
		font-size: 0.7rem;
		font-weight: 650;
		letter-spacing: 0.03em;
		cursor: pointer;
	}
	.group-head:hover {
		color: var(--color-ink-1);
	}
	.folder {
		flex-shrink: 0;
	}
	.group-name {
		flex: 1;
		min-width: 0;
		text-align: left;
	}
	.group-count {
		flex-shrink: 0;
		color: var(--color-ink-3);
		font-weight: 550;
	}
	.group-actions {
		display: flex;
		align-items: center;
		gap: 0.05rem;
		width: 0;
		overflow: hidden;
		padding-right: 0;
		opacity: 0;
		white-space: nowrap;
		transition: width 0.12s ease, padding-right 0.12s ease, opacity 0.12s ease;
	}
	.group-row:hover .group-actions,
	.group-row:focus-within .group-actions {
		width: 3.8rem;
		padding-right: 0.25rem;
		opacity: 1;
	}
	.group-action {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-3);
		cursor: pointer;
	}
	.group-action:hover,
	.group-action:focus-visible,
	.group-action.active {
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
	}
	.workspace-menu {
		position: absolute;
		z-index: 10;
		top: calc(100% - 0.1rem);
		right: 0.25rem;
		min-width: 10.5rem;
		padding: 0.3rem;
		border: 1px solid var(--color-line);
		border-radius: 0.6rem;
		background: var(--color-surface-raised);
		box-shadow: 0 10px 28px color-mix(in oklab, var(--color-ink-0) 18%, transparent);
	}
	.workspace-menu button {
		display: flex;
		width: 100%;
		padding: 0.45rem 0.55rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.78rem;
		text-align: left;
		cursor: pointer;
	}
	.workspace-menu button:hover,
	.workspace-menu button:focus-visible {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.workspace-menu button.danger {
		color: var(--color-state-danger);
	}
	.group-more {
		align-self: flex-start;
		margin: 0.05rem 0.5rem 0.3rem 1.5rem;
		padding: 0.25rem 0.4rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-3);
		font-size: 0.72rem;
		cursor: pointer;
	}
	.group-more:hover,
	.group-more:focus-visible {
		background: var(--color-surface-base);
		color: var(--color-ink-1);
	}
	.unassigned-divider {
		height: 1px;
		margin: 0.75rem 0.5rem 0.35rem;
		background: var(--color-line);
	}
	.item-row {
		display: flex;
		align-items: center;
		border-radius: 0.5rem;
		transition: background 0.12s;
	}
	.item-row:hover {
		background: var(--color-surface-base);
	}
	.item-row.active {
		background: var(--color-surface-raised);
	}
	.item-row[draggable='true'] {
		cursor: grab;
	}
	.item-row.dragging {
		opacity: 0.45;
	}
	.item-row.project-child {
		margin-left: 0.65rem;
	}
	.group-head.drop-target {
		background: color-mix(in oklab, var(--color-accent) 16%, transparent);
		color: var(--color-accent);
		border-radius: 0.5rem;
		outline: 1px dashed var(--color-accent);
	}
	.item {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex: 1;
		min-width: 0;
		text-align: left;
		padding: 0.5rem 0.6rem;
		border: none;
		background: transparent;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		cursor: pointer;
	}
	.item-row.active .item {
		color: var(--color-ink-0);
	}
	.item-title {
		display: block;
		min-width: 0;
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.run-indicator {
		position: relative;
		display: inline-flex;
		flex: 0 0 1rem;
		align-items: center;
		justify-content: center;
		width: 1rem;
		height: 1rem;
	}
	.run-spinner {
		width: 0.72rem;
		height: 0.72rem;
		border: 1.5px solid color-mix(in oklab, var(--color-accent) 28%, transparent);
		border-top-color: var(--color-accent);
		border-radius: 50%;
		animation: run-spin 0.8s linear infinite;
	}
	.unread-dot {
		position: absolute;
		top: -0.1rem;
		right: -0.1rem;
		width: 0.34rem;
		height: 0.34rem;
		border: 1px solid var(--color-surface-raised);
		border-radius: 50%;
		background: var(--color-accent);
		box-shadow: 0 0 0.35rem color-mix(in oklab, var(--color-accent) 70%, transparent);
	}
	@keyframes run-spin {
		to { transform: rotate(360deg); }
	}
	@media (prefers-reduced-motion: reduce) {
		.run-spinner { animation: none; }
	}
	.del {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.9rem;
		height: 1.9rem;
		margin-right: 0.2rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-3);
		cursor: pointer;
		opacity: 0;
		transition: opacity 0.12s, color 0.12s, background 0.12s;
	}
	.item-row:hover .del,
	.item-row:focus-within .del {
		opacity: 1;
	}
	.del:hover:not(:disabled) {
		color: var(--color-state-danger);
		background: color-mix(in oklab, var(--color-state-danger) 12%, transparent);
	}
	.del:disabled {
		cursor: not-allowed;
		opacity: 0.35;
	}
	.entries {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding-top: 0.5rem;
		margin: 0.25rem 0.75rem 0.75rem;
		border-top: 1px solid var(--color-line);
	}
	.entry {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.7rem;
		border-radius: 0.6rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-1);
		font-size: 0.8125rem;
		font-weight: 550;
		cursor: pointer;
		transition: background 0.15s, color 0.15s, border-color 0.15s;
	}
	.entry:hover {
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
		border-color: var(--color-line-2);
	}
	.user-bar {
		position: relative;
		margin: 0 0.75rem 0.75rem;
	}
	.user-btn {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.45rem 0.55rem;
		border-radius: 0.6rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-1);
		cursor: pointer;
		transition: background 0.15s, border-color 0.15s;
	}
	.user-btn:hover {
		background: var(--color-surface-raised);
		border-color: var(--color-line-2);
	}
	.user-avatar {
		flex-shrink: 0;
		width: 1.7rem;
		height: 1.7rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		background: var(--color-accent);
		color: var(--color-action-on-accent);
		font-size: 0.66rem;
		font-weight: 700;
	}
	.user-name {
		flex: 1;
		min-width: 0;
		text-align: left;
		font-size: 0.8125rem;
		font-weight: 550;
	}
	.dots {
		flex-shrink: 0;
		color: var(--color-ink-3);
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
