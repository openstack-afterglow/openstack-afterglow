import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import { readFileSync } from 'fs';

const pkg = JSON.parse(readFileSync('./package.json', 'utf-8'));
const isDocker = process.env.DOCKER === 'true';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	define: {
		__APP_VERSION__: JSON.stringify(pkg.version),
	},
	build: {
		// Chat, Mermaid and Shiki are route/on-demand chunks; the largest emitted chunk
		// is under 800 kB minified and remains independently lazy-loaded.
		chunkSizeWarningLimit: 800,
	},
	server: isDocker
		? {
				host: '0.0.0.0',
				port: 3000,
				watch: {
					usePolling: true, // Docker 볼륨 마운트에서 파일 변경 감지
					interval: 1000,
				},
				hmr: {
					clientPort: 3000, // 브라우저 HMR WebSocket 포트
				},
			}
		: undefined,
});
