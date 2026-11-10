import { render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import LoadingState from '../LoadingState.svelte';

// vi.mock is hoisted above static imports, so the replacement must be loaded inside the factory.
vi.mock('../AfterglowOrbit.svelte', async () => ({ default: (await import('./AfterglowOrbitProbe.svelte')).default }));

describe('LoadingState orbit wiring', () => {
	it('gives the surface artwork the pointer light used by the hero and auth art', () => {
		const { container } = render(LoadingState, { variant: 'surface' });
		expect(container.querySelector('[data-testid="orbit-probe"]')?.getAttribute('data-interactive')).toBe('true');
	});

	it('renders no orbit for the section variant', () => {
		const { container } = render(LoadingState, { variant: 'section' });
		expect(container.querySelector('[data-testid="orbit-probe"]')).toBeNull();
	});
});
