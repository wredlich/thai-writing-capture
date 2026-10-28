(function () {
  "use strict";

  const KEY_SESSION = "write-echo.session.v2";
  const KEY_QUEUE = "write-echo.queue.v1";
  const KEY_DONE = "write-echo.done.v1";
  const KIND_LABEL = {
    consonant: "พยัญชนะ · consonant",
    vowel: "สระ · vowel",
    tone: "วรรณยุกต์ · tone mark",
    mark: "เครื่องหมาย · mark",
    digit: "ตัวเลข · digit",
    word: "คำ · word",
  };

  const screenSetup = document.getElementById("screen-setup");
  const screenWrite = document.getElementById("screen-write");
  const screenThanks = document.getElementById("screen-thanks");
  const form = document.getElementById("start-form");
  const nicknameInput = document.getElementById("nickname");
  const consentInput = document.getElementById("consent");
  const btnStart = document.getElementById("btn-start");
  const banner = document.getElementById("config-banner");
  const progressEl = document.getElementById("progress");
  const whoEl = document.getElementById("who");
  const kindEl = document.getElementById("kind-label");
  const promptEl = document.getElementById("prompt-text");
  const styleEl = document.getElementById("style-label");
  const styleHelp = document.getElementById("style-help");
  const listWarning = document.getElementById("list-warning");
  const padWrap = document.getElementById("pad-wrap");
  const canvas = document.getElementById("pad");
  const hint = document.getElementById("hint");
  const writeError = document.getElementById("write-error");
  const uploadStatus = document.getElementById("upload-status");
  const thanksStatus = document.getElementById("thanks-status");
  const screenBreak = document.getElementById("screen-break");
  const screenPhone = document.getElementById("screen-phone");
  const breakCount = document.getElementById("break-count");
  const btnClear = document.getElementById("btn-clear");
  const btnSkip = document.getElementById("btn-skip");
  const btnNext = document.getElementById("btn-next");
  const ctx = canvas.getContext("2d");

  let prompts = [];
  let repeats = 3;
  let done = new Set();
  let session = null;
  let queue = [];
  let strokes = [];
  let t0 = 0;
  let activeId = null;
  let activeType = null;
  let bitmapW = 0;
  let bitmapH = 0;
  let flushing = false;
  let flushAgain = false;
  let dbClient = null;

  function readConfig() {
    const cfg = window.THAI_WRITING_CONFIG || {};
    return {
      url: String(cfg.SUPABASE_URL || "").trim(),
      key: String(cfg.SUPABASE_ANON_KEY || "").trim(),
    };
  }

  function configured() {
    const { url, key } = readConfig();
    if (!url || !key) return false;
    if (url.includes("YOUR_PROJECT") || key.includes("YOUR_SUPABASE")) return false;
    if (!url.startsWith("https://") || key.length < 20) return false;
    return true;
  }

  function db() {
    if (!configured() || !globalThis.supabase || !globalThis.supabase.createClient) return null;
    if (!dbClient) {
      const { url, key } = readConfig();
      dbClient = globalThis.supabase.createClient(url, key, {
        auth: {
          persistSession: false,
          autoRefreshToken: false,
          detectSessionInUrl: false,
        },
      });
    }
    return dbClient;
  }

  function loadQueue() {
    try {
      const raw = localStorage.getItem(KEY_QUEUE);
      const data = raw ? JSON.parse(raw) : [];
      return Array.isArray(data) ? data : [];
    } catch (err) {
      return [];
    }
  }

  function persistQueue() {
    try {
      localStorage.setItem(KEY_QUEUE, JSON.stringify(queue));
      return true;
    } catch (err) {
      return false;
    }
  }

  function enqueue(item) {
    queue.push(item);
    if (!persistQueue()) {
      queue.pop();
      return false;
    }
    return true;
  }

  function loadDone() {
    try {
      const raw = localStorage.getItem(KEY_DONE);
      const data = raw ? JSON.parse(raw) : [];
      return new Set(Array.isArray(data) ? data.filter((key) => typeof key === "string") : []);
    } catch (err) {
      return new Set();
    }
  }

  function saveDone() {
    try {
      localStorage.setItem(KEY_DONE, JSON.stringify(Array.from(done)));
      return true;
    } catch (err) {
      return false;
    }
  }

  function rememberDone(key) {
    if (!key || done.has(key)) return;
    done.add(key);
    saveDone();
    renderDone();
  }

  function loadSession() {
    try {
      const raw = localStorage.getItem(KEY_SESSION);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || !data.writer || !data.writer.id) return null;
      if (!Number.isInteger(data.index) || data.index < 0) data.index = 0;
      return data;
    } catch (err) {
      return null;
    }
  }

  function saveSession() {
    try {
      localStorage.setItem(KEY_SESSION, JSON.stringify({
        writer: session.writer,
        index: session.index,
        promptCount: prompts.length,
      }));
      return true;
    } catch (err) {
      return false;
    }
  }

  function isPhone() {
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    const shortSide = Math.min(window.screen.width || 0, window.screen.height || 0);
    return coarse && shortSide <= 500;
  }

  function deviceInfo() {
    return {
      screen_w: Math.round(window.screen.width || 0),
      screen_h: Math.round(window.screen.height || 0),
      dpr: window.devicePixelRatio || 1,
      user_agent: (navigator.userAgent || "unknown").slice(0, 1000),
    };
  }

  function setStatus(text) {
    uploadStatus.textContent = text;
    if (!screenThanks.hidden) thanksStatus.textContent = text;
  }

  function statusFromQueue(note) {
    const pending = queue.length;
    if (!configured()) {
      return pending
        ? `Saved on this device (${pending} waiting). Add the anon key in config.js to upload.`
        : "Saved on this device. Add the anon key in config.js to upload.";
    }
    if (!globalThis.supabase) {
      return "Upload library did not load. Samples stay on this device.";
    }
    if (note) return note;
    if (!pending) return "Uploaded";
    if (!navigator.onLine) return `Offline. ${pending} waiting to upload.`;
    return `${pending} waiting to upload`;
  }

  async function flush() {
    if (flushing) {
      flushAgain = true;
      return;
    }
    flushing = true;
    try {
      do {
        flushAgain = false;
        if (!queue.length) {
          setStatus(statusFromQueue());
          break;
        }
        if (!configured() || !navigator.onLine || !db()) {
          setStatus(statusFromQueue());
          break;
        }
        setStatus("Uploading…");
        while (queue.length) {
          const item = queue[0];
          const table = item.kind === "writer" ? "writers" : "samples";
          // insert() only. Do not chain .select(): the anon role cannot read.
          const { error } = await db().from(table).insert(item.payload);
          if (error && error.code !== "23505") {
            setStatus(`Upload paused: ${error.message || "request failed"}`);
            return;
          }
          if (item.kind === "sample" && item.doneKey && session && item.payload.writer_id === session.writer.id) {
            rememberDone(item.doneKey);
          }
          queue.shift();
          persistQueue();
        }
        setStatus(statusFromQueue());
      } while (flushAgain);
    } catch (err) {
      setStatus(`Upload paused: ${err.message || "network error"}`);
    } finally {
      flushing = false;
    }
  }

  function totalSteps() {
    return prompts.length * repeats;
  }

  function taskAt(index) {
    return {
      prompt: prompts[Math.floor(index / repeats)],
      rep: index % repeats,
      style: "everyday",
    };
  }

  function stepKey(index) {
    const task = taskAt(index);
    return `${task.prompt.id}#${task.rep + 1}`;
  }

  function doneCount() {
    let count = 0;
    for (let i = 0; i < totalSteps(); i += 1) {
      if (done.has(stepKey(i))) count += 1;
    }
    return count;
  }

  function firstUndone() {
    for (let i = 0; i < totalSteps(); i += 1) {
      if (!done.has(stepKey(i))) return i;
    }
    return totalSteps();
  }

  function renderDone() {
    const text = `${doneCount()} of ${totalSteps()} done`;
    progressEl.textContent = text;
    if (breakCount) breakCount.textContent = text;
  }

  function sizeClass(text) {
    const n = Array.from(text).length;
    if (n <= 2) return "size-xl";
    if (n <= 4) return "size-lg";
    if (n <= 8) return "size-md";
    if (n <= 14) return "size-sm";
    return "size-xs";
  }

  function hideCapture() {
    screenSetup.hidden = true;
    screenWrite.hidden = true;
    screenThanks.hidden = true;
    screenBreak.hidden = true;
    document.body.classList.remove("writing");
  }

  function showSetup() {
    hideCapture();
    screenPhone.hidden = true;
    screenSetup.hidden = false;
  }

  function showWrite() {
    hideCapture();
    screenPhone.hidden = true;
    screenWrite.hidden = false;
    document.body.classList.add("writing");
    whoEl.textContent = session.writer.nickname;
    listWarning.hidden = !(session.promptCount && session.promptCount !== prompts.length);
    showPrompt();
    requestAnimationFrame(resize);
  }

  function showThanks() {
    hideCapture();
    screenPhone.hidden = true;
    screenThanks.hidden = false;
    setStatus(statusFromQueue());
    flush();
  }

  function showBreak() {
    hideCapture();
    screenPhone.hidden = true;
    screenBreak.hidden = false;
    renderDone();
  }

  function showPrompt() {
    const task = taskAt(session.index);
    strokes = [];
    activeId = null;
    t0 = performance.now();
    writeError.hidden = true;
    renderDone();
    kindEl.textContent = KIND_LABEL[task.prompt.kind] || task.prompt.kind;
    promptEl.textContent = task.prompt.text;
    promptEl.className = `prompt-text ${sizeClass(task.prompt.text)}`;
    styleEl.textContent = `${task.rep + 1} of ${repeats}`;
    styleEl.classList.remove("fast");
    styleHelp.textContent = "เขียนแบบที่คุณเขียนปกติ";
    redraw();
  }

  function showWriteError(message) {
    writeError.hidden = false;
    writeError.textContent = message;
  }

  function inkWidth(point) {
    const pressure = point.pressure > 0 ? Math.min(point.pressure, 1) : 0.5;
    return 1.5 * (1.5 + pressure * 2.6);
  }

  function paint(points) {
    if (!points.length) return;
    if (points.length === 1) {
      ctx.beginPath();
      ctx.arc(points[0].x, points[0].y, inkWidth(points[0]) / 2, 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    for (let i = 1; i < points.length; i += 1) {
      ctx.beginPath();
      ctx.moveTo(points[i - 1].x, points[i - 1].y);
      ctx.lineTo(points[i].x, points[i].y);
      ctx.lineWidth = inkWidth(points[i]);
      ctx.stroke();
    }
  }

  function redraw() {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || canvas.width / dpr;
    const h = canvas.clientHeight || canvas.height / dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#FFFFFF";
    ctx.fillStyle = "#FFFFFF";
    strokes.forEach(paint);
    const hasInk = strokes.some((stroke) => stroke.length);
    hint.hidden = hasInk;
    btnClear.disabled = !hasInk;
    btnNext.disabled = !hasInk;
  }

  function resize() {
    if (screenWrite.hidden) return;
    const rect = padWrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const bw = Math.max(1, Math.round(rect.width * dpr));
    const bh = Math.max(1, Math.round(rect.height * dpr));
    if (bw === bitmapW && bh === bitmapH) {
      redraw();
      return;
    }
    bitmapW = bw;
    bitmapH = bh;
    canvas.width = bw;
    canvas.height = bh;
    redraw();
  }

  function addPoint(event) {
    const stroke = strokes[strokes.length - 1];
    if (!stroke) return;
    const rect = canvas.getBoundingClientRect();
    const point = {
      x: Math.round((event.clientX - rect.left) * 100) / 100,
      y: Math.round((event.clientY - rect.top) * 100) / 100,
      t: Math.max(0, Math.round(event.timeStamp - t0)),
      pressure: Number.isFinite(event.pressure) ? Math.round(event.pressure * 1000) / 1000 : 0,
      pointerType: String(event.pointerType || "mouse").slice(0, 32),
    };
    const prev = stroke[stroke.length - 1];
    if (prev && Math.abs(prev.x - point.x) < 0.2 && Math.abs(prev.y - point.y) < 0.2) return;
    stroke.push(point);
  }

  function endStroke(event, includePoint) {
    if (event.pointerId !== activeId) return;
    if (includePoint) addPoint(event);
    activeId = null;
    activeType = null;
    const last = strokes[strokes.length - 1];
    if (last && last.length === 0) strokes.pop();
    redraw();
  }

  function onPointerDown(event) {
    if (activeId !== null) {
      if (event.pointerType === "pen" && activeType === "touch") {
        strokes.pop();
        activeId = null;
      } else {
        return;
      }
    }
    event.preventDefault();
    try { canvas.setPointerCapture(event.pointerId); } catch (err) { /* ignore */ }
    activeId = event.pointerId;
    activeType = event.pointerType || "mouse";
    strokes.push([]);
    addPoint(event);
    redraw();
  }

  function onPointerMove(event) {
    if (event.pointerId !== activeId) return;
    event.preventDefault();
    const list = typeof event.getCoalescedEvents === "function" ? event.getCoalescedEvents() : [event];
    list.forEach(addPoint);
    redraw();
  }

  function commit(skipped) {
    writeError.hidden = true;
    const hasInk = strokes.some((stroke) => stroke.length);
    if (!skipped && !hasInk) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) {
      showWriteError("The writing area is not ready yet.");
      return;
    }
    const task = taskAt(session.index);
    if (task.style !== "everyday" && task.style !== "fast") return;
    const sample = {
      id: crypto.randomUUID(),
      writer_id: session.writer.id,
      prompt_id: task.prompt.id,
      prompt_text: task.prompt.text,
      style: task.style,
      strokes: strokes.map((stroke) => stroke.map((point) => ({
        x: point.x,
        y: point.y,
        t: point.t,
        pressure: point.pressure,
        pointerType: point.pointerType,
      }))),
      canvas_w: Math.round(rect.width),
      canvas_h: Math.round(rect.height),
      dpr: window.devicePixelRatio || 1,
      screen_w: Math.max(1, Math.round(window.screen.width || 1)),
      screen_h: Math.max(1, Math.round(window.screen.height || 1)),
      user_agent: (navigator.userAgent || "unknown").slice(0, 1000),
      skipped: Boolean(skipped),
    };
    const doneKey = stepKey(session.index);
    if (!flushing) {
      queue = queue.filter((item) => !(
        item.kind === "sample" &&
        item.doneKey === doneKey &&
        item.payload.writer_id === session.writer.id
      ));
      persistQueue();
    }
    if (!enqueue({ kind: "sample", payload: sample, doneKey })) {
      showWriteError("This device is out of storage. Stay online so saved writing can upload, then try again.");
      return;
    }
    session.index += 1;
    saveSession();
    flush();
    if (session.index >= totalSteps()) showThanks();
    else showPrompt();
  }

  function startOver() {
    const ok = window.confirm("Start over as a new writer? Samples already saved on this device will still upload.");
    if (!ok) return;
    localStorage.removeItem(KEY_SESSION);
    localStorage.removeItem(KEY_DONE);
    done = new Set();
    session = null;
    strokes = [];
    showSetup();
  }

  function refreshStart() {
    const handedness = form.querySelector('input[name="handedness"]:checked');
    const age = form.querySelector('input[name="age_range"]:checked');
    btnStart.disabled = !(nicknameInput.value.trim() && handedness && age && consentInput.checked);
  }

  function bind() {
    form.addEventListener("input", refreshStart);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      refreshStart();
      if (btnStart.disabled) return;
      const handedness = form.querySelector('input[name="handedness"]:checked').value;
      if (handedness !== "right" && handedness !== "left" && handedness !== "both") return;
      const writer = {
        id: crypto.randomUUID(),
        nickname: nicknameInput.value.trim().slice(0, 80),
        handedness,
        age_range: form.querySelector('input[name="age_range"]:checked').value,
        consented: true,
        device: deviceInfo(),
      };
      session = { writer, index: 0, promptCount: prompts.length };
      if (!saveSession() || !enqueue({ kind: "writer", payload: writer })) {
        localStorage.removeItem(KEY_SESSION);
        session = null;
        queue = queue.filter((item) => item.payload.id !== writer.id);
        persistQueue();
        banner.hidden = false;
        banner.textContent = "This browser could not store the session. Free some space and try again.";
        return;
      }
      flush();
      showWrite();
    });

    btnClear.addEventListener("click", () => {
      strokes = [];
      t0 = performance.now();
      redraw();
    });
    btnSkip.addEventListener("click", () => commit(true));
    btnNext.addEventListener("click", () => commit(false));
    document.getElementById("btn-restart").addEventListener("click", startOver);
    document.getElementById("btn-again").addEventListener("click", startOver);
    document.getElementById("btn-break").addEventListener("click", showBreak);
    document.getElementById("btn-continue").addEventListener("click", () => {
      if (!session) return;
      if (session.index >= totalSteps()) showThanks();
      else showWrite();
    });

    canvas.addEventListener("pointerdown", onPointerDown, { passive: false });
    canvas.addEventListener("pointermove", onPointerMove, { passive: false });
    canvas.addEventListener("pointerup", (event) => endStroke(event, true), { passive: false });
    canvas.addEventListener("pointercancel", (event) => endStroke(event, true), { passive: false });
    canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    padWrap.addEventListener("touchmove", (event) => event.preventDefault(), { passive: false });

    const observer = new ResizeObserver(() => resize());
    observer.observe(padWrap);
    window.addEventListener("online", flush);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") flush();
    });
    setInterval(flush, 15000);
  }

  function expandPrompts(data) {
    if (!data || typeof data !== "object" || Array.isArray(data) || data.repeats !== 3) {
      throw new Error("bad prompt file");
    }
    const groups = [
      ["consonants", "consonant"],
      ["vowels", "vowel"],
      ["tones", "tone"],
      ["words", "word"],
    ];
    const items = [];
    groups.forEach(([key, kind]) => {
      const list = data[key];
      if (!Array.isArray(list)) throw new Error(key);
      list.forEach((text, index) => {
        if (typeof text !== "string" || !text.trim()) throw new Error(key);
        const value = text.trim();
        const id = kind === "word"
          ? `word-${String(index + 1).padStart(2, "0")}`
          : `${kind}-${Array.from(value).map((ch) => ch.codePointAt(0).toString(16).padStart(4, "0")).join("-")}`;
        items.push({ id, text: value, kind });
      });
    });
    return items;
  }

  async function init() {
    try {
      const response = await fetch("prompts.json", { cache: "no-cache" });
      if (!response.ok) throw new Error("status " + response.status);
      prompts = expandPrompts(await response.json());
    } catch (err) {
      banner.hidden = false;
      banner.textContent = "Could not load the prompt list.";
      return;
    }
    if (!prompts.length) {
      banner.hidden = false;
      banner.textContent = "The prompt list is empty.";
      return;
    }
    queue = loadQueue();
    done = loadDone();
    session = loadSession();
    bind();
    if (!configured()) {
      banner.hidden = false;
      banner.textContent = "Uploads are off until SUPABASE_URL and SUPABASE_ANON_KEY are set in config.js. Writing still saves on this device.";
    }
    if (session) {
      session.index = firstUndone();
      saveSession();
    }
    if (session && session.index >= totalSteps()) showThanks();
    else if (session) showWrite();
    else showSetup();
    flush();
  }

  function showPhoneGate() {
    hideCapture();
    screenPhone.hidden = false;
    const link = new URL(location.href);
    link.search = "";
    link.hash = "";
    const holder = document.getElementById("phone-qr");
    if (!holder || holder.childElementCount || typeof qrcode !== "function") return;
    const code = qrcode(0, "M");
    code.addData(link.toString());
    code.make();
    holder.innerHTML = code.createSvgTag({
      cellSize: 4,
      margin: 8,
      scalable: true,
      alt: "QR code for this page",
      title: "Open on your phone",
    });
  }

  if (!isPhone()) showPhoneGate();
  else init();
}());
