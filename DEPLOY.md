# Deploy Desk

Desk can run as one container. The image builds the Vite app and serves it from FastAPI on `$PORT` (default `8000`), with `/api` on the same origin. Local development is unchanged: `./scripts/dev.sh` still runs the API on port 8000 and Vite on port 5173.

The shipped model (`backend/app/model/artifacts/`) is already in the image, so startup does not train. The Nifty 200 watchlist builds in the background after the process is listening. A copy of the NSE equity list ships in the image and is used if the live download is blocked.

## Environment

Set these in the host. Do not bake them into the image.

| Variable | Required | Purpose |
| --- | --- | --- |
| `PORT` | No | Listen port. Render sets this. Default `8000`. |
| `GEMINI_API_KEY` | No | Gemini news summaries. Leave empty to use the local word list. |
| `GEMINI_MODEL` | No | Defaults to `gemini-3.1-flash-lite`. |
| `APP_PASSWORD` | No | When set, the UI and API require this password (a sign-in page sets a cookie; HTTP Basic also works). `/api/health` stays open for the platform health check. When unset, the app is open. |

Gemini calls are capped at 12 per minute and 48 per hour inside one process. Past that, the page uses the local word list until the window clears. The cap is there so a public URL cannot drain the key.

The on-disk price cache lives in the container filesystem and disappears when the instance is replaced. The next start downloads history again. Search and scoring still work from the files in the image.

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

## Render

1. Push this branch to GitHub.
2. In Render, choose **New** → **Blueprint** and pick the repo. Render reads `render.yaml`.
3. When it asks for secret env vars, set `APP_PASSWORD` and, if you want Gemini, `GEMINI_API_KEY`. `GEMINI_MODEL` is already in the blueprint. Render sets `PORT` itself.
4. Deploy. The health check is `GET /api/health` and does not need the password.
5. Open the Render URL. The starter instance has 512 MB of RAM. If the Nifty 200 scan is killed for memory, change `plan` in `render.yaml` from `starter` to `standard` (2 GB) and redeploy.

## Hugging Face Spaces

1. Create a new Space, SDK **Docker**, and connect this repo (or upload it).
2. The root `README.md` starts with Space front matter (`sdk: docker`, `app_port: 8000`). Leave that block in place. The container listens on `$PORT`, which defaults to 8000, matching `app_port`.
3. In the Space **Settings** → **Variables and secrets**, add:
   - `APP_PASSWORD` (secret) if you want the sign-in page
   - `GEMINI_API_KEY` (secret) if you want Gemini
   - `GEMINI_MODEL` optional
4. The Space builds the Dockerfile and serves the app on the Space URL.

Hardware: the free CPU basic tier is tight once the watchlist scan holds a few hundred daily histories. If the Space restarts during that scan, pick a larger CPU tier.
