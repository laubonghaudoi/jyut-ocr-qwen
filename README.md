# jyut-ocr-qwen

Faithful OCR and proofreading of historical Chinese PDFs into Markdown, driven by a
local Qwen model and two local OCR engines (PaddleOCR-VL and HunyuanOCR).

This is the Linux/GPU branch of `jyut-ocr-proofread`, built on the two local OCR
engines only and calibrated for long books, financial tables and measured accuracy.

## What is here

- `SKILL.md` — the skill, in Cantonese, loaded by the agent harness
- `scripts/` — survey, both OCR runners, GPU handover, the proofread/merge pass
- `references/` — rules, known OCR traps, the long-book workflow
- `tests/` — golden-reference regression suite (`run_regression.py`, `cases/`)
- `env.sh.example` — machine-local paths; copy to `~/.config/jyut-ocr/env.sh`

## Install

    ln -s "$(pwd)" ~/.qwen/skills/jyut-ocr-qwen

## Regression

    python3 tests/run_regression.py OUTPUT_DIR

Every assertion carries its provenance: `human` (a person read the page), `regression`
(a bug found and fixed) or `machine` (a model reading, adversarially checked). Only the
first two fail the run.
