<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { audioStudioApi, audioReadiness, type AudioKind, type AudioModel, type AudioCapabilities, type AudioFormat, type AudioScope } from '$lib/api/audioStudio';
	import { offerAudioTranscript } from '$lib/api/audioChatHandoff';
	import { ApiError } from '$lib/api/client';
	import { Alert, Button, Card, Field, PageShell, SelectInput, TextareaInput, TextInput } from '$lib/components/ui';

	const AUDIO_MIMES = new Set(['audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/ogg', 'audio/webm']);
	const FORMATS: AudioFormat[] = ['mp3', 'wav'];
	// Only the selected model's capability response may advertise a voice.
	const scope = $derived($auth.token && $auth.projectId && $auth.userId ? { token: $auth.token, projectId: $auth.projectId } : null);
	const ownerKey = $derived(`${$auth.userId ?? ''}:${$auth.projectId ?? ''}`);
	let activeOwner = '';
	let generation = 0;
	let models = $state<Record<AudioKind, AudioModel[]>>({ tts: [], stt: [] });
	let selected = $state<Record<AudioKind, string>>({ tts: '', stt: '' });
	let capabilities = $state<Record<AudioKind, AudioCapabilities | null>>({ tts: null, stt: null });
	let loading = $state<Record<AudioKind, boolean>>({ tts: false, stt: false });
	let capabilityLoading = $state<Record<AudioKind, boolean>>({ tts: false, stt: false });
	let errors = $state<Record<AudioKind, string>>({ tts: '', stt: '' });
	let draft = $state('');
	let voice = $state('alloy');
	let format = $state<AudioFormat>('mp3');
	let language = $state('');
	let assetId = $state('');
	let assetName = $state('');
	let transcript = $state('');
	let recording = $state(false);
	let permissionPending = $state(false);
	let busyTts = $state(false);
	let busyStt = $state(false);
	let audioUrl = $state('');
	let outputFormat = $state<AudioFormat>('mp3');
	let media = $state<HTMLAudioElement | null>(null);
	let recorder: MediaRecorder | null = null;
	let stream: MediaStream | null = null;
	let aborters: AbortController[] = [];
	let pendingSpeech: { fingerprint: string; key: string } | null = null;
	let pendingTranscription: { fingerprint: string; key: string } | null = null;
	const ttsModel = $derived(models.tts.find((model) => String(model.id) === selected.tts));
	const sttModel = $derived(models.stt.find((model) => String(model.id) === selected.stt));
	const ttsReadiness = $derived(audioReadiness(ttsModel, capabilities.tts, 'tts'));
	const sttReadiness = $derived(audioReadiness(sttModel, capabilities.stt, 'stt'));
	const voices = $derived(capabilities.tts?.available_voices ?? []);
	const formats = $derived(capabilities.tts?.available_formats?.filter((item) => FORMATS.includes(item)) ?? []);
	const fingerprint = $derived(JSON.stringify([ownerKey, selected.tts, draft.trim(), voice, format]));
	const transcriptionFingerprint = $derived(JSON.stringify([ownerKey, selected.stt, assetId, language.trim()]));
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
	function controller(): AbortController {
		const item = new AbortController();
		aborters.push(item);
		return item;
	}
	function cleanupAudio() {
		media?.pause();
		if (audioUrl) URL.revokeObjectURL(audioUrl);
		audioUrl = '';
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
		models = { tts: [], stt: [] };
		selected = { tts: '', stt: '' };
		capabilities = { tts: null, stt: null };
		loading = { tts: false, stt: false };
		capabilityLoading = { tts: false, stt: false };
		errors = { tts: '', stt: '' };
		draft = '';
		voice = 'alloy';
		format = 'mp3';
		language = '';
		assetId = '';
		assetName = '';
		transcript = '';
		busyTts = false;
		busyStt = false;
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
		if (!scope || !ttsModel || ttsReadiness || !draft.trim() || !voices.includes(voice) || !formats.includes(format) || busyTts) return;
		const epoch = generation;
		const requestScope = scope;
		const fingerprintNow = fingerprint;
		const key = pendingSpeech?.fingerprint === fingerprintNow ? pendingSpeech.key : crypto.randomUUID();
		pendingSpeech = { fingerprint: fingerprintNow, key };
		const request = controller();
		busyTts = true;
		errors = { ...errors, tts: '' };
		try {
			const blob = await audioStudioApi.speech({ model_id: String(ttsModel.id), input: draft.trim(), voice, response_format: format }, requestScope, key, request.signal);
			if (epoch !== generation || request.signal.aborted) return;
			cleanupAudio();
			audioUrl = URL.createObjectURL(blob);
			outputFormat = format;
			pendingSpeech = null;
		} catch (cause) {
			if (epoch === generation && !request.signal.aborted) {
				if (cause instanceof ApiError && [400, 401, 402, 403, 404, 409, 422].includes(cause.status)) pendingSpeech = null;
				errors = { ...errors, tts: message(cause) };
			}
		} finally {
			if (epoch === generation) busyTts = false;
		}
	}
	async function upload(file: File) {
		if (!scope || busyStt) return;
		if (!AUDIO_MIMES.has(file.type)) { errors = { ...errors, stt: 'MP3, WAV, M4A, OGG 또는 WebM 음성 파일을 선택하세요.' }; return; }
		const epoch = generation;
		const requestScope = scope;
		const request = controller();
		busyStt = true;
		errors = { ...errors, stt: '' };
		assetId = '';
		transcript = '';
		try {
			const asset = await audioStudioApi.upload(file, requestScope, request.signal);
			if (epoch !== generation || request.signal.aborted) return;
			assetId = asset.id;
			assetName = asset.name;
		} catch (cause) {
			if (epoch === generation && !request.signal.aborted) errors = { ...errors, stt: `업로드 실패: ${message(cause)}` };
		} finally {
			if (epoch === generation) busyStt = false;
		}
	}
	async function startRecording() {
		if (recording || permissionPending || busyStt) return;
		if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { errors = { ...errors, stt: '이 브라우저는 마이크 녹음을 지원하지 않습니다. 파일을 선택하세요.' }; return; }
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
			active.onerror = () => { recordingFailed = true; if (epoch === generation) errors = { ...errors, stt: '녹음에 실패했습니다. 다시 시도하거나 파일을 선택하세요.' }; stopMic(); };
			active.onstop = () => {
				acquired.getTracks().forEach((track) => track.stop());
				if (epoch !== generation || recordingFailed || !chunks.length) return;
				const type = active.mimeType.split(';')[0];
				if (!AUDIO_MIMES.has(type)) { errors = { ...errors, stt: '녹음 형식이 지원되지 않습니다. 파일을 선택하세요.' }; return; }
				const extension = type === 'audio/mp4' ? 'm4a' : type.split('/')[1];
				void upload(new File(chunks, `recording.${extension}`, { type }));
			};
			active.start();
			recorder = active;
			recording = true;
			errors = { ...errors, stt: '' };
		} catch (cause) {
			stream?.getTracks().forEach((track) => track.stop());
			stream = null;
			if (epoch === generation) errors = { ...errors, stt: cause instanceof DOMException && cause.name === 'NotAllowedError' ? '마이크 권한이 거부되었습니다. 브라우저 권한을 확인하거나 파일을 선택하세요.' : `마이크를 시작하지 못했습니다: ${message(cause)}` };
		} finally {
			if (epoch === generation) permissionPending = false;
		}
	}
	async function transcribe() {
		if (!scope || !sttModel || sttReadiness || !assetId || busyStt || recording) return;
		const epoch = generation;
		const request = controller();
		const requestScope = scope;
		busyStt = true;
		errors = { ...errors, stt: '' };
		try {
			const intentFingerprint = transcriptionFingerprint;
			const intentKey = pendingTranscription?.fingerprint === intentFingerprint ? pendingTranscription.key : crypto.randomUUID();
			pendingTranscription = { fingerprint: intentFingerprint, key: intentKey };
			const text = await audioStudioApi.transcribe({ model_id: String(sttModel.id), input_asset_id: assetId, ...(language.trim() ? { language: language.trim() } : {}) }, requestScope, intentKey, request.signal);
			if (epoch === generation && !request.signal.aborted) {
				transcript = text;
				pendingTranscription = null;
			}
		} catch (cause) {
			if (epoch === generation && !request.signal.aborted) {
				if (cause instanceof ApiError && [400, 401, 402, 403, 404, 409, 422].includes(cause.status)) pendingTranscription = null;
				errors = { ...errors, stt: message(cause) };
			}
		} finally {
			if (epoch === generation) busyStt = false;
		}
	}
	function insertIntoChat() {
		if (!$auth.userId || !$auth.projectId || !transcript.trim()) return;
		offerAudioTranscript($auth.userId, $auth.projectId, transcript);
		void goto('/dashboard/chat');
	}
</script>

<PageShell max="7xl">
	<div class="studio">
		<header class="header"><div><p class="muted">AI 채팅 / 오디오</p><h1>오디오 Studio</h1><p class="muted">텍스트에서 음성을 만들거나 음성 파일을 텍스트로 변환합니다. 오디오는 브라우저에 저장하지 않습니다.</p></div><Button href="/dashboard/chat" variant="secondary">텍스트 채팅으로</Button></header>
		<div class="columns">
			<Card><form class="form" onsubmit={(event) => { event.preventDefault(); void speech(); }}>
				<h2>텍스트 → 음성</h2>
				<Field label="음성 모델" for="audio-tts-model"><SelectInput id="audio-tts-model" value={selected.tts} onchange={(event) => { selected = { ...selected, tts: (event.currentTarget as HTMLSelectElement).value }; }} disabled={loading.tts || busyTts}><option value="">모델 선택</option>{#each models.tts as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput></Field>
				{#if loading.tts || capabilityLoading.tts}<p role="status" class="muted">음성 모델과 가격을 확인하는 중…</p>{:else if errors.tts}<Alert tone="danger">{errors.tts} <Button variant="subtle" onclick={() => scope && loadModels('tts', scope, generation)}>모델 다시 조회</Button></Alert>{:else if !models.tts.length}<Alert tone="warning">사용 가능한 음성 모델이 없습니다.</Alert>{:else if ttsReadiness}<Alert tone="warning">{ttsReadiness}</Alert>{:else}<Alert tone="success">음성 생성 경로와 가격이 준비되었습니다.</Alert>{/if}
				<Field label="읽을 텍스트" for="audio-text" required><TextareaInput id="audio-text" bind:value={draft} rows={5} disabled={busyTts} placeholder="음성으로 읽을 텍스트" /></Field>
				<div class="options"><Field label="목소리" for="audio-voice"><SelectInput id="audio-voice" bind:value={voice} disabled={busyTts}>{#each voices as option}<option value={option}>{option}</option>{/each}</SelectInput></Field><Field label="형식" for="audio-format"><SelectInput id="audio-format" bind:value={format} disabled={busyTts}>{#each formats as option}<option value={option}>{option.toUpperCase()}</option>{/each}</SelectInput></Field></div>
				<Button type="submit" disabled={!scope || loading.tts || capabilityLoading.tts || Boolean(ttsReadiness) || !draft.trim() || !voices.includes(voice) || !formats.includes(format) || busyTts}>{busyTts ? '음성 생성 중…' : '음성 생성'}</Button>
				{#if audioUrl}<div class="output"><audio bind:this={media} src={audioUrl} controls aria-label="생성된 음성"></audio><a href={audioUrl} download={`speech.${outputFormat}`} class="download">음성 다운로드</a></div>{/if}
			</form></Card>
			<Card><div class="form">
				<h2>음성 → 텍스트</h2>
				<Field label="인식 모델" for="audio-stt-model"><SelectInput id="audio-stt-model" value={selected.stt} onchange={(event) => { selected = { ...selected, stt: (event.currentTarget as HTMLSelectElement).value }; }} disabled={loading.stt || busyStt}><option value="">모델 선택</option>{#each models.stt as model (model.id)}<option value={String(model.id)}>{model.display_name}</option>{/each}</SelectInput></Field>
				{#if loading.stt || capabilityLoading.stt}<p role="status" class="muted">인식 모델과 가격을 확인하는 중…</p>{:else if errors.stt}<Alert tone="danger">{errors.stt} <Button variant="subtle" onclick={() => scope && loadModels('stt', scope, generation)}>모델 다시 조회</Button></Alert>{:else if !models.stt.length}<Alert tone="warning">사용 가능한 인식 모델이 없습니다.</Alert>{:else if sttReadiness}<Alert tone="warning">{sttReadiness}</Alert>{:else}<Alert tone="success">음성 인식 경로와 가격이 준비되었습니다.</Alert>{/if}
				<Field label="음성 파일" for="audio-file" help="MP3, WAV, M4A, OGG, WebM · 소유권과 검사를 거쳐 인식합니다."><input id="audio-file" type="file" accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/ogg,audio/webm" disabled={busyStt || recording} onchange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file); }} /></Field>
				<div class="actions"><Button variant="secondary" disabled={busyStt || permissionPending} onclick={() => recording ? stopMic() : void startRecording()}>{permissionPending ? '마이크 권한 확인 중…' : recording ? '녹음 종료' : '마이크 녹음'}</Button>{#if recording}<span role="status">녹음 중 · 종료하면 업로드합니다.</span>{/if}</div>
				{#if assetId}<p class="muted" role="status">검사된 입력: {assetName}</p>{/if}
				<Field label="언어 코드 (선택)" for="audio-language"><TextInput id="audio-language" bind:value={language} placeholder="예: ko" disabled={busyStt} /></Field>
				<Button disabled={!scope || !assetId || Boolean(sttReadiness) || loading.stt || capabilityLoading.stt || busyStt || recording} onclick={() => void transcribe()}>{busyStt ? '음성 처리 중…' : '텍스트로 변환'}</Button>
				{#if transcript}<div class="output"><h3>인식 결과</h3><p class="transcript">{transcript}</p><div class="actions"><Button variant="secondary" onclick={insertIntoChat}>채팅 입력에 넣기</Button><Button variant="subtle" onclick={() => { void navigator.clipboard.writeText(transcript).catch((cause) => { errors = { ...errors, stt: `복사 실패: ${message(cause)}` }; }); }}>텍스트 복사</Button></div></div>{/if}
			</div></Card>
		</div>
	</div>
</PageShell>

<style>
	.studio, .form, .output { display: grid; gap: 1rem; min-width: 0; }
	.header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1rem; align-items: flex-start; }
	h1 { font-size: 1.25rem; font-weight: 600; line-height: 1.75rem; }
	h2, h3 { font-size: 0.875rem; font-weight: 600; }
	.muted, .actions, .transcript { font-size: 0.8125rem; color: var(--color-ink-2); line-height: 1.5; }
	.columns, .options { display: grid; gap: 1rem; align-items: start; }
	.actions { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; }
	.output { border-top: 1px solid var(--color-line); padding-top: 1rem; }
	.output audio { width: 100%; }
	.transcript { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--color-ink-1); }
	.download { color: var(--color-accent); text-decoration: underline; font-size: 0.8125rem; }
	input[type="file"] { width: 100%; min-width: 0; border: 1px solid var(--color-line-2); border-radius: var(--radius-md); padding: 0.5rem; background: var(--color-surface-sunken); color: var(--color-ink-1); font-size: 0.8125rem; }
	input[type="file"]:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	@media (min-width: 768px) { .options { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	@media (min-width: 1024px) { .columns { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
