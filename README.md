# Write Echo

Write Echo collects anonymous Thai handwriting strokes so a computer can learn to read them. The site is static. Each prompt is written three times, in the writer's everyday style. Prompts are shown in one looped serif Thai font.

The repository name stays `thai-writing-capture`. The live site is GitHub Pages:

- Writers: https://wredlich.github.io/thai-writing-capture/
- Export: https://wredlich.github.io/thai-writing-capture/admin.html

`writeecho.com` may be pointed at this GitHub Pages site later. This repo does not set a custom domain and has no CNAME file. Add that only when you are ready to attach the domain.

## What you need to do

### 1. Create a Supabase project

Open [supabase.com/dashboard](https://supabase.com/dashboard) and sign in with GitHub. Create a project on the free tier and wait until it finishes provisioning.

### 2. Run the schema

In the Supabase dashboard open **SQL Editor → New query**, paste the whole of `supabase/schema.sql`, and run it. The script is idempotent: tables and indexes use `if not exists`, and policies are dropped before they are created, so pasting it again is safe.

It creates `writers`, `samples`, `admins`, and `invites`. Strokes are a `jsonb` column. There is no storage bucket. The anon role can insert writers and samples and cannot read. A signed-in user can read `writers` and `samples` only when `admins.email` equals the email on their token.

The live project already has the base tables. Do not paste `schema.sql` into it again. Paste `supabase/migrations/20261028_invites.sql` instead. Until that migration has been run, the capture page keeps the previous behavior and does not require an invite. After it has been run, a new writer is stored only when their invite code exists.

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

The publishable key is safe to be public **only because of row level security**. Anon can insert writers and samples. It cannot select, update, or delete. The capture page sends `writers.id` and `samples.id` from `crypto.randomUUID()`, sets `consented` to true, and calls `.insert()` with no `.select()` after it, because anon cannot read the row back. `handedness` is `right`, `left`, or `both`. This test set sends `style` `everyday` for every sample. The database still accepts `fast`, but the page does not ask for a fast copy. Export signs in with an email magic link and then reads `writers` and `samples`.

Do not put any other Supabase key in `config.js`, this repository, or the browser. If you rotate the publishable key, replace `SUPABASE_ANON_KEY` and push to `main`.

### 6. Turn on GitHub Pages

On GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

`.github/workflows/pages.yml` deploys every push to `main`. If GitHub asks you to approve the first Actions run, open the **Actions** tab and approve it.

After you change `config.js`, hard-refresh the site if the old placeholder is still showing.

### 7. Open the site

Writers use https://wredlich.github.io/thai-writing-capture/

You export from https://wredlich.github.io/thai-writing-capture/admin.html — enter your admin email, open the magic link, then download JSON. The first sign-in creates the auth user. The `admins` table is what allows the download. An empty file means either nobody has written yet, or that email is not in `admins`.

## How a session works

The start screen asks for a nickname, handedness (right, left, or both), and this consent line: “I agree my anonymous handwriting strokes may be used to train a handwriting recognition model.”

`prompts.json` is the whole prompt list. It has the common consonants, the main vowel forms on อ, the four tone marks on อ, and ten short words. Each prompt is asked three times, so the progress counter runs to 183 (for example `4 of 183 done`). There are no Thai numerals and no second font or fast copy.

Back, Clear, and Next sit on one row under the writing box. Next stays disabled until there is ink. Clear wipes the current canvas. Back returns to the previous prompt; writing it again inserts a new sample. Rows are not updated. A successful upload shows a checkmark that fades out. Text appears only when an upload fails.

The writer id and the finished prompts are kept in localStorage on this phone. Samples that have not uploaded yet stay queued there and retry when the device is online. There is no control for starting over as a new writer.

A sample’s `strokes` field is `[[{x, y, t, pressure, pointerType}, ...], ...]`. `x` and `y` are CSS pixels from the top-left of the canvas. `t` is milliseconds since the prompt was shown.

## Replacing the prompt list

Edit `prompts.json` directly. It has `repeats`, then arrays named `consonants`, `vowels`, `tones`, and `words`. The ten words are the `words` array. Do not reorder the file after someone has started; resume progress is an index into that order, with each entry repeated three times.

`scripts/check_prompts.py` guards the shipped list. Update that script if you intentionally replace it, or the Pages workflow will fail.

## Local preview

```bash
python3 -m http.server 8000
```

Open http://localhost:8000/ . Uploads stay queued until `config.js` has real values.

Noto Serif Thai is included under the SIL Open Font License (`fonts/OFL.txt`).

## Invite links

After `supabase/migrations/20261028_invites.sql` has been run, each helper needs a personal link such as `https://wredlich.github.io/thai-writing-capture/?invite=CODE`. The capture page reads `invite` from the URL and remembers it on that phone. Without a code, a phone sees “You need an invite link” and does not show the writing form. A desktop still shows the phone screen, and its QR code includes the invite when the page was opened with one.

On the admin page, a signed-in admin types a label, creates an 8-character code, and copies the link. The page lists the codes already created. The anon key cannot read the invite table. A database function checks the code during insert.

The download JSON includes `writers`, `samples`, and `invites`. Each new sample also stores its repetition in `rep` (1, 2, or 3). Screen width, screen height, device pixel ratio, and user agent are stored as before: on `writers.device` at signup, and on each sample along with the canvas size.

## Review an export

The review tool reads that JSON file on your own machine. It does not connect to Supabase and it does not use a service key.

```bash
python3 -m scripts.review write-echo-export.json -o review
```

Open `review/index.html`. The index lists writers to drop: anyone with at least 3 kept samples who is flagged on half or more of them. Each prompt has its own page under `review/prompts/`, with a thumbnail of every sample. Flagged samples have a red border. Samples are grouped and labelled by the invite’s label (`No invite` when the writer has no code).

For each writer, prompt, and repetition, only the newest sample counts. An older rewrite stays on the prompt page, dimmed, and is left out of the score. Samples saved before `rep` existed are numbered in time order.

A sample can be flagged for any of these:

- Near-empty: fewer than 8 points, or a very short path.
- Scribble or overfill: the path is longer than 6 canvas diagonals, or many strokes run across the box.
- Too fast: under 180 ms, or faster than 2.2 CSS pixels per millisecond.
- Too slow: longer than 30 seconds.
- Abnormal stroke count: far from the other samples of that same prompt.
- Outlier: the resampled trajectory sits far from other writers on that prompt.
