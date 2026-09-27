# Deploy Desk

Desk can run as one container. The image builds the Vite app and serves it from FastAPI on `$PORT` (default `8000`), with `/api` on the same origin. Local development is unchanged: `./scripts/dev.sh` still runs the API on port 8000 and Vite on port 5173.

The shipped model (`backend/app/model/artifacts/`) is already in the image, so startup does not train. The process listens first. The Nifty watchlist, the equity list, and prices are filled in afterwards. Nothing in the image needs a persistent disk: a free Render instance throws the container away after 15 minutes with no requests, and the next visit downloads history again.

## Render (free)

The blueprint is `render.yaml`: a Docker web service on the **Free** plan (512 MB RAM), health check `GET /api/health`. That path does not need the password and does not call Yahoo or NSE, so a cold start can pass the check before the watchlist exists.

1. Push the branch that contains `render.yaml` to GitHub.
2. Open [https://dashboard.render.com](https://dashboard.render.com).
3. Click **New +**, then **Blueprint**.
4. If GitHub is not connected yet, connect it and grant Render access to `pritensarvaiya/stock-predictor`.
5. In the repo list, click **Connect** next to **stock-predictor**.
6. On the Blueprint form, name it (for example `desk`) and set **Branch** to the branch you pushed. Until this work is on `main`, that branch is `cursor/nse-desk-app-dbd3`. Leave **Blueprint Path** as `render.yaml`.
7. Render lists one web service, `desk`, plan Free. Under the secret environment variables (`sync: false` in the blueprint), enter:
   - **GEMINI_API_KEY** — your Gemini key. Leave it empty to use the local word list.
   - **APP_PASSWORD** — a password visitors must type. Leave it empty to leave the URL open.
   Do not put either value in the repo. **GEMINI_MODEL** is already `gemini-3.1-flash-lite`. Render sets **PORT** itself.
8. Click **Deploy Blueprint**.
9. Wait until the service is **Live**. The health check is `GET /api/health`.
10. Open the `onrender.com` URL. If `APP_PASSWORD` is set, the first page asks for it.

After about 15 minutes with no requests, Render spins the free instance down. The next visit starts a new container (often under a minute, plus a few seconds for this process). The page loads before the watchlist is finished; the scan runs in the background and rebuilds the price cache from scratch, because the free instance has no disk that survives sleep. The scan keeps only `WATCHLIST_BATCH` daily histories in memory at a time (4 on this blueprint). To scan fewer names, set `WATCHLIST_UNIVERSE` to `NIFTY 100` on the service's **Environment** page and redeploy.

## Environment

Set these in the host. Do not bake them into the image.

| Variable | Required | Purpose |
| --- | --- | --- |
| `PORT` | No | Listen port. Render sets this. Default `8000`. |
| `GEMINI_API_KEY` | No | Gemini news summaries. Leave empty to use the local word list. |
| `GEMINI_MODEL` | No | Defaults to `gemini-3.1-flash-lite`. |
| `APP_PASSWORD` | No | When set, the UI and API require this password (a sign-in page sets a cookie; HTTP Basic also works). `/api/health` stays open. When unset, the app is open. |
| `WATCHLIST_BATCH` | No | How many daily histories to hold while scoring. Default `4`, which is what the free blueprint sets. |
| `WATCHLIST_UNIVERSE` | No | `NIFTY 200` (default) or `NIFTY 100`. |

Gemini calls are capped at 12 per minute and 48 per hour inside one process. Past that, the page uses the local word list until the window clears. The cap is there so a public URL cannot drain the key.

## Docker on your own machine

```bash
docker build -t desk .
docker run --rm -p 8000:8000 \
  -e APP_PASSWORD='choose-a-password' \
  -e GEMINI_API_KEY='your-key' \
  -e GEMINI_MODEL='gemini-3.1-flash-lite' \
  desk
```

Open http://127.0.0.1:8000. If `APP_PASSWORD` is set, sign in on the first page.

## Hugging Face Spaces

1. Create a new Space, SDK **Docker**, and connect this repo (or upload it).
2. The root `README.md` starts with Space front matter (`sdk: docker`, `app_port: 8000`). Leave that block in place. The container listens on `$PORT`, which defaults to 8000, matching `app_port`.
3. In the Space **Settings** → **Variables and secrets**, add:
   - `APP_PASSWORD` (secret) if you want the sign-in page
   - `GEMINI_API_KEY` (secret) if you want Gemini
   - `GEMINI_MODEL` optional
4. The Space builds the Dockerfile and serves the app on the Space URL.

A Space also has no disk you should treat as permanent. The same batching used for Render applies. If a small CPU tier restarts during the scan, set `WATCHLIST_UNIVERSE` to `NIFTY 100` or pick a larger CPU tier.
