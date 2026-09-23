// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { resolvePostLoginProject } from '../authFlow';

describe('resolvePostLoginProject', () => {
	it.each([
		{
			name: 'uses project_id when default_project_id is empty',
			input: { project_id: 'proj-1', default_project_id: '' },
			expected: { projectId: 'proj-1', target: '/dashboard' }
		},
		{
			name: 'falls back to default_project_id when project_id is empty',
			input: { project_id: '', default_project_id: 'proj-default' },
			expected: { projectId: 'proj-default', target: '/dashboard' }
		},
		{
			name: 'trims both values and prefers project_id when both are present',
			input: { project_id: ' scoped ', default_project_id: ' default ' },
			expected: { projectId: 'scoped', target: '/dashboard' }
		},
		{
			name: 'routes to project selection when both values are blank after trim',
			input: { project_id: ' ', default_project_id: '' },
			expected: { projectId: null, target: '/select-project' }
		}
	])('$name', ({ input, expected }) => {
		expect(resolvePostLoginProject(input)).toEqual(expected);
	});
});
