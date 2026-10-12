/**
 * Audio Recorder using MediaRecorder (spec/09 §9.2).
 * Formats: audio/webm;codecs=opus (Chrome/Android) or audio/mp4 (Safari).
 * Constraints: mono 16kbps, max 90s, min 0.7s discard.
 */

class AudioRecorder {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.stream = null;
    this.startTime = 0;
    this.timerInterval = null;
    this.maxDurationSec = 90; // Auto-stop at 90s (§9.2)
    this.minDurationSec = 0.7; // Discard under 0.7s (§9.2)
    this.isRecording = false;
  }

  isSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }

  getMimeType() {
    if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
      return 'audio/webm;codecs=opus';
    }
    if (MediaRecorder.isTypeSupported('audio/webm')) {
      return 'audio/webm';
    }
    if (MediaRecorder.isTypeSupported('audio/mp4')) {
      return 'audio/mp4';
    }
    if (MediaRecorder.isTypeSupported('audio/aac')) {
      return 'audio/aac';
    }
    return '';
  }

  async start(onTick, onComplete, onError) {
    if (!this.isSupported()) {
      if (onError) onError('आपके ब्राउज़र में आवाज़ रिकॉर्ड करने की सुविधा उपलब्ध नहीं है।');
      return;
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const mimeType = this.getMimeType();
      const options = {
        audioBitsPerSecond: 16000,
      };
      if (mimeType) {
        options.mimeType = mimeType;
      }

      this.mediaRecorder = new MediaRecorder(this.stream, options);
      this.audioChunks = [];
      this.startTime = Date.now();
      this.isRecording = true;

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = () => {
        const durationSec = (Date.now() - this.startTime) / 1000;
        this.cleanup();

        if (durationSec < this.minDurationSec) {
          // Discard under 0.7s (§9.2)
          return;
        }

        const actualMime = this.mediaRecorder ? this.mediaRecorder.mimeType : (mimeType || 'audio/webm');
        const audioBlob = new Blob(this.audioChunks, { type: actualMime });
        if (onComplete) {
          onComplete(audioBlob, durationSec);
        }
      };

      this.mediaRecorder.start(250); // Slice every 250ms

      // Tick interval
      this.timerInterval = setInterval(() => {
        const elapsed = (Date.now() - this.startTime) / 1000;
        if (onTick) onTick(elapsed);

        if (elapsed >= this.maxDurationSec) {
          this.stop();
        }
      }, 200);

    } catch (err) {
      this.cleanup();
      loggerError(err);
      const isDenied = err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError';
      const msg = isDenied
        ? 'माइक्रोफ़ोन की अनुमति चाहिए। कृपया ब्राउज़र सेटिंग्स में जाकर माइक्रोफ़ोन की अनुमति दें।'
        : 'माइक्रोफ़ोन शुरू करने में समस्या आई: ' + (err.message || 'अज्ञात त्रुटि');
      if (onError) onError(msg);
    }
  }

  stop() {
    if (this.mediaRecorder && this.isRecording) {
      this.isRecording = false;
      this.mediaRecorder.stop();
    }
  }

  cancel() {
    this.isRecording = false;
    this.cleanup();
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

function loggerError(e) {
  if (window.console && console.error) {
    console.error('AudioRecorder error:', e);
  }
}

window.AudioRecorder = AudioRecorder;
