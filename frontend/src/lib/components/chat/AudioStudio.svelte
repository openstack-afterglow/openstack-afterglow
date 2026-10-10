<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { audioStudioApi, audioReadiness, type AudioKind, type AudioModel, type AudioCapabilities, type AudioFormat, type AudioScope } from '$lib/api/audioStudio';
	import { formatTranscriptTime, transcriptSrt, transcriptText, type AudioTranscript } from '$lib/api/audioTranscript';
	import { offerAudioTranscript } from '$lib/api/audioChatHandoff';
	import { ApiError } from '$lib/api/client';
	import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
	import LumenPermissionNotice from './LumenPermissionNotice.svelte';
	import { ActivityIndicator, Alert, Button, Field, PageShell, SelectInput, Tabs, TextareaInput, TextInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/chat-studio';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	const AUDIO_MIMES = new Set(['audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/ogg', 'audio/webm']);
	const MIME_LABELS: Record<string, string> = { 'audio/mpeg': 'MP3', 'audio/wav': 'WAV', 'audio/x-wav': 'WAV', 'audio/mp4': 'M4A', 'audio/ogg': 'OGG', 'audio/webm': 'WebM' };
	const FORMATS: AudioFormat[] = ['mp3', 'wav'];
	const SEGMENT_TIMESTAMPS: Array<'segment'> = ['segment'];
	// Example drafts only fill an empty canvas; they never replace text the user wrote.
	const EXAMPLES = [
		{ labelKey: 'audioStudio.example.greetingLabel', textKey: 'audioStudio.example.greetingText' },
		{ labelKey: 'audioStudio.example.announcementLabel', textKey: 'audioStudio.example.announcementText' },
		{ labelKey: 'audioStudio.example.storyLabel', textKey: 'audioStudio.example.storyText' }
	] as const;
	interface AudioSource { name: string; size: number; type: string; url: string }
	// Only the selected model's capability response may advertise a voice or timestamp granularity.
	// Permission reloads disable actions, but do not change the durable actor.
	const scope = $derived($authReady && !$projectSwitching && $auth.token && $auth.projectId && $auth.userId ? { token: $auth.token, projectId: $auth.projectId } : null);
	const audioAllowed = $derived(Boolean(scope) && $serviceCapabilities('lumen-audio_user'));
	const uploadAllowed = $derived(audioAllowed && $serviceCapabilities('lumen-assets_editor'));
	const ownerKey = $derived(`${$auth.userId ?? ''}:${$auth.projectId ?? ''}`);
	let activeOwner = '';
	let generation = 0;
	let sourceVersion = 0;
	let mode = $state<AudioKind>('tts');
	let models = $state<Record<AudioKind, AudioModel[]>>({ tts: [], stt: [] });
	let selected = $state<Record<AudioKind, string>>({ tts: '', stt: '' });
	let capabilities = $state<Record<AudioKind, AudioCapabilities | null>>({ tts: null, stt: null });
	let loading = $state<Record<AudioKind, boolean>>({ tts: false, stt: false });
	let capabilityLoading = $state<Record<AudioKind, boolean>>({ tts: false, stt: false });
	let errors = $state<Record<AudioKind, string>>({ tts: '', stt: '' });
	let failures = $state<Record<AudioKind, string>>({ tts: '', stt: '' });
	let draft = $state('');
	let voice = $state('alloy');
	let format = $state<AudioFormat>('mp3');
	let language = $state('');
	let timestamps = $state(true);
	let source = $state<AudioSource | null>(null);
	let assetId = $state('');
	let assetName = $state('');
	let transcript = $state<AudioTranscript | null>(null);
	let transcriptTimed = $state(false);
	let transcriptName = $state('transcript');
	let exportUrls = $state({ txt: '', srt: '' });
	let copyStatus = $state('');
	let dragging = $state(false);
	let recording = $state(false);
	let permissionPending = $state(false);
	let busyTts = $state(false);
	let uploading = $state(false);
	let transcribing = $state(false);
	let audioUrl = $state('');
	let outputFormat = $state<AudioFormat>('mp3');
	let outputVoice = $state('');
	let media = $state<HTMLAudioElement | null>(null);
	let sourceMedia = $state<HTMLAudioElement | null>(null);
	let recorder: MediaRecorder | null = null;
	let stream: MediaStream | null = null;
	let pendingCapture: File | null = null;
	let uploadRequest: AbortController | null = null;
	let transcriptionRequest: AbortController | null = null;
	let aborters: AbortController[] = [];
	let pendingSpeech: { fingerprint: string; key: string } | null = null;
	let pendingTranscription: { fingerprint: string; key: string } | null = null;
	const busyStt = $derived(uploading || transcribing);
	const sourceLocked = $derived(!uploadAllowed || busyStt || recording);
	// Microphone capture is only visible in the STT panel, so the mode stays there until it is stopped.
	const micActive = $derived(recording || permissionPending);
	const modeTabs = $derived([
		{ value: 'tts', label: t('audioStudio.textToSpeech'), panelId: 'audio-panel-tts', disabled: micActive && mode === 'stt' },
		{ value: 'stt', label: t('audioStudio.speechToText'), panelId: 'audio-panel-stt' }
	]);
	function selectMode(value: string) {
		const next: AudioKind = value === 'stt' ? 'stt' : 'tts';
		if (next === mode || (next === 'tts' && micActive)) return;
		// The generated speech stays available, but its hidden player must not keep playing.
		media?.pause();
		sourceMedia?.pause();
		mode = next;
	}
	const ttsModel = $derived(models.tts.find((model) => String(model.id) === selected.tts));
	const sttModel = $derived(models.stt.find((model) => String(model.id) === selected.stt));
	const ttsReadiness = $derived(audioReadiness(ttsModel, capabilities.tts, 'tts'));
	const sttReadiness = $derived(audioReadiness(sttModel, capabilities.stt, 'stt'));
	const voices = $derived(capabilities.tts?.available_voices ?? []);
	const formats = $derived(capabilities.tts?.available_formats?.filter((item) => FORMATS.includes(item)) ?? []);
	const timestampKnown = $derived(Boolean(sttModel && capabilities.stt?.model_id === sttModel.id));
	const timestampSupported = $derived(timestampKnown && Boolean(capabilities.stt?.available_timestamp_granularities?.includes('segment')));
	const requestTimestamps = $derived(timestampSupported && timestamps);
	const timestampHelp = $derived(
		!sttModel ? t('audioStudio.timestampSelectModel')
		: !timestampKnown ? (errors.stt ? t('audioStudio.timestampUnavailable') : t('audioStudio.timestampChecking'))
		: timestampSupported ? t('audioStudio.timestampSupported')
		: t('audioStudio.timestampUnsupported')
	);
	const fingerprint = $derived(JSON.stringify([ownerKey, selected.tts, draft.trim(), voice, format]));
	const transcriptionFingerprint = $derived(JSON.stringify([ownerKey, selected.stt, assetId, language.trim(), requestTimestamps ? SEGMENT_TIMESTAMPS : []]));
	const ttsReady = $derived(audioAllowed && !loading.tts && !capabilityLoading.tts && !ttsReadiness && Boolean(draft.trim()) && voices.includes(voice) && formats.includes(format) && !busyTts);
	const sttReady = $derived(audioAllowed && Boolean(assetId) && !sttReadiness && !loading.stt && !capabilityLoading.stt && !busyStt && !recording);
	$effect(() => {
		const current = fingerprint;
		untrack(() => { if (pendingSpeech && pendingSpeech.fingerprint !== current) pendingSpeech = null; });
	});
	$effect(() => {
		const current = transcriptionFingerprint;
		untrack(() => { if (pendingTranscription && pendingTranscription.fingerprint !== current) pendingTranscription = null; });
	});

	function message(cause: unknown): string {
		if (cause instanceof ApiError) {
			if (cause.status === 401 || cause.status === 403) return t('audioStudio.projectDenied');
			if (cause.status === 402) return t('audioStudio.quotaInsufficient');
			if ([400, 409, 422].includes(cause.status)) return cause.message.slice(0, 250);
			return t('audioStudio.requestFailed', { status: cause.status });
		}
		return cause instanceof Error ? cause.message : t('audioStudio.connectionFailed');
	}
	function fileSize(bytes: number): string {
		if (bytes < 1024) return `${bytes.toLocaleString(intlLocale())} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString(intlLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })} KB`;
		return `${(bytes / 1024 / 1024).toLocaleString(intlLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`;
	}
	/** Download stem derived from the selected input name, safe on common desktop file systems. */
	function exportStem(name: string): string {
		const cleaned = name.normalize('NFC').replace(/\.[^.]*$/, '').replace(/[\p{Cc}<>:"/\\|?*]+/gu, '_').replace(/\s+/g, '_');
		const stem = Array.from(cleaned).slice(0, 80).join('').replace(/^[._-]+|[._-]+$/g, '');
		return !stem || /^(con|prn|aux|nul|com\d|lpt\d)$/i.test(stem) ? 'transcript' : stem;
	}
	function controller(): AbortController {
		const item = new AbortController();
		aborters.push(item);
		return item;
	}
	function canPublish(epoch: number): boolean {
		return epoch === generation && activeOwner === ownerKey && audioAllowed;
	}
	function cleanupAudio() {
		media?.pause();
		if (audioUrl) URL.revokeObjectURL(audioUrl);
		audioUrl = '';
		outputVoice = '';
	}
	function releaseExports() {
		if (exportUrls.txt) URL.revokeObjectURL(exportUrls.txt);
		if (exportUrls.srt) URL.revokeObjectURL(exportUrls.srt);
		exportUrls = { txt: '', srt: '' };
	}
	function clearTranscript() {
		releaseExports();
		transcript = null;
		transcriptTimed = false;
		copyStatus = '';
	}
	/** Drops the local preview, scanned asset and every result derived from that source. */
	function releaseSource() {
		sourceVersion++;
		pendingCapture = null;
		sourceMedia?.pause();
		uploadRequest?.abort();
		uploadRequest = null;
		transcriptionRequest?.abort();
		transcriptionRequest = null;
		transcribing = false;
		pendingTranscription = null;
		if (source) URL.revokeObjectURL(source.url);
		source = null;
		assetId = '';
		assetName = '';
		uploading = false;
		clearTranscript();
	}
	function stopMic() {
		if (recorder && recorder.state !== 'inactive') recorder.stop();
		stream?.getTracks().forEach((track) => track.stop());
		recorder = null;
		stream = null;
		recording = false;
		permissionPending = false;
	}
	function reset() {
		generation++;
		aborters.forEach((item) => item.abort());
		aborters = [];
		stopMic();
		cleanupAudio();
		releaseSource();
		models = { tts: [], stt: [] };
		selected = { tts: '', stt: '' };
		capabilities = { tts: null, stt: null };
		loading = { tts: false, stt: false };
		capabilityLoading = { tts: false, stt: false };
		errors = { tts: '', stt: '' };
		failures = { tts: '', stt: '' };
		draft = '';
		voice = 'alloy';
		format = 'mp3';
		language = '';
		timestamps = true;
		dragging = false;
		busyTts = false;
		transcribing = false;
		pendingSpeech = null;
		pendingTranscription = null;
	}
	async function loadModels(kind: AudioKind, requestScope: AudioScope, epoch: number) {
		if (!audioAllowed || activeOwner !== ownerKey) return;
		loading = { ...loading, [kind]: true };
		errors = { ...errors, [kind]: '' };
		try {
			const list = await audioStudioApi.models(kind, requestScope);
			if (!canPublish(epoch)) return;
			models = { ...models, [kind]: list.filter((model) => model.model_kind === kind && Number.isSafeInteger(model.id) && model.id > 0) };
			if (!models[kind].some((model) => String(model.id) === selected[kind])) selected = { ...selected, [kind]: models[kind][0] ? String(models[kind][0].id) : '' };
		} catch (cause) {
			if (canPublish(epoch)) errors = { ...errors, [kind]: message(cause) };
		} finally {
			if (epoch === generation) loading = { ...loading, [kind]: false };
		}
	}
	async function loadCapability(kind: AudioKind, model: AudioModel, requestScope: AudioScope, epoch: number) {
		if (!audioAllowed || activeOwner !== ownerKey) return;
		capabilityLoading = { ...capabilityLoading, [kind]: true };
		try {
			const value = await audioStudioApi.capabilities(kind, model.id, requestScope);
			if (!canPublish(epoch) || selected[kind] !== String(model.id)) return;
			capabilities = { ...capabilities, [kind]: value };
			if (kind === 'tts') {
				if (!value.available_voices?.includes(voice)) voice = value.available_voices?.[0] ?? '';
				if (!value.available_formats?.includes(format)) format = value.available_formats?.[0] ?? 'mp3';
			}
		} catch (cause) {
			if (canPublish(epoch) && selected[kind] === String(model.id)) errors = { ...errors, [kind]: message(cause) };
		} finally {
			if (epoch === generation && selected[kind] === String(model.id)) capabilityLoading = { ...capabilityLoading, [kind]: false };
		}
	}
	$effect(() => {
		const next = scope && ownerKey ? ownerKey : '';
		if (next === activeOwner) return;
		activeOwner = next;
		untrack(() => {
			reset();
			if (audioAllowed && scope) {
				const requestScope = scope;
				const epoch = generation;
				void loadModels('tts', requestScope, epoch);
				void loadModels('stt', requestScope, epoch);
			}
		});
	});
	$effect(() => {
		const denied = $serviceDenials('lumen-audio_user');
		const assetsDenied = $serviceDenials('lumen-assets_editor');
		untrack(() => {
			if (denied) reset();
			else if (assetsDenied) { releaseSource(); stopMic(); }
		});
	});
	$effect(() => {
		const allowed = audioAllowed;
		untrack(() => {
			if (!allowed || !scope) return;
			for (const kind of ['tts', 'stt'] as const) {
				if (!models[kind].length && !loading[kind]) void loadModels(kind, scope, generation);
			}
		});
	});
	$effect(() => {
		const allowed = uploadAllowed;
		untrack(() => {
			if (allowed && pendingCapture) {
				const file = pendingCapture;
				pendingCapture = null;
				void upload(file);
			}
		});
	});
	$effect(() => {
		if (audioAllowed) return;
		untrack(() => { media?.pause(); sourceMedia?.pause(); });
	});
	$effect(() => {
		const tts = ttsModel;
		const stt = sttModel;
		const authenticated = Boolean(scope);
		const allowed = audioAllowed;
		const owner = ownerKey;
		untrack(() => {
			const requestScope = scope;
			if (!owner || !authenticated || !allowed || !requestScope) return;
			for (const [kind, model] of [['tts', tts], ['stt', stt]] as const) {
				if (model && capabilities[kind]?.model_id !== model.id) {
					capabilities = { ...capabilities, [kind]: null };
					void loadCapability(kind, model, requestScope, generation);
				}
			}
		});
	});
	onDestroy(reset);

	async function speech() {
		if (!canPublish(generation) || !ttsReady || !scope || !ttsModel) return;
		const epoch = generation;
		const requestScope = scope;
		const fingerprintNow = fingerprint;
		const requestVoice = voice;
		const requestFormat = format;
		const key = pendingSpeech?.fingerprint === fingerprintNow ? pendingSpeech.key : crypto.randomUUID();
		pendingSpeech = { fingerprint: fingerprintNow, key };
		const request = controller();
		busyTts = true;
		failures = { ...failures, tts: '' };
		try {
			const blob = await audioStudioApi.speech({ model_id: String(ttsModel.id), input: draft.trim(), voice: requestVoice, response_format: requestFormat }, requestScope, key, request.signal);
			if (!canPublish(epoch) || request.signal.aborted) return;
			cleanupAudio();
			audioUrl = URL.createObjectURL(blob);
			outputFormat = requestFormat;
			outputVoice = requestVoice;
			pendingSpeech = null;
		} catch (cause) {
			if (canPublish(epoch) && !request.signal.aborted) {
				if (cause instanceof ApiError && [400, 401, 402, 403, 404, 409, 422].includes(cause.status)) pendingSpeech = null;
				failures = { ...failures, tts: message(cause) };
			}
		} finally {
			if (epoch === generation) busyTts = false;
		}
	}
	async function upload(file: File) {
		if (!canPublish(generation) || !uploadAllowed || !scope || uploading || transcribing) return;
		if (!AUDIO_MIMES.has(file.type)) { failures = { ...failures, stt: t('audioStudio.invalidFile') }; return; }
		releaseSource();
		const version = sourceVersion;
		const epoch = generation;
		const requestScope = scope;
		const request = controller();
		uploadRequest = request;
		source = { name: file.name, size: file.size, type: file.type, url: URL.createObjectURL(file) };
		uploading = true;
		failures = { ...failures, stt: '' };
		try {
			const asset = await audioStudioApi.upload(file, requestScope, request.signal);
			if (!canPublish(epoch) || !uploadAllowed || version !== sourceVersion || request.signal.aborted) return;
			assetId = asset.id;
			assetName = asset.name;
		} catch (cause) {
			if (canPublish(epoch) && uploadAllowed && version === sourceVersion && !request.signal.aborted) {
				releaseSource();
				failures = { ...failures, stt: t('audioStudio.uploadFailed', { message: message(cause) }) };
			}
		} finally {
			if (epoch === generation && version === sourceVersion) {
				uploading = false;
				uploadRequest = null;
			}
		}
	}
	function chooseFile(event: Event & { currentTarget: HTMLInputElement }) {
		const input = event.currentTarget;
		const file = input.files?.[0];
		input.value = '';
		if (file && !sourceLocked) void upload(file);
	}
	function dragOver(event: DragEvent) {
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = sourceLocked ? 'none' : 'copy';
		dragging = !sourceLocked;
	}
	function dragLeave(event: DragEvent) {
		if (!(event.relatedTarget instanceof Node && (event.currentTarget as HTMLElement).contains(event.relatedTarget))) dragging = false;
	}
	function dropFile(event: DragEvent) {
		event.preventDefault();
		dragging = false;
		const file = event.dataTransfer?.files?.[0];
		if (file && !sourceLocked) void upload(file);
	}
	function removeSource() {
		if (transcribing) return;
		releaseSource();
		failures = { ...failures, stt: '' };
	}
	async function startRecording() {
		if (!canPublish(generation) || !scope || !uploadAllowed) return;
		if (recording || permissionPending || busyStt) return;
		if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { failures = { ...failures, stt: t('audioStudio.recordingUnsupported') }; return; }
		permissionPending = true;
		const epoch = generation;
		const version = sourceVersion;
		try {
			const acquired = await navigator.mediaDevices.getUserMedia({ audio: true });
			if (epoch !== generation || activeOwner !== ownerKey || !scope || version !== sourceVersion) { acquired.getTracks().forEach((track) => track.stop()); return; }
			stream = acquired;
			const mimeType = ['audio/webm', 'audio/ogg', 'audio/mp4'].find((mime) => MediaRecorder.isTypeSupported(mime));
			const active = new MediaRecorder(acquired, mimeType ? { mimeType } : undefined);
			const chunks: BlobPart[] = [];
			let recordingFailed = false;
			active.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
			active.onerror = () => {
				recordingFailed = true;
				if (epoch !== generation || activeOwner !== ownerKey || version !== sourceVersion) return;
				if (audioAllowed) failures = { ...failures, stt: t('audioStudio.recordingFailed') };
				stopMic();
			};
			active.onstop = () => {
				acquired.getTracks().forEach((track) => track.stop());
				if (epoch !== generation || activeOwner !== ownerKey || !scope || version !== sourceVersion || recordingFailed || !chunks.length) return;
				const type = active.mimeType.split(';')[0];
				if (!AUDIO_MIMES.has(type)) { failures = { ...failures, stt: t('audioStudio.recordingFormatUnsupported') }; return; }
				const extension = type === 'audio/mp4' ? 'm4a' : type.split('/')[1];
				const file = new File(chunks, `recording.${extension}`, { type });
				if (uploadAllowed) void upload(file);
				else {
					releaseSource();
					pendingCapture = file;
					source = { name: file.name, size: file.size, type: file.type, url: URL.createObjectURL(file) };
				}
			};
			active.start();
			recorder = active;
			recording = true;
			failures = { ...failures, stt: '' };
		} catch (cause) {
			if (epoch !== generation || activeOwner !== ownerKey || version !== sourceVersion) return;
			stream?.getTracks().forEach((track) => track.stop());
			stream = null;
			if (epoch === generation) failures = { ...failures, stt: cause instanceof DOMException && cause.name === 'NotAllowedError' ? t('audioStudio.microphoneDenied') : t('audioStudio.microphoneFailed', { message: message(cause) }) };
		} finally {
			if (epoch === generation && version === sourceVersion) permissionPending = false;
		}
	}
	function showTranscript(result: AudioTranscript, name: string, timed: boolean) {
		releaseExports();
		transcript = result;
		transcriptTimed = timed;
		transcriptName = exportStem(name);
		copyStatus = '';
		exportUrls = {
			txt: URL.createObjectURL(new Blob([transcriptText(result)], { type: 'text/plain;charset=utf-8' })),
			srt: result.segments.length ? URL.createObjectURL(new Blob([transcriptSrt(result)], { type: 'application/x-subrip;charset=utf-8' })) : ''
		};
	}
	async function transcribe() {
		if (!canPublish(generation) || !sttReady || !scope || !sttModel) return;
		const epoch = generation;
		const version = sourceVersion;
		const request = controller();
		transcriptionRequest = request;
		const requestScope = scope;
		const timed = requestTimestamps;
		const name = source?.name || assetName;
		transcribing = true;
		failures = { ...failures, stt: '' };
		try {
			const intentFingerprint = transcriptionFingerprint;
			const intentKey = pendingTranscription?.fingerprint === intentFingerprint ? pendingTranscription.key : crypto.randomUUID();
			pendingTranscription = { fingerprint: intentFingerprint, key: intentKey };
			const result = await audioStudioApi.transcribe({
				model_id: String(sttModel.id),
				input_asset_id: assetId,
				...(language.trim() ? { language: language.trim() } : {}),
				...(timed ? { timestamp_granularities: SEGMENT_TIMESTAMPS } : {})
			}, requestScope, intentKey, request.signal);
			if (canPublish(epoch) && version === sourceVersion && !request.signal.aborted) {
				showTranscript(result, name, timed);
				pendingTranscription = null;
			}
		} catch (cause) {
			if (canPublish(epoch) && version === sourceVersion && !request.signal.aborted) {
				if (cause instanceof ApiError && [400, 401, 402, 403, 404, 409, 422].includes(cause.status)) pendingTranscription = null;
				failures = { ...failures, stt: message(cause) };
			}
		} finally {
			if (epoch === generation && version === sourceVersion) {
				transcribing = false;
				if (transcriptionRequest === request) transcriptionRequest = null;
			}
		}
	}
	async function copyTranscript() {
		if (!canPublish(generation) || !transcript) return;
		const epoch = generation;
		const text = transcript.text;
		try {
			await navigator.clipboard.writeText(text);
			if (canPublish(epoch) && transcript?.text === text) copyStatus = t('audioStudio.copied');
		} catch (cause) {
			if (canPublish(epoch)) failures = { ...failures, stt: t('audioStudio.copyFailed', { message: message(cause) }) };
		}
	}
	function insertIntoChat() {
		if (!canPublish(generation) || !$serviceCapabilities('lumen-chat_user') || !$auth.userId || !$auth.projectId || !transcript?.text.trim()) return;
		offerAudioTranscript($auth.userId, $auth.projectId, transcript.text);
		void goto('/dashboard/chat');
	}
</script>

<PageShell max="7xl">
	<LumenPermissionNotice leaves={['lumen-audio_user']} />
	<div class="studio">
		<header class="header">
			<div class="title">
				<p class="muted">{t('audioStudio.breadcrumb')}</p>
				<h1>{t('audioStudio.title')}</h1>
				<p class="muted">{mode === 'tts' ? t('audioStudio.ttsDescription') : t('audioStudio.sttDescription')}</p>
			</div>
			<Button href="/dashboard/chat" variant="secondary">{t('audioStudio.textChat')}</Button>
		</header>
		<Tabs id="audio-mode" ariaLabel={t('audioStudio.mode')} value={mode} items={modeTabs} onchange={selectMode} />
		{#if micActive}<p class="muted">{t('audioStudio.recordingModeLocked')}</p>{/if}

		<div id="audio-panel-tts" role="tabpanel" aria-labelledby="audio-mode-tts" tabindex="0" class="panel" hidden={mode !== 'tts'}>
				<form class="workspace" onsubmit={(event) => { event.preventDefault(); void speech(); }}>
					<div class="canvas">
						<div class="canvas-head">
							<label for="audio-text" class="canvas-label">{t('audioStudio.textLabel')} <span class="required" aria-hidden="true">*</span></label>
							<Button variant="ghost" size="sm" disabled={!audioAllowed || !draft || busyTts} onclick={() => { if (audioAllowed) draft = ''; }}>{t('audioStudio.clear')}</Button>
						</div>
						<TextareaInput id="audio-text" bind:value={draft} rows={12} required disabled={!audioAllowed || busyTts} placeholder={t('audioStudio.textPlaceholder')} ariaDescribedBy="audio-text-count" class="draft" />
						<div class="canvas-foot">
							{#if !draft}
								<div class="examples" role="group" aria-label={t('audioStudio.examples')}>
									<span class="muted">{t('audioStudio.examplesHelp')}</span>
									{#each EXAMPLES as example (example.labelKey)}<Button variant="outline" size="sm" disabled={!audioAllowed || busyTts} onclick={() => { if (audioAllowed) draft = t(example.textKey); }}>{t(example.labelKey)}</Button>{/each}
								</div>
							{/if}
							<p id="audio-text-count" class="muted count">{t('audioStudio.characterCount', { count: draft.length.toLocaleString(intlLocale()) })}</p>
						</div>
					</div>
					<aside class="settings" aria-labelledby="audio-tts-settings">
						<h2 id="audio-tts-settings">{t('audioStudio.speechSettings')}</h2>
						<Field label={t('audioStudio.speechModel')} for="audio-tts-model"><SelectInput id="audio-tts-model" value={selected.tts} onchange={(event) => { if (audioAllowed) selected = { ...selected, tts: (event.currentTarget as HTMLSelectElement).value }; }} disabled={!audioAllowed || loading.tts || busyTts}><option value="">{t('audioStudio.selectModel')}</option>{#each models.tts as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput></Field>
						{#if loading.tts || capabilityLoading.tts}<p role="status" class="muted">{t('audioStudio.speechChecking')}</p>{:else if errors.tts}<Alert tone="danger">{errors.tts} <Button variant="subtle" disabled={!audioAllowed} onclick={() => scope && loadModels('tts', scope, generation)}>{t('audioStudio.reloadModels')}</Button></Alert>{:else if !models.tts.length}<Alert tone="warning">{t('audioStudio.noSpeechModels')}</Alert>{:else if ttsReadiness}<Alert tone="warning">{ttsReadiness}</Alert>{:else if audioAllowed}<p role="status" class="ready">{t('audioStudio.speechReady')}</p>{/if}
						<fieldset class="voices" disabled={!audioAllowed || busyTts || !voices.length}>
							<legend>{t('audioStudio.voice')}</legend>
							{#if voices.length}
								<div class="voice-list">{#each voices as option}<label class="voice"><input type="radio" name="audio-voice" value={option} bind:group={voice} /><span>{option}</span></label>{/each}</div>
							{:else}
								<p class="muted">{t('audioStudio.voicesHelp')}</p>
							{/if}
						</fieldset>
						<Field label={t('audioStudio.format')} for="audio-format"><SelectInput id="audio-format" bind:value={format} disabled={!audioAllowed || busyTts || !formats.length}>{#each formats as option}<option value={option}>{option.toUpperCase()}</option>{/each}</SelectInput></Field>
					</aside>
					<div class="playbar">
						<div class="playbar-output">
							{#if busyTts}<ActivityIndicator variant="bars" label={t('audioStudio.speechGenerating')} />{/if}
							{#if audioAllowed && audioUrl}
								<audio bind:this={media} src={audioUrl} controls aria-label={t('audioStudio.generatedSpeech')}></audio>
								<p class="muted">{t('audioStudio.speechOutputInfo', { voice: outputVoice, format: outputFormat.toUpperCase() })}</p>
							{:else}
								<p class="muted">{t('audioStudio.speechOutputHelp')}</p>
							{/if}
							{#if failures.tts}<Alert tone="danger">{failures.tts}</Alert>{/if}
						</div>
						<div class="playbar-actions">
							{#if audioAllowed && audioUrl}<a href={audioUrl} download={`speech.${outputFormat}`} class="file-action">{t('audioStudio.downloadSpeech')}</a>{/if}
							<Button type="submit" size="lg" disabled={!ttsReady}>{busyTts ? t('audioStudio.speechGenerating') : t('audioStudio.generateSpeech')}</Button>
						</div>
					</div>
				</form>
			</div>
		<div id="audio-panel-stt" role="tabpanel" aria-labelledby="audio-mode-stt" tabindex="0" class="panel" hidden={mode !== 'stt'}>
				<div class="workspace">
					<div class="canvas">
						<h2>{t('audioStudio.audioInput')}</h2>
						<div class="dropzone" class:dragging role="group" aria-label={t('audioStudio.dropzone')} ondragenter={dragOver} ondragover={dragOver} ondragleave={dragLeave} ondrop={dropFile}>
							<svg class="drop-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V5m0 0-4 4m4-4 4 4M5 15v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
							<p class="drop-title">{t('audioStudio.dropTitle')}</p>
							<p class="muted">{t('audioStudio.dropHelp')}</p>
							<div class="actions">
								<input id="audio-file" class="file-input" type="file" accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/ogg,audio/webm" disabled={sourceLocked} aria-describedby="audio-file-help" onchange={chooseFile} />
								<label for="audio-file" class="file-action">{t('audioStudio.chooseFile')}</label>
								<Button variant="secondary" disabled={!recording && (!uploadAllowed || busyStt || permissionPending)} onclick={() => recording ? stopMic() : void startRecording()}>{permissionPending ? t('audioStudio.microphonePermissionChecking') : recording ? t('audioStudio.stopRecording') : t('audioStudio.recordMicrophone')}</Button>
							</div>
							<p id="audio-file-help" class="muted">{t('audioStudio.audioFileHelp')}</p>
						</div>
						{#if recording}<p role="status" class="recording">{t('audioStudio.recordingStatus')}</p>{/if}
						{#if uploadAllowed && source}
							<div class="source">
								<div class="source-info">
									<p class="source-name">{source.name}</p>
									<p class="muted">{fileSize(source.size)} · {MIME_LABELS[source.type] ?? source.type}</p>
									{#if uploading}<ActivityIndicator variant="upload" label={t('audioStudio.uploading')} />{:else if assetId}<p role="status" class="muted">{t('audioStudio.scannedInput', { name: assetName })}</p>{/if}
								</div>
								<audio bind:this={sourceMedia} src={source.url} controls aria-label={t('audioStudio.previewSource', { name: source.name })}></audio>
								<Button variant="ghost" size="icon" ariaLabel={t('audioStudio.removeSource')} disabled={transcribing} onclick={removeSource}><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" /></svg></Button>
							</div>
						{/if}
					</div>
					<aside class="settings" aria-labelledby="audio-stt-settings">
						<h2 id="audio-stt-settings">{t('audioStudio.transcriptionSettings')}</h2>
						<Field label={t('audioStudio.transcriptionModel')} for="audio-stt-model"><SelectInput id="audio-stt-model" value={selected.stt} onchange={(event) => { if (audioAllowed) selected = { ...selected, stt: (event.currentTarget as HTMLSelectElement).value }; }} disabled={!audioAllowed || loading.stt || busyStt}><option value="">{t('audioStudio.selectModel')}</option>{#each models.stt as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput></Field>
						{#if loading.stt || capabilityLoading.stt}<p role="status" class="muted">{t('audioStudio.transcriptionChecking')}</p>{:else if errors.stt}<Alert tone="danger">{errors.stt} <Button variant="subtle" disabled={!audioAllowed} onclick={() => scope && loadModels('stt', scope, generation)}>{t('audioStudio.reloadModels')}</Button></Alert>{:else if !models.stt.length}<Alert tone="warning">{t('audioStudio.noTranscriptionModels')}</Alert>{:else if sttReadiness}<Alert tone="warning">{sttReadiness}</Alert>{:else if audioAllowed}<p role="status" class="ready">{t('audioStudio.transcriptionReady')}</p>{/if}
						<Field label={t('audioStudio.languageCode')} for="audio-language"><TextInput id="audio-language" bind:value={language} placeholder={t('audioStudio.languagePlaceholder')} disabled={!audioAllowed || busyStt} /></Field>
						<div class="switch-row">
							<div class="switch-copy">
								<label for="audio-timestamps">{t('audioStudio.timestamps')}</label>
								<p id="audio-timestamps-help" class="muted">{timestampHelp}</p>
							</div>
							<input id="audio-timestamps" class="switch" type="checkbox" role="switch" checked={requestTimestamps} disabled={!audioAllowed || !timestampSupported || busyStt} aria-describedby="audio-timestamps-help" onchange={(event) => { if (audioAllowed) timestamps = event.currentTarget.checked; }} />
						</div>
						<Button size="lg" disabled={!sttReady} onclick={() => void transcribe()}>{transcribing ? t('audioStudio.processingAudio') : t('audioStudio.convertToText')}</Button>
						{#if transcribing}<ActivityIndicator variant="dots" label={t('audioStudio.processingAudio')} />{/if}
						{#if failures.stt}<Alert tone="danger">{failures.stt}</Alert>{/if}
					</aside>
				</div>
				{#if audioAllowed && transcript}
					<section class="results" aria-labelledby="audio-result-title">
						<div class="results-head">
							<h2 id="audio-result-title">{t('audioStudio.transcriptionResult')}</h2>
							<div class="actions">
								<Button variant="secondary" onclick={() => void copyTranscript()}>{t('audioStudio.copyText')}</Button>
								{#if exportUrls.txt}<a href={exportUrls.txt} download={`${transcriptName}.txt`} class="file-action">{t('audioStudio.downloadText')}</a>{/if}
								{#if exportUrls.srt}<a href={exportUrls.srt} download={`${transcriptName}.srt`} class="file-action">{t('audioStudio.downloadSrt')}</a>{/if}
								<Button variant="secondary" disabled={!$serviceCapabilities('lumen-chat_user')} onclick={insertIntoChat}>{t('audioStudio.insertIntoChat')}</Button>
							</div>
						</div>
						{#if copyStatus}<p role="status" class="muted">{copyStatus}</p>{/if}
						{#if transcript.segments.length}
							<div class="table-wrap">
								<table class="segments">
									<thead><tr><th scope="col">{t('audioStudio.timeRange')}</th><th scope="col">{t('audioStudio.convertedText')}</th></tr></thead>
									<tbody>
										{#each transcript.segments as segment, index (index)}
											<tr><td class="range"><time datetime={`PT${segment.start}S`}>{formatTranscriptTime(segment.start)}</time> – <time datetime={`PT${segment.end}S`}>{formatTranscriptTime(segment.end)}</time></td><td>{segment.text}</td></tr>
										{/each}
									</tbody>
								</table>
							</div>
						{:else}
							<p class="muted">{transcriptTimed ? t('audioStudio.noSegments') : t('audioStudio.noTiming')}</p>
							<p class="transcript">{transcript.text}</p>
						{/if}
					</section>
				{/if}
			</div>
	</div>
</PageShell>

<style>
	.studio, .panel { display: grid; gap: 1.5rem; min-width: 0; }
	.panel[hidden] { display: none; }
	.header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1rem; align-items: flex-start; }
	.title { display: grid; gap: 0.25rem; min-width: 0; }
	h1 { font-size: 1.25rem; font-weight: 600; line-height: 1.75rem; color: var(--color-ink-0); }
	h2 { font-size: 0.875rem; font-weight: 600; color: var(--color-ink-0); }
	.muted { font-size: 0.8125rem; color: var(--color-ink-2); line-height: 1.5; }
	.ready { font-size: 0.8125rem; color: var(--color-state-success-text); line-height: 1.5; }
	.recording { font-size: 0.8125rem; color: var(--color-warm-text); }
	.actions { display: flex; gap: 0.5rem 0.75rem; flex-wrap: wrap; align-items: center; }
	.workspace { display: grid; gap: 1.5rem; min-width: 0; }
	.canvas, .settings { display: grid; gap: 1rem; align-content: start; min-width: 0; }
	.settings { border-top: 1px solid var(--color-line); padding-top: 1.25rem; }
	.canvas-head, .canvas-foot { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; align-items: center; justify-content: space-between; }
	.canvas-label { font-size: 0.8125rem; font-weight: 500; color: var(--color-ink-1); }
	.required { color: var(--color-state-danger); }
	.canvas :global(.draft) { min-height: 16rem; padding: 1rem; font-size: 0.875rem; line-height: 1.7; }
	.examples { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; min-width: 0; }
	.count { margin-left: auto; font-variant-numeric: tabular-nums; }
	.voices { display: grid; gap: 0.5rem; min-width: 0; margin: 0; padding: 0; border: 0; }
	.voices legend { margin-bottom: 0.5rem; padding: 0; font-size: 0.75rem; font-weight: 500; color: var(--color-ink-1); }
	.voice-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr)); gap: 0.5rem; max-height: 16rem; overflow-y: auto; padding: 2px; }
	.voice { display: flex; gap: 0.5rem; align-items: center; min-width: 0; padding: 0.5rem 0.625rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); color: var(--color-ink-1); font-size: 0.8125rem; cursor: pointer; transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard); }
	.voice span { overflow-wrap: anywhere; }
	.voice input { flex: none; accent-color: var(--color-action-warm); }
	.voice:hover { background: var(--color-surface-selected); }
	.voice:has(input:checked) { border-color: var(--color-action-warm); background: var(--color-surface-selected); color: var(--color-ink-0); }
	.voice:has(input:focus-visible) { box-shadow: var(--focus-ring); }
	.voices:disabled .voice { cursor: not-allowed; opacity: 0.55; }
	.playbar { display: flex; flex-wrap: wrap; gap: 0.75rem 1.25rem; align-items: center; border-top: 1px solid var(--color-line); padding-top: 1rem; min-width: 0; }
	.playbar-output { display: grid; gap: 0.375rem; flex: 1 1 18rem; min-width: 0; }
	.playbar-actions { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; margin-left: auto; }
	/* Native players follow the app theme (dark by default, html.light otherwise). */
	audio { width: 100%; min-width: 0; color-scheme: dark; }
	:global(html.light) audio { color-scheme: light; }
	.dropzone { display: grid; justify-items: center; gap: 0.5rem; padding: 2rem 1rem; border: 1px dashed var(--color-line-2); border-radius: var(--radius-lg); background: var(--color-surface-base); text-align: center; transition: border-color var(--motion-duration-fast) var(--motion-ease-standard), background var(--motion-duration-fast) var(--motion-ease-standard); }
	.dropzone.dragging { border-color: var(--color-action-warm); background: var(--color-surface-selected); }
	.dropzone .actions { justify-content: center; margin-top: 0.25rem; }
	.drop-icon { width: 2.25rem; height: 2.25rem; color: var(--color-ink-1); }
	.drop-title { font-size: 0.875rem; font-weight: 600; color: var(--color-ink-0); }
	.file-input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; opacity: 0; }
	.file-action { display: inline-flex; align-items: center; justify-content: center; gap: 0.375rem; padding: 0.4375rem 0.875rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-raised); color: var(--color-ink-1); font-size: 0.8125rem; font-weight: 500; line-height: 1.2; white-space: nowrap; text-decoration: none; cursor: pointer; transition: background var(--motion-duration-fast) var(--motion-ease-standard), color var(--motion-duration-fast) var(--motion-ease-standard); }
	.file-action:hover { background: var(--color-surface-sunken); color: var(--color-ink-0); }
	a.file-action:focus-visible, .file-input:focus-visible + .file-action { outline: none; box-shadow: var(--focus-ring); }
	.file-input:disabled + .file-action { opacity: 0.45; cursor: not-allowed; }
	.source { display: grid; grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: 'info remove' 'player player'; gap: 0.75rem; align-items: center; padding: 0.75rem 1rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); }
	.source-info { grid-area: info; display: grid; gap: 0.125rem; min-width: 0; }
	.source audio { grid-area: player; }
	.source :global(.btn) { grid-area: remove; }
	.source-name { font-size: 0.875rem; font-weight: 500; color: var(--color-ink-0); overflow-wrap: anywhere; }
	.switch-row { display: flex; gap: 1rem; align-items: flex-start; justify-content: space-between; }
	.switch-copy { display: grid; gap: 0.25rem; min-width: 0; }
	.switch-copy label { font-size: 0.75rem; font-weight: 500; color: var(--color-ink-1); }
	.switch { position: relative; flex: none; width: 2.5rem; height: 1.5rem; margin: 0; border: 1px solid var(--color-line-2); border-radius: 999px; background: var(--color-surface-sunken); appearance: none; cursor: pointer; transition: background var(--motion-duration-fast) var(--motion-ease-standard), border-color var(--motion-duration-fast) var(--motion-ease-standard); }
	.switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 1.125rem; height: 1.125rem; border-radius: 50%; background: var(--color-ink-1); transition: transform var(--motion-duration-fast) var(--motion-ease-standard); }
	.switch:checked { border-color: var(--color-action-warm); background: var(--color-action-warm); }
	.switch:checked::after { transform: translateX(1rem); background: var(--color-action-on-warm); }
	.switch:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.switch:disabled { opacity: 0.45; cursor: not-allowed; }
	.results { display: grid; gap: 1rem; min-width: 0; border-top: 1px solid var(--color-line); padding-top: 1.5rem; }
	.results-head { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; justify-content: space-between; }
	.table-wrap { min-width: 0; overflow-x: auto; }
	.segments { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
	.segments th { padding: 0.625rem 1rem; border-bottom: 1px solid var(--color-line); background: var(--color-surface-raised); color: var(--color-ink-2); font-size: 0.75rem; font-weight: 500; text-align: left; }
	.segments td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--color-line); color: var(--color-ink-1); vertical-align: top; overflow-wrap: anywhere; }
	.segments .range { width: 15rem; color: var(--color-ink-2); font-size: 0.8125rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
	.transcript { font-size: 0.875rem; line-height: 1.6; color: var(--color-ink-1); white-space: pre-wrap; overflow-wrap: anywhere; }
	@media (max-width: 767px) {
		.playbar-actions { width: 100%; margin-left: 0; }
		.playbar-actions > :global(*) { flex: 1 1 auto; }
		.segments thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
		.segments tr { display: grid; gap: 0.25rem; padding: 0.75rem 0; border-bottom: 1px solid var(--color-line); }
		.segments td { display: block; padding: 0; border: 0; }
		.segments .range { width: auto; }
	}
	@media (min-width: 768px) {
		.source { grid-template-columns: minmax(0, 14rem) minmax(0, 1fr) auto; grid-template-areas: 'info player remove'; }
	}
	@media (min-width: 1024px) {
		.workspace { grid-template-columns: minmax(0, 1fr) minmax(17rem, 20rem); gap: 2rem; }
		.settings { border-top: 0; padding-top: 0; border-left: 1px solid var(--color-line); padding-left: 1.5rem; }
		.playbar { grid-column: 1 / -1; }
		.canvas :global(.draft) { min-height: 22rem; }
	}
</style>
