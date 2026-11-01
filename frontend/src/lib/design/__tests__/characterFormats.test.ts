import { describe, expect, it } from 'vitest';
import { circularProgress, linearProgress, settledSignal, statusSignal } from '../characterFormats';

const lit = (text: string) => [...text].filter(char => char === '#').length;

describe('shared text progress formats', () => {
  it('fills known circular progress clockwise from the top and clamps endpoints', () => {
    const zero = circularProgress(-4), quarter = circularProgress(25), half = circularProgress(50), complete = circularProgress(140);
    expect(lit(zero)).toBe(0);
    expect(quarter.split('\n')[1][12]).toBe('#');
    expect(quarter.split('\n')[11][12]).toBe('·');
    expect(lit(half)).toBeGreaterThan(lit(quarter));
    expect(lit(complete)).toBeGreaterThan(lit(half));
    expect(zero).toContain('0%');
    expect(complete).toContain('100%');
  });

  it('keeps unknown circular work nonnumeric and freezes its frame under caller control', () => {
    const waiting = circularProgress(null, 14, true);
    expect(waiting).not.toMatch(/[0-9%]/);
    expect(lit(waiting)).toBeGreaterThan(0);
    expect(circularProgress(null, 14, true)).toBe(waiting);
    expect(circularProgress(null, 15, true)).not.toBe(waiting);
    expect(lit(circularProgress(null, 14, false))).toBe(0);
    expect(circularProgress(Number.NaN, 14, true)).toBe(waiting);
  });

  it('distinguishes real linear endpoints from unknown moving segments', () => {
    expect(lit(linearProgress(0))).toBe(0);
    expect(lit(linearProgress(100))).toBe(26);
    expect(lit(linearProgress(null, 2, true))).toBe(5);
    expect(linearProgress(null, 2, true)).not.toMatch(/[0-9%]/);
    expect(lit(linearProgress(null))).toBe(0);
  });

  it('keeps each compact signal frame the same width and offers alternatives to tilde', () => {
    for (const type of ['dots', 'bars', 'brackets', 'spinner'] as const) {
      const frames = Array.from({ length: 10 }, (_, i) => statusSignal(type, i));
      expect(new Set(frames.map(text => text.length)).size).toBe(1);
      expect(new Set(frames).size).toBeGreaterThan(1);
      expect(frames.join('')).not.toContain('~');
    }
    expect(statusSignal('wave', 100)).toBe('[~]');
  });

  it('gives each settled outcome its own static glyph at the spinner width', () => {
    const outcomes = ['success', 'failed', 'blocked', 'canceled'] as const;
    const glyphs = outcomes.map(outcome => settledSignal(outcome));
    expect(new Set(glyphs).size).toBe(outcomes.length);
    expect(glyphs.every(glyph => glyph.length === statusSignal('spinner', 0).length)).toBe(true);
  });
});
