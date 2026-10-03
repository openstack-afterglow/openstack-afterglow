/* Voice frames stay in memory and are transferred to the active WebSocket only. */
class Pcm16Capture extends AudioWorkletProcessor {
	constructor(options) {
		super();
		const targetRate = options.processorOptions.targetRate;
		if (targetRate !== 16000 && targetRate !== 24000) throw new Error('Unsupported PCM sample rate');
		this.ratio = sampleRate / targetRate;
		this.phase = 0;
		this.sum = 0;
		this.count = 0;
		this.buffer = new Int16Array(2048);
		this.offset = 0;
	}
	process(inputs) {
		const mono = inputs[0]?.[0];
		if (!mono) return true;
		for (let i = 0; i < mono.length; i++) {
			this.sum += mono[i];
			this.count++;
			this.phase++;
			if (this.phase < this.ratio) continue;
			const value = Math.max(-1, Math.min(1, this.sum / this.count));
			this.buffer[this.offset++] = value < 0 ? Math.round(value * 32768) : Math.round(value * 32767);
			this.sum = 0;
			this.count = 0;
			this.phase -= this.ratio;
			if (this.offset === this.buffer.length) {
				this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
				this.buffer = new Int16Array(2048);
				this.offset = 0;
			}
		}
		return true;
	}
}
registerProcessor('pcm16-capture', Pcm16Capture);
