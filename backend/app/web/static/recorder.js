/* Audio Recorder using MediaRecorder (spec/09 §9.2). MIME by feature detection: webm/opus, */

const REC_DEFAULTS = { maxSec: 60, minSec: 1 };

class AudioRecorder {
  constructor(cfg) {
    const c = Object.assign({}, REC_DEFAULTS, cfg || {});
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.stream = null;
    this.startTime = 0;
    this.timerInterval = null;
    this.maxDurationSec = c.maxSec; 
    this.minDurationSec = c.minSec; 
    this.phase = 'idle'; 
    this.pendingAction = null; 
    this.cancelled = false; 
    this.autoStopped = false;
  }

  get isRecording() {
    return this.phase !== 'idle';
  }

  isSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }

  getMimeType() {
    for (const type of ['audio/webm;codecs=opus', 'audio/mp4']) {
      if (MediaRecorder.isTypeSupported(type)) return type;
    }
    return ''; 
  }

  
  
  async start(handlers) {
    const h = handlers || {};
    if (this.phase !== 'idle') return;
    if (window.isSecureContext === false) {
      if (h.onError) h.onError('insecure', '');
      return;
    }
    if (!this.isSupported()) {
      if (h.onError) h.onError('unsupported', '');
      return;
    }

    this.phase = 'starting';
    this.pendingAction = null;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (err) {
      this.cleanup();
      this.phase = 'idle';
      loggerError(err);
      if (h.onError) h.onError(classifyMediaError(err), err && err.message ? err.message : '');
      return;
    }

    if (this.pendingAction) {
      const action = this.pendingAction;
      this.pendingAction = null;
      this.cleanup();
      this.phase = 'idle';
      if (action === 'stop' && h.onTooShort) h.onTooShort();
      return;
    }

    try {
      const mimeType = this.getMimeType();
      const options = { audioBitsPerSecond: 16000 };
      if (mimeType) options.mimeType = mimeType;

      this.mediaRecorder = new MediaRecorder(this.stream, options);
      this.audioChunks = [];
      this.cancelled = false;
      this.autoStopped = false;

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) this.audioChunks.push(event.data);
      };

      this.mediaRecorder.onerror = (event) => {
        loggerError(event && event.error ? event.error : event);
        this.cancelled = true;
        this.cleanup();
        this.phase = 'idle';
        if (h.onError) h.onError('start_failed', '');
      };

      this.mediaRecorder.onstop = () => {
        const durationSec = (Date.now() - this.startTime) / 1000;
        const wasCancelled = this.cancelled;
        const reason = this.autoStopped ? 'auto' : 'user';
        
        const actualMime =
          (this.mediaRecorder && this.mediaRecorder.mimeType) || mimeType || 'audio/webm';
        const audioBlob = new Blob(this.audioChunks, { type: actualMime });
        this.cleanup();
        this.phase = 'idle';
        this.cancelled = false;

        if (wasCancelled) return; 
        if (durationSec < this.minDurationSec || audioBlob.size === 0) {
          if (h.onTooShort) h.onTooShort();
          return;
        }
        if (h.onComplete) h.onComplete(audioBlob, durationSec, reason);
      };

      this.startTime = Date.now();
      this.phase = 'recording';
      this.mediaRecorder.start(250); 

      this.timerInterval = setInterval(() => {
        const elapsed = (Date.now() - this.startTime) / 1000;
        if (h.onTick) h.onTick(elapsed);
        if (elapsed >= this.maxDurationSec) {
          this.autoStopped = true;
          this.stop();
        }
      }, 200);
    } catch (err) {
      this.cleanup();
      this.phase = 'idle';
      loggerError(err);
      if (h.onError) h.onError('start_failed', err && err.message ? err.message : '');
    }
  }

  stop() {
    if (this.phase === 'starting') {
      this.pendingAction = 'stop';
    } else if (this.phase === 'recording' && this.mediaRecorder) {
      if (this.mediaRecorder.state !== 'inactive') this.mediaRecorder.stop();
    }
  }

  cancel() {
    if (this.phase === 'starting') {
      this.pendingAction = 'cancel';
      return;
    }
    if (this.phase !== 'recording') return;
    this.cancelled = true;
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop(); 
    } else {
      this.cleanup();
      this.phase = 'idle';
    }
  }

  cleanup() {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    this.audioChunks = [];
  }
}

function classifyMediaError(err) {
  const name = err && err.name;
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    return 'permission';
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError' || name === 'OverconstrainedError') {
    return 'no_mic';
  }
  if (name === 'NotReadableError' || name === 'TrackStartError' || name === 'AbortError') {
    return 'busy';
  }
  return 'start_failed';
}

function loggerError(e) {
  if (window.console && console.warn) {
    console.warn('AudioRecorder error:', e);
  }
}

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) {
    return meta.content;
  }
  const match = document.cookie.match(/(?:^|;\s*)abhyas_csrf=([^;]+)/);
  if (match) {
    return decodeURIComponent(match[1]);
  }
  return '';
}

window.getCsrfToken = window.getCsrfToken || getCsrfToken;
window.AudioRecorder = AudioRecorder;
