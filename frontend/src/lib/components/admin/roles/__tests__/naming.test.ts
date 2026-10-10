import { describe, expect, it } from 'vitest';
import { isNativeRole, managedRoleName, splitManagedRole, validRolePart } from '../naming';
describe('managed role area and grade', () => {
	it('preserves existing underscore names and normalizes every whitespace run before trimming', () => {
		expect(splitManagedRole('project_owner')).toEqual({ area: 'project', grade: 'owner' });
		expect(managedRoleName(' Waygate\tClients ', ' Custom\nGrade ')).toBe('-waygate-clients-_-custom-grade-');
		expect(managedRoleName('lumen-chat', 'user')).toBe('lumen-chat_user');
	});
	it('keeps legacy names readable and protects only exact native names', () => {
		expect(splitManagedRole('legacy-read-only')).toBeNull();
		expect(splitManagedRole('lumen_extra_user')).toBeNull();
		expect(isNativeRole('manager')).toBe(true);
		expect(isNativeRole('project_owner')).toBe(false);
		expect(validRolePart('---')).toBe(false);
		expect(validRolePart('custom-grade')).toBe(true);
	});
});
