<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { realtimeVoiceApi, realtimeReadiness, pcm16Base64, decodePcm16, type RealtimeModel, type RealtimeCapabilities, type RealtimeScope } from '$lib/api/realtimeVoice';
	import { ApiError } from '$lib/api/client';
	import { ActivityIndicator, Alert, Button, Card, Field, PageShell, SelectInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/chat-studio';

	const scope = $derived($auth.token && $auth.projectId && $auth.userId ? { token: $auth.token, projectId: $auth.projectId } : null);
	const ownerKey = $derived(`${$auth.userId ?? ''}:${$auth.projectId ?? ''}`);
	let activeOwner = '';
	let generation = 0;
	let models = $state<RealtimeModel[]>([]);
	let selected = $state('');
	let capabilities = $state<RealtimeCapabilities | null>(null);
	let voice = $state('');
	let loading = $state(false);
	let capabilityLoading = $state(false);
	let connecting = $state(false);
	let connected = $state(false);
	let muted = $state(false);
	let inputTranscript = $state('');
	let outputTranscript = $state('');
	let error = $state('');
	let socket: WebSocket | null = null;
	let activeProvider = $state('');
	let media: MediaStream | null = null;
	let context: AudioContext | null = null;
	let microphone: MediaStreamAudioSourceNode | null = null;
	let capture: AudioWorkletNode | null = null;
	let playback: AudioBufferSourceNode[] = [];
	let nextPlayback = 0;
	let pendingRequest: AbortController | null = null;
	let pendingIntent: { fingerprint: string; key: string } | null = null;
	const model = $derived(models.find((item) => String(item.id) === selected));
	const readiness = $derived(realtimeReadiness(model, capabilities));
	const fingerprint = $derived(JSON.stringify([ownerKey, selected, voice]));
	$effect(() => {
		const current = fingerprint;
		untrack(() => { if (pendingIntent?.fingerprint !== current) pendingIntent = null; });
	});

	function flushPlayback() {
		for (const source of playback) {
			try { source.stop(); } catch { /* Already finished. */ }
		}
		playback = [];
		nextPlayback = context?.currentTime ?? 0;
	}
	function stop(clearError = true, preserveIntent = false) {
		generation++;
		pendingRequest?.abort();
		pendingRequest = null;
		if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'session.close' }));
		socket?.close();
		socket = null;
		capture?.disconnect();
		capture = null;
		microphone?.disconnect();
		microphone = null;
		media?.getTracks().forEach((track) => track.stop());
		media = null;
		flushPlayback();
		if (context) void context.close().catch(() => {});
		context = null;
		connecting = false;
		connected = false;
		muted = false;
		inputTranscript = '';
		outputTranscript = '';
		activeProvider = '';
		if (!preserveIntent) pendingIntent = null;
		if (clearError) error = '';
	}
	async function loadModels(requestScope: RealtimeScope, epoch: number) {
		loading = true;
		try {
			const list = await realtimeVoiceApi.models(requestScope);
			if (epoch !== generation) return;
			models = list.filter((item) => item.model_kind === 'realtime' && Number.isSafeInteger(item.id) && item.id > 0);
			selected = models[0] ? String(models[0].id) : '';
		} catch {
			if (epoch === generation) error = t('realtimeVoice.modelsLoadFailed');
		} finally {
			if (epoch === generation) loading = false;
		}
	}
	async function loadCapabilities(current: RealtimeModel, requestScope: RealtimeScope, epoch: number) {
		capabilityLoading = true;
		try {
			const response = await realtimeVoiceApi.capabilities(current.id, requestScope);
			if (epoch !== generation || selected !== String(current.id)) return;
			capabilities = response;
			voice = response.available_voices?.includes(voice) ? voice : (response.default_voice ?? '');
		} catch {
			if (epoch === generation && selected === String(current.id)) error = t('realtimeVoice.routeUnverified');
		} finally {
			if (epoch === generation && selected === String(current.id)) capabilityLoading = false;
		}
	}
	$effect(() => {
		const next = scope && ownerKey ? ownerKey : '';
		if (next === activeOwner) return;
		activeOwner = next;
		untrack(() => {
			stop();
			models = [];
			selected = '';
			capabilities = null;
			voice = '';
			if (scope) void loadModels(scope, generation);
		});
	});
	$effect(() => {
		const chosen = model;
		const requestScope = scope;
		untrack(() => {
			capabilities = null;
			if (chosen && requestScope) void loadCapabilities(chosen, requestScope, generation);
		});
	});
	onDestroy(() => stop());

	function play(delta: string, rate: number) {
		if (!context || !connected || rate !== 24000) return;
		const samples = decodePcm16(delta);
		const buffer = context.createBuffer(1, samples.length, rate);
		buffer.getChannelData(0).set(samples);
		const source = context.createBufferSource();
		source.buffer = buffer;
		source.connect(context.destination);
		const start = Math.max(context.currentTime, nextPlayback);
		source.start(start);
		nextPlayback = start + buffer.duration;
		playback.push(source);
		source.onended = () => { playback = playback.filter((item) => item !== source); source.disconnect(); };
	}
	async function captureAudio(stream: MediaStream, rate: number, epoch: number) {
		const active = new AudioContext({ sampleRate: rate });
		context = active;
		await active.audioWorklet.addModule('/audio/pcm16-capture.js');
		if (epoch !== generation || socket?.readyState !== WebSocket.OPEN) return;
		microphone = active.createMediaStreamSource(stream);
		capture = new AudioWorkletNode(active, 'pcm16-capture', { processorOptions: { targetRate: rate } });
		capture.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
			if (muted || socket?.readyState !== WebSocket.OPEN || epoch !== generation || !event.data) return;
			socket.send(JSON.stringify({ type: 'audio.input.append', audio: pcm16Base64(new Int16Array(event.data)) }));
		};
		microphone.connect(capture);
		capture.connect(active.destination);
		await active.resume();
		connected = true;
		connecting = false;
		pendingIntent = null;
	}
	function onFrame(event: MessageEvent, epoch: number) {
		if (epoch !== generation || typeof event.data !== 'string' || event.data.length > 64 * 1024) return;
		try {
			const packet = JSON.parse(event.data);
			switch (packet.type) {
				case 'session.ready':
					if (media && [16000, 24000].includes(packet.input_sample_rate_hz) && packet.output_sample_rate_hz === 24000) {
						void captureAudio(media, packet.input_sample_rate_hz, epoch).catch(() => { error = t('realtimeVoice.microphoneStreamFailed'); stop(false); });
					} else { error = t('realtimeVoice.sessionFormatMismatch'); stop(false); }
					break;
				case 'audio.output.delta': play(packet.delta, packet.sample_rate_hz); break;
				case 'transcript.input.delta': if (typeof packet.delta === 'string') inputTranscript = (inputTranscript + packet.delta).slice(-4096); break;
				case 'transcript.output.delta': if (typeof packet.delta === 'string') outputTranscript = (outputTranscript + packet.delta).slice(-4096); break;
				case 'session.interrupted': flushPlayback(); break;
				case 'session.closed': stop(); break;
				case 'error': error = t('realtimeVoice.providerFailed'); stop(false); break;
			}
		} catch {
			error = t('realtimeVoice.invalidResponse');
			stop(false);
		}
	}
	async function start() {
		if (!scope || !model || !capabilities || readiness || connecting || connected || !capabilities.available_voices.includes(voice)) return;
		if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
			error = t('realtimeVoice.streamingUnsupported');
			return;
		}
		connecting = true;
		error = '';
		const epoch = generation;
		const requestScope = scope;
		const currentFingerprint = fingerprint;
		try {
			const acquired = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
			if (epoch !== generation) { acquired.getTracks().forEach((track) => track.stop()); return; }
			media = acquired;
			const key = pendingIntent?.fingerprint === currentFingerprint ? pendingIntent.key : crypto.randomUUID();
			pendingIntent = { fingerprint: currentFingerprint, key };
			pendingRequest = new AbortController();
			const session = await realtimeVoiceApi.createSession(model.id, voice, requestScope, key, pendingRequest.signal);
			if (epoch !== generation) return;
			activeProvider = session.provider_type;
			socket = realtimeVoiceApi.connect(session);
			socket.onmessage = (event) => onFrame(event, epoch);
			socket.onclose = () => { if (epoch === generation) { error = connected ? t('realtimeVoice.connectionClosed') : t('realtimeVoice.connectionFailed'); stop(false, !connected); } };
			socket.onerror = () => { if (epoch === generation) { error = t('realtimeVoice.connectionUnavailable'); stop(false, !connected); } };
		} catch (cause) {
			if (epoch !== generation) return;
			if (cause instanceof DOMException && cause.name === 'NotAllowedError') error = t('realtimeVoice.microphoneDenied');
			else if (cause instanceof ApiError && cause.status === 402) error = t('realtimeVoice.quotaInsufficient');
			else error = t('realtimeVoice.sessionFailed');
			stop(false, !(cause instanceof ApiError && cause.status >= 400 && cause.status < 500));
		} finally {
			if (epoch === generation) connecting = false;
		}
	}
	function interrupt() {
		if (activeProvider === 'gemini') {
			// Gemini Live has automatic barge-in, not a response.cancel command.
			stop();
			return;
		}
		flushPlayback();
		if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'response.cancel' }));
	}
</script>

<PageShell max="7xl">
	<div class="studio">
		<header class="header"><div><p class="muted">{t('realtimeVoice.breadcrumb')}</p><h1>{t('realtimeVoice.title')}</h1><p class="muted">{t('realtimeVoice.description')}</p></div><Button href="/dashboard/chat" variant="secondary">{t('realtimeVoice.textChat')}</Button></header>
		<Card><div class="controls">
			<Field label={t('realtimeVoice.model')} for="realtime-model"><SelectInput id="realtime-model" bind:value={selected} disabled={connecting || connected || loading}><option value="">{t('realtimeVoice.selectModel')}</option>{#each models as item (item.id)}<option value={String(item.id)}>{item.display_name}</option>{/each}</SelectInput></Field>
			<Field label={t('realtimeVoice.voice')} for="realtime-voice"><SelectInput id="realtime-voice" bind:value={voice} disabled={connecting || connected || capabilityLoading}>{#each capabilities?.available_voices ?? [] as option (option)}<option value={option}>{option}</option>{/each}</SelectInput></Field>
			{#if error}<Alert tone="danger">{error}</Alert>{:else if loading || capabilityLoading}<p role="status" class="muted">{t('realtimeVoice.checking')}</p>{:else if readiness}<Alert tone="warning">{readiness}</Alert>{:else}<Alert tone="success">{t('realtimeVoice.ready')}</Alert>{/if}
			<div class="actions"><Button disabled={Boolean(readiness) || loading || capabilityLoading || connecting || connected || !scope} onclick={() => void start()}>{connecting ? t('realtimeVoice.connecting') : t('realtimeVoice.startSession')}</Button><Button variant="secondary" disabled={!connected} onclick={() => muted = !muted}>{muted ? t('realtimeVoice.microphoneOn') : t('realtimeVoice.microphoneOff')}</Button><Button variant="secondary" disabled={!connected} onclick={interrupt}>{activeProvider === 'gemini' ? t('realtimeVoice.interruptAndEnd') : t('realtimeVoice.interrupt')}</Button><Button variant="danger-outline" disabled={!connected && !connecting} onclick={() => stop()}>{t('realtimeVoice.endSession')}</Button></div>
			{#if connecting}<ActivityIndicator variant="pulse" label={t('realtimeVoice.connecting')} />{/if}
			{#if connected}<p role="status" class="muted">{muted ? t('realtimeVoice.connectedMuted') : t('realtimeVoice.connectedMicrophoneOn')}</p>{/if}
		</div></Card>
		{#if connected}<div class="transcripts"><Card><h2>{t('realtimeVoice.mySpeech')}</h2><p class="transcript">{inputTranscript || t('realtimeVoice.waitingInputTranscript')}</p></Card><Card><h2>{t('realtimeVoice.response')}</h2><p class="transcript">{outputTranscript || t('realtimeVoice.waitingOutputTranscript')}</p></Card></div>{/if}
	</div>
</PageShell>

<style>
	.studio, .controls { display: grid; gap: 1rem; min-width: 0; }
	.header { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 1rem; }
	h1 { font-size: 1.25rem; font-weight: 600; }
	h2 { font-size: 0.875rem; font-weight: 600; }
	.muted { font-size: 0.8125rem; line-height: 1.5; color: var(--color-ink-2); }
	.actions { display: flex; flex-wrap: wrap; gap: 0.75rem; }
	.transcripts { display: grid; gap: 1rem; }
	.transcript { white-space: pre-wrap; overflow-wrap: anywhere; margin-top: 0.75rem; font-size: 0.875rem; line-height: 1.6; }
	@media (min-width: 768px) { .transcripts { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
