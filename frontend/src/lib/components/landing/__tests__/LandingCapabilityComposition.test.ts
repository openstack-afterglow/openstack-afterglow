// @vitest-environment node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(__dirname, '../../../../..');
const landingSource = readFileSync(resolve(frontendRoot, 'src/lib/components/landing/LandingPage.svelte'), 'utf8');
const designSource = readFileSync(resolve(frontendRoot, '../DESIGN.md'), 'utf8');

describe('landing capability composition contract', () => {
	it('groups the four static capabilities into one divided matrix with contained artwork', () => {
		expect(landingSource).toContain('<Card surface="subtle" padding="none" class="capability-grid">');
		expect(landingSource).toContain('{#each capabilities as capability}');
		expect(landingSource).toContain('fit="contain"');
		expect(landingSource).not.toContain('class:cap-card-wide');
		expect(landingSource).not.toContain('class="cap-card-surface"');
		expect(landingSource).not.toMatch(/\.cap-card:hover/);
	});

	it('keeps the matrix two-column and moves the section label rail to desktop only', () => {
		expect(landingSource).toContain('.landing-page :global(.capability-grid) { grid-template-columns: repeat(2, minmax(0, 1fr)); }');
		expect(landingSource).toContain('@media (min-width: 1024px)');
		expect(landingSource).toContain('.section-head { grid-template-columns: minmax(10rem, 0.3fr) minmax(0, 1fr); gap: 2rem; }');
		expect(designSource).toContain('one divided two-by-two service matrix');
		expect(designSource).toContain('static cells do not use hover affordances');
	});
});
