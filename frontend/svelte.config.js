import adapter from '@sveltejs/adapter-node';
import { relative, sep } from 'node:path';

const impeccableLiveDev = process.env.NODE_ENV === 'development' ? ['http://localhost:8400'] : [];

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// defaults to rune mode for the project, except for `node_modules`. Can be removed in svelte 6.
		runes: ({ filename }) => {
			const relativePath = relative(import.meta.dirname, filename);
			const pathSegments = relativePath.toLowerCase().split(sep);
			const isExternalLibrary = pathSegments.includes('node_modules');

			return isExternalLibrary ? undefined : true;
		}
	},
	kit: {
		adapter: adapter(),
		typescript: {
			config: (config) => { config.include.push('../src/**/*.tsx'); }
		},
		// SvelteKit stamps its generated scripts with a per-response nonce (hashes when prerendered).
		csp: { mode: 'auto', directives: { 'script-src': ['self', ...impeccableLiveDev] } }
	}
};

export default config;
