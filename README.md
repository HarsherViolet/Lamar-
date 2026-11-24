# Lamar on Vercel

Lamar is an installable web app (PWA) for finding startup roles in Kuala Lumpur and Singapore. It matches them to your CV and drafts outreach emails. Hosting is free on Vercel's Hobby plan, and the AI is free through Google Gemini's free tier, or through Ollama on your own computer.

```
public/                 the app (installable PWA)
  index.html            the Lamar app
  ai-shim.js            AI settings (free cloud or Ollama) and backup/restore
  sw.js                 service worker: opens offline, keeps the last role list
  manifest.webmanifest  icons/
api/
  roles.py              GET /api/roles: reads ~20 company job feeds live; cached 6 hours
  ai.py                 POST /api/ai: Gemini (free), then Groq (free), then OpenAI (paid, optional)
  _lamar/               the job pipeline and companies.json (the watch list)
tests/                  offline tests: python -m unittest discover -s tests -t .
```

## Deploy (about 10 minutes, no Git needed)

1. **Get a free Gemini key.** Go to aistudio.google.com, sign in with Google, and choose **Get API key** → **Create API key**. No card is needed.
2. **Deploy.** Go to **vercel.com/drop**, sign in (a free Hobby account), and unzip the download and drag the `lamar-vercel` folder onto the page. Name the project `lamar` and deploy.
3. **Add the key.** In the Vercel project, go to **Settings → Environment Variables**. Add `GEMINI_API_KEY` with your key, and add `LAMAR_PASSCODE` with any word you'll remember. Without a passcode, anyone who finds your URL can use up your free AI quota.
4. **Redeploy** so the settings take effect: **Deployments** → the latest one → **⋯** → **Redeploy**.
5. **Install it.** Open your `https://lamar-xxxx.vercel.app` link.
   - **Phone:** in Chrome on Android, use ⋮ → **Add to Home screen**. In Safari on iPhone, use Share → **Add to Home Screen**.
   - **Laptop:** in Chrome, click the install icon in the address bar.

The first AI action asks for your passcode once.

## Optional settings (Vercel → Settings → Environment Variables)

| Variable | What it does |
|---|---|
| `GEMINI_MODEL` | Gemini model ID. The default is `gemini-flash-latest`. If AI calls fail with a model error, copy the current Flash model ID from AI Studio. |
| `GROQ_API_KEY` | Free backup if Gemini's free quota runs out (console.groq.com, no card). Text only. |
| `GROQ_MODEL` | Default is `openai/gpt-oss-120b`. |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Paid. Used last, only if set. `OPENAI_BASE_URL` points it at any OpenAI-compatible service. |

Redeploy after any change.

## Ollama (free, runs on your computer)

1. Install Ollama from ollama.com, then pull a model: `ollama pull llama3.1`. For reading scanned CVs, also pull a vision model: `ollama pull llava`.
2. Allow Lamar to talk to it. Quit Ollama, then start it with your Lamar address allowed:
   - **Mac:** `launchctl setenv OLLAMA_ORIGINS "https://lamar-xxxx.vercel.app"`, then reopen Ollama.
   - **Windows:** add a user environment variable `OLLAMA_ORIGINS` = `https://lamar-xxxx.vercel.app`, then restart Ollama.
3. In Lamar, open **AI settings and backup** in your brief, choose **Ollama on this computer**, and press **Connect**.

This works only on that computer, while Ollama is running, in Chrome or Edge. Safari blocks a secure site from calling `localhost`. Your phone keeps using the free cloud option. Small local models are weaker than Gemini at reading CVs and ranking, so check their output.

## Things to know

- **Privacy:** on Gemini's free tier, Google may use what you send, including your CV text, to improve its products. Ollama keeps everything on your computer.
- **Your data stays in the browser.** The brief, drafts and tracker are saved on each device separately. Use **Back up** and **Restore** in AI settings to move them between devices.
- **Roles** are read live from public job feeds, about four times a day at most because of the 6-hour cache. Edit `api/_lamar/companies.json` to watch more companies, then redeploy. Failed feeds are listed in `/api/roles` under `meta.failures`.
- **Vercel's Hobby plan is for personal, non-commercial use.** If Lamar becomes a product, move to Pro.
