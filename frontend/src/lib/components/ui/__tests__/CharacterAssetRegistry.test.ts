import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import AssetGlyph from '../AssetGlyph.svelte';
import assets from '$lib/design/characterAssets.json';

afterEach(cleanup);

describe('universal character asset registry', () => {
  it('can switch from infrastructure to media without adding status authority', async () => {
    const view = render(AssetGlyph, { variant: 'storage' });
    expect(view.container.querySelector('pre')?.textContent).toBe(assets.storage.art);
    await view.rerender({ variant: 'audio' });
    expect(view.container.querySelector('pre')?.textContent).toBe(assets.audio.art);
    expect(view.container.querySelector('pre')?.getAttribute('aria-hidden')).toBe('true');
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(view.container.querySelector('svg,canvas,img')).toBeNull();
  });

  it('keeps public IDs path-safe and authored glyphs bounded for shared state surfaces', () => {
    const art = new Set<string>();
    for (const [id, asset] of Object.entries(assets)) {
      expect(id).toMatch(/^[a-z][a-z0-9-]*$/);
      expect(asset.category).toBeTruthy();
      expect(asset.label).toBeTruthy();
      expect(asset.art.trim()).toBeTruthy();
      expect(asset.art.split('\n').length).toBeLessThanOrEqual(24);
      expect(Math.max(...asset.art.split('\n').map(line => line.length))).toBeLessThanOrEqual(64);
      expect(art.has(asset.art)).toBe(false);
      art.add(asset.art);
    }
    for (const id of ['empty','error','offline','success','locked','upload','search']) {
      expect(assets).toHaveProperty(id);
    }
  });
});
