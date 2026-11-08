import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { theme, resolvedTheme } from '$lib/stores/theme';
import Fixture from './HeaderAccountControlsFixture.svelte';

const viewport = vi.hoisted(() => ({ current: true }));
vi.mock('$lib/utils/mobileViewport', () => ({ mobileViewport: viewport }));

function trigger() {
	return screen.getByRole('button', { name: /프로필 메뉴 열기/ });
}

async function openMenu() {
	await fireEvent.click(trigger());
	await tick();
	return screen.getByRole('menu', { name: '프로필 메뉴' });
}

describe('HeaderAccountControls', () => {
	beforeEach(() => {
		viewport.current = true;
		theme.set('light');
	});
	afterEach(() => {
		localStorage.clear();
	});

	it('renders the avatar menu on desktop outside mobile', async () => {
		viewport.current = false;
		render(Fixture);
		const button = trigger();
		expect(button.getAttribute('aria-haspopup')).toBe('menu');
		expect(button.getAttribute('aria-expanded')).toBe('false');
		const menu = await openMenu();
		expect(menu).toBeTruthy();
	});

	it('replaces docs, theme, bell and logout with one avatar menu', async () => {
		render(Fixture);
		const button = trigger();
		expect(button.getAttribute('aria-haspopup')).toBe('menu');
		expect(button.getAttribute('aria-expanded')).toBe('false');

		const menu = await openMenu();
		expect(button.getAttribute('aria-expanded')).toBe('true');
		expect(button.getAttribute('aria-controls')).toBe(menu.id);
		const items = Array.from(menu.querySelectorAll('[data-profile-menu-item]')).map(item => item.getAttribute('data-profile-menu-item'));
		expect(items).toEqual(['account', 'myResources', 'notifications', 'docs', 'theme', 'logout']);
		expect(screen.getByRole('menuitem', { name: '계정 설정' }).getAttribute('href')).toBe('/dashboard/account');
		expect(screen.getByRole('menuitem', { name: '내 리소스' }).getAttribute('href')).toBe('/dashboard/my-resources');
		expect(screen.getByRole('menuitem', { name: '알림함' }).getAttribute('href')).toBe('/dashboard/notifications');
		// Logout is last and visually separated from the other entries.
		const logout = screen.getByRole('menuitem', { name: '로그아웃' });
		expect(logout.previousElementSibling?.getAttribute('role')).toBe('separator');
		expect(menu.lastElementChild).toBe(logout);
		// The panel stays inside a 390px viewport: right-anchored with a viewport-bounded width.
		expect(menu.className).toContain('right-0');
		expect(menu.className).toContain('max-w-[calc(100vw-1rem)]');
		expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '계정 설정' }));
	});

	it('mirrors the bell unread indicator on the avatar and the notifications entry', async () => {
		const { container } = render(Fixture, { unread: true });
		expect(screen.getByRole('button', { name: '프로필 메뉴 열기. 읽지 않은 알림 있음' })).toBeTruthy();
		await openMenu();
		const notifications = screen.getByRole('menuitem', { name: '알림함 읽지 않은 알림 있음' });
		expect(notifications.querySelector('[data-unread-indicator]')).toBeTruthy();
		expect(container.querySelectorAll('[data-unread-indicator]')).toHaveLength(2);
	});

	it('shows no unread indicator without unread notifications', async () => {
		const { container } = render(Fixture);
		await openMenu();
		expect(container.querySelector('[data-unread-indicator]')).toBeNull();
	});

	it('toggles light and dark mode through the theme store without closing', async () => {
		render(Fixture);
		await openMenu();
		const toggle = screen.getByRole('menuitemcheckbox', { name: '다크 모드' });
		expect(toggle.getAttribute('aria-checked')).toBe('false');
		await fireEvent.click(toggle);
		expect(get(theme)).toBe('dark');
		expect(get(resolvedTheme)).toBe('dark');
		expect(toggle.getAttribute('aria-checked')).toBe('true');
		await fireEvent.click(toggle);
		expect(get(theme)).toBe('light');
		expect(screen.getByRole('menu')).toBeTruthy();
	});

	it('runs the existing logout handler and returns focus to the avatar', async () => {
		const onlogout = vi.fn();
		render(Fixture, { onlogout });
		await openMenu();
		await fireEvent.click(screen.getByRole('menuitem', { name: '로그아웃' }));
		expect(onlogout).toHaveBeenCalledOnce();
		expect(screen.queryByRole('menu')).toBeNull();
		expect(document.activeElement).toBe(trigger());
	});

	it('disables logout while a logout is already in progress', async () => {
		render(Fixture, { logoutDisabled: true });
		await openMenu();
		expect((screen.getByRole('menuitem', { name: '로그아웃' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('supports arrow, Home and End navigation and closes on Escape with focus restored', async () => {
		render(Fixture);
		const menu = await openMenu();
		await fireEvent.keyDown(menu, { key: 'ArrowDown' });
		expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '내 리소스' }));
		await fireEvent.keyDown(menu, { key: 'End' });
		expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '로그아웃' }));
		await fireEvent.keyDown(menu, { key: 'ArrowDown' });
		expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '계정 설정' }));
		await fireEvent.keyDown(menu, { key: 'ArrowUp' });
		expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '로그아웃' }));
		await fireEvent.keyDown(menu, { key: 'Home' });
		expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '계정 설정' }));
		await fireEvent.keyDown(menu, { key: 'Escape' });
		expect(screen.queryByRole('menu')).toBeNull();
		expect(document.activeElement).toBe(trigger());
	});

	it('opens from the keyboard with ArrowDown on the avatar', async () => {
		render(Fixture);
		trigger().focus();
		await fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
		await tick();
		expect(screen.getByRole('menu')).toBeTruthy();
		expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '계정 설정' }));
	});

	it('closes on outside pointer down and when a link is chosen', async () => {
		render(Fixture);
		await openMenu();
		await fireEvent.pointerDown(screen.getByTestId('outside'));
		expect(screen.queryByRole('menu')).toBeNull();

		await openMenu();
		await fireEvent.pointerDown(screen.getByRole('menuitem', { name: '내 리소스' }));
		expect(screen.getByRole('menu')).toBeTruthy();
		// jsdom cannot navigate; the menu's own click handler still runs before default prevention.
		const preventNavigation = (event: Event) => event.preventDefault();
		document.addEventListener('click', preventNavigation);
		await fireEvent.click(screen.getByRole('menuitem', { name: '내 리소스' }));
		document.removeEventListener('click', preventNavigation);
		expect(screen.queryByRole('menu')).toBeNull();
	});

	it('dismisses on an outside tap without activating the control underneath', async () => {
		render(Fixture);
		await openMenu();
		const outside = screen.getByTestId('outside');
		await fireEvent.pointerDown(outside);
		await fireEvent.mouseDown(outside);
		await fireEvent.pointerUp(outside);
		await fireEvent.mouseUp(outside);
		await fireEvent.click(outside);
		expect(screen.queryByRole('menu')).toBeNull();
		expect(screen.getByTestId('outside-activations').textContent).toBe('0');
		// Only the dismissing gesture is swallowed; the next tap reaches the control.
		await fireEvent.click(outside);
		expect(screen.getByTestId('outside-activations').textContent).toBe('1');
	});

	it('releases the swallowed gesture when it turns into a scroll', async () => {
		vi.useFakeTimers();
		try {
			render(Fixture);
			await openMenu();
			const outside = screen.getByTestId('outside');
			await fireEvent.pointerDown(outside);
			vi.advanceTimersByTime(700);
			await fireEvent.click(outside);
			expect(screen.getByTestId('outside-activations').textContent).toBe('1');
		} finally {
			vi.useRealTimers();
		}
	});

	it('hides entries a mockup profile may not navigate to', async () => {
		render(Fixture, { allowPath: (href: string) => href !== '/dashboard/account' });
		await openMenu();
		expect(screen.queryByRole('menuitem', { name: '계정 설정' })).toBeNull();
		expect(screen.getByRole('menuitem', { name: '내 리소스' })).toBeTruthy();
		expect(screen.getByRole('menuitem', { name: '로그아웃' })).toBeTruthy();
	});
});
