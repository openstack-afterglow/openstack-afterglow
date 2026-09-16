import { setContext, getContext } from 'svelte';
import { SvelteSet, SvelteMap } from 'svelte/reactivity';
import { api, ApiError, fetchWithAuth, getBaseUrl } from '$lib/api/client';
import { downloadBlobAs } from '$lib/utils/downloadBlob';
import { uploadQueue } from '$lib/stores/uploadQueue';
import type { SwiftContainer } from '$lib/types/common';
import type { SwiftObject, SwiftObjectMeta } from '$lib/types/objectStorage';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { pruneSelectionByIds } from '$lib/utils/selectionSet';
import { executeBulkMutations } from '$lib/utils/bulkActions';
import { toast } from '$lib/stores/toast';

export type TreeRow = {
	obj: SwiftObject;
	depth: number;
	isDir: boolean;
	isExpanded: boolean;
	isLoading: boolean;
	fullPath: boolean;
};

interface ObjectBrowserOpts {
	mode: () => 'user' | 'admin';
	containerName: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
}

const OBJECT_BROWSER_KEY = Symbol('object-browser');

export function createObjectBrowserStore(opts: ObjectBrowserOpts) {
	// ——— 공통 상태 ———
	let objects = $state<SwiftObject[]>([]);
	let loading = $state(true);
	let prefix = $state('');
	let deleting = $state<string | null>(null);
	let downloading = $state<string | null>(null);
	let selected = $state<Set<string>>(new Set());
	let bulkDeleting = $state(false);

	let filterText = $state('');
	let sortKey = $state<'name' | 'bytes' | 'last_modified'>('name');
	let sortAsc = $state(true);

	let showUpload = $state(false);
	let dragActive = $state(false);

	let showNewDir = $state(false);
	let newDirName = $state('');
	let creatingDir = $state(false);
	let dirError = $state('');

	let showRename = $state(false);
	let renameTarget = $state('');
	let renameNew = $state('');
	let renameIsDir = $state(false);
	let renaming = $state(false);
	let renameError = $state('');

	let showMove = $state(false);
	let moveTarget = $state('');
	let moveDest = $state('');
	let moveDestContainer = $state('');
	let moveDestinationChosen = $state(false);
	let moving = $state(false);
	let moveError = $state('');
	let moveContainers = $state<SwiftContainer[]>([]);
	let moveDirectories = $state<string[]>([]);
	let moveLoadingDirs = $state(false);
	let moveSelectedDir = $state('');

	let showBulkMove = $state(false);
	let bulkMoving = $state(false);

	let showPreview = $state(false);
	let previewName = $state('');
	let previewContentType = $state('');
	let previewText = $state('');
	let loadingPreview = $state(false);
	let previewUrl = $state('');

	let selectedMeta = $state<SwiftObjectMeta | null>(null);
	let loadingMeta = $state(false);
	let containerMeta = $state<SwiftContainer | null>(null);

	let colWidths = $state({ name: 38, bytes: 12, type: 16, modified: 16, action: 12 });

	// ——— user 전용 상태 ———
	let searchScope = $state<'current' | 'expanded' | 'all'>('current');
	let expandedDirs = $state<SvelteSet<string>>(new SvelteSet());
	let dirCache = $state<SvelteMap<string, SwiftObject[]>>(new SvelteMap());
	let dirLoading = $state<SvelteSet<string>>(new SvelteSet());
	let allObjectsCache = $state<SwiftObject[] | null>(null);
	let allObjectsLoading = $state(false);

	// ——— derived ———
	const breadcrumbs = $derived(
		prefix ? prefix.replace(/\/$/, '').split('/').filter(Boolean) : []
	);

	// ——— 헬퍼 ———
	function encObj(name: string) {
		return name.split('/').map(encodeURIComponent).join('/');
	}

	function isDirectory(obj: SwiftObject) {
		return obj.is_dir === true || obj.content_type === 'application/directory' || obj.name.endsWith('/');
	}

	function isPreviewable(contentType: string) {
		return contentType.startsWith('text/') || contentType.startsWith('image/') ||
			contentType === 'application/pdf' || contentType === 'application/json';
	}

	function displayName(fullName: string) {
		if (prefix && fullName.startsWith(prefix)) return fullName.slice(prefix.length);
		return fullName;
	}

	function baseName(fullName: string): string {
		const stripped = fullName.endsWith('/') ? fullName.slice(0, -1) : fullName;
		const idx = stripped.lastIndexOf('/');
		return idx >= 0 ? stripped.slice(idx + 1) : stripped;
	}

	function sortIcon(key: typeof sortKey) {
		if (sortKey !== key) return '';
		return sortAsc ? '↑' : '↓';
	}

	function breadcrumbPrefix(idx: number) {
		return breadcrumbs.slice(0, idx + 1).join('/') + '/';
	}

	// ——— API ———
	async function loadContainerMeta() {
		try {
			containerMeta = await api.get<SwiftContainer>(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}`,
				opts.token(), opts.projectId()
			);
		} catch { containerMeta = null; }
	}

	async function load(o: { silent?: boolean } = {}) {
		if (!o.silent) loading = true;
		try {
			const qs = new URLSearchParams({ delimiter: '/' });
			if (prefix) qs.set('prefix', prefix);
			objects = await api.get<SwiftObject[]>(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects?${qs}`,
				opts.token(), opts.projectId()
			);
			pruneSelected(objects.map((item) => item.name));
		} catch { if (!o.silent) objects = []; }
		finally { if (!o.silent) loading = false; }
	}

	// user: prefix 단위 캐시 fetch
	async function fetchDir(p: string): Promise<SwiftObject[]> {
		dirLoading.add(p);
		try {
			const qs = new URLSearchParams({ delimiter: '/' });
			if (p) qs.set('prefix', p);
			const items = await api.get<SwiftObject[]>(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects?${qs}`,
				opts.token(), opts.projectId()
			);
			dirCache.set(p, items);
			return items;
		} finally {
			dirLoading.delete(p);
		}
	}

	async function fetchAllObjects(o: { silent?: boolean } = {}): Promise<void> {
		if (!o.silent) allObjectsLoading = true;
		try {
			const qs = new URLSearchParams({ delimiter: '' });
			const items = await api.get<SwiftObject[]>(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects?${qs}`,
				opts.token(), opts.projectId()
			);
			allObjectsCache = items;
		} catch { if (!o.silent) allObjectsCache = []; }
		finally { if (!o.silent) allObjectsLoading = false; }
	}

	// user: 펼친 모든 prefix 병렬 재페치 (동시성 4)
	async function refreshAll(o: { silent?: boolean } = {}): Promise<void> {
		if (!o.silent) loading = true;
		try {
			const queue = [prefix, ...expandedDirs];
			while (queue.length) {
				const batch = queue.splice(0, 4);
				await Promise.all(batch.map(p => fetchDir(p).catch(() => [])));
			}
			objects = dirCache.get(prefix) ?? [];
			if (searchScope === 'all' && filterText.trim()) {
				await fetchAllObjects({ silent: true });
			}
			const available = searchScope === 'all' && filterText.trim() && allObjectsCache
				? allObjectsCache
				: [...dirCache.values()].flat();
			pruneSelected(available.map((item) => item.name));
		} catch { /* ignore per-dir failures */ }
		finally { if (!o.silent) loading = false; }
	}
	async function loadCurrent(o: { silent?: boolean } = {}) {
		if (opts.mode() === 'user') {
			if (!o.silent) loading = true;
			try {
				const items = await fetchDir(prefix);
				objects = items;
				pruneSelected(items.map((item) => item.name));
			} catch { if (!o.silent) objects = []; }
			finally { if (!o.silent) loading = false; }
		} else {
			await load(o);
		}
	}

	async function doRefresh(o: { silent?: boolean } = {}) {
		if (opts.mode() === 'user') await refreshAll(o);
		else await load(o);
	}

	async function toggleExpand(dirName: string): Promise<void> {
		if (expandedDirs.has(dirName)) { expandedDirs.delete(dirName); return; }
		expandedDirs.add(dirName);
		if (!dirCache.has(dirName)) {
			try { await fetchDir(dirName); }
			catch { expandedDirs.delete(dirName); }
		}
	}

	function findObject(name: string): SwiftObject | undefined {
		for (const items of dirCache.values()) {
			const found = items.find(o => o.name === name);
			if (found) return found;
		}
		if (allObjectsCache) return allObjectsCache.find(o => o.name === name);
		return objects.find(o => o.name === name);
	}

	function pruneSelected(ids: Iterable<string>) {
		selected = pruneSelectionByIds(selected, ids);
	}
	// ——— 네비게이션 ———
	function navigatePrefix(newPrefix: string) {
		prefix = newPrefix;
		selectedMeta = null;
		showPreview = false;
		filterText = '';
		selected = new Set();
		if (opts.mode() === 'user') {
			searchScope = 'current';
			expandedDirs.clear();
			dirCache.clear();
			allObjectsCache = null;
		}
		loadCurrent();
	}

	// ——— 정렬/필터/선택 ———
	function toggleSort(key: typeof sortKey) {
		if (sortKey === key) sortAsc = !sortAsc;
		else { sortKey = key; sortAsc = true; }
	}

	function toggleSelect(name: string) {
		if (bulkDeleting || bulkMoving) return;
		const next = new Set(selected);
		if (next.has(name)) next.delete(name);
		else next.add(name);
		selected = next;
	}

	// ——— admin 평탄 목록 ———
	const filteredObjects = $derived(() => {
		let list = objects.filter(o => {
			if (o.name === prefix) return false;
			const rel = displayName(o.name);
			const check = rel.endsWith('/') ? rel.slice(0, -1) : rel;
			if (check.includes('/')) return false;
			return true;
		});
		if (filterText.trim()) {
			const q = filterText.trim().toLowerCase();
			list = list.filter(o => displayName(o.name).toLowerCase().includes(q));
		}
		return [...list].sort((a, b) => {
			const aDir = isDirectory(a) ? 0 : 1;
			const bDir = isDirectory(b) ? 0 : 1;
			if (aDir !== bDir) return aDir - bDir;
			let cmp = 0;
			if (sortKey === 'name') cmp = displayName(a.name).localeCompare(displayName(b.name));
			else if (sortKey === 'bytes') cmp = (a.bytes || 0) - (b.bytes || 0);
			else if (sortKey === 'last_modified') cmp = (a.last_modified || '').localeCompare(b.last_modified || '');
			return sortAsc ? cmp : -cmp;
		});
	});

	// ——— user 트리 ———
	function sortItems(items: SwiftObject[]): SwiftObject[] {
		return [...items].sort((a, b) => {
			const aDir = isDirectory(a) ? 0 : 1;
			const bDir = isDirectory(b) ? 0 : 1;
			if (aDir !== bDir) return aDir - bDir;
			let cmp = 0;
			if (sortKey === 'name') cmp = baseName(a.name).localeCompare(baseName(b.name));
			else if (sortKey === 'bytes') cmp = (a.bytes || 0) - (b.bytes || 0);
			else if (sortKey === 'last_modified') cmp = (a.last_modified || '').localeCompare(b.last_modified || '');
			return sortAsc ? cmp : -cmp;
		});
	}

	function directChildren(parentPrefix: string, items: SwiftObject[] | undefined): SwiftObject[] {
		if (!items) return [];
		return items.filter(o => {
			if (o.name === parentPrefix) return false;
			const rel = parentPrefix && o.name.startsWith(parentPrefix) ? o.name.slice(parentPrefix.length) : o.name;
			const check = rel.endsWith('/') ? rel.slice(0, -1) : rel;
			if (check.includes('/')) return false;
			return true;
		});
	}

	function buildTreeRows(
		p: string,
		depth: number,
		effectiveExpanded: Set<string> | SvelteSet<string>,
		matchSet: Set<string> | null
	): TreeRow[] {
		const items = sortItems(directChildren(p, dirCache.get(p)));
		const rows: TreeRow[] = [];
		for (const obj of items) {
			const isDir = isDirectory(obj);
			let children: TreeRow[] = [];
			if (isDir && effectiveExpanded.has(obj.name)) {
				children = buildTreeRows(obj.name, depth + 1, effectiveExpanded, matchSet);
			}
			if (matchSet) {
				const selfMatch = matchSet.has(obj.name);
				if (!selfMatch && children.length === 0) continue;
			}
			const isLoading = isDir && effectiveExpanded.has(obj.name) && dirLoading.has(obj.name) && !dirCache.has(obj.name);
			rows.push({ obj, depth, isDir, isExpanded: isDir && effectiveExpanded.has(obj.name), isLoading, fullPath: false });
			rows.push(...children);
		}
		return rows;
	}

	function ancestorPrefixes(name: string): string[] {
		const stripped = name.endsWith('/') ? name.slice(0, -1) : name;
		const parts = stripped.split('/').filter(Boolean);
		const result: string[] = [];
		let acc = '';
		for (let i = 0; i < parts.length - 1; i++) {
			acc += parts[i] + '/';
			result.push(acc);
		}
		if (name.endsWith('/')) result.push(name);
		return result;
	}

	const treeRows = $derived(() => {
		const q = filterText.trim().toLowerCase();
		if (!q) return buildTreeRows(prefix, 0, expandedDirs, null);
		if (searchScope === 'all') {
			if (!allObjectsCache) return [];
			const matched = allObjectsCache
				.filter(o => o.name.toLowerCase().includes(q))
				.filter(o => !o.name.endsWith('/'));
			return sortItems(matched).map(obj => ({
				obj, depth: 0, isDir: false, isExpanded: false, isLoading: false, fullPath: true,
			}));
		}
		if (searchScope === 'expanded') {
			const matchSet = new Set<string>();
			const ancestorSet = new Set<string>();
			for (const items of dirCache.values()) {
				for (const o of items) {
					if (baseName(o.name).toLowerCase().includes(q)) {
						matchSet.add(o.name);
						for (const a of ancestorPrefixes(o.name)) ancestorSet.add(a);
					}
				}
			}
			const effective = new Set<string>([...expandedDirs, ...ancestorSet]);
			return buildTreeRows(prefix, 0, effective, matchSet);
		}
		const items = sortItems(
			directChildren(prefix, dirCache.get(prefix)).filter(o =>
				baseName(o.name).toLowerCase().includes(q)
			)
		);
		return items.map(obj => ({
			obj, depth: 0, isDir: isDirectory(obj), isExpanded: false, isLoading: false, fullPath: false,
		}));
	});

	function visibleObjectNames(): string[] {
		return opts.mode() === 'user'
			? treeRows().map((row) => row.obj.name)
			: filteredObjects().map((object) => object.name);
	}

	function visibleSelectedCount(): number {
		return visibleObjectNames().filter((name) => selected.has(name)).length;
	}

	function toggleSelectAll() {
		if (bulkDeleting || bulkMoving) return;
		const visibleNames = visibleObjectNames();
		selected = visibleNames.length > 0 && visibleNames.every((name) => selected.has(name))
			? new Set()
			: new Set(visibleNames);
	}

	// ——— 액션 ———
	async function bulkDelete() {
		const submitted = [...selected];
		const requestContainer = opts.containerName();
		const requestToken = opts.token();
		const requestProject = opts.projectId();
		const dirs = submitted.filter(n => {
			const obj = findObject(n);
			return obj && isDirectory(obj);
		});
		let msg = `${submitted.length}개 항목을 휴지통으로 이동합니다. 보관 기간 내에 복구할 수 있습니다.`;
		if (dirs.length > 0) msg += `\n\n⚠️ ${dirs.length}개 디렉토리 포함 — 하위 파일이 모두 휴지통으로 이동됩니다.`;
		if (!(await confirmDialog(msg))) return;
		bulkDeleting = true;
		try {
			const result = await api.post<{ deleted?: string[]; failed?: { name: string; error?: string }[] }>(
				`/api/v1/object-storage/${encodeURIComponent(requestContainer)}/objects/bulk-delete`,
				{ objects: submitted, recursive: true },
				requestToken, requestProject
			);
			const deleted = result.deleted ?? [];
			const failedCount = result.failed?.length ?? Math.max(0, submitted.length - deleted.length);
			if (deleted.length) toast.success(`${deleted.length}개 휴지통 이동 요청을 완료했습니다.`);
			if (failedCount) toast.error(`${failedCount}개 휴지통 이동에 실패했습니다.`);
			if (opts.projectId() === requestProject && opts.containerName() === requestContainer) {
				selected = pruneSelectionByIds(selected, submitted.filter((name) => !deleted.includes(name)));
				await doRefresh();
				loadContainerMeta();
			}
		} catch {
			toast.error('삭제 요청에 실패했습니다.');
		} finally { bulkDeleting = false; }
	}

	async function downloadObject(name: string) {
		downloading = name;
		try {
			if (opts.mode() === 'user') {
				const { url } = await api.post<{ url: string; expires_in: number }>(
					`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/${encObj(name)}/download-token`,
					{}, opts.token(), opts.projectId()
				);
				const absoluteUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
				const a = document.createElement('a');
				a.href = absoluteUrl; a.rel = 'noopener';
				document.body.appendChild(a); a.click(); a.remove();
			} else {
				const { blob, filename } = await api.downloadBlob(
					`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/${encObj(name)}/download`,
					opts.token(), opts.projectId()
				);
				downloadBlobAs(blob, filename);
			}
		} catch (e) {
			toast.error('다운로드 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally { downloading = null; }
	}

	async function deleteObject(name: string) {
		if (!(await confirmDialog(`"${displayName(name)}"을(를) 휴지통으로 이동합니다. 보관 기간 내에 복구할 수 있습니다.`))) return;
		deleting = name;
		try {
			await api.delete(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/${encObj(name)}`,
				opts.token(), opts.projectId()
			);
			await doRefresh();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally { deleting = null; }
	}

	async function showMeta(name: string) {
		showPreview = false; loadingMeta = true; selectedMeta = null;
		try {
			selectedMeta = await api.get<SwiftObjectMeta>(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/${encObj(name)}/metadata`,
				opts.token(), opts.projectId()
			);
		} catch { /* ignore */ }
		finally { loadingMeta = false; }
	}

	async function openPreview(obj: SwiftObject) {
		selectedMeta = null; showPreview = true;
		previewName = obj.name; previewContentType = obj.content_type;
		previewText = ''; previewUrl = ''; loadingPreview = true;
		const tok = opts.token(); const pid = opts.projectId();
		const encodedPath = `/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/${encObj(obj.name)}/preview`;
		try {
			const res = await fetchWithAuth(encodedPath, {}, tok, pid);
			if (obj.content_type.startsWith('image/') || obj.content_type === 'application/pdf') {
				previewUrl = URL.createObjectURL(await res.blob());
			} else {
				previewText = await res.text();
			}
		} catch { previewText = '미리보기를 불러오지 못했습니다.'; }
		finally { loadingPreview = false; }
	}

	function closePreview() {
		showPreview = false;
		if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = ''; }
	}

	async function createDirectory() {
		if (!newDirName.trim()) { dirError = '폴더 이름을 입력하세요.'; return; }
		creatingDir = true; dirError = '';
		try {
			await api.post(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/directory`,
				{ path: prefix + newDirName.trim().replace(/\/$/, '') + '/' },
				opts.token(), opts.projectId()
			);
			showNewDir = false; newDirName = '';
			await doRefresh();
		} catch (e) {
			dirError = e instanceof ApiError ? e.message : '폴더 생성 실패';
		} finally { creatingDir = false; }
	}

	function openRename(name: string) {
		renameTarget = name;
		renameIsDir = isDirectory(findObject(name) ?? { name, bytes: 0, content_type: '', last_modified: '', etag: '' });
		renameNew = displayName(name).replace(/\/$/, '');
		renameError = ''; showRename = true;
	}

	async function doRename() {
		if (!renameNew.trim()) { renameError = '새 이름을 입력하세요.'; return; }
		renaming = true; renameError = '';
		try {
			let newFullName = prefix + renameNew.trim();
			if (renameIsDir) newFullName = newFullName.replace(/\/$/, '') + '/';
			await api.post(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/rename`,
				{ source: renameTarget, new_name: newFullName }, opts.token(), opts.projectId()
			);
			showRename = false;
			await doRefresh();
		} catch (e) {
			renameError = e instanceof ApiError ? e.message : '이름 변경 실패';
		} finally { renaming = false; }
	}

	async function loadMoveContainers() {
		try {
			moveContainers = await api.get<SwiftContainer[]>('/api/v1/object-storage', opts.token(), opts.projectId());
		} catch { moveContainers = []; }
	}

	async function loadMoveDirectories(targetContainer: string) {
		moveLoadingDirs = true;
		try {
			const all = await api.get<SwiftObject[]>(
				`/api/v1/object-storage/${encodeURIComponent(targetContainer)}/objects?delimiter=/`,
				opts.token(), opts.projectId()
			);
			moveDirectories = ['/ (루트)', ...all
				.filter(o => o.is_dir === true || o.content_type === 'application/directory' || o.name.endsWith('/'))
				.map(o => o.name)];
		} catch { moveDirectories = ['/ (루트)']; }
		finally { moveLoadingDirs = false; }
	}

	async function openMove(name: string) {
		moveTarget = name; moveDest = ''; moveDestContainer = opts.containerName();
		moveDestinationChosen = false;
		moveSelectedDir = ''; moveError = ''; showMove = true;
		await Promise.all([loadMoveContainers(), loadMoveDirectories(opts.containerName())]);
	}

	function selectMoveDir(dir: string) {
		const stripped = moveTarget.replace(/\/$/, '');
		const bname = stripped.split('/').pop() || stripped;
		const filename = moveTarget.endsWith('/') ? bname + '/' : bname;
		if (dir === '/ (루트)') { moveSelectedDir = ''; moveDest = filename; }
		else { moveSelectedDir = dir; moveDest = dir + filename; }
		moveDestinationChosen = true;
	}

	function selectBulkMoveDir(dir: string) {
		moveSelectedDir = dir === '/ (루트)' ? '' : dir;
		moveDest = moveSelectedDir;
		moveDestinationChosen = true;
	}

	async function onMoveContainerChange(newContainer: string) {
		moveDestContainer = newContainer; moveSelectedDir = ''; moveDest = '';
		moveDestinationChosen = false;
		await loadMoveDirectories(newContainer);
	}

	async function doMove() {
		if (!moveDestinationChosen) { moveError = '대상 경로를 선택하세요.'; return; }
		moving = true; moveError = '';
		try {
			await api.post(
				`/api/v1/object-storage/${encodeURIComponent(opts.containerName())}/objects/move`,
				{ source: moveTarget, destination: moveDest.trim(), dest_container: moveDestContainer || null },
				opts.token(), opts.projectId()
			);
			showMove = false;
			await doRefresh();
		} catch (e) {
			moveError = e instanceof ApiError ? e.message : '이동 실패';
		} finally { moving = false; }
	}

	async function openBulkMove() {
		moveDest = ''; moveDestContainer = opts.containerName();
		moveDestinationChosen = false;
		moveSelectedDir = ''; moveError = ''; showBulkMove = true;
		await Promise.all([loadMoveContainers(), loadMoveDirectories(opts.containerName())]);
	}

	async function doBulkMove() {
		if (!moveDestinationChosen) { moveError = '대상 경로를 선택하세요.'; return; }
		const requestDest = moveDest.trim();
		const submitted = [...selected];
		const requestContainer = opts.containerName();
		const requestToken = opts.token();
		const requestProject = opts.projectId();
		const requestDestContainer = moveDestContainer;
		bulkMoving = true; moveError = '';
		try {
			const results = await executeBulkMutations(submitted, async (name) => {
				const isDir2 = isDirectory(findObject(name) ?? { name, bytes: 0, content_type: '', last_modified: '', etag: '' });
				const basename = isDir2
					? `${name.replace(/\/$/, '').split('/').pop() || name}/`
					: name.split('/').pop() || name;
				const destination = requestDest
					? `${requestDest.replace(/\/$/, '')}/${basename}`
					: basename;
				await api.post(
					`/api/v1/object-storage/${encodeURIComponent(requestContainer)}/objects/move`,
					{ source: name, destination, dest_container: requestDestContainer || null },
					requestToken, requestProject
				);
			});
			const moved = results.filter((result) => result.ok).map((result) => result.id);
			const failedCount = results.length - moved.length;
			if (moved.length) toast.success(`${moved.length}개 이동 요청을 완료했습니다.`);
			if (failedCount) toast.error(`${failedCount}개 이동에 실패했습니다.`);
			if (opts.projectId() === requestProject && opts.containerName() === requestContainer) {
				showBulkMove = false;
				selected = pruneSelectionByIds(selected, submitted.filter((name) => !moved.includes(name)));
				await doRefresh();
				loadContainerMeta();
			}
		} finally { bulkMoving = false; }
	}

	function handleDrop(e: DragEvent) {
		const refreshFn = opts.mode() === 'user'
			? () => refreshAll({ silent: true })
			: () => load({ silent: true });
		for (const f of Array.from(e.dataTransfer?.files ?? [])) {
			uploadQueue.enqueue(f, {
				containerName: opts.containerName(),
				prefix,
				token: opts.token(),
				projectId: opts.projectId(),
				onComplete: (job) => { if (job.status === 'success') refreshFn(); }
			});
		}
	}

	function onResizeStart(e: MouseEvent, col: keyof typeof colWidths, tableEl: HTMLTableElement | null) {
		e.preventDefault();
		const startX = e.clientX;
		const startW = colWidths[col];
		const tableW = tableEl?.offsetWidth ?? 800;
		const onMove = (ev: MouseEvent) => {
			const diff = ((ev.clientX - startX) / tableW) * 100;
			colWidths[col] = Math.max(5, startW + diff);
		};
		const onUp = () => {
			document.removeEventListener('mousemove', onMove);
			document.removeEventListener('mouseup', onUp);
		};
		document.addEventListener('mousemove', onMove);
		document.addEventListener('mouseup', onUp);
	}

	// ——— effects ———
	$effect(() => {
		if (opts.mode() === 'user' && searchScope === 'all' && filterText.trim() && allObjectsCache === null && !allObjectsLoading) {
			fetchAllObjects();
		}
	});

	$effect(() => {
		const cn = opts.containerName();
		const pid = opts.projectId();
		prefix = '';
		objects = [];
		selected = new Set();
		filterText = '';
		selectedMeta = null;
		showPreview = false;
		containerMeta = null;
		showMove = false;
		showBulkMove = false;
		moveDest = '';
		moveSelectedDir = '';
		moveDestinationChosen = false;
		moveError = '';
		moveContainers = [];
		moveDirectories = [];
		if (opts.mode() === 'user') {
			searchScope = 'current';
			expandedDirs.clear();
			dirCache.clear();
			allObjectsCache = null;
		}
		if (!cn || !pid) return;
		loadCurrent();
		loadContainerMeta();
	});

	// ——— 반환 ———
	return {
		get mode() { return opts.mode(); },
		get containerName() { return opts.containerName(); },
		get objects() { return objects; },
		get loading() { return loading; },
		get prefix() { return prefix; },
		get deleting() { return deleting; },
		get downloading() { return downloading; },
		get selected() { return selected; },
		set selected(v: Set<string>) { selected = v; },
		get bulkDeleting() { return bulkDeleting; },
		get filterText() { return filterText; },
		set filterText(v: string) {
			if (filterText !== v) selected = new Set();
			filterText = v;
		},
		get sortKey() { return sortKey; },
		get sortAsc() { return sortAsc; },
		get showUpload() { return showUpload; },
		set showUpload(v: boolean) { showUpload = v; },
		get dragActive() { return dragActive; },
		set dragActive(v: boolean) { dragActive = v; },
		get showNewDir() { return showNewDir; },
		set showNewDir(v: boolean) { showNewDir = v; },
		get newDirName() { return newDirName; },
		set newDirName(v: string) { newDirName = v; },
		get creatingDir() { return creatingDir; },
		get dirError() { return dirError; },
		get showRename() { return showRename; },
		set showRename(v: boolean) { showRename = v; },
		get renameTarget() { return renameTarget; },
		get renameNew() { return renameNew; },
		set renameNew(v: string) { renameNew = v; },
		get renameIsDir() { return renameIsDir; },
		get renaming() { return renaming; },
		get renameError() { return renameError; },
		get showMove() { return showMove; },
		set showMove(v: boolean) { showMove = v; },
		get moveTarget() { return moveTarget; },
		get moveDest() { return moveDest; },
		get moveDestContainer() { return moveDestContainer; },
		get moveDestinationChosen() { return moveDestinationChosen; },
		set moveDestContainer(v: string) { moveDestContainer = v; },
		get moving() { return moving; },
		get moveError() { return moveError; },
		get moveContainers() { return moveContainers; },
		get moveDirectories() { return moveDirectories; },
		get moveLoadingDirs() { return moveLoadingDirs; },
		get moveSelectedDir() { return moveSelectedDir; },
		get showBulkMove() { return showBulkMove; },
		set showBulkMove(v: boolean) { showBulkMove = v; },
		get bulkMoving() { return bulkMoving; },
		get showPreview() { return showPreview; },
		set showPreview(v: boolean) { showPreview = v; },
		get previewName() { return previewName; },
		get previewContentType() { return previewContentType; },
		get previewText() { return previewText; },
		get loadingPreview() { return loadingPreview; },
		get previewUrl() { return previewUrl; },
		get selectedMeta() { return selectedMeta; },
		set selectedMeta(v: SwiftObjectMeta | null) { selectedMeta = v; },
		get loadingMeta() { return loadingMeta; },
		get containerMeta() { return containerMeta; },
		get colWidths() { return colWidths; },
		// user-only
		get searchScope() { return searchScope; },
		set searchScope(v: 'current' | 'expanded' | 'all') {
			if (searchScope !== v) selected = new Set();
			searchScope = v;
		},
		get expandedDirs() { return expandedDirs; },
		get dirCache() { return dirCache; },
		get dirLoading() { return dirLoading; },
		get allObjectsCache() { return allObjectsCache; },
		get allObjectsLoading() { return allObjectsLoading; },
		// derived
		get breadcrumbs() { return breadcrumbs; },
		get filteredObjects() { return filteredObjects(); },
		get treeRows() { return treeRows(); },
		get selectedCount() { return selected.size; },
		get visibleObjectCount() { return visibleObjectNames().length; },
		get visibleSelectedCount() { return visibleSelectedCount(); },
		// helpers
		isDirectory,
		isPreviewable,
		displayName,
		baseName,
		sortIcon,
		breadcrumbPrefix,
		encObj,
		// handlers
		load,
		refreshAll,
		doRefresh,
		fetchDir,
		fetchAllObjects,
		toggleExpand,
		navigatePrefix,
		toggleSelect,
		toggleSelectAll,
		toggleSort,
		bulkDelete,
		downloadObject,
		deleteObject,
		showMeta,
		openPreview,
		closePreview,
		createDirectory,
		openRename,
		doRename,
		openMove,
		selectMoveDir,
		selectBulkMoveDir,
		onMoveContainerChange,
		doMove,
		openBulkMove,
		doBulkMove,
		handleDrop,
		loadContainerMeta,
		onResizeStart,
	};
}

export type ObjectBrowserStore = ReturnType<typeof createObjectBrowserStore>;

export function provideObjectBrowser(store: ObjectBrowserStore) {
	setContext(OBJECT_BROWSER_KEY, store);
}

export function useObjectBrowser(): ObjectBrowserStore {
	return getContext<ObjectBrowserStore>(OBJECT_BROWSER_KEY);
}
