// @vitest-environment node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(__dirname, '../../..');
const readSource = (path: string) => readFileSync(resolve(root, path), 'utf8');

// AI 채팅(LibreChat)은 services.chat([services] chat = true + [chat] base_url 설정)일 때만 활성화된다.
// 비활성 시 사이드바·커맨드 팔레트 어디에도 노출되지 않아야 한다.
describe('chat-gated feature surfaces', () => {
	it('marks AI chat navigation entries with chat service metadata', () => {
		const source = [
			'src/lib/components/Sidebar.svelte',
			'src/lib/config/nav.ts',
		].map(readSource).join('\n');

		const occurrences = source.match(/service: 'chat'/g) ?? [];
		expect(occurrences.length).toBeGreaterThanOrEqual(2);
	});

	it('gates the sidebar chat section on services.chat', () => {
		const source = readSource('src/lib/components/Sidebar.svelte');
		expect(source).toContain("section.service === 'chat'");
		expect(source).toContain("item.service === 'chat'");
		const gated = source.match(/svcs\?\.chat \?\? false/g) ?? [];
		expect(gated.length).toBeGreaterThanOrEqual(2);
	});

	it('keeps command palette entries filtered by their configured service', () => {
		const source = readSource('src/lib/components/CmdPalette.svelte');
		expect(source).toContain('.filter((item) => !item.service ||');
		expect(source).toContain('[item.service] ?? false');
	});
});
