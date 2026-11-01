import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, within } from '@testing-library/svelte';
import DocRoleHierarchy from './DocRoleHierarchy.svelte';

afterEach(cleanup);

describe('document inclusion graph accessibility', () => {
	it('announces directed main and side relations without reversing inclusion or inferring branch links', () => {
		const view = render(DocRoleHierarchy, {
			id: 'example-hierarchy',
			hierarchy: {
				title: 'Role inclusion', description: 'Configured implications, not grants.', relation: 'includes',
				levels: [
					{ role: 'owner' },
					{ role: 'operator', alsoIncludes: ['writer'] },
					{ role: 'observer', alsoIncludes: ['reader'] },
				],
			},
		});
		const figure = view.getByRole('figure', { name: 'Role inclusion' });
		expect(figure.getAttribute('aria-describedby')).toBe(view.getByText('Configured implications, not grants.').id);
		expect(within(figure).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
			'owner includes operator', 'operator includes observer', 'operator includes writer', 'observer includes reader',
		]);
	});
});
