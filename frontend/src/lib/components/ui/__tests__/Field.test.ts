import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import Field from '../Field.svelte';
import TextInput from '../TextInput.svelte';
import SelectInput from '../SelectInput.svelte';
import TextareaInput from '../TextareaInput.svelte';

const rawSnippet = (html: string) => createRawSnippet(() => ({ render: () => html }));

describe('Field and form controls', () => {
	it('renders label, help, and required marker', () => {
		render(Field, {
			label: 'Name',
			for: 'name',
			help: 'Use the project name.',
			required: true,
			children: rawSnippet('<input id="name" />'),
		});
		expect(screen.getByText('Name')).toBeTruthy();
		expect(screen.getByText('*')).toBeTruthy();
		expect(screen.getByText('Use the project name.')).toBeTruthy();
	});

	it('renders error instead of help', () => {
		render(Field, {
			label: 'Name',
			help: 'Help text',
			error: 'Name is required',
			children: rawSnippet('<input />'),
		});
		expect(screen.getByText('Name is required')).toBeTruthy();
		expect(screen.queryByText('Help text')).toBeNull();
	});

	it('TextInput supports values and input events', async () => {
		const { container } = render(TextInput, { value: 'before' });
		const input = container.querySelector('input') as HTMLInputElement;
		expect(input.value).toBe('before');
		await fireEvent.input(input, { target: { value: 'after' } });
		expect(input.value).toBe('after');
	});

	it('TextInput forwards the numeric keyboard hint and accessible name', () => {
		const { container } = render(TextInput, { inputmode: 'decimal', ariaLabel: '월 한도' });
		const input = container.querySelector('input') as HTMLInputElement;
		expect(input.getAttribute('inputmode')).toBe('decimal');
		expect(input.getAttribute('aria-label')).toBe('월 한도');
	});

	it('SelectInput renders options and exposes its value', () => {
		const { container } = render(SelectInput, { value: 'a', children: rawSnippet('<option value="a">A</option>') });
		const select = container.querySelector('select') as HTMLSelectElement;
		expect(screen.getByText('A')).toBeTruthy();
		expect(select.value).toBe('a');
	});

	it('TextareaInput supports values', () => {
		const { container } = render(TextareaInput, { value: 'hello', rows: 3 });
		const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
		expect(textarea.value).toBe('hello');
		expect(textarea.rows).toBe(3);
	});
});
