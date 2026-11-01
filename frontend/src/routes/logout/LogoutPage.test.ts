import { cleanup, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/shell';
import { ensureLogoutStarted, logoutProgress, type LogoutProgress } from '$lib/utils/logout';
import Page from './+page.svelte';

const mocks = vi.hoisted(() => ({ ensure: vi.fn(), goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/utils/logout', async () => {
	const { writable } = await import('svelte/store');
	return { ensureLogoutStarted: mocks.ensure, logoutProgress: writable({ phase: 'idle', all: false, shell: 'pending', server: 'pending', local: 'pending', serverNotRequired: false, loginHref: '/login' }) };
});

const progress = logoutProgress as Writable<LogoutProgress>;
const pending: LogoutProgress = { phase: 'running', all: false, shell: 'pending', server: 'pending', local: 'pending', serverNotRequired: false, loginHref: '/login' };
const complete: LogoutProgress = { ...pending, phase: 'complete', shell: 'done', server: 'done', local: 'done' };

beforeEach(() => { vi.resetAllMocks(); initLocale('ko'); progress.set({ ...pending }); mocks.ensure.mockResolvedValue(undefined); });
afterEach(() => { cleanup(); initLocale('ko'); });

function backAction(): HTMLAnchorElement { return screen.getByText(t('logout.back')).closest('a')!; }

describe('dedicated logout page', () => {
	it('renders a pending page before cleanup and starts direct entry only on mount', () => {
		render(Page);
		expect(screen.getByRole('heading', { level: 1, name: t('logout.working') })).toBeTruthy();
		expect(ensureLogoutStarted).toHaveBeenCalledOnce();
		expect(screen.getByText(t('logout.explanation'))).toBeTruthy();
		expect(screen.getAllByText(t('logout.pending'))).toHaveLength(3);
		expect(backAction().getAttribute('aria-disabled')).toBe('true');
		expect(backAction().hasAttribute('href')).toBe(false);
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it('shows only the actual active and finished steps while server cleanup is deferred', async () => {
		const { container } = render(Page);
		progress.set({ ...pending, shell: 'done', server: 'active' }); await tick();
		expect(container.querySelector('[data-step="shell"]')?.textContent).toContain(t('logout.complete'));
		expect(container.querySelector('[data-step="server"]')?.textContent).toContain(t('logout.active'));
		expect(container.querySelector('[data-step="local"]')?.textContent).toContain(t('logout.pending'));
		expect(backAction().hasAttribute('href')).toBe(false);
		expect(screen.queryByText(t('logout.done'))).toBeNull();
	});

	it('keeps completion visible through remount and locale change, with an explicit login link only', async () => {
		progress.set(complete);
		const first = render(Page);
		expect(screen.getByRole('heading', { level: 1, name: t('logout.finished') })).toBeTruthy();
		expect(screen.getByText(t('logout.done'))).toBeTruthy();
		expect(backAction().getAttribute('href')).toBe('/login');
		first.unmount(); initLocale('en'); render(Page); await tick();
		expect(screen.getByRole('heading', { level: 1, name: t('logout.finished') })).toBeTruthy();
		expect(backAction().getAttribute('href')).toBe('/login');
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each([false, true])('distinguishes unconfirmed server cleanup for all=%s without blocking cleared-local recovery', async all => {
		render(Page); progress.set({ ...complete, all, server: 'warning' }); await tick();
		expect(screen.getByRole('heading', { level: 1, name: t('logout.partialTitle') })).toBeTruthy();
		expect(screen.getByText(all ? t('logout.allPartial') : t('logout.partial'))).toBeTruthy();
		expect(screen.getByText(t('logout.unconfirmed'))).toBeTruthy();
		expect(backAction().getAttribute('href')).toBe('/login');
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it('marks absent server credentials as not required, never as confirmed server revocation', () => {
		progress.set({ ...complete, serverNotRequired: true }); render(Page);
		expect(screen.getByText(t('logout.notRequired'))).toBeTruthy();
		expect(screen.getAllByText(t('logout.complete'))).toHaveLength(2);
	});

	it('reports connection cleanup rejection separately from successful server and browser removal', () => {
		progress.set({ ...complete, shell: 'warning' }); render(Page);
		expect(screen.getByText(t('logout.shellFailed'))).toBeTruthy();
		expect(screen.queryByText(t('logout.done'))).toBeNull();
		expect(backAction().getAttribute('href')).toBe('/login');
	});

	it('does not claim completion or enable login when local removal could not be confirmed', () => {
		progress.set({ ...complete, local: 'warning' }); render(Page);
		expect(screen.getByRole('heading', { level: 1, name: t('logout.pageTitle') })).toBeTruthy();
		expect(screen.getByRole('alert').textContent).toContain(t('logout.localFailed'));
		expect(screen.queryByText(t('logout.done'))).toBeNull();
		expect(backAction().hasAttribute('href')).toBe(false);
	});

	it('returns tutorial sessions to explicit tutorial-off login', () => {
		progress.set({ ...complete, serverNotRequired: true, loginHref: '/login?tutorial=off' }); render(Page);
		expect(backAction().getAttribute('href')).toBe('/login?tutorial=off');
	});
});
