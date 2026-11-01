import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import LandingMotionGraphic from '../LandingMotionGraphic.svelte';

afterEach(cleanup);

describe('landing service scenes', () => {
  it.each(['server', 'gpu', 'kubernetes', 'onprem'] as const)('%s names the concept and renders fully localized decorative copy', (kind) => {
    const view = render(LandingMotionGraphic, { kind, state: 'static' });
    const graphic = screen.getByRole('img');
    expect(graphic.getAttribute('aria-label')).toBeTruthy();
    expect(graphic.getAttribute('aria-label')).not.toContain('landing.story.');
    const picture = view.container.querySelector('.window')!;
    expect(picture.getAttribute('aria-hidden')).toBe('true');
    expect(picture.textContent).not.toMatch(/landing\.story\.|\{\w+\}/);
  });

  it('settles on the finished state and follows the scene motion state', async () => {
    const view = render(LandingMotionGraphic, { kind: 'server', state: 'static' });
    expect(view.container.textContent).toContain('실행 중');
    await view.rerender({ kind: 'kubernetes', state: 'paused' });
    expect(view.container.textContent).toContain('컨테이너 6개 실행 중');
    expect(screen.getByRole('img').getAttribute('data-motion')).toBe('paused');
  });
});
