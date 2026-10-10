import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

const enqueue = vi.hoisted(() => vi.fn());
vi.mock('$lib/stores/uploadQueue', () => ({ uploadQueue: { enqueue } }));
import UploadModal from '$lib/components/UploadModal.svelte';

it('shows armed upload activity only during file drag and enqueues the dropped selection on confirmation', async () => {
	const onClose = vi.fn();
	const onSuccess = vi.fn();
	render(UploadModal, { containerName: 'bucket', prefix: 'docs/', onClose, onSuccess });
	const zone = screen.getByRole('group', { name: '업로드 파일 선택' });
	const file = new File(['report'], 'report.csv', { type: 'text/csv' });
	const dataTransfer = { types: ['Files'], files: [file] };

	expect(screen.queryByText('파일을 여기에 떨어뜨리세요')).toBeNull();
	await fireEvent.dragEnter(zone, { dataTransfer });
	expect(screen.getByText('파일을 여기에 떨어뜨리세요')).toBeTruthy();
	await fireEvent.drop(zone, { dataTransfer });
	expect(screen.queryByText('파일을 여기에 떨어뜨리세요')).toBeNull();
	expect(screen.getByText('1개 파일 선택됨')).toBeTruthy();
	expect(enqueue).not.toHaveBeenCalled();

	await fireEvent.click(screen.getByRole('button', { name: '업로드' }));
	expect(enqueue).toHaveBeenCalledWith(file, expect.objectContaining({ containerName: 'bucket', prefix: 'docs/' }));
	expect(onClose).toHaveBeenCalledOnce();
});
