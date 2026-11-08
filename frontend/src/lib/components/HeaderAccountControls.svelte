<script lang="ts">
	import { tick, type Snippet } from 'svelte';
	import { page } from '$app/stores';
	import ProfileImage from '$lib/components/account/ProfileImage.svelte';
	import { theme, resolvedTheme } from '$lib/stores/theme';
	import { t } from '$lib/i18n/ns/shell';
	import { t as tn } from '$lib/i18n/ns/nav';
	import { t as tAccount } from '$lib/i18n/ns/account';

	interface Props {
		username: string;
		title?: string;
		/** Mirrors the header bell indicator (announcements, usage reminders, usage load failure). */
		unread: boolean;
		logoutDisabled: boolean;
		onlogout: () => void;
		/** Mockup profiles may only navigate to their allowed paths. */
		allowPath?: (href: string) => boolean;
	}

	let { username, title, unread, logoutDisabled, onlogout, allowPath = () => true }: Props = $props();

	const id = $props.id();
	const menuId = `${id}-profile-menu`;
	let open = $state(false);
	let root = $state<HTMLDivElement | null>(null);
	let trigger = $state<HTMLButtonElement | null>(null);
	let menu = $state<HTMLDivElement | null>(null);

	const links = $derived([
		{ key: 'account', href: '/dashboard/account', label: tn('sections.account'), icon: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M12 14a7 7 0 0 0-7 7h14a7 7 0 0 0-7-7' },
		{ key: 'myResources', href: '/dashboard/my-resources', label: tn('routes.myResources'), icon: 'M4 6h16M4 12h16M4 18h10' },
		{ key: 'notifications', href: '/dashboard/notifications', label: tn('routes.notifications'), icon: 'M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 0 0-4-5.7V5a2 2 0 1 0-4 0v.3C7.7 6.2 6 8.4 6 11v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9' },
		{ key: 'docs', href: '/docs', label: tn('items.documentation'), icon: 'M12 6v14M4 6h5a3 3 0 0 1 3 3v11a2 2 0 0 0-2-2H4zM20 6h-5a3 3 0 0 0-3 3v11a2 2 0 0 1 2-2h6z' },
	].filter(link => allowPath(link.href)));
	const dark = $derived($resolvedTheme === 'dark');
	const triggerLabel = $derived(unread ? `${t('profileMenu.open')}. ${t('profileMenu.unread')}` : t('profileMenu.open'));

	function items(): HTMLElement[] {
		return Array.from(menu?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not([disabled])') ?? []);
	}

	async function show() {
		open = true;
		await tick();
		items()[0]?.focus();
	}

	function close(restoreFocus = false) {
		open = false;
		if (restoreFocus) trigger?.focus();
	}

	function toggleTheme() {
		theme.set(dark ? 'light' : 'dark');
	}

	function logout() {
		// Return focus to a mounted control so a cancelled confirmation does not drop it to <body>.
		close(true);
		onlogout();
	}

	function triggerKeydown(event: KeyboardEvent) {
		if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
		event.preventDefault();
		void show().then(() => { if (event.key === 'ArrowUp') items().at(-1)?.focus(); });
	}

	function menuKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			close(true);
			return;
		}
		if (event.key === 'Tab') {
			close();
			return;
		}
		if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
		event.preventDefault();
		const list = items();
		const index = list.indexOf(document.activeElement as HTMLElement);
		const next = event.key === 'Home' ? 0
			: event.key === 'End' ? list.length - 1
			: (index + (event.key === 'ArrowUp' ? -1 : 1) + list.length) % list.length;
		list[next]?.focus();
	}

	function focusout(event: FocusEvent) {
		const next = event.relatedTarget;
		if (next instanceof Node && root?.contains(next)) return;
		if (next instanceof Node) close();
	}

	/** An outside tap only dismisses the menu: the rest of that gesture must not reach the control underneath. */
	function swallowDismissGesture() {
		const events = ['pointerup', 'mousedown', 'mouseup', 'click'] as const;
		const swallow = (event: Event) => {
			// The avatar itself starts a new interaction rather than finishing the dismissing tap.
			if (root?.contains(event.target as Node)) {
				release();
				return;
			}
			event.preventDefault();
			event.stopPropagation();
			if (event.type === 'click') release();
		};
		// A gesture that turns into a scroll never produces a click; do not swallow a later tap.
		const timer = window.setTimeout(release, 700);
		function release() {
			window.clearTimeout(timer);
			for (const type of events) window.removeEventListener(type, swallow, true);
			window.removeEventListener('pointercancel', release, true);
		}
		for (const type of events) window.addEventListener(type, swallow, true);
		window.addEventListener('pointercancel', release, true);
	}

	$effect(() => {
		if (!open) return;
		const onPointerDown = (event: PointerEvent) => {
			if (!root || root.contains(event.target as Node)) return;
			event.preventDefault();
			event.stopPropagation();
			close();
			swallowDismissGesture();
		};
		window.addEventListener('pointerdown', onPointerDown, true);
		return () => window.removeEventListener('pointerdown', onPointerDown, true);
	});

	$effect(() => {
		$page.url.pathname;
		open = false;
	});
</script>

	<div class="relative shrink-0" bind:this={root} onfocusout={focusout}>
		<button
			bind:this={trigger}
			type="button"
			class="relative flex size-11 shrink-0 items-center justify-center rounded-full focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
			title={title || username}
			aria-label={triggerLabel}
			aria-haspopup="menu"
			aria-expanded={open}
			aria-controls={menuId}
			onclick={() => (open ? close() : void show())}
			onkeydown={triggerKeydown}
		>
			<ProfileImage name={username} label={tAccount('profile.image.alt')} />
			{#if unread}<span class="absolute right-1.5 top-1.5 size-2 rounded-full bg-[var(--color-state-danger)] ring-2 ring-[var(--color-surface-base)]" data-unread-indicator aria-hidden="true"></span>{/if}
		</button>
		{#if open}
			<div
				bind:this={menu}
				id={menuId}
				role="menu"
				tabindex="-1"
				aria-label={t('profileMenu.label')}
				class="motion-pop absolute right-0 top-full z-[var(--z-popover)] mt-2 w-64 max-w-[calc(100vw-1rem)] rounded-lg border border-line-2 bg-surface-raised py-1 shadow-[var(--shadow-popover)]"
				onkeydown={menuKeydown}
			>
				<p class="truncate px-4 pb-2 pt-2 text-xs text-ink-2" title={title || username}>{title || username}</p>
				{#each links as link (link.key)}
					<a
						href={link.href}
						role="menuitem"
						tabindex="-1"
						data-profile-menu-item={link.key}
						class="flex min-h-11 items-center gap-3 px-4 text-sm text-ink-1 transition-colors hover:bg-surface-selected hover:text-ink-0 focus-visible:bg-surface-selected focus-visible:text-ink-0 focus-visible:outline-none"
						onclick={() => close()}
					>
						<svg class="size-4 shrink-0 text-ink-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d={link.icon} /></svg>
						<span class="min-w-0 flex-1 truncate">{link.label}</span>
						{#if link.key === 'notifications' && unread}
							<span class="size-2 shrink-0 rounded-full bg-[var(--color-state-danger)]" data-unread-indicator aria-hidden="true"></span>
							<span class="sr-only">{t('profileMenu.unread')}</span>
						{/if}
					</a>
				{/each}
				<button
					type="button"
					role="menuitemcheckbox"
					tabindex="-1"
					aria-checked={dark}
					data-profile-menu-item="theme"
					class="flex min-h-11 w-full items-center gap-3 px-4 text-left text-sm text-ink-1 transition-colors hover:bg-surface-selected hover:text-ink-0 focus-visible:bg-surface-selected focus-visible:text-ink-0 focus-visible:outline-none"
					onclick={toggleTheme}
				>
					<svg class="size-4 shrink-0 text-ink-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" /></svg>
					<span class="min-w-0 flex-1 truncate">{t('theme.dark')}</span>
					<span class="relative h-5 w-9 shrink-0 rounded-full border border-line-2 transition-colors {dark ? 'bg-accent' : 'bg-surface-sunken'}" aria-hidden="true">
						<span class="absolute top-0.5 size-3.5 rounded-full bg-surface-raised shadow-sm transition-[left] motion-reduce:transition-none {dark ? 'left-[1.125rem]' : 'left-0.5'}"></span>
					</span>
				</button>
				<div role="separator" class="my-1 border-t border-line"></div>
				<button
					type="button"
					role="menuitem"
					tabindex="-1"
					disabled={logoutDisabled}
					data-profile-menu-item="logout"
					class="flex min-h-11 w-full items-center gap-3 px-4 text-left text-sm text-state-danger-text transition-colors hover:bg-surface-selected focus-visible:bg-surface-selected focus-visible:outline-none disabled:opacity-50"
					onclick={logout}
				>
					<svg class="size-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
					<span class="min-w-0 flex-1 truncate">{t('logout.action')}</span>
				</button>
			</div>
		{/if}
	</div>
