import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import SearchSelect from '../SearchSelect.svelte';

const options = [
	{ value: 'user-1', label: 'dustywindow', description: 'user-1' },
	{ value: 'user-2', label: 'LeeSongHeon', description: 'user-2' },
	{ value: 'user-3', label: 'afterglow-admin', description: 'user-3' },
];

describe('SearchSelect', () => {
	it('filters by visible label or identifier and selects the result', async () => {
		const onchange = vi.fn();
		render(SearchSelect, {
			id: 'announcement-user',
			value: '',
			options,
			placeholder: '유저를 선택하세요',
			searchPlaceholder: '유저 이름 또는 ID 검색',
			ariaLabel: '유저 선택',
			onchange,
		});

		await fireEvent.click(screen.getByRole('button', { name: '유저 선택' }));
		const search = screen.getByRole('combobox', { name: '유저 이름 또는 ID 검색' });
		await fireEvent.input(search, { target: { value: 'user-2' } });

		expect(screen.queryByRole('option', { name: /dustywindow/ })).toBeNull();
		await fireEvent.click(screen.getByRole('option', { name: /LeeSongHeon/ }));
		expect(onchange).toHaveBeenCalledWith('user-2');
		expect(screen.queryByRole('listbox')).toBeNull();
	});

	it('supports keyboard navigation and restores focus after selection', async () => {
		const onchange = vi.fn();
		render(SearchSelect, {
			id: 'announcement-project',
			value: '',
			options,
			placeholder: '프로젝트를 선택하세요',
			searchPlaceholder: '프로젝트 이름 또는 ID 검색',
			ariaLabel: '프로젝트 선택',
			onchange,
		});

		const trigger = screen.getByRole('button', { name: '프로젝트 선택' });
		await fireEvent.click(trigger);
		const search = screen.getByRole('combobox', { name: '프로젝트 이름 또는 ID 검색' });
		await fireEvent.keyDown(search, { key: 'ArrowDown' });
		await fireEvent.keyDown(search, { key: 'Enter' });

		expect(onchange).toHaveBeenCalledWith('user-2');
		expect(document.activeElement).toBe(trigger);
	});

	it('shows an explicit no-match state', async () => {
		render(SearchSelect, {
			id: 'announcement-empty',
			value: '',
			options,
			searchPlaceholder: '대상 검색',
			emptyText: '일치하는 대상이 없습니다',
			ariaLabel: '대상 선택',
			onchange: vi.fn(),
		});

		await fireEvent.click(screen.getByRole('button', { name: '대상 선택' }));
		await fireEvent.input(screen.getByRole('combobox', { name: '대상 검색' }), { target: { value: 'missing' } });
		expect(screen.getByText('일치하는 대상이 없습니다')).toBeTruthy();
	});

	it('portals the popover outside clipping ancestors and keeps the last option selectable', async () => {
		const onchange = vi.fn();
		const longOptions = Array.from({ length: 30 }, (_, index) => ({
			value: `project-${index + 1}`,
			label: `Project ${index + 1}`,
			description: `project-${index + 1}`,
		}));
		const { container } = render(SearchSelect, {
			id: 'announcement-long-projects',
			value: '',
			options: longOptions,
			ariaLabel: '긴 프로젝트 선택',
			onchange,
		});

		await fireEvent.click(screen.getByRole('button', { name: '긴 프로젝트 선택' }));
		const listbox = screen.getByRole('listbox', { name: '긴 프로젝트 선택' });
		expect(document.body.contains(listbox)).toBe(true);
		expect(container.contains(listbox)).toBe(false);

		await fireEvent.click(screen.getByRole('option', { name: /Project 30/ }));
		expect(onchange).toHaveBeenCalledWith('project-30');
	});
});
