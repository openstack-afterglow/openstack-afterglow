const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const os = require("node:os")
const { spawnSync } = require("node:child_process")
const test = require("node:test")

const root = path.resolve(__dirname, "..")
const role = "deploy/kolla/ansible/roles/afterglow"
const helper = path.join(root, role, "files/snapshot_nova_pci_aliases.py")
const fields = ["name", "vendor_id", "product_id", "resource_class", "device_type", "traits", "numa_policy"]
const gpu = { name: "RTX-3090", vendor_id: "10DE", product_id: "2204" }
const audio = { name: "RTX-3090-Audio", vendor_id: "10DE", product_id: "1AEB" }

function run(request) {
	const result = spawnSync("python3", [helper], { input: JSON.stringify(request), encoding: "utf8", maxBuffer: 8 * 1024 * 1024 })
	assert.equal(result.status, 0, result.stderr)
	assert.equal(result.stderr, "")
	return JSON.parse(result.stdout)
}

function collect(content, prepare) {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kolla-pci-snapshot-"))
	try {
		const file = path.join(dir, "nova.conf")
		if (content !== null) fs.writeFileSync(file, content)
		if (prepare) prepare(file)
		return run({ host: "controller-a", path: file })
	} finally {
		fs.rmSync(dir, { recursive: true, force: true })
	}
}

function unavailable(record) {
	assert.deepEqual(record, { host: "controller-a", observed_at: null, state: "unavailable", aliases: [] })
}

test("Kolla PCI snapshot preserves duplicate aliases, multiline JSON and stock INI comments without secrets", () => {
	const record = collect(`[DEFAULT]\ntransport_url=rabbit://private:SECRET@host\n# never export SECRET\n[pci]\nalias=${JSON.stringify(gpu)}\n; whole-line comment\nalias: {\n  "name": "RTX-3090-Audio",\n  "vendor_id": "10DE",\n  "product_id": "1AEB"\n  }\nalias='${JSON.stringify(gpu)}'\n[database]\nconnection=mysql://private:SECRET@host\n`)
	assert.equal(record.state, "ready")
	assert.match(record.observed_at, /^\d{4}-\d{2}-\d{2}T/)
	assert.deepEqual(record.aliases.map(item => item.name), [gpu.name, audio.name, gpu.name])
	for (const alias of record.aliases) assert.deepEqual(Object.keys(alias).sort(), [...fields].sort())
	assert.equal(record.aliases[0].resource_class, null)
	assert.doesNotMatch(JSON.stringify(record), /SECRET|database|transport_url|connection/)
})

test("Kolla PCI snapshot preserves conflicting alternatives rather than deduplicating exact names", () => {
	const record = collect(`[pci]\nalias=${JSON.stringify(gpu)}\nalias=${JSON.stringify({ ...gpu, product_id: "2206" })}\n`)
	assert.equal(record.state, "ready")
	assert.deepEqual(record.aliases.map(item => item.name), [gpu.name, gpu.name])
	assert.deepEqual(record.aliases.map(item => item.product_id), ["2204", "2206"])
})

test("Kolla PCI snapshot includes deprecated DEFAULT pci_alias alongside current aliases", () => {
	const record = collect(`[DEFAULT]\npci_alias=${JSON.stringify(audio)}\npci_alias=${JSON.stringify({ ...gpu, product_id: "2206" })}\n[pci]\nalias=${JSON.stringify(gpu)}\n`)
	assert.equal(record.state, "ready")
	assert.deepEqual(record.aliases.map(item => [item.name, item.product_id]), [[audio.name, "1AEB"], [gpu.name, "2206"], [gpu.name, "2204"]])
	const legacyOnly = collect(`[DEFAULT]\npci_alias=${JSON.stringify(gpu)}\n`)
	assert.equal(legacyOnly.state, "ready")
	assert.deepEqual(legacyOnly.aliases.map(item => item.name), [gpu.name])
	unavailable(collect(`[DEFAULT]\npci_alias={SECRET malformed}\n[pci]\nalias=${JSON.stringify(gpu)}\n`))
})

test("Kolla PCI snapshot rejects padded names that Nova would merge under a trimmed alias", () => {
	for (const name of [" RTX-3090", "RTX-3090 "]) {
		unavailable(collect(`[pci]\nalias=${JSON.stringify(gpu)}\nalias=${JSON.stringify({ ...gpu, name, product_id: "2206" })}\n`))
	}
})

test("Kolla PCI snapshot repeats identical source revision times and aggregate bytes", () => {
	let first
	const record = collect(`[pci]\nalias=${JSON.stringify(gpu)}\n`, file => {
		fs.utimesSync(file, new Date("2026-10-30T00:00:00Z"), new Date("2026-10-30T00:00:00Z"))
		first = run({ host: "controller-a", path: file })
	})
	assert.deepEqual(record, first)
	assert.equal(record.observed_at, "2026-10-30T00:00:00+00:00")
	const aggregate = observation => run({ mode: "aggregate", controllers: ["controller-a"], results: [
		{ item: "controller-a", rc: 0, stdout: JSON.stringify(observation) },
	] })
	assert.deepEqual(aggregate(record), aggregate(first))
})

test("Kolla PCI snapshot reports unavailable for absent, empty, malformed, oversized and symlink inputs", () => {
	for (const text of [null, "", "# comment only\n", "[pci\nalias={}\n", "alias={}\n", "[pci]\nalias={broken SECRET}\n",
		`[pci]\nalias=${JSON.stringify(gpu)} # SECRET\n`, `[pci]\nalias=${JSON.stringify(gpu)}\n # invalid indented comment\n`,
		`[pci]\nalias=${JSON.stringify(gpu)}\nalias={}\n`, `[pci]\nalias={"name":"a","name":"b"}\n`,
		`[PCI]\nalias=${JSON.stringify(gpu)}\n`,
		`[pci]\nalias=${JSON.stringify({ ...gpu, traits: ["SECRET"] })}\n`, "#".repeat(1024 * 1024 + 1)]) {
		unavailable(collect(text))
	}
	unavailable(collect("[pci]\n", file => {
		fs.renameSync(file, `${file}.real`)
		fs.symlinkSync(`${file}.real`, file)
	}))
})

test("Kolla PCI snapshot does not certify aliases after silently discarding unknown constraints", () => {
	unavailable(collect(`[pci]\nalias=${JSON.stringify({ ...gpu, password: "SECRET" })}\n`))
	unavailable(collect(`[pci]\nalias=${JSON.stringify({ ...gpu, live_migratable: "yes" })}\n`))
	const record = collect(`[pci]\nalias=${JSON.stringify({ ...gpu, traits: "CUSTOM_GPU,CUSTOM_FAST", device_type: "type-PCI", numa_policy: "required" })}\n`)
	assert.equal(record.state, "ready")
	assert.equal(record.aliases[0].traits, "CUSTOM_GPU,CUSTOM_FAST")
	assert.equal(record.aliases[0].numa_policy, "required")
})

test("Kolla PCI snapshot distinguishes a valid config with no aliases from unavailable files", () => {
	for (const text of ["[DEFAULT]\ntransport_url=SECRET\n", "[pci]\n# alias is deliberately absent\n"]) {
		const record = collect(text)
		assert.equal(record.state, "ready")
		assert.deepEqual(record.aliases, [])
	}
})

test("Kolla PCI snapshot aggregates all controllers and never publishes connection errors or foreign observations", () => {
	const ready = collect(`[pci]\nalias=${JSON.stringify(gpu)}\n`)
	const snapshot = run({ mode: "aggregate", controllers: ["controller-d", "controller-c", "controller-b", "controller-a"], results: [
		{ item: "controller-a", rc: 0, stdout: JSON.stringify(ready) },
		{ item: "controller-b", unreachable: true, msg: "SECRET SSH ERROR" },
		{ item: "controller-c", rc: 0, stdout: JSON.stringify({ ...ready, host: "controller-other" }) },
	] })
	assert.deepEqual(Object.keys(snapshot).sort(), ["controllers", "schema_version", "source"])
	assert.equal(snapshot.schema_version, 1)
	assert.equal(snapshot.source, "nova_api_config")
	assert.deepEqual(snapshot.controllers.map(item => item.host), ["controller-a", "controller-b", "controller-c", "controller-d"])
	assert.deepEqual(snapshot.controllers.map(item => item.state), ["ready", "unavailable", "unavailable", "unavailable"])
	assert.ok(snapshot.controllers.slice(1).every(item => item.observed_at === null && item.aliases.length === 0))
	assert.doesNotMatch(JSON.stringify(snapshot), /SECRET|SSH|controller-other/)
})

test("Kolla PCI snapshot bounds aggregate bytes without truncating a ready controller alias set", () => {
	const aliases = Array.from({ length: 256 }, () => ({ name: "a".repeat(255), vendor_id: "10DE", product_id: "2204", traits: "T".repeat(4096) }))
	const snapshot = run({ mode: "aggregate", controllers: ["controller-a", "controller-b"], results: ["controller-a", "controller-b"].map(host => ({
		item: host, rc: 0, stdout: JSON.stringify({ host, state: "ready", observed_at: "2026-10-30T00:00:00+00:00", aliases }),
	})) })
	assert.ok(Buffer.byteLength(JSON.stringify(snapshot)) + 1 <= 1024 * 1024)
	assert.ok(snapshot.controllers.every(item => item.state === "unavailable" && item.aliases.length === 0))
})
