<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';
	import '@xterm/xterm/css/xterm.css';
	import { resolvedTheme } from '$lib/stores/theme';
	import { cloudShell } from '$lib/stores/cloudShell.svelte';
	import { getTerminalTheme } from '$lib/utils/terminalTheme';

	let terminalElement = $state<HTMLDivElement | null>(null);
	let terminal = $state.raw<import('@xterm/xterm').Terminal | null>(null);
	let fitAddon: import('@xterm/addon-fit').FitAddon | null = null;
	let resizeObserver: ResizeObserver | null = null;
	let dataDisposable: import('@xterm/xterm').IDisposable | null = null;
	let resizeDisposable: import('@xterm/xterm').IDisposable | null = null;
	let lastEpoch = -1;

	onMount(async () => {
		await tick();
		if (!terminalElement) return;
		const [{ Terminal }, { FitAddon }, { WebLinksAddon }] = await Promise.all([
			import('@xterm/xterm'),
			import('@xterm/addon-fit'),
			import('@xterm/addon-web-links'),
		]);
		terminal = new Terminal({
			theme: getTerminalTheme(),
			fontFamily: 'var(--font-mono)',
			fontSize: 13,
			lineHeight: 1.2,
			cursorBlink: true,
			convertEol: false,
			disableStdin: cloudShell.phase !== 'ready',
			scrollback: 5000,
		});
		fitAddon = new FitAddon();
		terminal.loadAddon(fitAddon);
		terminal.loadAddon(new WebLinksAddon());
		terminal.open(terminalElement);
		fitAddon.fit();
		dataDisposable = terminal.onData((data) => cloudShell.sendInput(data));
		resizeDisposable = terminal.onResize(({ cols, rows }) => cloudShell.resize(cols, rows));
		resizeObserver = new ResizeObserver(() => fitAddon?.fit());
		resizeObserver.observe(terminalElement);
		cloudShell.setTerminalSink({
			write: (data) => terminal?.write(data),
			clear: () => terminal?.reset(),
			focus: () => terminal?.focus(),
			fit: () => fitAddon?.fit(),
		});
		lastEpoch = cloudShell.terminalEpoch;
	});

	$effect(() => {
		const activeTheme = $resolvedTheme;
		if (!terminal || typeof document === 'undefined') return;
		void activeTheme;
		terminal.options.theme = getTerminalTheme();
	});

	$effect(() => {
		if (!terminal) return;
		terminal.options.disableStdin = cloudShell.phase !== 'ready';
	});

	$effect(() => {
		const epoch = cloudShell.terminalEpoch;
		if (!terminal || epoch === lastEpoch) return;
		lastEpoch = epoch;
		terminal.reset();
	});

	onDestroy(() => {
		cloudShell.setTerminalSink(null);
		resizeObserver?.disconnect();
		dataDisposable?.dispose();
		resizeDisposable?.dispose();
		terminal?.dispose();
		terminal = null;
		fitAddon = null;
	});
</script>

<div class="relative h-full min-h-0 bg-surface-canvas" aria-label="Cloud Shell terminal">
	<div bind:this={terminalElement} class="h-full w-full p-2"></div>
	{#if cloudShell.phase !== 'ready'}
		<div class="pointer-events-none absolute inset-0 flex items-center justify-center bg-surface-canvas/70" aria-hidden="true">
			<p class="rounded-md border border-line bg-surface-raised px-3 py-2 text-xs text-ink-2">
				{cloudShell.statusStep || cloudShell.phaseLabel}
			</p>
		</div>
	{/if}
</div>
