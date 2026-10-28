# Write Echo

Write Echo collects anonymous Thai handwriting strokes so a computer can learn to read them. The site is static. Each prompt is written twice: first in your everyday style, then fast.

The repository name stays `thai-writing-capture`. The live site is GitHub Pages:

- Writers: https://wredlich.github.io/thai-writing-capture/
- Export: https://wredlich.github.io/thai-writing-capture/admin.html

`writeecho.com` may be pointed at this GitHub Pages site later. This repo does not set a custom domain and has no CNAME file. Add that only when you are ready to attach the domain.

## What you need to do

### 1. Create a Supabase project

Open [supabase.com/dashboard](https://supabase.com/dashboard) and sign in with GitHub. Create a project on the free tier and wait until it finishes provisioning.

### 2. Run the schema

In the Supabase dashboard open **SQL Editor → New query**, paste the whole of `supabase/schema.sql`, and run it. The script is idempotent: tables and indexes use `if not exists`, and policies are dropped before they are created, so pasting it again is safe.

It creates `writers`, `samples`, and `admins`. Strokes are a `jsonb` column. There is no storage bucket. The anon role can insert and cannot read. A signed-in user can read `writers` and `samples` only when `admins.email` equals the email on their token.

### 3. Add your email as an admin

The last line of `supabase/schema.sql` is:

```sql
insert into public.admins(email) values ('REPLACE_WITH_YOUR_EMAIL') on conflict do nothing;
```

Change `REPLACE_WITH_YOUR_EMAIL` to your real email before you run the script. The export policy compares that value to the email in the magic-link token with no case change, so it must be the same address you type on the export page. If you already ran the script with the placeholder, run the insert again with your real email.

### 4. Allow the magic-link redirect

Open **Authentication → URL Configuration**.

- Site URL: `https://wredlich.github.io/thai-writing-capture`
- Redirect URLs, add:
  - `https://wredlich.github.io/thai-writing-capture/admin.html`
  - `http://localhost:8000/admin.html` if you try the export page on your own machine

Email sign-in is on by default. If the message never arrives, check **Authentication → Providers → Email** and look in spam. The built-in mailer only sends a few messages an hour.

### 5. Public API values

`config.js` already has this project's URL (`https://iicbhwkehchwmqrlrflb.supabase.co`) and its anon public key. That key is the new-style publishable key. `supabase-js` v2 takes it as the second argument to `createClient`.

The publishable key is safe to be public **only because of row level security**. Anon can insert writers and samples. It cannot select, update, or delete. The capture page sends `writers.id` and `samples.id` from `crypto.randomUUID()`, sets `consented` to true, and calls `.insert()` with no `.select()` after it, because anon cannot read the row back. `handedness` is `right`, `left`, or `both`. `style` is `everyday` or `fast`. Export signs in with an email magic link and then reads `writers` and `samples`.

Do not put any other Supabase key in `config.js`, this repository, or the browser. If you rotate the publishable key, replace `SUPABASE_ANON_KEY` and push to `main`.

### 6. Turn on GitHub Pages

On GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

`.github/workflows/pages.yml` deploys every push to `main`. If GitHub asks you to approve the first Actions run, open the **Actions** tab and approve it.

After you change `config.js`, hard-refresh the site if the old placeholder is still showing.

### 7. Open the site

Writers use https://wredlich.github.io/thai-writing-capture/

You export from https://wredlich.github.io/thai-writing-capture/admin.html — enter your admin email, open the magic link, then download JSON. The first sign-in creates the auth user. The `admins` table is what allows the download. An empty file means either nobody has written yet, or that email is not in `admins`.

## How a session works

The start screen asks for a nickname, handedness (right, left, or both), an age range, and this consent line: “I agree my anonymous handwriting strokes may be used to train a handwriting recognition model.”

`prompts.json` has 300 prompts. Each is shown twice, so the progress counter runs to 600 (for example `37 / 600`). Order is consonants, vowel signs (with อ where a carrier is needed), tone marks, ์ ๆ ฯ, Thai and Arabic digits, then common words. Words cover vowels above, below, leading, trailing, and surrounding the consonant, including stacked vowel and tone marks such as กิน เพื่อน เที่ยว ไม่ น้ำ ใคร ก๋วยเตี๋ยว.

Clear wipes the current canvas. Next saves it. Skip saves the item as skipped. The writer id and the prompt index are kept in localStorage, and samples that have not uploaded yet stay queued there and retry when the device is online.

A sample’s `strokes` field is `[[{x, y, t, pressure, pointerType}, ...], ...]`. `x` and `y` are CSS pixels from the top-left of the canvas. `t` is milliseconds since the prompt was shown.

## Replacing the prompt list

`prompts.json` is an array of `{ "id", "text", "kind" }`. `kind` is `consonant`, `vowel`, `tone`, `mark`, `digit`, or `word`. The page uses whatever length it finds. Do not reorder the file after someone has started; resume progress is an index into the array.

`scripts/check_prompts.py` guards the shipped list (44 consonants in order, both digit sets, and the vowel-position words). Update that script if you intentionally replace the list, or the Pages workflow will fail.

`scripts/build_prompts.py` regenerates the current 300-item file.

## Local preview

```bash
python3 -m http.server 8000
```

Open http://localhost:8000/ . Uploads stay queued until `config.js` has real values.

Noto Sans Thai is included under the SIL Open Font License (`fonts/OFL.txt`).
