(function () {
  "use strict";

  const KEY_SESSION = "write-echo.session.v2";
  const KEY_QUEUE = "write-echo.queue.v1";
  const KEY_DONE = "write-echo.done.v1";
  const KEY_INVITE = "write-echo.invite.v1";

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
  const promptEl = document.getElementById("prompt-text");
  const styleEl = document.getElementById("style-label");
  const listWarning = document.getElementById("list-warning");
  const padWrap = document.getElementById("pad-wrap");
  const canvas = document.getElementById("pad");
  const hint = document.getElementById("hint");
  const writeError = document.getElementById("write-error");
  const uploadCheck = document.getElementById("upload-check");
  const uploadText = document.getElementById("upload-text");
  const thanksCheck = document.getElementById("thanks-check");
  const thanksText = document.getElementById("thanks-text");
  const screenBreak = document.getElementById("screen-break");
  const screenPhone = document.getElementById("screen-phone");
  const screenInvite = document.getElementById("screen-invite");
  const breakCount = document.getElementById("break-count");
  const btnBack = document.getElementById("btn-back");
  const btnClear = document.getElementById("btn-clear");
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
  let invitesOn = false;
  let legacyColumns = false;
  let checkTimer = 0;

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

  function normalizeInvite(value) {
    const code = String(value || "").trim().toLowerCase();
    return /^[a-z0-9]{4,32}$/.test(code) ? code : "";
  }

  function readInvite() {
    try {
      return normalizeInvite(localStorage.getItem(KEY_INVITE));
    } catch (err) {
      return "";
    }
  }

  function inviteFromUrl() {
    return normalizeInvite(new URLSearchParams(location.search).get("invite"));
  }

  function captureInvite() {
    const fromUrl = inviteFromUrl();
    if (!fromUrl) return readInvite();
    try {
      localStorage.setItem(KEY_INVITE, fromUrl);
    } catch (err) { /* the URL still carries the code */ }
    return fromUrl;
  }

  // A new ?invite= cannot update the stored writer (anon is insert-only).
  // Insert a new row and keep the local done-set so the list does not restart.
  function adoptUrlInvite() {
    const urlInvite = inviteFromUrl();
    if (!urlInvite || !session || !session.writer) return;
    if (normalizeInvite(session.writer.invite_code) === urlInvite) return;
    const previous = session.writer;
    const handedness = previous.handedness;
    if (handedness !== "right" && handedness !== "left" && handedness !== "both") return;
    const nickname = String(previous.nickname || "").trim().slice(0, 80);
    if (!nickname) return;
    const writer = {
      id: crypto.randomUUID(),
      nickname,
      handedness,
      consented: true,
      device: deviceInfo(),
    };
    if (previous.age_range) writer.age_range = previous.age_range;
    if (!legacyColumns) writer.invite_code = urlInvite;
    session.writer = writer;
    if (!saveSession() || !enqueue({ kind: "writer", payload: writer })) {
      session.writer = previous;
      saveSession();
      queue = queue.filter((item) => item.payload.id !== writer.id);
      persistQueue();
    }
  }

  async function detectInvites() {
    const client = db();
    if (!client) return false;
    try {
      const { data, error } = await client.rpc("capture_invites_enabled");
      return !error && data === true;
    } catch (err) {
      return false;
    }
  }

  function withoutNewColumns(payload) {
    const next = Object.assign({}, payload);
    delete next.invite_code;
    delete next.rep;
    return next;
  }

  function isMissingColumn(error) {
    const code = String(error.code || "");
    const msg = String(error.message || "").toLowerCase();
    if (code === "42703" || code === "PGRST204") return true;
    return msg.includes("invite_code") || msg.includes("schema cache");
  }

  function isInviteRejection(error) {
    const code = String(error.code || "");
    const msg = String(error.message || "").toLowerCase();
    return code === "42501" || msg.includes("row-level security") || msg.includes("permission denied");
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

  function reveal() {
    document.documentElement.classList.remove("booting");
  }

  function clearUploadStatus() {
    clearTimeout(checkTimer);
    uploadText.textContent = "";
    thanksText.textContent = "";
    uploadCheck.hidden = true;
    thanksCheck.hidden = true;
    uploadCheck.classList.remove("fade");
    thanksCheck.classList.remove("fade");
  }

  function showUploadedCheck() {
    uploadText.textContent = "";
    thanksText.textContent = "";
    [uploadCheck, thanksCheck].forEach((el) => {
      el.hidden = false;
      el.classList.remove("fade");
      void el.getBoundingClientRect();
      el.classList.add("fade");
    });
    clearTimeout(checkTimer);
    checkTimer = setTimeout(() => {
      uploadCheck.hidden = true;
      thanksCheck.hidden = true;
    }, 1600);
  }

  function showUploadError(message) {
    clearTimeout(checkTimer);
    uploadCheck.hidden = true;
    thanksCheck.hidden = true;
    uploadCheck.classList.remove("fade");
    thanksCheck.classList.remove("fade");
    uploadText.textContent = message;
    thanksText.textContent = message;
  }

  function rejectWriter(writerId) {
    queue = queue.filter((item) => item.payload.id !== writerId && item.payload.writer_id !== writerId);
    persistQueue();
    clearUploadStatus();
    if (session && session.writer.id === writerId) {
      try { localStorage.removeItem(KEY_SESSION); } catch (err) { /* ignore */ }
      session = null;
    }
    if (!readInvite()) {
      showInvite();
      return;
    }
    showSetup();
    banner.hidden = false;
    banner.textContent = "This invite link is not recognized. Ask for a new link.";
  }

  async function flush() {
    if (flushing) {
      flushAgain = true;
      return;
    }
    flushing = true;
    let stripped = false;
    try {
      do {
        flushAgain = false;
        if (!queue.length || !configured() || !navigator.onLine || !db()) break;
        while (queue.length) {
          const item = queue[0];
          const table = item.kind === "writer" ? "writers" : "samples";
          // insert() only. Do not chain .select(): the anon role cannot read.
          const { error } = await db().from(table).insert(item.payload);
          if (error && error.code !== "23505") {
            if (!stripped && isMissingColumn(error)) {
              stripped = true;
              legacyColumns = true;
              queue.forEach((queued) => {
                queued.payload = withoutNewColumns(queued.payload);
              });
              persistQueue();
              continue;
            }
            if (item.kind === "writer" && isInviteRejection(error)) {
              rejectWriter(item.payload.id);
              return;
            }
            showUploadError(`Upload failed: ${error.message || "request failed"}`);
            return;
          }
          if (item.kind === "sample" && item.doneKey && session && item.payload.writer_id === session.writer.id) {
            rememberDone(item.doneKey);
          }
          queue.shift();
          persistQueue();
          showUploadedCheck();
        }
      } while (flushAgain);
    } catch (err) {
      showUploadError(`Upload failed: ${err.message || "network error"}`);
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
    reveal();
    screenSetup.hidden = true;
    screenWrite.hidden = true;
    screenThanks.hidden = true;
    screenBreak.hidden = true;
    screenInvite.hidden = true;
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
    flush();
  }

  function showBreak() {
    hideCapture();
    screenPhone.hidden = true;
    screenBreak.hidden = false;
    renderDone();
  }

  function showInvite() {
    hideCapture();
    screenPhone.hidden = true;
    screenInvite.hidden = false;
  }

  function showPrompt() {
    const task = taskAt(session.index);
    strokes = [];
    activeId = null;
    t0 = performance.now();
    writeError.hidden = true;
    renderDone();
    promptEl.textContent = task.prompt.text;
    promptEl.className = `prompt-text ${sizeClass(task.prompt.text)}`;
    styleEl.textContent = `${task.rep + 1} of ${repeats}`;
    styleEl.classList.remove("fast");
    btnBack.disabled = session.index <= 0;
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
    btnNext.classList.toggle("ready", hasInk);
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

  function commit() {
    writeError.hidden = true;
    const hasInk = strokes.some((stroke) => stroke.length);
    if (!hasInk) return;
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
      skipped: false,
    };
    if (!legacyColumns) sample.rep = task.rep + 1;
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

  function goBack() {
    if (!session || session.index <= 0) return;
    session.index -= 1;
    saveSession();
    showPrompt();
  }

  function refreshStart() {
    const handedness = form.querySelector('input[name="handedness"]:checked');
    btnStart.disabled = !(nicknameInput.value.trim() && handedness && consentInput.checked);
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
        consented: true,
        device: deviceInfo(),
      };
      const invite = captureInvite();
      if (!legacyColumns && invite) writer.invite_code = invite;
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
    btnBack.addEventListener("click", goBack);
    btnNext.addEventListener("click", commit);
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
    const invite = captureInvite();
    queue = loadQueue();
    done = loadDone();
    session = loadSession();
    invitesOn = await detectInvites();
    if (invitesOn && !invite && !session) {
      showInvite();
      return;
    }
    try {
      const response = await fetch("prompts.json", { cache: "no-cache" });
      if (!response.ok) throw new Error("status " + response.status);
      prompts = expandPrompts(await response.json());
    } catch (err) {
      showSetup();
      banner.hidden = false;
      banner.textContent = "Could not load the prompt list.";
      return;
    }
    if (!prompts.length) {
      showSetup();
      banner.hidden = false;
      banner.textContent = "The prompt list is empty.";
      return;
    }
    bind();
    if (!configured()) {
      banner.hidden = false;
      banner.textContent = "Uploads are off until SUPABASE_URL and SUPABASE_ANON_KEY are set in config.js. Writing still saves on this device.";
    }
    if (session) {
      adoptUrlInvite();
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
    const invite = captureInvite();
    const link = new URL(location.href);
    link.search = "";
    link.hash = "";
    if (invite) link.searchParams.set("invite", invite);
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
