<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { realtimeVoiceApi, realtimeReadiness, realtimeMode, applyTranscriptionFrame, pcm16Base64, decodePcm16, REALTIME_OUTPUT_LANGUAGE, REALTIME_REASONING_EFFORTS, type RealtimeReasoningEffort, type RealtimeModel, type RealtimeCapabilities, type RealtimeScope, type RealtimeMode, type RealtimeTranscript } from '$lib/api/realtimeVoice';
	import { ApiError } from '$lib/api/client';
	import { encodeRealtimeImageFrame, REALTIME_IMAGE_ACCEPT, REALTIME_IMAGE_FRAME_BYTES, REALTIME_IMAGES_PER_SESSION } from '$lib/api/realtimeImage';
	import { Alert, Button, Card, Field, PageShell, SelectInput, TextareaInput, TextInput } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/chat-studio';
	import { t as chatT } from '$lib/i18n/ns/chat-panel';
	import { effortLabel } from '$lib/api/chatEffort';
	import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
	import PersonalWorkspaceNotice from './PersonalWorkspaceNotice.svelte';
	import { personalWorkspace } from '$lib/stores/personalWorkspace';
	import { dashboardCreditMessage } from '$lib/api/chatDomainBilling';
	import ProviderModelSelect from './ProviderModelSelect.svelte';
	import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState, type ExperienceContext } from '$lib/utils/experience';

	// A refreshed token is the same actor, even while exact grants are unavailable.
	const scope = $derived($authReady && !$projectSwitching && $auth.token && $auth.projectId && $auth.userId ? { token: $auth.token, projectId: $auth.projectId } : null);
	const audioAllowed = $derived(Boolean(scope) && $serviceCapabilities('lumen-audio_user'));
	const ownerKey = $derived(`${$auth.userId ?? ''}:${$auth.projectId ?? ''}`);
	let activeOwner = '';
	let generation = 0;
	let models = $state<RealtimeModel[]>([]);
	let selected = $state<number | null>(null);
	let capabilities = $state<RealtimeCapabilities | null>(null);
	let voice = $state('');
	let outputLanguage = $state('');
	let instructions = $state('');
	let reasoningEffort = $state<RealtimeReasoningEffort | ''>('');
	let loading = $state(false);
	let capabilityLoading = $state(false);
	let connecting = $state(false);
	let connected = $state(false);
	let muted = $state(false);
	let inputTranscript = $state('');
	let outputTranscript = $state('');
	let error = $state('');
	let activeMode = $state<RealtimeMode>('conversation');
	let segments = $state<RealtimeTranscript[]>([]);
	let ending = $state(false);
	let ended = $state(false);
	let commitBusy = $state(false);
	let pendingAudio = $state(false);
	let capabilityTicket = 0;
	let flushTicket = 0;
	let pendingFlush: { id: number; resolve: () => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> } | null = null;
	let closeTimer: ReturnType<typeof setTimeout> | null = null;
	let socket: WebSocket | null = null;
	let activeProvider = $state('');
	let admittedImageInput = $state(false);
	let imagePicker = $state<HTMLInputElement>();
	let sendingImage = $state(false);
	let sentImages = $state(0);
	let imageError = $state('');
	let media: MediaStream | null = null;
	let context: AudioContext | null = null;
	let microphone: MediaStreamAudioSourceNode | null = null;
	let capture: AudioWorkletNode | null = null;
	let playback: AudioBufferSourceNode[] = [];
	let nextPlayback = 0;
	let pendingRequest: AbortController | null = null;
	let pendingIntent: { fingerprint: string; key: string } | null = null;
	let connectionExperience: ExperienceContext | undefined;
	const model = $derived(models.find((item) => item.id === selected));
	const readiness = $derived(realtimeReadiness(model, capabilities));
	const mode = $derived(realtimeMode(capabilities));
	const transcription = $derived(mode === 'transcription');
	const translation = $derived(mode === 'translation');
	const showVoice = $derived(mode === 'conversation' || mode === 'live');
	const showInstructions = $derived(showVoice && capabilities?.realtime_session_fields?.includes('instructions'));
	const imageSupported = $derived(mode === 'conversation' && capabilities?.realtime_image_input === true);
	const canSendImage = $derived(audioAllowed && connected && !ending && admittedImageInput && imageSupported && sentImages < REALTIME_IMAGES_PER_SESSION);
	const reasoningEfforts = $derived(mode === 'conversation' && capabilities?.realtime_session_fields?.includes('reasoning_effort')
		? (capabilities.available_reasoning_efforts ?? []).filter((effort) => REALTIME_REASONING_EFFORTS.includes(effort))
		: []);
	const selectedEffort = $derived(reasoningEffort && reasoningEfforts.includes(reasoningEffort) ? reasoningEffort : '');
	const languageValid = $derived(!translation || REALTIME_OUTPUT_LANGUAGE.test(outputLanguage.trim()));
	const modeLabel = $derived(
		mode === 'translation' ? t('realtimeModes.translation')
			: mode === 'live' ? t('realtimeModes.live')
			: mode === 'transcription' ? t('realtimeTranscription.transcription')
			: mode === 'conversation' ? t('realtimeTranscription.conversation')
			: t('realtimeTranscription.unsupported')
	);
	const fingerprint = $derived(JSON.stringify([ownerKey, selected, mode, showVoice ? voice : '', translation ? outputLanguage.trim() : '', showInstructions ? instructions.trim() : '', selectedEffort]));
	$effect(() => {
		const current = fingerprint;
		untrack(() => { if (pendingIntent?.fingerprint !== current) pendingIntent = null; });
	});

	function canPublish(epoch: number): boolean {
		return epoch === generation && activeOwner === ownerKey && audioAllowed;
	}
	function pauseMicrophone() {
		media?.getTracks().forEach((track) => { track.enabled = audioAllowed && !muted; });
	}
	function toggleMute() {
		if (!connected || (muted && !canPublish(generation))) return;
		muted = !muted;
		if (activeMode === 'live' && canPublish(generation) && socket?.readyState === WebSocket.OPEN) {
			socket.send(JSON.stringify({ type: muted ? 'audio.input.mute' : 'audio.input.unmute' }));
		}
		pauseMicrophone();
	}
	function flushPlayback() {
		for (const source of playback) {
			try { source.stop(); } catch { /* Already finished. */ }
		}
		playback = [];
		nextPlayback = context?.currentTime ?? 0;
	}
	function releaseMicrophone() {
		if (pendingFlush) { clearTimeout(pendingFlush.timer); pendingFlush.reject(new Error('capture stopped')); pendingFlush = null; }
		capture?.disconnect();
		capture = null;
		microphone?.disconnect();
		microphone = null;
		media?.getTracks().forEach((track) => track.stop());
		media = null;
	}
	function releaseAudio() {
		releaseMicrophone();
		flushPlayback();
		if (context) void context.close().catch(() => {});
		context = null;
	}
	function stop(clearError = true, preserveIntent = false, preserveResults = false) {
		const wasConnected = connected;
		generation++;
		if (closeTimer) clearTimeout(closeTimer);
		closeTimer = null;
		const experience = connectionExperience;
		connectionExperience = undefined;
		pendingRequest?.abort();
		pendingRequest = null;
		if (socket?.readyState === WebSocket.OPEN && !ending) socket.send(JSON.stringify({ type: 'session.close' }));
		socket?.close();
		socket = null;
		releaseAudio();
		connecting = false;
		connected = false;
		muted = false;
		ending = false;
		commitBusy = false;
		pendingAudio = false;
		if (!preserveResults) {
			inputTranscript = '';
			outputTranscript = '';
			segments = [];
			ended = false;
		}
		activeProvider = '';
		admittedImageInput = false;
		sendingImage = false;
		sentImages = 0;
		imageError = '';
		if (!preserveIntent) pendingIntent = null;
		if (clearError) error = '';
		if (wasConnected) {
			experienceState(experience, 'disabled', 4);
			void experienceApplied(experience, {}, () => !connected && !connecting);
		}
	}
	function flushAudio(): Promise<void> {
		if (!capture) return Promise.reject(new Error('capture unavailable'));
		return new Promise((resolve, reject) => {
			const id = ++flushTicket;
			const timer = setTimeout(() => { if (pendingFlush?.id === id) { pendingFlush = null; reject(new Error('capture flush timed out')); } }, 2000);
			pendingFlush = { id, resolve, reject, timer };
			capture!.port.postMessage({ type: 'flush', id });
		});
	}
	async function commitSegment(closeAfter = false) {
		if (!canPublish(generation) || !connected || ending || commitBusy || socket?.readyState !== WebSocket.OPEN) return;
		commitBusy = true;
		const epoch = generation;
		if (closeAfter) media?.getTracks().forEach((track) => { track.enabled = false; });
		try {
			await flushAudio();
			if (!canPublish(epoch) || socket?.readyState !== WebSocket.OPEN) return;
			if (pendingAudio && activeMode === 'transcription') { socket.send(JSON.stringify({ type: 'audio.input.commit' })); pendingAudio = false; }
			if (closeAfter) {
				ending = true;
				releaseMicrophone();
				socket.send(JSON.stringify({ type: 'session.close' }));
				closeTimer = setTimeout(() => {
					if (epoch === generation && ending) { error = disconnectMessage(); stop(false, false, true); }
				}, 30000);
			}
		} catch {
			if (epoch === generation) { error = t('realtimeVoice.microphoneStreamFailed'); stop(false, false, true); }
		} finally { if (epoch === generation) commitBusy = false; }
	}
	function disconnectMessage(): string {
		return connected && activeMode === 'live' ? t('realtimeModes.usageUnconfirmed')
			: connected ? t('realtimeVoice.connectionClosed') : t('realtimeVoice.connectionFailed');
	}
	function endSession() {
		if (activeMode !== 'conversation' && connected && audioAllowed) void commitSegment(true);
		else stop();
	}
	function finishSession(epoch: number) {
		if (socket) socket.onclose = null;
		if (closeTimer) clearTimeout(closeTimer);
		closeTimer = null;
		ending = true;
		releaseMicrophone();
		const finish = () => {
			if (epoch !== generation) return;
			stop(true, false, true);
			ended = true;
		};
		const remaining = nextPlayback - (context?.currentTime ?? nextPlayback);
		if (playback.length && remaining > 0) closeTimer = setTimeout(finish, Math.min(remaining * 1000, 30_000));
		else finish();
	}
	async function loadModels(requestScope: RealtimeScope, epoch: number) {
		if (!audioAllowed || activeOwner !== ownerKey) return;
		requestScope = { ...requestScope, experience: beginExperienceLoad('lumen', 'resource.list') };
		experienceState(requestScope.experience, 'loading', 0);
		loading = true;
		try {
			const list = await realtimeVoiceApi.models(requestScope);
			if (!canPublish(epoch)) { experienceDiscarded(requestScope.experience, 'stale'); return; }
			models = list.filter((item) => item.model_kind === 'realtime' && Number.isSafeInteger(item.id) && item.id > 0);
			selected = models[0]?.id ?? null;
			experienceState(requestScope.experience, models.length ? 'ready' : 'empty', 0);
			const appliedModels = models;
			void experienceApplied(requestScope.experience, {}, () => canPublish(epoch) && models === appliedModels);
		} catch {
			if (canPublish(epoch)) { error = t('realtimeVoice.modelsLoadFailed'); experienceState(requestScope.experience, 'error', 0); }
		} finally {
			if (epoch === generation) loading = false;
		}
	}
	function selectModel(row: RealtimeModel | null) {
		const id = row?.id ?? null;
		if (!audioAllowed || connecting || connected || loading || selected === id) return;
		capabilityTicket++;
		capabilities = null;
		capabilityLoading = false;
		error = '';
		selected = id;
	}
	async function loadCapabilities(current: RealtimeModel, requestScope: RealtimeScope, epoch: number) {
		if (!audioAllowed || activeOwner !== ownerKey) return;
		requestScope = { ...requestScope, experience: beginExperienceLoad('lumen', 'resource.detail') };
		const ticket = ++capabilityTicket;
		experienceState(requestScope.experience, 'loading', 1);
		capabilityLoading = true;
		try {
			const response = await realtimeVoiceApi.capabilities(current.id, requestScope);
			if (!canPublish(epoch) || selected !== current.id || ticket !== capabilityTicket) { experienceDiscarded(requestScope.experience, 'stale'); return; }
			capabilities = response;
			voice = response.available_voices?.includes(voice) ? voice : (response.default_voice ?? '');
			outputLanguage = '';
			instructions = '';
			reasoningEffort = '';
			inputTranscript = '';
			outputTranscript = '';
			segments = [];
			ended = false;
			experienceState(requestScope.experience, 'ready', 1);
			const appliedCapabilities = capabilities;
			void experienceApplied(requestScope.experience, {}, () => canPublish(epoch) && selected === current.id && capabilities === appliedCapabilities);
		} catch {
			if (canPublish(epoch) && selected === current.id && ticket === capabilityTicket) { error = t('realtimeVoice.routeUnverified'); experienceState(requestScope.experience, 'error', 1); }
		} finally {
			if (epoch === generation && selected === current.id && ticket === capabilityTicket) capabilityLoading = false;
		}
	}
	$effect(() => {
		const next = scope && ownerKey ? ownerKey : '';
		if (next === activeOwner) return;
		activeOwner = next;
		untrack(() => {
			stop();
			models = [];
			selected = null;
			capabilities = null;
			voice = '';
			outputLanguage = '';
			instructions = '';
			reasoningEffort = '';
			loading = false;
			capabilityLoading = false;
			if (audioAllowed && scope) void loadModels(scope, generation);
		});
	});
	$effect(() => {
		const denied = $serviceDenials('lumen-audio_user');
		untrack(() => {
			if (!denied) return;
			stop();
			models = [];
			selected = null;
			capabilities = null;
			voice = '';
			outputLanguage = '';
			instructions = '';
			reasoningEffort = '';
			loading = false;
			capabilityLoading = false;
		});
	});
	$effect(() => {
		const allowed = audioAllowed;
		const owner = ownerKey;
		untrack(() => {
			if (allowed && owner && scope && !models.length && !loading) void loadModels(scope, generation);
		});
	});
	$effect(() => {
		const allowed = audioAllowed;
		const isMuted = muted;
		const active = connected || connecting;
		untrack(() => {
			if (!active) return;
			media?.getTracks().forEach((track) => { track.enabled = allowed && !isMuted; });
			if (!allowed) flushPlayback();
		});
	});
	$effect(() => {
		const chosen = model;
		const authenticated = Boolean(scope);
		const allowed = audioAllowed;
		untrack(() => {
			if (!authenticated || !allowed || !scope) return;
			if (chosen && capabilities?.model_id !== chosen.id) {
				capabilities = null;
				void loadCapabilities(chosen, scope, generation);
			}
		});
	});
	onDestroy(() => stop());

	function play(delta: string, rate: number) {
		if (!audioAllowed || !context || !connected || rate !== 24000) return;
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
	async function captureAudio(stream: MediaStream, rate: number, epoch: number, experience: ExperienceContext | undefined) {
		const active = new AudioContext({ sampleRate: rate });
		context = active;
		await active.audioWorklet.addModule('/audio/pcm16-capture.js');
		if (epoch !== generation || activeOwner !== ownerKey || !scope || socket?.readyState !== WebSocket.OPEN) return;
		pauseMicrophone();
		microphone = active.createMediaStreamSource(stream);
		capture = new AudioWorkletNode(active, 'pcm16-capture', { processorOptions: { targetRate: rate } });
		capture.port.onmessage = (event: MessageEvent<ArrayBuffer | { type: string; id: number }>) => {
			if (event.data && !(event.data instanceof ArrayBuffer)) {
				if (event.data.type === 'flushed' && pendingFlush?.id === event.data.id) {
					clearTimeout(pendingFlush.timer); pendingFlush.resolve(); pendingFlush = null;
				}
				return;
			}
			if (!canPublish(epoch) || muted || ending || socket?.readyState !== WebSocket.OPEN || !event.data || event.data.byteLength === 0) return;
			socket.send(JSON.stringify({ type: 'audio.input.append', audio: pcm16Base64(new Int16Array(event.data)) }));
			pendingAudio = true;
		};
		microphone.connect(capture);
		capture.connect(active.destination);
		await active.resume();
		if (epoch !== generation || activeOwner !== ownerKey || !scope) return;
		pauseMicrophone();
		connected = true;
		connecting = false;
		pendingIntent = null;
		experienceState(experience, 'ready', 3);
		void experienceApplied(experience, {}, () => canPublish(epoch) && connected);
	}
	function onFrame(event: MessageEvent, epoch: number, experience: ExperienceContext | undefined) {
		if (epoch !== generation || activeOwner !== ownerKey || !scope || typeof event.data !== 'string' ||
			event.data.length > (admittedImageInput ? REALTIME_IMAGE_FRAME_BYTES : 64 * 1024)) return;
		try {
			const packet = JSON.parse(event.data);
			switch (packet.type) {
				case 'session.ready':
					if (connected || context) break;
					if (media && (packet.realtime_kind ?? 'conversation') === activeMode &&
						[16000, 24000].includes(packet.input_sample_rate_hz) &&
						(activeMode === 'conversation' || packet.input_sample_rate_hz === capabilities?.input_sample_rate_hz) &&
						packet.output_sample_rate_hz === (activeMode === 'transcription' ? 0 : 24000)) {
						void captureAudio(media, packet.input_sample_rate_hz, epoch, experience).catch(() => { if (epoch === generation && activeOwner === ownerKey && scope) { error = t('realtimeVoice.microphoneStreamFailed'); experienceState(experience, 'error', 5); stop(false, false, activeMode === 'transcription'); } });
					} else { error = t('realtimeVoice.sessionFormatMismatch'); stop(false); }
					break;
				case 'audio.output.delta': if (activeMode !== 'transcription') play(packet.delta, packet.sample_rate_hz); break;
				case 'transcript.input.delta':
					if (audioAllowed) {
						if (activeMode === 'transcription') segments = applyTranscriptionFrame(segments, packet);
						else if (typeof packet.delta === 'string') inputTranscript = (inputTranscript + packet.delta).slice(-4096);
					}
					break;
				case 'transcript.input.completed':
				case 'transcript.input.failed':
					if (audioAllowed && activeMode === 'transcription') segments = applyTranscriptionFrame(segments, packet);
					break;
				case 'transcript.output.delta': if (audioAllowed && activeMode !== 'transcription' && typeof packet.delta === 'string') outputTranscript = (outputTranscript + packet.delta).slice(-4096); break;
				case 'session.interrupted': flushPlayback(); break;
				case 'session.closed':
					if (activeMode !== 'conversation') finishSession(epoch);
					else stop();
					break;
				case 'error':
					// Lumen reports rejected operations independently of session closure.
					if (audioAllowed) {
						error = dashboardCreditMessage(packet.code) ?? t(packet.code === 'realtime_hold_limit' ? 'realtimeVoice.quotaInsufficient' : 'realtimeVoice.providerFailed');
						experienceState(experience, 'error', 5);
					}
					break;
			}
		} catch {
			error = t('realtimeVoice.invalidResponse');
			stop(false, false, activeMode === 'transcription');
		}
	}
	async function start() {
		if (!canPublish(generation) || !scope || !model || !capabilities || !mode || readiness || connecting || connected ||
			!languageValid || (showVoice && !capabilities.available_voices.includes(voice)) || $personalWorkspace) return;
		if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
			error = t('realtimeVoice.streamingUnsupported');
			return;
		}
		connecting = true;
		error = '';
		activeMode = mode;
		segments = [];
		inputTranscript = '';
		outputTranscript = '';
		ended = false;
		const epoch = generation;
		const currentFingerprint = fingerprint;
		const sessionVoice = showVoice ? voice : null;
		const sessionOptions = {
			...(translation ? { output_language: outputLanguage.trim() } : {}),
			...(showInstructions && instructions.trim() ? { instructions: instructions.trim() } : {}),
			...(selectedEffort ? { reasoning_effort: selectedEffort } : {}),
			max_duration_seconds: Math.min(capabilities.default_duration_seconds ?? 300, capabilities.max_duration_seconds)
		};
		const experience = beginExperienceAction('lumen', 'start', 'shared.stream');
		connectionExperience = experience;
		experienceState(experience, 'loading', 2);
		try {
			const acquired = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
			if (!canPublish(epoch)) { acquired.getTracks().forEach((track) => track.stop()); if (epoch === generation) stop(true, true); return; }
			media = acquired;
			pauseMicrophone();
			const key = pendingIntent?.fingerprint === currentFingerprint ? pendingIntent.key : crypto.randomUUID();
			pendingIntent = { fingerprint: currentFingerprint, key };
			pendingRequest = new AbortController();
			if (!audioAllowed || !scope) { stop(true, true); return; }
			const session = await realtimeVoiceApi.createSession(model.id, sessionVoice, { ...scope, experience }, key, pendingRequest.signal, mode, sessionOptions);
			if (!canPublish(epoch)) { experienceDiscarded(experience, 'stale'); if (epoch === generation) stop(true, true); return; }
			activeProvider = session.provider_type;
			admittedImageInput = session.realtime_image_input === true;
			socket = realtimeVoiceApi.connect(session);
			socket.onmessage = (event) => onFrame(event, epoch, experience);
			socket.onclose = () => { if (epoch === generation) { error = disconnectMessage(); experienceState(experience, connected ? 'disabled' : 'error', connected ? 4 : 5); stop(false, !connected, activeMode === 'transcription'); } };
			socket.onerror = () => { if (epoch === generation) { error = connected && activeMode === 'live' ? disconnectMessage() : t('realtimeVoice.connectionUnavailable'); experienceState(experience, 'error', 5); stop(false, !connected, activeMode === 'transcription'); } };
		} catch (cause) {
			if (epoch !== generation) return;
			const credit = dashboardCreditMessage(cause);
			if (cause instanceof DOMException && cause.name === 'NotAllowedError') error = t('realtimeVoice.microphoneDenied');
			else if (credit) error = credit;
			else if (cause instanceof ApiError && cause.status === 402) error = t('realtimeVoice.quotaInsufficient');
			else error = t('realtimeVoice.sessionFailed');
			experienceState(experience, 'error', 5);
			if (!(cause instanceof DOMException && cause.name === 'NotAllowedError') && !(cause instanceof ApiError && cause.status >= 400 && cause.status < 500)) experienceDiscarded(experience, 'unknown');
			stop(false, !(cause instanceof ApiError && cause.status >= 400 && cause.status < 500));
		}
	}
	async function sendImage(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file || !canSendImage || sendingImage || !socket || socket.readyState !== WebSocket.OPEN) return;
		const epoch = generation;
		const target = socket;
		const current = () => canPublish(epoch) && canSendImage && socket === target && target.readyState === WebSocket.OPEN;
		imageError = '';
		sendingImage = true;
		try {
			const frame = await encodeRealtimeImageFrame(file);
			if (!current()) return;
			target.send(frame);
			sentImages++;
		} catch {
			if (current()) imageError = t('realtimeImage.error');
		} finally {
			if (epoch === generation) sendingImage = false;
		}
	}
	function interrupt() {
		if (activeProvider === 'gemini') {
			// Gemini Live has automatic barge-in, not a response.cancel command.
			stop();
			return;
		}
		flushPlayback();
		if (canPublish(generation) && socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'response.cancel' }));
	}
</script>

<PageShell>
	<LumenPermissionNotice leaves={['lumen-audio_user']} />
	<PersonalWorkspaceNotice />
	<div class="studio">
		<header class="header"><div><p class="muted">{t('realtimeVoice.breadcrumb')}</p><h1>{t('realtimeTranscription.title')}</h1><p class="muted">{t('realtimeTranscription.description')}</p></div><Button href="/dashboard/chat" variant="secondary">{t('realtimeVoice.textChat')}</Button></header>
		<Card><div class="controls">
			<ProviderModelSelect {models} value={selected} onSelect={selectModel} modelLabel={t('realtimeVoice.model')} placeholder={t('realtimeVoice.selectModel')} id="realtime-model" disabled={!audioAllowed || connecting || connected || loading} />
			{#if capabilities}<p class="muted">{t('realtimeTranscription.mode')}: {modeLabel}</p>{/if}
			{#if showVoice}
				<Field label={t('realtimeVoice.voice')} for="realtime-voice"><SelectInput id="realtime-voice" bind:value={voice} disabled={!audioAllowed || connecting || connected || capabilityLoading}>{#each capabilities?.available_voices ?? [] as option (option)}<option value={option}>{option}</option>{/each}</SelectInput></Field>
			{/if}
			{#if translation}
				<Field label={t('realtimeModes.outputLanguage')} for="realtime-language" help={t('realtimeModes.languageHelp')} error={outputLanguage && !languageValid ? t('realtimeModes.invalidLanguage') : undefined}>
					<TextInput id="realtime-language" bind:value={outputLanguage} maxlength={12} placeholder="es" ariaInvalid={Boolean(outputLanguage && !languageValid)} disabled={!audioAllowed || connecting || connected || capabilityLoading} />
				</Field>
			{/if}
			{#if showInstructions}
				<Field label={t('realtimeModes.instructions')} for="realtime-instructions"><TextareaInput id="realtime-instructions" bind:value={instructions} maxlength={4096} rows={2} disabled={!audioAllowed || connecting || connected || capabilityLoading} /></Field>
			{/if}
			{#if reasoningEfforts.length}
				<Field label={chatT('input.reasoningEffort')} for="realtime-effort"><SelectInput id="realtime-effort" bind:value={reasoningEffort} disabled={!audioAllowed || connecting || connected || capabilityLoading}><option value="">{effortLabel('auto')}</option>{#each reasoningEfforts as effort (effort)}<option value={effort}>{effortLabel(effort)}</option>{/each}</SelectInput></Field>
			{/if}
			{#if error}<Alert tone="danger">{error}</Alert>{:else if loading || capabilityLoading}<LoadingState variant="inline" label={t('realtimeVoice.checking')} />{:else if readiness}<Alert tone="warning">{readiness}</Alert>{:else if audioAllowed && !$personalWorkspace}<Alert tone="success">{transcription ? t('realtimeTranscription.ready') : t('realtimeVoice.ready')}</Alert>{/if}
			<div class="actions">
				<Button disabled={!audioAllowed || $personalWorkspace || !languageValid || Boolean(readiness) || loading || capabilityLoading || connecting || connected} onclick={() => void start()}>{#if connecting}<LoadingState variant="control" label={t('realtimeVoice.connecting')} />{:else}{transcription ? t('realtimeTranscription.start') : t('realtimeVoice.startSession')}{/if}</Button>
				<Button variant="secondary" disabled={!connected || ending || (!audioAllowed && muted)} onclick={toggleMute}>{muted ? t('realtimeVoice.microphoneOn') : t('realtimeVoice.microphoneOff')}</Button>
				{#if transcription}
					<Button variant="secondary" disabled={!connected || !audioAllowed || ending || commitBusy} onclick={() => void commitSegment()}>{t('realtimeTranscription.commit')}</Button>
				{:else if mode === 'conversation'}
					<Button variant="secondary" disabled={!connected} onclick={interrupt}>{activeProvider === 'gemini' ? t('realtimeVoice.interruptAndEnd') : t('realtimeVoice.interrupt')}</Button>
				{/if}
				{#if imageSupported}
					<Button variant="secondary" disabled={!canSendImage || sendingImage} onclick={() => imagePicker?.click()}>{#if sendingImage}<LoadingState variant="control" label={t('realtimeImage.encoding')} />{:else}{t('realtimeImage.send')}{/if}</Button>
					<input bind:this={imagePicker} type="file" accept={REALTIME_IMAGE_ACCEPT} hidden aria-label={t('realtimeImage.send')} onchange={sendImage} disabled={!canSendImage || sendingImage} />
				{/if}
				<Button variant="danger-outline" disabled={(!connected && !connecting) || ending || commitBusy} onclick={endSession}>{t('realtimeVoice.endSession')}</Button>
			</div>
			{#if imageError && audioAllowed}<Alert tone="warning">{imageError}</Alert>{/if}
			{#if sentImages === REALTIME_IMAGES_PER_SESSION && audioAllowed}<p class="muted" role="status">{t('realtimeImage.limit')}</p>{/if}
			{#if ending}<p role="status" class="muted">{activeMode === 'transcription' ? t('realtimeTranscription.ending') : t('realtimeModes.ending')}</p>
			{:else if ended && audioAllowed}<p role="status" class="muted">{t('realtimeTranscription.ended')}</p>
			{:else if connected}<p role="status" class="muted">{muted || !audioAllowed ? t('realtimeVoice.connectedMuted') : t('realtimeVoice.connectedMicrophoneOn')}</p>{/if}
		</div></Card>
		{#if audioAllowed && transcription && (connected || segments.length || ended)}
			<Card><h2>{t('realtimeTranscription.transcription')}</h2>
				{#if !segments.length}<p class="transcript">{connected ? t('realtimeTranscription.waiting') : t('realtimeTranscription.empty')}</p>{/if}
				{#each segments as segment (segment.id)}
					<p class="muted">{segment.state === 'final' ? t('realtimeTranscription.final') : segment.state === 'failed' ? t('realtimeTranscription.failed') : t('realtimeTranscription.partial')}</p>
					<p class="transcript">{segment.text}</p>
				{/each}
				{#if segments.some((segment) => segment.state !== 'final')}<p class="muted">{t('realtimeTranscription.unfinished')}</p>{/if}
			</Card>
		{:else if (connected || ended) && audioAllowed}
			<div class="transcripts"><Card><h2>{t('realtimeVoice.mySpeech')}</h2><p class="transcript">{inputTranscript || t('realtimeVoice.waitingInputTranscript')}</p></Card><Card><h2>{translation ? t('realtimeModes.translation') : t('realtimeVoice.response')}</h2><p class="transcript">{outputTranscript || t('realtimeVoice.waitingOutputTranscript')}</p></Card></div>
		{/if}
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
