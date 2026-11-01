import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import AssetGlyph from '../AssetGlyph.svelte';
import EmptyStateFixture from './EmptyStateFixture.svelte';

afterEach(cleanup);

describe('character state artwork', () => {
  it('keeps artwork decorative while empty-state copy and action remain accessible', () => {
    const { container } = render(EmptyStateFixture);
    expect(screen.getByText('No resources')).toBeTruthy();
    expect(screen.getByText('Create a resource to begin.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Create resource' })).toBeTruthy();
    expect(container.querySelector('pre')?.getAttribute('aria-hidden')).toBe('true');
    expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('renders an error illustration without inventing status authority or motion', () => {
    const { container } = render(AssetGlyph, { variant: 'error' });
    expect(container.querySelector('pre')?.textContent).toContain('!');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(container.querySelector('canvas, svg')).toBeNull();
  });
});
