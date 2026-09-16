import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { FileLogWriter, getLocalDateString } from './run-with-file-log.mjs';

test('getLocalDateString returns YYYY-MM-DD format', () => {
  const d = new Date(2026, 7, 31); // Aug 31, 2026
  assert.equal(getLocalDateString(d), '2026-08-31');
});

test('FileLogWriter creates base log file on first write', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'log-test-'));
  try {
    const writer = new FileLogWriter({ logDir: tmpDir, maxBytes: 100 });
    writer.write('hello world\n');

    const todayStr = getLocalDateString();
    const expectedFile = path.join(tmpDir, `frontend-${todayStr}.log`);
    assert.equal(fs.existsSync(expectedFile), true);
    assert.equal(fs.readFileSync(expectedFile, 'utf8'), 'hello world\n');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('FileLogWriter resumes appending to existing file if size < maxBytes', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'log-test-'));
  try {
    const todayStr = getLocalDateString();
    const baseFile = path.join(tmpDir, `frontend-${todayStr}.log`);
    fs.mkdirSync(tmpDir, { recursive: true });
    fs.writeFileSync(baseFile, 'existing data\n');

    const writer = new FileLogWriter({ logDir: tmpDir, maxBytes: 100 });
    writer.write('new data\n');

    assert.equal(fs.readFileSync(baseFile, 'utf8'), 'existing data\nnew data\n');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('FileLogWriter rotates to suffixed file when maxBytes would be exceeded', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'log-test-'));
  try {
    const todayStr = getLocalDateString();
    const writer = new FileLogWriter({ logDir: tmpDir, maxBytes: 20 });

    // First write: 15 bytes -> fits in base file
    writer.write('123456789012345');
    const baseFile = path.join(tmpDir, `frontend-${todayStr}.log`);
    assert.equal(fs.existsSync(baseFile), true);
    assert.equal(fs.readFileSync(baseFile, 'utf8'), '123456789012345');

    // Second write: 10 bytes -> 15 + 10 = 25 > 20 -> rotates to -01.log
    writer.write('abcdefghij');
    const suffixFile1 = path.join(tmpDir, `frontend-${todayStr}-01.log`);
    assert.equal(fs.existsSync(suffixFile1), true);
    assert.equal(fs.readFileSync(suffixFile1, 'utf8'), 'abcdefghij');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('FileLogWriter starts an unsuffixed file after a local date rollover', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'log-test-'));
  try {
    let currentDate = new Date(2026, 7, 31);
    const writer = new FileLogWriter({
      logDir: tmpDir,
      maxBytes: 100,
      dateProvider: () => currentDate,
    });

    writer.write('august');
    currentDate = new Date(2026, 8, 1);
    writer.write('september');

    assert.equal(fs.readFileSync(path.join(tmpDir, 'frontend-2026-08-31.log'), 'utf8'), 'august');
    assert.equal(fs.readFileSync(path.join(tmpDir, 'frontend-2026-09-01.log'), 'utf8'), 'september');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('FileLogWriter handles sequence gaps by allocating fresh higher suffix', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'log-test-'));
  try {
    const todayStr = getLocalDateString();
    fs.mkdirSync(tmpDir, { recursive: true });

    // Create base file (full) and -02.log (full), leaving gap at -01.log
    const baseFile = path.join(tmpDir, `frontend-${todayStr}.log`);
    const suffix2 = path.join(tmpDir, `frontend-${todayStr}-02.log`);
    fs.writeFileSync(baseFile, 'X'.repeat(50));
    fs.writeFileSync(suffix2, 'X'.repeat(50));

    const writer = new FileLogWriter({ logDir: tmpDir, maxBytes: 50 });
    writer.write('new chunk');

    // Highest sequence present was 02; since 02 is full, next allocated suffix must be -03.log
    const suffix3 = path.join(tmpDir, `frontend-${todayStr}-03.log`);
    assert.equal(fs.existsSync(suffix3), true);
    assert.equal(fs.readFileSync(suffix3, 'utf8'), 'new chunk');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('FileLogWriter allows oversized first chunk to write alone in unsuffixed file', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'log-test-'));
  try {
    const todayStr = getLocalDateString();
    const writer = new FileLogWriter({ logDir: tmpDir, maxBytes: 10 });

    // Oversized chunk (50 bytes > 10 maxBytes) when file size is 0
    writer.write('A'.repeat(50));

    const baseFile = path.join(tmpDir, `frontend-${todayStr}.log`);
    const suffix1 = path.join(tmpDir, `frontend-${todayStr}-01.log`);

    assert.equal(fs.existsSync(baseFile), true);
    assert.equal(fs.readFileSync(baseFile, 'utf8'), 'A'.repeat(50));
    // Must NOT have created an empty base file and immediately rotated to -01.log
    assert.equal(fs.existsSync(suffix1), false);

    // Next chunk triggers rotation to -01.log
    writer.write('B');
    assert.equal(fs.existsSync(suffix1), true);
    assert.equal(fs.readFileSync(suffix1, 'utf8'), 'B');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('FileLogWriter fails open on filesystem errors', () => {
  const writer = new FileLogWriter({ logDir: '/invalid-non-existent-dir-for-test-fail-open/sub' });
  // Should not throw exception
  assert.doesNotThrow(() => {
    writer.write('test string\n');
  });
});

test('run-with-file-log runner executes child command and mirrors stdio', (t, done) => {
  const scriptPath = fileURLToPath(new URL('./run-with-file-log.mjs', import.meta.url));
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'log-runner-test-'));

  const child = spawn(process.execPath, [scriptPath, 'node', '-e', 'console.log("hello from child"); console.error("error from child");'], {
    env: {
      ...process.env,
      LOG_DIRECTORY: tmpDir,
    },
  });

  let stdout = '';
  let stderr = '';

  child.stdout.on('data', (d) => { stdout += d.toString(); });
  child.stderr.on('data', (d) => { stderr += d.toString(); });

  child.on('close', (code) => {
    try {
      assert.equal(code, 0);
      assert.match(stdout, /hello from child/);
      assert.match(stderr, /error from child/);

      const todayStr = getLocalDateString();
      const logFile = path.join(tmpDir, `frontend-${todayStr}.log`);
      assert.equal(fs.existsSync(logFile), true);

      const content = fs.readFileSync(logFile, 'utf8');
      assert.match(content, /hello from child/);
      assert.match(content, /error from child/);
      done();
    } catch (err) {
      done(err);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});
