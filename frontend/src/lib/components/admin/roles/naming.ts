const NATIVE_ROLES: Record<string, true> = { admin: true, manager: true, member: true, reader: true };
export function isNativeRole(name: string): boolean { return NATIVE_ROLES[name.toLowerCase()] === true; }
export function normalizeRolePart(value: string): string { return value.toLowerCase().replace(/\s+/g, '-'); }
export function managedRoleName(area: string, grade: string): string { return `${normalizeRolePart(area)}_${normalizeRolePart(grade)}`; }
export function validRolePart(value: string): boolean { return /^[a-z0-9-]+$/.test(value) && /[a-z0-9]/.test(value); }
export function splitManagedRole(name: string): { area: string; grade: string } | null {
	const parts = name.split('_');
	return parts.length === 2 && parts.every(validRolePart) ? { area: parts[0], grade: parts[1] } : null;
}
