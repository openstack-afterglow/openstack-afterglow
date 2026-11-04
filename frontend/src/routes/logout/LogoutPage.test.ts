import { cleanup, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/shell';
import { ensureLogoutStarted, logoutProgress, type LogoutProgress } from '$lib/utils/logout';
import Page from './+page.svelte';
import { clearAuth, setLoginAuth } from '$lib/stores/auth';
import type * as ExperienceModule from '$lib/utils/experience';

const mocks = vi.hoisted(() => ({ ensure: vi.fn(), goto: vi.fn(), experienceBegin: vi.fn(), experienceApplied: vi.fn(), experienceState: vi.fn(), experienceMessage: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/utils/logout', async () => {
	const { writable } = await import('svelte/store');
	return { ensureLogoutStarted: mocks.ensure, logoutProgress: writable({ phase: 'idle', all: false, shell: 'pending', server: 'pending', local: 'pending', serverNotRequired: false, loginHref: '/login' }) };
});
vi.mock('$lib/utils/experience', async importOriginal => {
	const actual = await importOriginal<typeof ExperienceModule>();
	return {
		...actual, beginExperienceAction: mocks.experienceBegin, beginExperienceLoad: mocks.experienceBegin,
		experienceApplied: mocks.experienceApplied, experienceState: mocks.experienceState, experienceMessage: mocks.experienceMessage,
	};
});

const progress = logoutProgress as Writable<LogoutProgress>;
const pending: LogoutProgress = { phase: 'running', all: false, shell: 'pending', server: 'pending', local: 'pending', serverNotRequired: false, loginHref: '/login' };
const complete: LogoutProgress = { ...pending, phase: 'complete', shell: 'done', server: 'done', local: 'done' };

beforeEach(() => { vi.resetAllMocks(); clearAuth(); initLocale('ko'); progress.set({ ...pending }); mocks.ensure.mockResolvedValue(undefined); mocks.experienceApplied.mockResolvedValue(undefined); });
afterEach(() => { cleanup(); clearAuth(); initLocale('ko'); });

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

describe('logout source observations', () => {
	it('preserves unconfirmed server cleanup and fences a replaced post-tick progress snapshot', async () => {
		const context = Object.freeze({ segmentId: 'logout-segment' });
		mocks.experienceBegin.mockReturnValue(context);
		render(Page);
		progress.set({ ...complete, server: 'warning' }); await tick();
		expect(mocks.experienceState).toHaveBeenLastCalledWith(context, 'error', 2);
		expect(mocks.experienceMessage).toHaveBeenCalledWith(context, expect.objectContaining({ key: 'shell:logout.partial', tone: 'warning', locale: 'ko' }));
		expect(mocks.experienceMessage.mock.calls.some(([, metadata]) => metadata.key === 'shell:logout.done')).toBe(false);
		const guard = mocks.experienceApplied.mock.calls.at(-1)![2] as () => boolean;
		progress.set({ ...complete, local: 'warning' });
		expect(guard()).toBe(false);
		expect(mocks.ensure).toHaveBeenCalledOnce();
	});

	it('starts an independent anonymous observation after actual auth clearing instead of relabelling the prior logout owner', async () => {
		setLoginAuth({ token: 'private-token', userId: 'private-user', sessionId: 'private-session', domainId: 'private-domain' });
		mocks.experienceBegin.mockImplementation(() => Object.freeze({ segmentId: `segment-${mocks.experienceBegin.mock.calls.length}` }));
		render(Page); await tick();
		const original = mocks.ensure.mock.calls[0][0];
		clearAuth(); progress.set(complete); await tick();
		const presented = mocks.experienceMessage.mock.calls.find(([, metadata]) => metadata.key === 'shell:logout.done')?.[0];
		expect(presented).toBeTruthy(); expect(presented).not.toBe(original);
		expect(original.segmentId).toBe('segment-1');
		expect(JSON.stringify(mocks.experienceMessage.mock.calls)).not.toContain('private-token');
		expect(mocks.ensure).toHaveBeenCalledOnce();
	});
});
