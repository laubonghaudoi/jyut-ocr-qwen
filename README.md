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

    sudo apt install python3-numpy python3-pil   # the scripts run on the system python3
    ln -s "$(pwd)" ~/.qwen/skills/jyut-ocr-qwen

## Regression

    python3 tests/run_regression.py OUTPUT_DIR

Every assertion carries its provenance: `human` (a person read the page), `regression`
(a bug found and fixed) or `machine` (a model reading, adversarially checked). Only the
first two fail the run.

## 人工標註

人工對圖、疑字裁定同 golden 覆核統一用 `jyut-ocr-bench` 嘅共用介面；本 repo 只提供薄啟動器。程式集中維護，圖片、題目同 append-only 裁定歷史留喺各 project。

```bash
export JYUT_OCR_BENCH_ROOT=/path/to/jyut-ocr-bench
python3 scripts/review.py --project-root /path/to/book-project --port 8765
```

需要 Python 3.10+ 及 review API 1。啟動後打開印出嘅 localhost 網址。入口設定、舊 audit／goldgate 匯入同 benchmark 覆核見 [共用人工標註工具](references/manual-review-tool.md)。保存答案唔會自動改正文或 golden。
