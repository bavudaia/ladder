# Deploying PrepHero across your devices

Goal: one ladder, reachable from your laptop and your phone, that only you can open, with your Anthropic key never sitting on any device.

This takes about fifteen minutes and costs nothing — everything below is inside Cloudflare's free tier.

## What you end up with

| | |
| --- | --- |
| **Who can open it** | Anyone with the password. The API refuses every request without a valid session. |
| **Where the key lives** | A deployment secret. It is never sent to a browser — sessions call your own `/api/claude`, which adds the key server-side. |
| **Where progress lives** | Cloudflare KV, keyed by your identity. Every device pulls it on load and pushes as you practise. |
| **Login** | A password you set as a deployment secret, exchanged for an HttpOnly session cookie. Upgradeable to Cloudflare Access later without code changes. |

In this mode the app's lock screen becomes a single password prompt: no local profiles, no per-device key, because the server holds both.

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

Check it worked: open `https://<project>.pages.dev/api/me`. You want `{"hosted": true, "authed": false}` — the Functions built. That signed-out reply is deliberately bare: it is a public endpoint, so it reveals nothing about what the deployment holds or whether it is configured. The full picture appears in the same response once you are signed in. A **404** means Functions did not build, and you are back on the drag-and-drop path.

> Never drag the project folder into an uploader. It includes `.git/`, which would publish your entire repository history at your site's URL, and `tests/.build/`, which is megabytes of generated junk. Git integration avoids both — `.gitignore` already excludes them.

## 2. Create the KV namespace

**Workers & Pages → KV → Create a namespace**, call it `prephero-seasons`.

Then **your Pages project → Settings → Bindings → Add → KV namespace**:

| Variable name | Value |
| --- | --- |
| `PREPHERO` | `prephero-seasons` |

The variable name must be exactly `PREPHERO` — that is what `functions/api/state.js` reads.

## 3. Add your API key as a secret

Do this **inside the Pages project**, not in the account-level Secrets Store.
They are different features: the Secrets Store is a shared vault, and a secret
sitting there is invisible to a Pages Function unless it is explicitly bound to
that project.

**Your Pages project → Settings → Variables and Secrets → Add**, type **Secret**:

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | `sk-ant-...` |

Add it to **Production**, and to **Preview** as well if you ever open a preview
URL — the two environments have separate variables, and a deployment only sees
its own.

(If you would rather keep secrets in the Secrets Store, that works too: bind
them to this project under Settings → Bindings, using the same names. The code
accepts either shape.)

## 4. Set your password

**Settings → Variables and Secrets → Add**, type **Secret**:

| Name | Value |
| --- | --- |
| `APP_PASSWORD` | a generated 24+ character password |

Generate it with a password manager. Do not pick something memorable — this one
secret is the entire gate in front of your API key. Optionally add
`SESSION_HOURS` (plaintext, default 24) to control how often you sign in again.

**Redeploy** after adding variables — Pages only picks them up on a new
deployment. *Deployments → ⋯ → Retry deployment.*

### Why a password and not Cloudflare Access

Access is the stronger option and this app still supports it: set
`ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` and the middleware prefers it
automatically, no code change. It is enforced at Cloudflare's edge, so an
unauthenticated request never reaches your code, and there is no password to
guess. It needs Zero Trust, which asks for a card on file even on the free plan.

The password path is weaker in ways worth knowing:

- The login endpoint is publicly reachable, so password strength is the security.
- Correctness is this repo's code — HMAC-signed cookie, constant-time compare,
  KV-backed throttling of 8 failed attempts per IP per 15 minutes — rather than
  Cloudflare's.
- There is no second factor.

Set a **spend limit on your Anthropic key** either way. That is the backstop
that bounds the worst case no matter which gate you use.

## 5. Use it

Open `https://<project>.pages.dev` on any device. You get a single **Unlock** prompt: enter the password, and the app loads with a **Synced** chip in the top-right and a **Sign out** button beside it.

Do a session on your laptop, open your phone, enter the same password, and the points are there.

Sessions last 24 hours by default. Changing `APP_PASSWORD` signs out every device immediately — the cookie signing key is derived from it, so rotating the password is also the panic button.

---

## Checking it works

| Symptom | Cause |
| --- | --- |
| Lock screen asking you to **create a profile** | The app did not detect hosted mode — `/api/me` is not answering. Functions did not build, or you are opening the file locally. |
| Sign-in says **unavailable** | `APP_PASSWORD` or the `PREPHERO` binding is missing, or you have not redeployed since adding them. The page stays deliberately vague about which — it is public. Check `/api/me` while signed in, or the Pages settings. |
| **Too many failed attempts** | The throttle tripped: 8 wrong passwords from one IP. It clears after 15 minutes. |
| Chip says **No sync store** | The `PREPHERO` KV binding is missing or misnamed. |
| Sessions still say *Offline bank* | `ANTHROPIC_API_KEY` is not set, or was added as plaintext to the wrong environment. |
| Chip says **Sync failed** | Hover it for the error. A 503 means the KV binding is missing; a 401 means your session expired — sign in again. |
| Signed out unexpectedly | The session expired, or `APP_PASSWORD` changed. Both are by design. |

Anthropic's own **spend limit** on the key is the backstop for all of this. Set one.

## What still does not sync

**Diagrams.** Attached images are stripped before the season is pushed — they are megabytes of base64 belonging to the device that took the screenshot. Everything else (points, log, streak, rivals, milestones, an unfinished session) travels.

## If two devices drift

Practise on a plane on your laptop and on the train on your phone, both offline, and each device has sessions the other has never seen. When they reconnect, the app takes the **union of both logs** and recomputes points and streak from it. Nothing is lost, and re-merging is stable — the session log is the ground truth, and every entry is timestamped.

The server also refuses a write that is older than what it holds; the client merges and retries rather than rolling your ladder backwards.

## Running it locally afterwards

Nothing about this breaks local use. Open `index.html` directly, or serve it with `python3 -m http.server 8000`, and the app finds no `/api/me`, falls back to the profile lock screen, and uses a key you paste into Settings. Same file, both modes — and the local profiles are encrypted per device, independent of the deployment password.
