// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { loginDestination, resolvePostLoginProject } from '../authFlow';

describe('resolvePostLoginProject', () => {
	it.each([
		{
			name: 'uses project_id when default_project_id is empty',
			input: { project_id: 'proj-1', default_project_id: '' },
			expected: { projectId: 'proj-1', target: '/dashboard' }
		},
		{
			name: 'does not treat a default_project_id hint as native scope',
			input: { project_id: '', default_project_id: 'proj-default' },
			expected: { projectId: null, target: '/select-project' }
		},
		{
			name: 'trims the scoped project_id and ignores the default hint',
			input: { project_id: ' scoped ', default_project_id: ' default ' },
			expected: { projectId: 'scoped', target: '/dashboard' }
		},
		{
			name: 'routes to project selection when both values are blank after trim',
			input: { project_id: ' ', default_project_id: '' },
			expected: { projectId: null, target: '/select-project' }
		},
		{
			name: 'does not treat a missing project_id as native scope',
			input: { default_project_id: 'proj-default' },
			expected: { projectId: null, target: '/select-project' }
		}
	])('$name', ({ input, expected }) => {
		expect(resolvePostLoginProject(input)).toEqual(expected);
	});
});

describe('existing-session destination', () => {
	const domains = [{ id: 'home', name: 'Home' }, { id: 'team', name: 'Team' }];
	it.each([
		{ availableDomains: domains, projectId: 'default', expected: '/dashboard' },
		{ availableDomains: domains, projectId: null, expected: '/select-domain' },
		{ availableDomains: [domains[0]], projectId: 'default', expected: '/dashboard' },
		{ availableDomains: [domains[0]], projectId: null, expected: '/select-project' },
		{ availableDomains: domains, projectId: ' ', expected: '/select-domain' },
		{ availableDomains: [], projectId: '', expected: '/select-project' },
	])('routes project $projectId to $expected using only actual project scope', ({ expected, ...state }) => {
		expect(loginDestination(state)).toBe(expected);
	});
});
