<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { audioStudioApi, audioReadiness, type AudioKind, type AudioModel, type AudioCapabilities, type AudioFormat, type AudioScope } from '$lib/api/audioStudio';
	import { formatTranscriptTime, transcriptSrt, transcriptText, type AudioTranscript } from '$lib/api/audioTranscript';
	import { offerAudioTranscript } from '$lib/api/audioChatHandoff';
	import { ApiError } from '$lib/api/client';
	import { Alert, Button, Field, PageShell, SelectInput, Tabs, TextareaInput, TextInput } from '$lib/components/ui';

	const AUDIO_MIMES = new Set(['audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/ogg', 'audio/webm']);
	const MIME_LABELS: Record<string, string> = { 'audio/mpeg': 'MP3', 'audio/wav': 'WAV', 'audio/x-wav': 'WAV', 'audio/mp4': 'M4A', 'audio/ogg': 'OGG', 'audio/webm': 'WebM' };
	const FORMATS: AudioFormat[] = ['mp3', 'wav'];
	const SEGMENT_TIMESTAMPS: Array<'segment'> = ['segment'];
	// Example drafts only fill an empty canvas; they never replace text the user wrote.
	const EXAMPLES = [
		{ label: '따뜻한 인사말', text: '안녕하세요. 오늘도 와 주셔서 고맙습니다. 작은 일에도 웃을 수 있는 하루가 되기를 바랍니다.' },
		{ label: '차분한 안내', text: '잠시 후 회의를 시작하겠습니다. 마이크를 음소거하고 화면 공유 준비가 되었는지 확인해 주세요.' },
		{ label: '짧은 동화', text: '옛날 어느 작은 마을에 별을 좋아하는 아이가 살았습니다. 아이는 매일 밤 창가에 앉아 가장 밝은 별에게 인사를 건넸습니다.' }
	];
	interface AudioSource { name: string; size: number; type: string; url: string }
	// Only the selected model's capability response may advertise a voice or timestamp granularity.
	const scope = $derived($auth.token && $auth.projectId && $auth.userId ? { token: $auth.token, projectId: $auth.projectId } : null);
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
	let uploadRequest: AbortController | null = null;
	let aborters: AbortController[] = [];
	let pendingSpeech: { fingerprint: string; key: string } | null = null;
	let pendingTranscription: { fingerprint: string; key: string } | null = null;
	const busyStt = $derived(uploading || transcribing);
	const sourceLocked = $derived(!scope || busyStt || recording);
	// Microphone capture is only visible in the STT panel, so the mode stays there until it is stopped.
	const micActive = $derived(recording || permissionPending);
	const modeTabs = $derived([
		{ value: 'tts', label: '텍스트 → 음성', panelId: 'audio-panel-tts', disabled: micActive && mode === 'stt' },
		{ value: 'stt', label: '음성 → 텍스트', panelId: 'audio-panel-stt' }
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
		!sttModel ? '인식 모델을 선택하면 타임스탬프 지원 여부를 확인합니다.'
		: !timestampKnown ? (errors.stt ? '모델 기능을 확인하지 못해 타임스탬프를 요청할 수 없습니다.' : '선택한 모델의 타임스탬프 지원 여부를 확인하는 중입니다.')
		: timestampSupported ? '제공자가 반환한 구간별 시작·종료 시간을 표시하고 SRT로 내보냅니다.'
		: '선택한 모델은 구간 타임스탬프를 제공하지 않습니다. 텍스트만 변환하며 TXT는 내려받을 수 있지만 SRT는 만들 수 없습니다.'
	);
	const fingerprint = $derived(JSON.stringify([ownerKey, selected.tts, draft.trim(), voice, format]));
	const transcriptionFingerprint = $derived(JSON.stringify([ownerKey, selected.stt, assetId, language.trim(), requestTimestamps ? SEGMENT_TIMESTAMPS : []]));
	const ttsReady = $derived(Boolean(scope) && !loading.tts && !capabilityLoading.tts && !ttsReadiness && Boolean(draft.trim()) && voices.includes(voice) && formats.includes(format) && !busyTts);
	const sttReady = $derived(Boolean(scope) && Boolean(assetId) && !sttReadiness && !loading.stt && !capabilityLoading.stt && !busyStt && !recording);
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
			if (cause.status === 401 || cause.status === 403) return '현재 프로젝트에 접근할 수 없습니다.';
			if (cause.status === 402) return '사용 가능한 크레딧 또는 할당량이 부족합니다.';
			if ([400, 409, 422].includes(cause.status)) return cause.message.slice(0, 250);
			return `오디오 서비스 요청 실패 (${cause.status}).`;
		}
		return cause instanceof Error ? cause.message : '오디오 서비스에 연결하지 못했습니다.';
	}
	function fileSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
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
		sourceMedia?.pause();
		uploadRequest?.abort();
		uploadRequest = null;
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
		loading = { ...loading, [kind]: true };
		errors = { ...errors, [kind]: '' };
		try {
			const list = await audioStudioApi.models(kind, requestScope);
			if (epoch !== generation) return;
			models = { ...models, [kind]: list.filter((model) => model.model_kind === kind && Number.isSafeInteger(model.id) && model.id > 0) };
			if (!models[kind].some((model) => String(model.id) === selected[kind])) selected = { ...selected, [kind]: models[kind][0] ? String(models[kind][0].id) : '' };
		} catch (cause) {
			if (epoch === generation) errors = { ...errors, [kind]: message(cause) };
		} finally {
			if (epoch === generation) loading = { ...loading, [kind]: false };
		}
	}
	async function loadCapability(kind: AudioKind, model: AudioModel, requestScope: AudioScope, epoch: number) {
		capabilityLoading = { ...capabilityLoading, [kind]: true };
		try {
			const value = await audioStudioApi.capabilities(kind, model.id, requestScope);
			if (epoch !== generation || selected[kind] !== String(model.id)) return;
			capabilities = { ...capabilities, [kind]: value };
			if (kind === 'tts') {
				if (!value.available_voices?.includes(voice)) voice = value.available_voices?.[0] ?? '';
				if (!value.available_formats?.includes(format)) format = value.available_formats?.[0] ?? 'mp3';
			}
		} catch (cause) {
			if (epoch === generation && selected[kind] === String(model.id)) errors = { ...errors, [kind]: message(cause) };
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
			if (scope) {
				const requestScope = scope;
				const epoch = generation;
				void loadModels('tts', requestScope, epoch);
				void loadModels('stt', requestScope, epoch);
			}
		});
	});
	$effect(() => {
		const tts = ttsModel;
		const stt = sttModel;
		const requestScope = scope;
		const owner = ownerKey;
		untrack(() => {
			if (!owner || !requestScope) return;
			for (const [kind, model] of [['tts', tts], ['stt', stt]] as const) {
				capabilities = { ...capabilities, [kind]: null };
				if (model) void loadCapability(kind, model, requestScope, generation);
			}
		});
	});
	onDestroy(reset);

	async function speech() {
		if (!ttsReady || !scope || !ttsModel) return;
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
			if (epoch !== generation || request.signal.aborted) return;
			cleanupAudio();
			audioUrl = URL.createObjectURL(blob);
			outputFormat = requestFormat;
			outputVoice = requestVoice;
			pendingSpeech = null;
		} catch (cause) {
			if (epoch === generation && !request.signal.aborted) {
				if (cause instanceof ApiError && [400, 401, 402, 403, 404, 409, 422].includes(cause.status)) pendingSpeech = null;
				failures = { ...failures, tts: message(cause) };
			}
		} finally {
			if (epoch === generation) busyTts = false;
		}
	}
	async function upload(file: File) {
		if (!scope || uploading || transcribing) return;
		if (!AUDIO_MIMES.has(file.type)) { failures = { ...failures, stt: 'MP3, WAV, M4A, OGG 또는 WebM 음성 파일을 선택하세요.' }; return; }
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
			if (epoch !== generation || version !== sourceVersion || request.signal.aborted) return;
			assetId = asset.id;
			assetName = asset.name;
		} catch (cause) {
			if (epoch === generation && version === sourceVersion && !request.signal.aborted) {
				releaseSource();
				failures = { ...failures, stt: `업로드 실패: ${message(cause)}` };
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
		if (file) void upload(file);
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
		if (recording || permissionPending || busyStt) return;
		if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { failures = { ...failures, stt: '이 브라우저는 마이크 녹음을 지원하지 않습니다. 파일을 선택하세요.' }; return; }
		permissionPending = true;
		const epoch = generation;
		try {
			const acquired = await navigator.mediaDevices.getUserMedia({ audio: true });
			if (epoch !== generation) { acquired.getTracks().forEach((track) => track.stop()); return; }
			stream = acquired;
			const mimeType = ['audio/webm', 'audio/ogg', 'audio/mp4'].find((mime) => MediaRecorder.isTypeSupported(mime));
			const active = new MediaRecorder(acquired, mimeType ? { mimeType } : undefined);
			const chunks: BlobPart[] = [];
			let recordingFailed = false;
			active.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
			active.onerror = () => { recordingFailed = true; if (epoch === generation) failures = { ...failures, stt: '녹음에 실패했습니다. 다시 시도하거나 파일을 선택하세요.' }; stopMic(); };
			active.onstop = () => {
				acquired.getTracks().forEach((track) => track.stop());
				if (epoch !== generation || recordingFailed || !chunks.length) return;
				const type = active.mimeType.split(';')[0];
				if (!AUDIO_MIMES.has(type)) { failures = { ...failures, stt: '녹음 형식이 지원되지 않습니다. 파일을 선택하세요.' }; return; }
				const extension = type === 'audio/mp4' ? 'm4a' : type.split('/')[1];
				void upload(new File(chunks, `recording.${extension}`, { type }));
			};
			active.start();
			recorder = active;
			recording = true;
			failures = { ...failures, stt: '' };
		} catch (cause) {
			stream?.getTracks().forEach((track) => track.stop());
			stream = null;
			if (epoch === generation) failures = { ...failures, stt: cause instanceof DOMException && cause.name === 'NotAllowedError' ? '마이크 권한이 거부되었습니다. 브라우저 권한을 확인하거나 파일을 선택하세요.' : `마이크를 시작하지 못했습니다: ${message(cause)}` };
		} finally {
			if (epoch === generation) permissionPending = false;
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
		if (!sttReady || !scope || !sttModel) return;
		const epoch = generation;
		const version = sourceVersion;
		const request = controller();
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
			if (epoch === generation && version === sourceVersion && !request.signal.aborted) {
				showTranscript(result, name, timed);
				pendingTranscription = null;
			}
		} catch (cause) {
			if (epoch === generation && version === sourceVersion && !request.signal.aborted) {
				if (cause instanceof ApiError && [400, 401, 402, 403, 404, 409, 422].includes(cause.status)) pendingTranscription = null;
				failures = { ...failures, stt: message(cause) };
			}
		} finally {
			if (epoch === generation) transcribing = false;
		}
	}
	async function copyTranscript() {
		if (!transcript) return;
		const epoch = generation;
		const text = transcript.text;
		try {
			await navigator.clipboard.writeText(text);
			if (epoch === generation && transcript?.text === text) copyStatus = '텍스트를 복사했습니다.';
		} catch (cause) {
			if (epoch === generation) failures = { ...failures, stt: `복사 실패: ${message(cause)}` };
		}
	}
	function insertIntoChat() {
		if (!$auth.userId || !$auth.projectId || !transcript?.text.trim()) return;
		offerAudioTranscript($auth.userId, $auth.projectId, transcript.text);
		void goto('/dashboard/chat');
	}
</script>

<PageShell max="7xl">
	<div class="studio">
		<header class="header">
			<div class="title">
				<p class="muted">AI 채팅 / 오디오</p>
				<h1>오디오 Studio</h1>
				<p class="muted">{mode === 'tts' ? '텍스트를 선택한 모델의 목소리로 읽어 음성 파일을 만듭니다.' : '음성 파일을 텍스트로 변환하고, 지원 모델에서는 구간 시간을 함께 받습니다.'} 오디오는 브라우저에 저장하지 않습니다.</p>
			</div>
			<Button href="/dashboard/chat" variant="secondary">텍스트 채팅으로</Button>
		</header>
		<Tabs id="audio-mode" ariaLabel="오디오 작업" value={mode} items={modeTabs} onchange={selectMode} />
		{#if micActive}<p class="muted">녹음 중에는 텍스트 → 음성으로 이동할 수 없습니다. 녹음을 종료하면 이동할 수 있습니다.</p>{/if}

		<div id="audio-panel-tts" role="tabpanel" aria-labelledby="audio-mode-tts" tabindex="0" class="panel" hidden={mode !== 'tts'}>
				<form class="workspace" onsubmit={(event) => { event.preventDefault(); void speech(); }}>
					<div class="canvas">
						<div class="canvas-head">
							<label for="audio-text" class="canvas-label">읽을 텍스트 <span class="required" aria-hidden="true">*</span></label>
							<Button variant="ghost" size="sm" disabled={!draft || busyTts} onclick={() => { draft = ''; }}>지우기</Button>
						</div>
						<TextareaInput id="audio-text" bind:value={draft} rows={12} required disabled={busyTts} placeholder="음성으로 읽을 텍스트를 입력하세요" ariaDescribedBy="audio-text-count" class="draft" />
						<div class="canvas-foot">
							{#if !draft}
								<div class="examples" role="group" aria-label="예시 문장">
									<span class="muted">이런 문장으로 시작해 보세요.</span>
									{#each EXAMPLES as example (example.label)}<Button variant="outline" size="sm" disabled={busyTts} onclick={() => { draft = example.text; }}>{example.label}</Button>{/each}
								</div>
							{/if}
							<p id="audio-text-count" class="muted count">글자 수 {draft.length.toLocaleString('ko-KR')}</p>
						</div>
					</div>
					<aside class="settings" aria-labelledby="audio-tts-settings">
						<h2 id="audio-tts-settings">음성 설정</h2>
						<Field label="음성 모델" for="audio-tts-model"><SelectInput id="audio-tts-model" value={selected.tts} onchange={(event) => { selected = { ...selected, tts: (event.currentTarget as HTMLSelectElement).value }; }} disabled={loading.tts || busyTts}><option value="">모델 선택</option>{#each models.tts as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput></Field>
						{#if loading.tts || capabilityLoading.tts}<p role="status" class="muted">음성 모델과 가격을 확인하는 중…</p>{:else if errors.tts}<Alert tone="danger">{errors.tts} <Button variant="subtle" onclick={() => scope && loadModels('tts', scope, generation)}>모델 다시 조회</Button></Alert>{:else if !models.tts.length}<Alert tone="warning">사용 가능한 음성 모델이 없습니다.</Alert>{:else if ttsReadiness}<Alert tone="warning">{ttsReadiness}</Alert>{:else}<p role="status" class="ready">음성 생성 경로와 가격이 준비되었습니다.</p>{/if}
						<fieldset class="voices" disabled={busyTts || !voices.length}>
							<legend>목소리</legend>
							{#if voices.length}
								<div class="voice-list">{#each voices as option}<label class="voice"><input type="radio" name="audio-voice" value={option} bind:group={voice} /><span>{option}</span></label>{/each}</div>
							{:else}
								<p class="muted">선택한 모델이 제공하는 목소리를 확인하면 여기에서 고를 수 있습니다.</p>
							{/if}
						</fieldset>
						<Field label="출력 형식" for="audio-format"><SelectInput id="audio-format" bind:value={format} disabled={busyTts || !formats.length}>{#each formats as option}<option value={option}>{option.toUpperCase()}</option>{/each}</SelectInput></Field>
					</aside>
					<div class="playbar">
						<div class="playbar-output">
							{#if audioUrl}
								<audio bind:this={media} src={audioUrl} controls aria-label="생성된 음성"></audio>
								<p class="muted">{outputVoice} · {outputFormat.toUpperCase()} · 다른 음성을 생성하기 전까지 유지됩니다.</p>
							{:else}
								<p class="muted">생성한 음성은 여기에서 재생하고 내려받을 수 있습니다.</p>
							{/if}
							{#if failures.tts}<Alert tone="danger">{failures.tts}</Alert>{/if}
						</div>
						<div class="playbar-actions">
							{#if audioUrl}<a href={audioUrl} download={`speech.${outputFormat}`} class="file-action">음성 다운로드</a>{/if}
							<Button type="submit" size="lg" disabled={!ttsReady}>{busyTts ? '음성 생성 중…' : '음성 생성'}</Button>
						</div>
					</div>
				</form>
			</div>
		<div id="audio-panel-stt" role="tabpanel" aria-labelledby="audio-mode-stt" tabindex="0" class="panel" hidden={mode !== 'stt'}>
				<div class="workspace">
					<div class="canvas">
						<h2>오디오 입력</h2>
						<div class="dropzone" class:dragging role="group" aria-label="음성 파일 놓기 영역" ondragenter={dragOver} ondragover={dragOver} ondragleave={dragLeave} ondrop={dropFile}>
							<svg class="drop-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V5m0 0-4 4m4-4 4 4M5 15v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
							<p class="drop-title">오디오 파일을 여기에 놓으세요</p>
							<p class="muted">또는 파일을 선택하거나 마이크로 직접 녹음하세요.</p>
							<div class="actions">
								<input id="audio-file" class="file-input" type="file" accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/ogg,audio/webm" disabled={sourceLocked} aria-describedby="audio-file-help" onchange={chooseFile} />
								<label for="audio-file" class="file-action">음성 파일 선택</label>
								<Button variant="secondary" disabled={busyStt || permissionPending} onclick={() => recording ? stopMic() : void startRecording()}>{permissionPending ? '마이크 권한 확인 중…' : recording ? '녹음 종료' : '마이크 녹음'}</Button>
							</div>
							<p id="audio-file-help" class="muted">MP3, WAV, M4A, OGG, WebM · 소유권과 검사를 거쳐 인식합니다.</p>
						</div>
						{#if recording}<p role="status" class="recording">녹음 중 · 종료하면 업로드합니다.</p>{/if}
						{#if source}
							<div class="source">
								<div class="source-info">
									<p class="source-name">{source.name}</p>
									<p class="muted">{fileSize(source.size)} · {MIME_LABELS[source.type] ?? source.type}</p>
									{#if uploading}<p role="status" class="muted">업로드하고 검사하는 중…</p>{:else if assetId}<p role="status" class="muted">검사된 입력: {assetName}</p>{/if}
								</div>
								<audio bind:this={sourceMedia} src={source.url} controls aria-label={`선택한 음성 미리 듣기: ${source.name}`}></audio>
								<Button variant="ghost" size="icon" ariaLabel="선택한 음성 제거" disabled={transcribing} onclick={removeSource}><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" /></svg></Button>
							</div>
						{/if}
					</div>
					<aside class="settings" aria-labelledby="audio-stt-settings">
						<h2 id="audio-stt-settings">변환 설정</h2>
						<Field label="인식 모델" for="audio-stt-model"><SelectInput id="audio-stt-model" value={selected.stt} onchange={(event) => { selected = { ...selected, stt: (event.currentTarget as HTMLSelectElement).value }; }} disabled={loading.stt || busyStt}><option value="">모델 선택</option>{#each models.stt as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput></Field>
						{#if loading.stt || capabilityLoading.stt}<p role="status" class="muted">인식 모델과 가격을 확인하는 중…</p>{:else if errors.stt}<Alert tone="danger">{errors.stt} <Button variant="subtle" onclick={() => scope && loadModels('stt', scope, generation)}>모델 다시 조회</Button></Alert>{:else if !models.stt.length}<Alert tone="warning">사용 가능한 인식 모델이 없습니다.</Alert>{:else if sttReadiness}<Alert tone="warning">{sttReadiness}</Alert>{:else}<p role="status" class="ready">음성 인식 경로와 가격이 준비되었습니다.</p>{/if}
						<Field label="언어 코드 (선택)" for="audio-language"><TextInput id="audio-language" bind:value={language} placeholder="예: ko" disabled={busyStt} /></Field>
						<div class="switch-row">
							<div class="switch-copy">
								<label for="audio-timestamps">타임스탬프</label>
								<p id="audio-timestamps-help" class="muted">{timestampHelp}</p>
							</div>
							<input id="audio-timestamps" class="switch" type="checkbox" role="switch" checked={requestTimestamps} disabled={!timestampSupported || busyStt} aria-describedby="audio-timestamps-help" onchange={(event) => { timestamps = event.currentTarget.checked; }} />
						</div>
						<Button size="lg" disabled={!sttReady} onclick={() => void transcribe()}>{transcribing ? '음성 처리 중…' : '텍스트로 변환'}</Button>
						{#if failures.stt}<Alert tone="danger">{failures.stt}</Alert>{/if}
					</aside>
				</div>
				{#if transcript}
					<section class="results" aria-labelledby="audio-result-title">
						<div class="results-head">
							<h2 id="audio-result-title">변환 결과</h2>
							<div class="actions">
								<Button variant="secondary" onclick={() => void copyTranscript()}>텍스트 복사</Button>
								{#if exportUrls.txt}<a href={exportUrls.txt} download={`${transcriptName}.txt`} class="file-action">텍스트 다운로드</a>{/if}
								{#if exportUrls.srt}<a href={exportUrls.srt} download={`${transcriptName}.srt`} class="file-action">SRT 다운로드</a>{/if}
								<Button variant="secondary" onclick={insertIntoChat}>채팅 입력에 넣기</Button>
							</div>
						</div>
						{#if copyStatus}<p role="status" class="muted">{copyStatus}</p>{/if}
						{#if transcript.segments.length}
							<div class="table-wrap">
								<table class="segments">
									<thead><tr><th scope="col">시간 구간</th><th scope="col">변환된 텍스트</th></tr></thead>
									<tbody>
										{#each transcript.segments as segment, index (index)}
											<tr><td class="range"><time datetime={`PT${segment.start}S`}>{formatTranscriptTime(segment.start)}</time> – <time datetime={`PT${segment.end}S`}>{formatTranscriptTime(segment.end)}</time></td><td>{segment.text}</td></tr>
										{/each}
									</tbody>
								</table>
							</div>
						{:else}
							<p class="muted">{transcriptTimed ? '제공자가 인식한 음성 구간이 없습니다.' : '구간 시간 없이 변환했습니다. SRT는 타임스탬프를 지원하는 모델에서 만들 수 있습니다.'}</p>
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
