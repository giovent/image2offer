# image2offer webdemo (Render)

## Run locally

1. Create a Python environment.
2. Install dependencies:
   - `pip install -r webdemo_render/requirements.txt`
3. Set `OPENAI_API_KEY` in your environment (or in `.env`).
4. Start server:
   - `uvicorn webdemo_render.app:app --reload --host 0.0.0.0 --port 8000`
5. Open `http://localhost:8000`.

## Features

- Upload image from file picker or drag-and-drop.
- Paste image directly from clipboard.
- Press Enter to run.
- Live trace stream while graph nodes run.
- Pretty-printed final JSON output.

## Notes

- The web app reuses the existing graph under `src/graph`.
- Allowed image types: png, jpeg, webp, gif.
- Upload size limit is 10MB.
