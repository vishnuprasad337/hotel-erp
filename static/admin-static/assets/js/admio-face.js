/*!
 * admio-face.js  (v2 - auto capture)
 * Global `AdmioFace` with:
 *   start(video)                 open camera + load models
 *   stop(video)                  close camera + cancel auto capture
 *   autoCapture(video, opts)     scan until a good face is steady, then capture automatically
 *   capture(video)               one-shot manual capture
 *
 * Optional overrides (set BEFORE this script loads):
 *   window.ADMIO_FACE_LIB_URL, window.ADMIO_FACE_MODEL_URL
 */
(function (global) {
  'use strict';

  var VERSION = '1.7.13';
  var LIB_URL = global.ADMIO_FACE_LIB_URL ||
    'https://cdn.jsdelivr.net/npm/@vladmandic/face-api@' + VERSION + '/dist/face-api.js';
  var MODEL_URL = global.ADMIO_FACE_MODEL_URL ||
    'https://cdn.jsdelivr.net/npm/@vladmandic/face-api@' + VERSION + '/model/';

  var loadPromise = null;
  var autoToken = 0;

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src; s.async = true;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('Could not load face recognition library.')); };
      document.head.appendChild(s);
    });
  }

  function ensureLoaded() {
    if (loadPromise) return loadPromise;
    loadPromise = (async function () {
      if (!global.faceapi) await loadScript(LIB_URL);
      if (!global.faceapi) throw new Error('Face recognition library failed to initialise.');
      var nets = global.faceapi.nets;
      await Promise.all([
        nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        nets.faceRecognitionNet.loadFromUri(MODEL_URL)
      ]);
    })().catch(function (e) { loadPromise = null; throw e; });
    return loadPromise;
  }

  function detectorOptions() {
    // Lower threshold = works better with backlight / window behind the person
    return new global.faceapi.TinyFaceDetectorOptions({ inputSize: 416, scoreThreshold: 0.3 });
  }

  async function start(video) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Camera not available. Use https or localhost.');
    }
    await ensureLoaded();
    var stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      });
    } catch (e) {
      if (e && e.name === 'NotAllowedError') throw new Error('Camera permission denied. Allow camera access and try again.');
      if (e && e.name === 'NotFoundError') throw new Error('No camera found on this device.');
      throw new Error('Could not start the camera.');
    }
    video.srcObject = stream;
    await new Promise(function (resolve) {
      if (video.readyState >= 2) return resolve();
      video.onloadeddata = function () { resolve(); };
    });
    try { await video.play(); } catch (_) {}
  }

  function stop(video) {
    autoToken++; // cancels any running autoCapture loop
    if (!video) return;
    var stream = video.srcObject;
    if (stream && stream.getTracks) stream.getTracks().forEach(function (t) { t.stop(); });
    video.srcObject = null;
  }

  function frameToBlob(video) {
    return new Promise(function (resolve, reject) {
      var canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function (blob) {
        blob ? resolve(blob) : reject(new Error('Could not capture image.'));
      }, 'image/jpeg', 0.92);
    });
  }

  function area(d) { return d.box.width * d.box.height; }

  // Look at the frame and say whether it is good enough. Returns { state, message, det }
  async function analyze(video) {
    var faces = await global.faceapi.detectAllFaces(video, detectorOptions());
    if (!faces.length) {
      return { state: 'none', message: 'Looking for your face… face the light and look at the camera.' };
    }
    faces.sort(function (a, b) { return area(b) - area(a); });
    var main = faces[0];
    // Ignore small faces in the background (other people far away)
    var others = faces.slice(1).filter(function (f) { return area(f) > area(main) * 0.5; });
    if (others.length) {
      return { state: 'multi', message: 'More than one person in frame. Only one person please.' };
    }
    var b = main.box;
    if (b.width < video.videoWidth * 0.18) {
      return { state: 'small', message: 'Move closer to the camera.' };
    }
    var cx = b.x + b.width / 2, cy = b.y + b.height / 2;
    if (Math.abs(cx - video.videoWidth / 2) > video.videoWidth * 0.3 ||
        Math.abs(cy - video.videoHeight / 2) > video.videoHeight * 0.3) {
      return { state: 'off', message: 'Move to the centre of the frame.' };
    }
    return { state: 'ok', message: 'Hold still…', det: main };
  }

  // Compute descriptor + photo for the current frame (largest face)
  async function grab(video) {
    var results = await global.faceapi
      .detectAllFaces(video, detectorOptions())
      .withFaceLandmarks()
      .withFaceDescriptors();
    if (!results.length) return null;
    results.sort(function (a, b) { return area(b.detection) - area(a.detection); });
    var blob = await frameToBlob(video);
    return { ok: true, blob: blob, descriptor: Array.prototype.slice.call(results[0].descriptor) };
  }

  /**
   * Automatic capture.
   * opts: { onStatus(text), stableFrames (default 5), timeoutMs (default 30000) }
   * Resolves: { ok:true, blob, descriptor } | { ok:false, reason, timeout? } | { ok:false, cancelled:true }
   */
  async function autoCapture(video, opts) {
    opts = opts || {};
    var need = opts.stableFrames || 5;
    var timeoutMs = opts.timeoutMs || 30000;
    var onStatus = opts.onStatus || function () {};
    await ensureLoaded();

    var token = ++autoToken;
    var t0 = Date.now();
    var good = 0, last = null;

    while (token === autoToken) {
      if (Date.now() - t0 > timeoutMs) {
        return { ok: false, timeout: true, reason: 'Could not detect a clear face. Improve the lighting (do not sit with a window behind you) and try again.' };
      }
      if (!video || !video.videoWidth || video.paused) { await sleep(200); continue; }

      var res;
      try { res = await analyze(video); }
      catch (e) { await sleep(300); continue; }
      if (token !== autoToken) break;

      if (res.state !== 'ok') {
        good = 0; last = null;
        onStatus(res.message, false);
      } else {
        var b = res.det.box;
        var moved = last ? Math.hypot(b.x - last.x, b.y - last.y) > video.videoWidth * 0.06 : false;
        good = moved ? 1 : good + 1;
        last = { x: b.x, y: b.y };
        onStatus('Hold still… ' + Math.min(good, need) + '/' + need, false);

        if (good >= need) {
          onStatus('Capturing…', false);
          var out = null;
          try { out = await grab(video); } catch (e) { out = null; }
          if (token !== autoToken) break;
          if (out) return out;
          good = 0; last = null;
        }
      }
      await sleep(180);
    }
    return { ok: false, cancelled: true, reason: 'Cancelled' };
  }

  // Manual one-shot (kept for compatibility)
  async function capture(video) {
    await ensureLoaded();
    if (!video || !video.videoWidth) return { ok: false, reason: 'Camera is not ready yet.' };
    var res = await analyze(video);
    if (res.state !== 'ok') return { ok: false, reason: res.message };
    var out = await grab(video);
    return out || { ok: false, reason: 'No face detected. Face the light and look straight at the camera.' };
  }

  global.AdmioFace = { start: start, stop: stop, autoCapture: autoCapture, capture: capture };
})(window);