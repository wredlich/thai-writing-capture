// config.js
//
// This project's Supabase URL and anon public key (the new-style publishable
// key). supabase-js v2 createClient accepts that key as its second argument.
//
// The publishable key is public by design. It is safe to commit only because
// supabase/schema.sql lets the anon role INSERT into writers and samples
// and nothing else. Do not put any other Supabase key in this file, this
// repo, or the browser.

window.THAI_WRITING_CONFIG = {
  SUPABASE_URL: "https://iicbhwkehchwmqrlrflb.supabase.co",
  SUPABASE_ANON_KEY: "sb_publishable_NmHRQF4EfhClCDAJp_fmvw_kWog-dou",
};
