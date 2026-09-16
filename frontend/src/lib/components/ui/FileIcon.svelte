<script lang="ts">
	interface Props {
		name: string;
		contentType?: string;
		isDir?: boolean;
		class?: string;
	}

	let { name, contentType = '', isDir = false, class: className = '' }: Props = $props();
	type IconType = 'folder' | 'pdf' | 'spreadsheet' | 'config' | 'code' | 'text' | 'archive' | 'image' | 'file';

	function getIconType(filename: string, ct: string, dir: boolean): IconType {
		if (dir) return 'folder';
		const ext = filename.split('.').pop()?.toLowerCase() ?? '';
		if (ext === 'pdf') return 'pdf';
		if (['csv', 'xlsx', 'xls', 'ods'].includes(ext)) return 'spreadsheet';
		if (['json', 'yaml', 'yml', 'toml', 'ini', 'conf', 'env', 'cfg'].includes(ext)) return 'config';
		if (['py', 'js', 'ts', 'go', 'rs', 'java', 'c', 'cpp', 'h', 'sh', 'bash', 'zsh', 'rb', 'php'].includes(ext)) return 'code';
		if (['md', 'txt', 'log', 'rst'].includes(ext)) return 'text';
		if (['zip', 'tar', 'gz', 'bz2', 'xz', 'rar', '7z', 'tgz'].includes(ext)) return 'archive';
		if (ct.startsWith('image/')) return 'image';
		return 'file';
	}

	const iconType = $derived(getIconType(name, contentType, isDir));
</script>

<span class="file-icon file-icon-{iconType} {className}">
	{#if iconType === 'folder'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/></svg>
	{:else if iconType === 'pdf'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd"/></svg>
	{:else if iconType === 'spreadsheet'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5 4a3 3 0 00-3 3v6a3 3 0 003 3h10a3 3 0 003-3V7a3 3 0 00-3-3H5zm-1 9v-1h5v2H5a1 1 0 01-1-1zm7 1h4a1 1 0 001-1v-1h-5v2zm0-4h5V8h-5v2zM9 8H4v2h5V8z" clip-rule="evenodd"/></svg>
	{:else if iconType === 'config'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
	{:else if iconType === 'code'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"/></svg>
	{:else if iconType === 'text'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm3 1h6v2H7V5zm0 4h6v2H7V9zm0 4h4v2H7v-2z" clip-rule="evenodd"/></svg>
	{:else if iconType === 'archive'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path d="M4 3a2 2 0 100 4h12a2 2 0 100-4H4z"/><path fill-rule="evenodd" d="M3 8h14v7a2 2 0 01-2 2H5a2 2 0 01-2-2V8zm5 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z" clip-rule="evenodd"/></svg>
	{:else if iconType === 'image'}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd"/></svg>
	{:else}
		<svg class="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/></svg>
	{/if}
</span>

<style>
	/* 파일 종류는 상태가 아니다. 아홉 개의 glyph 모양과 옆의 파일명이 이미 종류를 구분하므로
	   상태 톤을 빌려 쓰면 오브젝트 목록이 건강 상태 열처럼 읽힌다. */
	.file-icon {
		flex-shrink: 0;
		color: var(--color-ink-2);
	}
	.file-icon-code { color: var(--color-accent); }
	.file-icon-text { color: var(--color-ink-2); }
	.file-icon-file { color: var(--color-ink-2); }
</style>
