import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Page from '../../../../../routes/admin/monitoring/traffic/+page.svelte';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/traffic-analytics';
import { observations } from './observations';

const { read } = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: read } }));

beforeEach(() => {
    initLocale('en');
    auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true });
    authReady.set(true); projectSwitching.set(false);
    read.mockReset().mockResolvedValue(observations());
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); initLocale('ko'); });

describe('traffic route source and origin authority', () => {
    it('applies origin to the request and fences stale all-origin and source responses', async () => {
        const initial = Promise.withResolvers<unknown>();
        const external = Promise.withResolvers<unknown>();
        read.mockImplementationOnce(() => initial.promise).mockImplementationOnce(() => external.promise)
            .mockResolvedValueOnce(observations({ source: 'frontend', origin: 'external', origins: { internal: 0, external: 10, unknown: 0, legacy_unclassified: 0 }, routes: [] }));
        render(Page);
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(1));
        await fireEvent.change(screen.getByLabelText(t('controls.origin')), { target: { value: 'external' } });
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2));
        expect(read.mock.calls[1][0]).toContain('source=backend&origin=external');
        await fireEvent.change(screen.getByLabelText(t('controls.source')), { target: { value: 'frontend' } });
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(3));
        await vi.waitFor(() => expect(screen.getByText(t('coverage.frontend'))).toBeTruthy());
        initial.resolve(observations());
        external.resolve(observations({ origin: 'external', origins: { internal: 0, external: 10, unknown: 0, legacy_unclassified: 0 }, routes: [] }));
        await Promise.resolve(); await Promise.resolve();
        expect(screen.queryByText(t('coverage.backend'))).toBeNull();
        expect(screen.getByText(t('origins.note'))).toBeTruthy();
    });
    it('removes visible observations on authority loss and ignores the inflight response', async () => {
        const pending = Promise.withResolvers<unknown>();
        read.mockImplementationOnce(() => pending.promise);
        render(Page);
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(1));
        auth.update(value => ({ ...value, isSystemAdmin: false }));
        await vi.waitFor(() => expect(screen.getByText(t('adminRequired'))).toBeTruthy());
        pending.resolve(observations()); await Promise.resolve(); await Promise.resolve();
        expect(screen.queryByText(t('routes.title'))).toBeNull();
    });
});
