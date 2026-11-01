import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import LoadingState from '../LoadingState.svelte';
import { settledSignal, statusSignal, type SettledSignal } from '$lib/design/characterFormats.js';

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('compact loading signal selection', () => {
  it('keeps the actual task text separate from changing decorative formats', async () => {
    const view = render(LoadingState, { variant: 'inline', indicator: 'dots', label: '프로젝트 불러오는 중' });
    const before = view.container.querySelector('[data-art]')?.getAttribute('data-art');
    await view.rerender({ variant: 'inline', indicator: 'bars', label: '프로젝트 불러오는 중' });
    const glyph = view.container.querySelector('[data-art]');
    expect(glyph?.getAttribute('data-art')).not.toBe(before);
    expect(glyph?.getAttribute('aria-hidden')).toBe('true');
    expect(screen.getByRole('status').textContent?.trim()).toBe('프로젝트 불러오는 중');
    expect(view.container.querySelector('canvas')).toBeNull();
  });
  it('rotates by default, and its frozen reduced-motion frame never reads as a settled outcome', () => {
    const view = render(LoadingState, { variant: 'control', label: '처리 중' });
    const frame = view.container.querySelector('[data-art]')?.getAttribute('data-art');
    expect(Array.from({ length: 4 }, (_, i) => statusSignal('spinner', i))).toContain(frame);
    expect(['success', 'failed', 'blocked', 'canceled'].map(o => settledSignal(o as SettledSignal))).not.toContain(frame);
  });
});
