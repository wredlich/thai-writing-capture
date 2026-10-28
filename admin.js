(function () {
  "use strict";

  const banner = document.getElementById("admin-banner");
  const signedOut = document.getElementById("panel-signed-out");
  const signedIn = document.getElementById("panel-signed-in");
  const form = document.getElementById("magic-form");
  const emailInput = document.getElementById("email");
  const magicStatus = document.getElementById("magic-status");
  const signedInAs = document.getElementById("signed-in-as");
  const exportStatus = document.getElementById("export-status");
  const btnExport = document.getElementById("btn-export");
  const btnSend = document.getElementById("btn-send");
  const inviteForm = document.getElementById("invite-form");
  const inviteLabel = document.getElementById("invite-label");
  const inviteStatus = document.getElementById("invite-status");
  const inviteList = document.getElementById("invite-list");
  const btnInvite = document.getElementById("btn-invite");
  const INVITE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789";
  const redirectUrl = new URL("admin.html", window.location.href).href;
  document.getElementById("redirect-url").textContent = redirectUrl;

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

  function authErrorFromUrl() {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const query = new URLSearchParams(window.location.search);
    return hash.get("error_description") || query.get("error_description") || "";
  }

  function cleanUrl() {
    const url = new URL(window.location.href);
    ["code", "error", "error_description", "error_code"].forEach((key) => {
      url.searchParams.delete(key);
    });
    url.hash = "";
    history.replaceState(null, "", url.pathname + url.search);
  }

  if (!configured() || !globalThis.supabase || !globalThis.supabase.createClient) {
    banner.hidden = false;
    banner.textContent = "Set SUPABASE_URL and SUPABASE_ANON_KEY in config.js before signing in.";
    btnSend.disabled = true;
    return;
  }

  const { url, key } = readConfig();
  const client = globalThis.supabase.createClient(url, key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      flowType: "implicit",
      storageKey: "write-echo-admin",
    },
  });

  const linkError = authErrorFromUrl();
  if (linkError) magicStatus.textContent = linkError;

  function inviteUrl(code) {
    const link = new URL("./", window.location.href);
    link.searchParams.set("invite", code);
    return link.href;
  }

  function randomCode() {
    const bytes = new Uint8Array(8);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => INVITE_ALPHABET[byte % INVITE_ALPHABET.length]).join("");
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      const input = document.createElement("input");
      input.value = text;
      document.body.appendChild(input);
      input.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (copyErr) { ok = false; }
      input.remove();
      return ok;
    }
  }

  function renderInvites(rows) {
    inviteList.replaceChildren();
    rows.forEach((row) => {
      const url = inviteUrl(row.code);
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = row.label || "Untitled";
      const code = document.createElement("code");
      code.textContent = row.code;
      const link = document.createElement("a");
      link.href = url;
      link.textContent = url;
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "ghost";
      copy.textContent = "Copy link";
      copy.addEventListener("click", async () => {
        const ok = await copyText(url);
        copy.textContent = ok ? "Copied" : "Copy link";
      });
      item.append(title, code, link, copy);
      inviteList.appendChild(item);
    });
  }

  function invitesMissing(error) {
    const code = String(error && error.code || "");
    const msg = String(error && error.message || "").toLowerCase();
    return code === "42P01" || code === "PGRST205" || msg.includes("schema cache") || msg.includes("does not exist");
  }

  async function loadInvites() {
    const { data, error } = await client
      .from("invites")
      .select("code,label,created_at")
      .order("created_at", { ascending: false });
    if (error) {
      inviteList.replaceChildren();
      inviteStatus.textContent = invitesMissing(error)
        ? "Invite codes are not set up yet. Handwriting export still works. Paste supabase/migrations/20261028_invites.sql into the Supabase SQL editor."
        : error.message;
      return;
    }
    if (!inviteStatus.textContent) inviteStatus.textContent = "";
    renderInvites(data || []);
  }

  function render(session) {
    const user = session && session.user;
    signedOut.hidden = Boolean(user);
    signedIn.hidden = !user;
    if (user) {
      signedInAs.textContent = `Signed in as ${user.email || "this account"}.`;
      loadInvites();
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    btnSend.disabled = true;
    magicStatus.textContent = "Sending…";
    const { error } = await client.auth.signInWithOtp({
      email: emailInput.value.trim(),
      options: {
        emailRedirectTo: redirectUrl,
        shouldCreateUser: true,
      },
    });
    btnSend.disabled = false;
    magicStatus.textContent = error
      ? error.message
      : "Check your email and open the link. It returns to this page.";
  });

  async function fetchAll(table) {
    const pageSize = 100;
    const rows = [];
    for (let from = 0; ; from += pageSize) {
      const { data, error } = await client
        .from(table)
        .select("*")
        .order("created_at", { ascending: true })
        .order("id", { ascending: true })
        .range(from, from + pageSize - 1);
      if (error) throw error;
      rows.push(...(data || []));
      exportStatus.textContent = `Fetched ${rows.length} ${table}…`;
      if (!data || data.length < pageSize) break;
    }
    return rows;
  }

  btnExport.addEventListener("click", async () => {
    btnExport.disabled = true;
    exportStatus.textContent = "Fetching writers…";
    try {
      const writers = await fetchAll("writers");
      exportStatus.textContent = "Fetching samples…";
      const samples = await fetchAll("samples");
      let invites = [];
      try {
        const { data, error } = await client
          .from("invites")
          .select("code,label,created_at")
          .order("created_at", { ascending: true })
          .order("code", { ascending: true });
        if (error) throw error;
        invites = data || [];
      } catch (inviteErr) {
        invites = [];
      }
      const payload = {
        exported_at: new Date().toISOString(),
        writers,
        samples,
        invites,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const stamp = payload.exported_at.replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `write-echo-export-${stamp}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      const empty = writers.length === 0 && samples.length === 0;
      exportStatus.textContent = empty
        ? "Downloaded an empty file. If people have already written, confirm this email is in the admins table."
        : `Downloaded ${writers.length} writers and ${samples.length} samples.`;
    } catch (err) {
      exportStatus.textContent = err.message || "Export failed.";
    } finally {
      btnExport.disabled = false;
    }
  });

  inviteForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const label = inviteLabel.value.trim().slice(0, 80);
    if (!label) return;
    btnInvite.disabled = true;
    inviteStatus.textContent = "Creating…";
    let created = null;
    let lastError = null;
    for (let attempt = 0; attempt < 3 && !created; attempt += 1) {
      const code = randomCode();
      const { error } = await client.from("invites").insert({ code, label });
      if (!error) created = code;
      else if (error.code !== "23505") {
        lastError = error;
        break;
      } else lastError = error;
    }
    btnInvite.disabled = false;
    if (!created) {
      inviteStatus.textContent = lastError && invitesMissing(lastError)
        ? "Invite codes are not set up yet. Paste supabase/migrations/20261028_invites.sql into the Supabase SQL editor."
        : (lastError && lastError.message) || "Could not create an invite.";
      return;
    }
    inviteLabel.value = "";
    const url = inviteUrl(created);
    const copied = await copyText(url);
    inviteStatus.textContent = copied ? "Copied the new link." : "Created. Copy the link below.";
    await loadInvites();
    inviteStatus.textContent = copied ? "Copied the new link." : "Created. Copy the link below.";
  });

  document.getElementById("btn-sign-out").addEventListener("click", async () => {
    await client.auth.signOut();
    exportStatus.textContent = "";
    render(null);
  });

  client.auth.onAuthStateChange((_event, session) => render(session));
  client.auth.getSession().then(({ data }) => {
    cleanUrl();
    render(data.session);
  });
}());
