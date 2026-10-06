import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';

const { controller } = vi.hoisted(() => ({ controller: { current: {} as Record<string, unknown> } }));
vi.mock('$lib/stores/imageDetailController.svelte', () => ({
	useImageDetailController: () => controller.current,
	VISIBILITY_OPTIONS: [{ value: 'private', label: '비공개' }, { value: 'public', label: '공개' }],
	isReservedKey: () => false,
}));
import ImageMembersSection from '../ImageMembersSection.svelte';
import ImageVisibilitySection from '../ImageVisibilitySection.svelte';
import ImagePropertiesSection from '../ImagePropertiesSection.svelte';
import ImageDeleteAction from '../ImageDeleteAction.svelte';
import ImageDetailHeader from '../ImageDetailHeader.svelte';

beforeEach(() => {
	controller.current = {
		image: { id: 'image-a', name: 'ubuntu:latest', status: 'active', visibility: 'private', properties: { architecture: 'x86_64' } },
		newMemberId: '', loadingMembers: false, members: [], memberError: '',
		addingMember: false, removingMember: null, visibilityValue: 'public',
		savingVisibility: false, visibilitySuccess: false, visibilityError: '',
		canEditMetadata: true, editingProps: true, propsDraft: { architecture: 'x86_64' },
		newPropKey: '', newPropValue: '', propsError: '', savingProps: false, deleting: false,
	};
});

describe('image operation feedback', () => {
	it('shows member-loading feedback instead of claiming the sharing list is empty', () => {
		controller.current.loadingMembers = true;
		render(ImageMembersSection);
		expect(screen.getByRole('status').textContent?.trim()).toBe('불러오는 중...');
		expect(screen.queryByText('공유된 프로젝트가 없습니다.')).toBeNull();
	});

	it('attributes removal to the affected member while retaining the other action', () => {
		controller.current.members = [{ member_id: 'project-a', status: 'accepted' }, { member_id: 'project-b', status: 'pending' }];
		controller.current.removingMember = 'project-b';
		render(ImageMembersSection);
		expect(screen.getByRole('button', { name: '삭제 중...' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: '삭제' }).hasAttribute('disabled')).toBe(false);
	});

	it('shows the add request alongside its own label', () => {
		controller.current.addingMember = true;
		render(ImageMembersSection);
		expect(screen.getByRole('button', { name: '추가 중...' }).hasAttribute('disabled')).toBe(true);
	});

	it('keeps visibility save feedback distinct from success', () => {
		controller.current.savingVisibility = true;
		render(ImageVisibilitySection);
		expect(screen.getByRole('status').textContent?.trim()).toBe('저장 중...');
		expect(screen.getByRole('button', { name: '저장 중...' }).hasAttribute('disabled')).toBe(true);
		expect(screen.queryByText('저장됨')).toBeNull();
	});

	it('retains the property count and indicates only an actual property save', () => {
		controller.current.savingProps = true;
		render(ImagePropertiesSection);
		expect(screen.getByRole('heading').textContent?.replace(/\s/g, '')).toContain('(1)');
		expect(screen.getByRole('button', { name: '저장 중...' }).hasAttribute('disabled')).toBe(true);
	});

	it('labels delete activity without replacing image operational status', () => {
		controller.current.deleting = true;
		render(ImageDetailHeader);
		render(ImageDeleteAction);
		expect(screen.getByText('active')).toBeTruthy();
		expect(screen.getByRole('status').textContent?.trim()).toBe('삭제 중...');
		expect(screen.getByRole('button', { name: '삭제 중...' }).hasAttribute('disabled')).toBe(true);
	});
});
