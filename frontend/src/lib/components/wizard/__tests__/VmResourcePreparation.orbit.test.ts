import { render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import VmResourcePreparation from '../VmResourcePreparation.svelte';

// vi.mock is hoisted above static imports, so the replacement must be loaded inside the factory.
vi.mock('$lib/components/ui/AfterglowOrbit.svelte', async () => ({ default: (await import('$lib/components/ui/__tests__/AfterglowOrbitProbe.svelte')).default }));

describe('VmResourcePreparation orbit wiring', () => {
	it('passes the pointer light to the waiting artwork', () => {
		const { getByTestId } = render(VmResourcePreparation, {
			tasks: [{ id: 'network', label: 'network', status: 'pending' }],
			error: false,
			onRetry: vi.fn(),
			retrying: false,
		});
		expect(getByTestId('orbit-probe').getAttribute('data-interactive')).toBe('true');
	});
});
