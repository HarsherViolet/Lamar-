# Lamar on Vercel

Lamar is an installable web app (PWA) for finding startup roles in Kuala Lumpur and Singapore. It matches them to your CV and drafts outreach emails. Hosting is free on Vercel's Hobby plan, and the AI is free through Google Gemini's free tier, or through Ollama on your own computer.

```
frontend/               the app (installable PWA)
  index.html            the Lamar app
  ai-shim.js            AI settings (free cloud or Ollama) and backup/restore
  sw.js                 service worker: opens offline, keeps the last role list
  manifest.webmanifest  icons/
api/                    backend: Python serverless functions (Vercel needs this folder name)
  roles.py              GET /api/roles: reads ~20 company job feeds live; cached 6 hours
  ai.py                 POST /api/ai: Gemini (free), then Groq (free), then OpenAI (paid, optional)
  _lamar/               the job pipeline and companies.json (the watch list)
tests/                  offline tests: python -m unittest discover -s tests -t .
```

## Deploy

Lamar deploys from GitHub. Every merge to `main` goes to production, and every pull request gets its own preview link.

1. **Get a free Gemini key.** Go to aistudio.google.com and choose **Get API key** → **Create API key**. No card is needed.
2. **Import the repo.** On vercel.com, choose **Add New → Project**, pick this repo, and keep the Framework Preset as **Other**. `vercel.json` sets everything else.
3. **Add keys.** Under **Settings → Environment Variables**, add `GEMINI_API_KEY` and `LAMAR_PASSCODE` as **Secret**, ticking Production and Preview.
4. **Deploy.** Merge to `main`. Keys added or changed later only reach the next deployment.
5. **Install it.** Open the production link. Chrome shows an install icon in the address bar; on a phone, use **Add to Home screen**.

Don't deploy with Vercel Drop. It uploads files as-is and skips building the `api/` functions, so `/api/roles` and `/api/ai` return 404.

### Workflow

- Branch from `main` (`feat/…`, `fix/…`, `docs/…`), open a pull request, and wait for the **Tests** check and the Vercel preview, then squash-merge.
- Run tests locally with `python -m unittest discover -s tests -t .`. They're offline, so no keys are needed.

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
