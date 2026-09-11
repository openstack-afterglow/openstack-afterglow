import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath, URL } from 'url';

// vitest 전용 설정 — sveltekit() 대신 svelte()를 사용해 browser 모드에서 컴포넌트 테스트 가능하게 함
// @testing-library/svelte의 mount()가 server 버전 Svelte를 로드하는 문제 방지
export default defineConfig({
	plugins: [svelte()],
	resolve: {
		conditions: ['browser'],
		alias: [
			// svelte 메인 진입점을 browser 버전으로 강제 → @testing-library/svelte의 mount() 정상 동작
			{ find: /^svelte$/, replacement: fileURLToPath(new URL('./node_modules/svelte/src/index-client.js', import.meta.url)) },
			{ find: '$lib', replacement: fileURLToPath(new URL('./src/lib', import.meta.url)) },
			// SvelteKit 가상 모듈 스텁 — 테스트에서 vi.mock()으로 재정의 가능
			{
				find: '$app/stores',
				replacement: fileURLToPath(new URL('./src/__mocks__/sveltekit/app-stores.ts', import.meta.url)),
			},
			{
				find: '$app/environment',
				replacement: fileURLToPath(new URL('./src/__mocks__/sveltekit/app-environment.ts', import.meta.url)),
			},
			{
				find: '$env/dynamic/public',
				replacement: fileURLToPath(new URL('./src/__mocks__/sveltekit/env-dynamic-public.ts', import.meta.url)),
			},
			{
				find: '$app/navigation',
				replacement: fileURLToPath(new URL('./src/__mocks__/sveltekit/app-navigation.ts', import.meta.url)),
			},
		],
	},
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		globals: true,
	},
});
