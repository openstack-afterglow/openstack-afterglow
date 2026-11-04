// @vitest-environment node

import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';
import type * as SvelteModule from 'svelte';
import ExperienceSupportCode from '../ExperienceSupportCode.svelte';

vi.mock('svelte', async () => {
	const actual = await vi.importActual<typeof SvelteModule>('svelte');
	return { ...actual, onMount: vi.fn() };
});
vi.mock('$lib/utils/experience', async () => {
	// The hoisted mock factory runs before static value imports initialize.
	const { readable } = await import('svelte/store');
	return {
		experienceSupportCode: { subscribe: readable('12345678-1234-4123-8123-123456789abc').subscribe },
		experienceHealth: { subscribe: readable({ status: 'ready', queued: 0, sent: 0, dropped: 0, failedBatches: 0 }).subscribe },
	};
});

describe('support-code server rendering', () => {
	it('does not serialize a current client code or disclosure before mount', () => {
		const { body } = render(ExperienceSupportCode);
		expect(body).not.toContain('12345678-1234-4123-8123-123456789abc');
		expect(body).not.toContain('<details');
		expect(body).not.toContain('<button');
	});
});
