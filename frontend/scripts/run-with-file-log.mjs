import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export function getLocalDateString(d = new Date()) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export class FileLogWriter {
  constructor(options = {}) {
    this.prefix = options.prefix || 'frontend';
    this.logDir = options.logDir || process.env.LOG_DIRECTORY || path.resolve(process.cwd(), 'logs');
    this.maxBytes = options.maxBytes || (process.env.LOG_MAX_BYTES ? parseInt(process.env.LOG_MAX_BYTES, 10) : 10485760);
    this.dateProvider = options.dateProvider || (() => new Date());
    this.currentDateStr = null;
    this.currentFilePath = null;
    this.currentSize = 0;
    this.currentSeq = 0;
  }

  ensureLogDir() {
    try {
      if (!fs.existsSync(this.logDir)) {
        fs.mkdirSync(this.logDir, { recursive: true });
      }
    } catch (err) {
      // Fail open
    }
  }

  findActiveFileForDate(dateStr) {
    this.ensureLogDir();
    try {
      const files = fs.readdirSync(this.logDir);
      const baseName = `${this.prefix}-${dateStr}.log`;
      const suffixedRegex = new RegExp(`^${this.prefix}-${dateStr}-(\\d+)\\.log$`);

      let maxSeq = -1;

      for (const f of files) {
        if (f === baseName) {
          if (maxSeq < 0) maxSeq = 0;
        } else {
          const match = f.match(suffixedRegex);
          if (match) {
            const seq = parseInt(match[1], 10);
            if (seq > maxSeq) {
              maxSeq = seq;
            }
          }
        }
      }

      if (maxSeq < 0) {
        return {
          filePath: path.join(this.logDir, baseName),
          size: 0,
          seq: 0,
        };
      }

      const activeFileName = maxSeq === 0 ? baseName : `${this.prefix}-${dateStr}-${String(maxSeq).padStart(2, '0')}.log`;
      const fullPath = path.join(this.logDir, activeFileName);
      let size = 0;
      try {
        const stat = fs.statSync(fullPath);
        size = stat.size;
      } catch (err) {
        size = 0;
      }

      if (size < this.maxBytes) {
        return { filePath: fullPath, size, seq: maxSeq };
      }

      const nextSeq = maxSeq + 1;
      const nextFileName = `${this.prefix}-${dateStr}-${String(nextSeq).padStart(2, '0')}.log`;
      return {
        filePath: path.join(this.logDir, nextFileName),
        size: 0,
        seq: nextSeq,
      };
    } catch (err) {
      return {
        filePath: path.join(this.logDir, `${this.prefix}-${dateStr}.log`),
        size: 0,
        seq: 0,
      };
    }
  }

  rotateToDate(dateStr) {
    this.currentDateStr = dateStr;
    const target = this.findActiveFileForDate(dateStr);
    this.currentFilePath = target.filePath;
    this.currentSize = target.size;
    this.currentSeq = target.seq;
  }

  rotateNextSuffix(dateStr) {
    this.currentDateStr = dateStr;
    const target = this.findActiveFileForDate(dateStr);
    if (target.size < this.maxBytes && target.filePath !== this.currentFilePath) {
      this.currentFilePath = target.filePath;
      this.currentSize = target.size;
      this.currentSeq = target.seq;
    } else {
      const nextSeq = (this.currentSeq || target.seq || 0) + 1;
      const nextFileName = `${this.prefix}-${dateStr}-${String(nextSeq).padStart(2, '0')}.log`;
      this.currentFilePath = path.join(this.logDir, nextFileName);
      this.currentSize = 0;
      this.currentSeq = nextSeq;
    }
  }

  closeStream() {
    // No-op for appendFileSync, present for interface parity
  }

  write(chunk) {
    try {
      const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      const nowStr = getLocalDateString(this.dateProvider());

      if (!this.currentDateStr || this.currentDateStr !== nowStr) {
        this.rotateToDate(nowStr);
      } else if (this.currentSize > 0 && this.currentSize + buf.length > this.maxBytes) {
        this.rotateNextSuffix(nowStr);
      }

      this.ensureLogDir();
      fs.appendFileSync(this.currentFilePath, buf);
      this.currentSize += buf.length;
    } catch (err) {
      // Fail open on file errors
    }
  }
}

export function run(args = process.argv.slice(2)) {
  if (args.length === 0) {
    console.error('Usage: node run-with-file-log.mjs <command> [args...]');
    process.exit(1);
  }

  const writer = new FileLogWriter();

  const child = spawn(args[0], args.slice(1), {
    stdio: ['inherit', 'pipe', 'pipe'],
    env: process.env,
  });

  child.stdout?.on('data', (chunk) => {
    process.stdout.write(chunk);
    writer.write(chunk);
  });

  child.stderr?.on('data', (chunk) => {
    process.stderr.write(chunk);
    writer.write(chunk);
  });

  const forwardSignal = (sig) => {
    if (child && !child.killed) {
      try {
        child.kill(sig);
      } catch (err) {
        // ignore
      }
    }
  };

  process.on('SIGTERM', () => forwardSignal('SIGTERM'));
  process.on('SIGINT', () => forwardSignal('SIGINT'));
  process.on('SIGHUP', () => forwardSignal('SIGHUP'));

  child.on('close', (code, signal) => {
    writer.closeStream();
    if (code !== null) {
      process.exit(code);
    } else if (signal) {
      process.exit(128 + 15);
    } else {
      process.exit(0);
    }
  });

  return child;
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
if (isMain) {
  run();
}
