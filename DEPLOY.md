# Deploying PrepHero across your devices

Goal: one ladder, reachable from your laptop and your phone, that only you can open, with your Anthropic key never sitting on any device.

This takes about fifteen minutes and costs nothing — everything below is inside Cloudflare's free tier.

## What you end up with

| | |
| --- | --- |
| **Who can open it** | Only email addresses you list. Cloudflare Access checks before the page is ever served. |
| **Where the key lives** | A deployment secret. It is never sent to a browser — sessions call your own `/api/claude`, which adds the key server-side. |
| **Where progress lives** | Cloudflare KV, keyed by your email. Every device pulls it on load and pushes as you practise. |
| **Login** | Your email plus a one-time code Cloudflare mails you. No password for you to manage or lose. |

The in-app profile lock screen disappears in this mode — Access has already proved who you are, so a second password would be theatre.

## Before you start

- A Cloudflare account (free).
- Your Anthropic API key.
- The folder: `index.html`, `functions/`, `README.md`. The `tests/` folder is harmless to deploy but pointless — you can leave it out.

---

## 1. Deploy the site

**Connect a Git repository. Do not drag the folder in.**

This app is not purely static — `functions/` is what holds your API key and syncs your season. Dashboard drag-and-drop does not compile Functions:

- The **Create a Worker → Upload and deploy** flow rejects them outright with *"Pages functions are not supported."*
- Even the Pages uploader is for static assets. The two paths that build Functions are **Git integration** and **Wrangler** (`npx wrangler pages deploy`, which needs Node).

Git integration needs nothing installed locally, so use that.

**Dashboard → Workers & Pages → Create → Pages → Connect to Git**, pick your repository, then:

| Setting | Value |
| --- | --- |
| Framework preset | None |
| Build command | *(leave empty)* |
| Build output directory | `/` |

Save and deploy. You get `https://<project>.pages.dev`.

Check it worked: open `https://<project>.pages.dev/api/me`. A **503 saying the deployment is not protected** is the correct answer at this stage — the API fails closed until Access is configured. A **404** means Functions did not build, and you are back on the drag-and-drop path.

> Never drag the project folder into an uploader. It includes `.git/`, which would publish your entire repository history at your site's URL, and `tests/.build/`, which is megabytes of generated junk. Git integration avoids both — `.gitignore` already excludes them.

## 2. Create the KV namespace

**Workers & Pages → KV → Create a namespace**, call it `prephero-seasons`.

Then **your Pages project → Settings → Bindings → Add → KV namespace**:

| Variable name | Value |
| --- | --- |
| `PREPHERO` | `prephero-seasons` |

The variable name must be exactly `PREPHERO` — that is what `functions/api/state.js` reads.

## 3. Add your API key as a secret

**Settings → Variables and Secrets → Add**, and make sure you choose **Secret**, not plaintext:

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | `sk-ant-...` |

Add it for **Production** (and Preview too, if you plan to use preview URLs).

## 4. Put Access in front of it

**Zero Trust → Access → Applications → Add an application → Self-hosted.**

- **Application name:** PrepHero
- **Session duration:** whatever you like — 1 month means you rarely re-authenticate
- **Domain:** `prephero.pages.dev` (your hostname, no path)

Then add a policy:

- **Name:** Me
- **Action:** Allow
- **Include:** *Emails* → your email address

Leave the login method as **One-time PIN**. Cloudflare emails you a code; there is no password anywhere in this system.

## 5. Tell the Functions about Access

This is the step that is easy to skip and important not to. The middleware verifies Access's signature on every API call, and it needs two values to do that.

From **Zero Trust → Settings → Custom Pages** (or the team domain shown in the top-left of Zero Trust) get your team domain, e.g. `yourteam.cloudflareaccess.com`.

From the Access application you just made → **Overview**, copy the **Application Audience (AUD) Tag**.

Back in **Pages → Settings → Variables and Secrets**, add both as plaintext variables:

| Name | Value |
| --- | --- |
| `ACCESS_TEAM_DOMAIN` | `yourteam.cloudflareaccess.com` |
| `ACCESS_AUD` | the AUD tag |

**Redeploy** after adding variables — Pages only picks them up on a new deployment. (*Deployments → ⋯ → Retry deployment* is enough.)

## 6. Use it

Open `https://prephero.pages.dev` on any device. Cloudflare asks for your email, mails you a code, and then the app loads straight into the dashboard — no lock screen, your email in the top-right, and a **Synced** chip next to it.

Do a session on your laptop, open your phone, and the points are there.

---

## Checking it works

| Symptom | Cause |
| --- | --- |
| Lock screen asking you to create a profile | The app did not detect hosted mode: `/api/me` is not returning 200. Usually the variables are missing or you have not redeployed since adding them. |
| Chip says **No sync store** | The `PREPHERO` KV binding is missing or misnamed. |
| Sessions still say *Offline bank* | `ANTHROPIC_API_KEY` is not set, or was added as plaintext to the wrong environment. |
| Chip says **Sync failed** | Hover it for the error. A 503 means the KV binding; a 403 means the Access AUD does not match the application. |
| Everyone can open the URL | The Access application's domain does not match your hostname. The API still refuses to work, so your key is safe, but fix the policy. |

Anthropic's own **spend limit** on the key is the backstop for all of this. Set one.

## What still does not sync

**Diagrams.** Attached images are stripped before the season is pushed — they are megabytes of base64 belonging to the device that took the screenshot. Everything else (points, log, streak, rivals, milestones, an unfinished session) travels.

## If two devices drift

Practise on a plane on your laptop and on the train on your phone, both offline, and each device has sessions the other has never seen. When they reconnect, the app takes the **union of both logs** and recomputes points and streak from it. Nothing is lost, and re-merging is stable — the session log is the ground truth, and every entry is timestamped.

The server also refuses a write that is older than what it holds; the client merges and retries rather than rolling your ladder backwards.

## Running it locally afterwards

Nothing about this breaks local use. Open `index.html` directly, or serve it with `python3 -m http.server 8000`, and the app finds no `/api/me`, falls back to the profile lock screen, and uses a key you paste into Settings. Same file, both modes.
