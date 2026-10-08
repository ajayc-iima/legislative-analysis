# OCR model trial (2026-10-08)

4 endpoints × 12 stratified PDF pages (4 text-layer, 4 clean 2026 scans,
4 noisy 2018 scans), hand-transcribed ground truth
(`packages/extract/trial_ground_truth.json`): memo no, reply/scheduled
dates, minister, reply excerpt, table cells. Substring matching per field.

## Endpoint status

| Model | Status |
|---|---|
| `nvidia/nemotron-ocr-v1` | works (`ai.api.../v1/cv/...`) |
| `nvidia/nemotron-ocr-v2` | works |
| `baidu/paddleocr` | works |
| `nvidia/nemotron-parse` | works via chat + `markdown_no_bbox` tool; transcription arrives in `tool_calls[0].function.arguments` (message content is null) |
| `nvidia/nemotron-parse-2.0` | not callable (server-side tool-parser flags missing) |
| `nvidia/nemoretriever-ocr-v1` | **410 Gone since 2026-05-18 — dropped permanently** |
| `llama-nemotron-rerank-vl-1b-v2` | no endpoint exists (404 on chat, embeddings, ranking, retrieval paths) — dropped |
| `llama-nemotron-embed-vl-1b-v2` | works for **text** input (`input_type` + string, 2048-dim); image-input shape rejected — text is all the under-merge task needs |

## Results (accuracy = fields matched / fields checked, 0 failures)

| Model | Accuracy | Avg latency |
|---|---|---|
| **nemotron-ocr-v1** | **0.937** | 1.3 s |
| nemotron-ocr-v2 | 0.857 | 1.3 s |
| nemotron-parse | 0.857 | 2.7 s |
| baidu/paddleocr | 0.825 | 1.5 s |

Winner: **ocr-v1** — highest accuracy on this corpus (the newer v2 does
not beat it here), fastest alongside v2. Parse ties v2 but costs 2×
latency for equal accuracy, so it stays as the table-structure fallback,
not the primary.

## Lessons that cost real API calls

1. **Never downscale OCR input.** An early harness capped images at
   170 KB; all four models scored ~0.40 on thumbnails. Full-resolution
   (~1.5 MB) renders score 0.83–0.94. `render_page` now caps at 1.8 MB.
2. **Parse needs image-only content** — any text part in the message
   returns 400 ("model does not support text input").
3. Re-run: `python -m legislative_extract --pdf-root data/pdfs
   --truth packages/extract/trial_ground_truth.json --out scorecard.json`
   (needs `NVIDIA_API_KEY` in env or `.env`).
