# simple-chat

A tiny two-person live chat — pure Python standard library, zero dependencies.

## Run locally
```bash
python3 chat.py
```
Open the two links it prints (the name comes from the URL path, e.g. `/You`, `/Guest`).

## Run locally + share over the internet (ngrok)
```bash
./start.sh
```

## Hosted on Render
Deployed as a free web service. The name in the URL path picks your display name:
- Your link:  `https://<your-app>.onrender.com/You`
- Share link: `https://<your-app>.onrender.com/Guest`

Render config lives in `render.yaml`. The server reads `$PORT` from the environment.
