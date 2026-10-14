import { readable } from 'svelte/store';

export const page = readable({ data: {}, url: new URL('http://localhost/dashboard/chat'), state: {} });
