---
name: jyut-ocr-qwen
description: 用本機 Qwen harness 加本機 OCR 模型（PaddleOCR-VL + HunyuanOCR）逐頁識別、校對歷史中文 PDF 成 Markdown；兩個獨立引擎合併、算術核對表格、直排表格轉置同讀向修正、頁面家具學習、golden reference 回歸測試。呢個係 jyut-ocr-proofread 嘅 Linux／GPU 分支，淨係用兩個本機 OCR 引擎，針對長書、財政表格同高準確度校準。Use when asked to OCR, transcribe, 校對, proofread historical Chinese PDFs on a machine running a local Qwen model and local OCR engines.
---

# Jyut OCR 校對（Qwen 本機版）

用呢個 skill 將歷史中文 PDF 忠實轉錄成 Markdown，或者按同名 PDF 校對既有 OCR。目標係保存原文，而唔係現代化、改寫或潤飾。

## 先讀邊份規則

- 先讀目標 repo 嘅 `AGENTS.md` 或其他本地指示；本地規則優先。
- 做全文、長報告、章程、表格、票據、尾頁或速記錄時，讀 `references/jyut-ocr-detailed-rules.md`。
- references 入面講「核圖」「放大」「對 PDF 查」「逐頁 final pass」嘅地方，喺本 skill 係流程（phase 3、修書步驟對住裁圖問模型）或者用戶睇 `doubts.md` 時做嘅；agent 喺對話入面唔讀頁圖（見〈做完之後〉）。
- 遇到反覆近形錯字、官職、人名、地名、數字符號或舊式標點時，讀 `references/common-ocr-traps.md`。
- 處理單一長書、掃描 spread、旋轉／重複／缺頁、分段並行、PaddleOCR-VL／HunyuanOCR 底稿、跨頁註腳或外部同版復原時，讀 `references/long-book-workflow.md`。
- 用 Codex／Claude Code subagent 分段寫稿或做獨立 visual audit 時，讀 `references/subagent-orchestration.md`；raw OCR 另用本機 runner（每個引擎一個常駐 GPU worker），唔用一頁一個 LLM agent 包裝。
- 書內有凡例、編者校勘符號或原書不配對引號時，讀 `references/release-gate.md` 嘅相應 feature；只有已揀 `release` profile 先跟入面嘅 plan／receipt 封關部分。
- 遇到題名星號／來源題注、獨立覆核後再修改、跨冊證據重用，或者要判斷上游改動令邊批 release evidence 失效時，讀 `references/review-evidence.md`。

## 原文依據

- 以 PDF 圖像為最終依據；OCR、PaddleOCR-VL、HunyuanOCR、Gemini、GJ.cool、OCR JSON 同外部研究都只係底稿或提示。PaddleOCR-VL 本身係 VLM，輸出讀落好順，但一樣會漏字、跳行同自動補字，唔可以因為佢似「已經校對過」就當權威。
- 保留原有異體字、舊字形同舊式標點，例如 `粤/粵`、`淸/清`、`决/決`、`吿/告`、`塲/場`、`箚/劄/剳/札`。唔好靜靜正規化，**亦唔好過度古化**——唔可以用「邊個字形舊啲」做判準，頁上係普通「即」就寫「即」，唔好「改正」成「卽」。詳見 `common-ocr-traps.md`。
- **既有轉錄（包括你自己上一版、或者其他模型／人做嘅參考檔）唔係 ground truth，只係另一份底稿。** 本項目實測：一份用 GPT-5.6＋Apple Vision 做嘅參考檔，喺人手裁決嘅 10 個分歧之中 6 個係錯，包括整段 36 字漏失同一個讀反語意嘅近形錯字。所以分歧只係「要人核圖」嘅訊號，唔係對錯判決；用未經核實嘅參考做評分基準，會將正確輸出判成錯誤。
- 流程輸出冇 `[]` 低信心字：兩個引擎唔一致嘅字由 phase 3 對住裁圖問模型定；兩個引擎一致嘅字亦可能錯（兩個一齊讀錯），冇任何訊號。定唔到嘅位由 `finish_book.py` 寫入 `doubts.md`，交畀用戶對住原書核——唔係 agent 喺對話入面按圖檢查（見〈做完之後〉）。
- 開始正文前先讀凡例／編輯說明，建立本書符號政策。`[]`、`［］`、`〈〉`、`□`、`（？）` 同註號可能係原書校勘內容，唔可以當 residual 一律刪；同一系列各冊亦要分開判斷。
- Annotated audit 唔接受 notation policy 豁免：已核實嘅來源符號可以原樣保留並記成 known annotated-stage issue，但呢一關唔可以聲稱 clean；移除 OCR confidence markup 後，只喺 final mode 先按 exact policy 接受來源 notation。
- PDF 模糊而底稿合理時，保留最有根據讀法或報告 uncertainty；唔好憑空補字。
- **唔可以話「已逐頁視覺校對」「已逐頁同 PDF 對照」，或者任何講到有人逐頁睇過 PDF 嘅說法。** 本流程冇人逐頁睇過 PDF：字由兩個引擎讀，phase 3 同修書步驟對住裁圖問模型定；agent 冇睇，亦唔准睇（見〈做完之後〉）。交付時照實講：全文由流程校對，流程定唔到嘅位列喺 `doubts.md`，要用戶對住原書核；冇列出嚟嘅字唔代表一定啱。

## 分三次交付

用戶唔使等成本書校對完先睇到嘢：同一本書交三次，檔名固定用英文：`draft.md`、`proofreading.md`、`final.md`（第三次連埋疑問清單 `doubts.md`）。全部寫喺本書目錄 `BOOK`（`renders/`、`page-manifest.json`、`ocr-paddle/`、`ocr-hunyuan/`、`proofread/` 所在嗰個目錄，即係〈做完之後〉嘅 `BOOK`）。

- **本書目錄嘅名**：用冇聲調嘅粵拼（例如「廣州城坊志」寫 `gwongzau-singfong-zi`），或者簡單英文（例如 `canton-gazetteer`）；唔好用普通話拼音（`guangzhou-…` 唔得）。
- **第一次：未校對草稿 `draft.md`**。兩個 OCR 引擎都做完（第 3 步兩個 runner 都 exit 0）就即刻跑：

  ```bash
  python3 scripts/build_draft.py BOOK
  ```

  唔問模型，幾秒做完。入面係引擎 B（HunyuanOCR）讀出嚟嘅字，唔係引擎 A 嘅：引擎 A 讀直排頁會亂欄序（golden 頁實測 CER：引擎 A 75.8%，引擎 B 5.8%）。頁按 page manifest 嘅掃描次序排，manifest 標咗 `marker_expected: false`（核過圖嘅空白頁、重複掃描）或者 `content: blank` 嘅頁略過（淨係標咗 `relation: exact_duplicate` 嘅頁照出：一對重複掃描可能兩頁都有呢個標，成品書亦照留）；書眉同頁碼係由引擎 B 自己嘅字學（全書好多頁頁頭頁尾都有嘅一段字，同埋對得上頁序嘅頁碼），保守咁刪；冇 page marker，頁同頁之間分段；冇引擎 B 文字（冇檔，或者讀唔到字）嘅頁寫一行空位，講明係掃描第幾頁；引擎 B 停唔到、將同一段字不停重複（loop，例如成頁幾千個「口」）嘅地方唔抄：嗰段字留一次，跟住寫一行空位講明重複咗幾多次（短嘅重複，例如表入面一格字印幾次，同淨係表格標記嘅重複照抄）；檔頭講明係未校對 OCR 同幾時整。**跑完即刻用一行話畀用戶知草稿喺邊**（例如「未校對草稿：`BOOK/draft.md`」），唔使等佢回覆，直接做落去（第 6 步 book profile）。佢寫唔到（exit 1）都唔阻流程：講一句，照做落去。
- **第二次：校對進度 `proofreading.md`**。Phase 3 跑緊嘅時候，`wait_for_run.py` 加 `--progress BOOK`（見〈安全並行〉），佢每 5 分鐘同每次返嚟之前重整 `BOOK/proofreading.md`（`scripts/build_progress.py`，都可以自己跑）：封存齊嘅頁（`.json` 同 `.md` 都喺度、封條對得上；淨係睇封條，唔睇封嗰陣用咩參數，所以用 `--overwrite` 重做嘅時候，上一輪封咗嘅頁未重新封之前照計已校對）用校對稿，其他頁（未做、寫緊一半、封條唔啱）用草稿嘅字；冇 page marker，頁同頁之間淨係分段（跨頁駁句留畀定稿）；檔頭一行講已校對幾多頁／總共幾多頁同幾時更新。佢寫落暫存檔再改名，用戶打開嗰陣唔會見到寫咗一半嘅檔。`wait_for_run.py` 嗰行最後會講呢個檔喺邊、校對咗幾多頁；**呢行唔使次次話畀用戶知**：用戶問先講，或者最多每個鐘講一次。唔好為咗講進度去睇 log 或者讀頁。
- **第三次：定稿 `final.md` 同疑問清單 `doubts.md`**，最後一次交付。Phase 3 封存晒全書之後，照〈做完之後〉喺背景跑 `finish_book.py BOOK`、用 `wait_for_run.py` 等：拼書、修書（`repair_book.py`，跨頁駁句同修補喺呢度做）、定稿同 final audit 一個 command 做晒，寫出 `BOOK/final.md` 同 `BOOK/doubts.md`（流程定唔到、要用戶對住原書核嘅位）。做完照〈做完之後〉交付。

## OCR 工具次序

0. **開工前先 source 本機設定**（如果存在）：

   ```bash
   [ -f ~/.config/jyut-ocr/env.sh ] && . ~/.config/jyut-ocr/env.sh
   ```

   入面有本機先知道嘅嘢：OCR 引擎嘅 venv／權重路徑、LLM server 嘅 start／stop 指令同
   health URL、讀圖模型嘅 endpoint。**冇咗佢，`run_ocr_phase.py` 唔知點騰 GPU、
   `run_hunyuanocr.py` 唔知權重喺邊**，第二階段一定失敗。範本見 skill 目錄嘅
   `env.sh.example`；冇呢個檔就照樣行得，但要用戶自己喺 shell 出 export。

1. 立即 render PDF，先睇圖認清版式（直排／橫排、欄數、有冇表格、題名頁、空白頁、家具位置），唔為任何服務停低。**呢一步係認版式，唔係逐字轉錄**：正文嘅字由第 2–3 步嘅兩個引擎同 merger 出，你喺對話入面逐欄放大讀字係最貴而且最唔準嘅路（見第 6 點）；爭議位同 research 項亦唔使你睇，流程會問模型，定唔到嘅寫入 `doubts.md` 交用戶（見〈做完之後〉）。認版式淨係睇幾頁全頁圖（題名頁、一兩頁正文、survey 報嘅空白頁 candidate），唔放大、唔逐字讀。長書用 `scripts/survey_pdf.py SOURCE.pdf OUT_DIR` 一次過 render 晒同封存 page manifest（實測一本幾百頁嘅書 300dpi 約 5 分鐘，純 CPU）。佢淨係產生 anomaly **candidates**，唔會自己判定空白頁；`marker_expected: false` 一定要核圖之後先手動寫入。
2. 揀本機 draft engine。唔好靠估、唔好逐個試，直接問：

   ```bash
   python3 scripts/detect_ocr_engine.py          # 完整 JSON
   python3 scripts/detect_ocr_engine.py --brief  # paddleocr-vl+hunyuanocr｜paddleocr-vl｜none
   ```

   `--brief` 會出 `paddleocr-vl+hunyuanocr` 咁嘅字串：`+` 之後係**第二引擎**，
   唔係替代品。**兩個都行**——一個做主底稿（有 layout box，裁圖裁決要用），
   另一個做獨立第二讀。實測一本幾百頁嘅書，兩個引擎喺 **94.3%** 嘅字上面一致；
   一致就凍結，唔一致由**本書量度出嚟**嘅引擎偏好決定（見第 6 步嘅 book profile）。得一個引擎嘅話 phase 3 會退化成
   模型重新轉錄，實測準確度由 9/11 跌到 4/11。

   主引擎 PaddleOCR-VL 用到就 exit 0，用唔到就 exit 1：`paddleocr` import 得到就係 `paddleocr-vl`；import 唔到 → 冇本機主底稿，直接由頁圖人手／VLM 逐頁識別，唔好因此改用禁用引擎。HunyuanOCR 睇 `HUNYUAN_MODEL`、`HUNYUAN_MMPROJ` 同 `llama-server` 齊唔齊。呢個判斷同 host harness（Claude Code／Codex／Qwen Code 等）無關，只睇已裝嘅套件同權重。
3. 兩個 runner（`run_paddleocr_vl.py`、`run_hunyuanocr.py`）批量產生有 page provenance 嘅底稿；直排次序、表格、淡字、註腳同跨頁段落仍要按圖重建。兩個 runner 嘅共用 CLI（`render_directory`、`output_directory`、`--overwrite`、`--report`；page selector 可省略，預設跑晒 `render_directory` 入面所有 `page-NNNN.png`，要限範圍先加 `--pages` 或 `--first-page`／`--last-page`）、輸出檔名、sealed provenance 同 resume 語義完全一樣；分別只在 engine 專屬選項：`run_paddleocr_vl.py` 用 `--python` 或 `PADDLEOCR_PYTHON` 指向裝咗 paddleocr 嘅 venv，`run_hunyuanocr.py` 用 `--model`、`--mmproj`、`--llama-server`（或者 `env.sh` 嘅 `HUNYUAN_*`）。兩個 runner 都做完就即刻出未校對草稿（`build_draft.py`），話畀用戶知，唔使等（見〈分三次交付〉）。
4. 只有已有 token、API 正常而且 5 秒內即時回應時，先用 GJ.cool 作輔助底稿。timeout、quota、auth、服務錯誤或 `wait for ... seconds` 後，本輪唔再自發重試。
5. Tesseract/Tessdata 係硬性禁用：唔安裝、唔調用、唔等待、唔讀取現成輸出、唔採納結果。
6. **開 phase 3 之前先量度本書**：兩個引擎 OCR 完全書之後，跑

   ```bash
   python3 scripts/book_profile.py RENDER_DIR OCR_A_DIR OCR_B_DIR book-profile.json --workers 8
   ```

   佢量度四樣嘢，全部連證據封喺 `book-profile.json`（放喺 OCR 目錄隔籬，`proofread_pages.py` 自動讀，仲會核對佢係咪量度緊呢批底稿）：
   - **書眉／家具**：由 layout block 搵（同頁重複、幾乎每頁都有），記埋字級大細。預設仲會按位置學（`--learned-heads`，round 4 基準之後用戶 2026-09-30 定咗預設開；`book_profile.py` 同 `proofread_pages.py` 都係，加 `--no-learned-heads` 就關）：書名旁邊印嘅卷冊標籤同佢哋嘅家族、頁碼序列、書眉帶喺單雙頁企喺邊；phase 3 拎走書眉帶入面全部係書眉嘅 block（見 `references/long-book-workflow.md`）。
   - **邊個引擎讀字讀得啱**：淨係數真正嘅換字分歧——兩個引擎都有字、唔係家具、唔係同一個字嘅兩種寫法——逐個裁圖問模型，甲乙次序隨機，每對唔同字（已/巳、問/間）只算一票；Wilson 下界過咗一半先定偏好，唔夠信心就寫 `adjudicate`（全部換字分歧都裁圖）。
   - **異體（同一個字兩種寫法，粵/粤、既/旣）**：兩個字係咪異體係知識題（純文字問，全部答啱），所以先分類，再按全書出現次數列出每對，每對留幾張唔同頁嘅裁圖；一條裁決管全書（分佈好偏，一對可以佔一半）。**印嘅係邊種寫法由模型逐對裁，唔使人裁，成個流程唔會停低等人**：`book_profile.py` 最後一步（`scripts/variant_vote.py`）逐張裁圖問模型圖上印嘅係邊種寫法（兩種寫法嘅次序每張裁圖唔同，可以答「睇唔清」），每對按裁圖多數定：至少兩張裁圖揀同一種、多過揀另一種嘅、又過咗答咗嗰啲裁圖嘅一半，先算裁定；打和、全部睇唔清、得一票嘅對唔裁；四級 effort 都俾 token 上限截斷（可能不停重複「答：甲」）或者冇答嘅裁圖唔算票，記 `noAnswer`。點解逐張問再投票：實測模型逐張裁圖答得唔一致（同一本書同一個鉛字，19 比 9 咁分；用現代字體逐像素比對一樣分唔到），所以一張裁圖唔可以定成本書，亦唔逐處問。結果寫入 profile 隔籬嘅 `variant-rulings.json`：模型裁嘅對記 `ruledBy: model`、揀咗邊種（`modelPrinted`）、票數同每張裁圖（檔案、SHA-256、兩種寫法點排、答案）；冇裁到嘅對記入 `modelUnruled`（票數同原因），phase 3 照舊做法揀（跟已裁嘅對嗰邊引擎，冇任何裁決就跟讀字偏好），run report 嘅 `variantQueue` 按次數列出。每對問幾多張裁圖（`--variant-vote-crops`，預設 3，即係 profile 留低嘅張數）同全書最多幾多個 call（`--variant-vote-calls`，預設 120，每張裁圖一個 call；答案俾 token 上限截斷就降一級 effort 再問，所以一個 call 最多 4 個 request，實際 request 數記喺 `modelVote.usage.n`）都有上限，call 同 phase 3 一樣按 `--workers` 並行；`--no-variant-vote` 關（即係舊做法：模型唔裁，人冇裁嘅對照上面規則揀；之前投票寫低嘅模型裁決會由 `variant-rulings.json` 拎走，人裁嘅留低，冇人裁嘅就成個檔刪咗；淨係人寫嘅檔唔郁）。一對異體兩種寫法都係可接受異體（見下面兩層清單），裁錯唔算錯字，淨係字形忠實度差啲；等人裁就要成個流程停低（實測一本書等咗超過一個鐘），唔抵。所以 **agent 唔好停低問人、唔好等人裁，亦唔使自己放大裁圖逐對睇**：profile 跑完就直接開 phase 3，互動定非互動（headless）跑都一樣。已經有 `variant-rulings.json`（例如人以前裁過）嘅話，人裁嘅對原封不動，模型淨係裁人冇裁嘅對。人想改（可選，流程唔會等）：喺 `variant-rulings.json` 將嗰對嘅 `printed` 改做頁上嘅字形、`ruledBy` 改做 `person`（淨係改咗 `printed` 都當係人裁）；模型裁咗嘅對喺 `rulings`，模型冇裁嘅對喺 `modelUnruled`，改返嗰對自己嗰條就得（`modelUnruled` 嗰條下次跑 profile 會搬入 `rulings`），再淨係重跑受影響嘅頁（`--pages` 加 `--overwrite`）；人裁嘅對之後重跑 profile 都唔會再投票，同一對兩樣都有就以人為準。用戶想睇裁圖可以跑 `python3 scripts/variant_sheet.py book-profile.json`（`variant-sheet.png`，每對附模型嘅裁決同票數；張圖畀用戶睇，agent 唔好讀入對話）。舊 profile（未有模型裁決）可以單獨跑 `python3 scripts/variant_vote.py book-profile.json --workers 8`。
     - **異體字原則：頁面印乜字形就寫乜字形**，逐處跟圖，唔正規化、唔古化；golden 同 assertion 亦一樣要記頁面字形。**可接受異體分兩層。** 第一層 `references/variant-equivalents.json` 淨係收用戶逐對裁過嘅對，接受定唔接受都以佢為準。第二層 `references/opencc-allographs.txt` 係 OpenCC 嘅 `Allographs.txt`（釘死 commit、逐 byte 照抄），收 Unicode 分咗唔同碼位、其實係同一個字嘅字（淸/清、愼/慎、旣/既）；用戶未裁嘅對先用佢。收第二層係因為實測可信：同用戶裁決重疊嘅 15 對全部一致，亦冇收字典同模型搞錯嘅對。除此之外唔好由 Unihan、其他字典或者模型自動加（實測字典將 刺/剌、着/著 當異體，模型分類亦錯過）；第二層個檔唔好手改，唔同意佢就喺第一層裁。清單改咗之後，book profile 入面嘅分類可能同清單唔一致：合併照清單，但模型投票同 variant sheet 都係由 profile 出（profile 當唔同字嘅對冇裁圖），phase 3 開頭會警告，要重跑 `book_profile.py`。`acceptable: true` 係同一個字嘅兩種寫法：合併時當異體問題處理（跟本書 `variant-rulings.json` 嘅 printed，唔送去讀圖裁決），評分時輸出同 golden 喺呢類之內唔同，算「可接受異體」，唔算錯字，但另外報字形忠實度，淨係第二層接受嘅互換另外計（`acceptable-opencc`）；人寫嘅單字 assertion（`contains` 等）係人對字形嘅裁決，淨係用第一層，第二層唔會令佢通過；第一層裁咗唔接受嘅對，第二層就算收咗都當唔同字；`acceptable: false` 係唔可以互換（唔同字、簡繁），一定要跟頁面，合併時當普通讀字分歧。兩層都冇嘅對照舊由模型分類——佢會錯——所以校準時將新見到嘅對交用戶裁，裁完加入第一層（呢個係校準 skill 嘅工作，唔係每本書嘅流程，流程唔會等）。清單係通用字形知識，唔寫書名、頁碼。
   - **標點體例**：逐 block 問圖上印咗乜符號（圈、點、雙圈、圈點係圈定點、括號）同有幾密（淨係印雙圈嘅 block 答「符號：無、雙圈：有」都當雙圈 block 計，唔當冇標點；`book_profile.py --no-doubled-notation` 用返舊讀法），以比例畀 punctuator 做參考，退化輸出門檻按本書第二密嗰個 block 放寬。**冇 profile 又冇 `--prefer-engine`，phase 3 會拒絕開工**——因為邊個引擎讀得好係因書而異：實測同一個引擎，喺一本書 11 次啱 10 次，喺另一本書 14 次淨係啱 2 次。

   校對階段用 `scripts/proofread_pages.py`，唔好喺對話入面逐頁逐字自己開 VLM call。跑完唔使睇 run report、sealed JSON 或者頁面，直接去〈做完之後〉跑 `finish_book.py`：佢將 run report 嘅 `researchQueue`（即係每頁 sealed JSON 嘅 `needsResearch`／`adjudications[].needs_research`）寫入 `doubts.md`〈要查資料嘅專名〉，連上下文同兩個引擎嘅讀法。題名頁嘅題字者、印章、人名、地名、官職呢類專名，**淨靠字形係定唔到案嘅**，兩個引擎同讀圖模型可以一齊錯而且各錯各嘅；要用本書嘅出版脈絡（出版年、出版社、作者圈子、題字者係邊個）去查，唔好憑筆畫夾硬揀一個，所以亦唔好放大頁圖睇（睇字形定唔到，正正係佢哋入 research 嘅原因）。交付之後有網先可以查：淨係用文字搜尋，查到就用一兩句話畀用戶知，唔改 `final.md`；冇網或者查唔到，`doubts.md` 已經寫明未定案。實測同一 3 頁：harness 對話式做法每頁 24.7 次 model call、每次重發約 92K context（3 頁共 683 萬 input token），45 分鐘都未做完；同樣工作用 runner 直接調用係每頁 2 次 call、共 5.5 萬 token、202 秒做完。差別唔喺推理深度，喺 round trip 同 context 重發。**並行數**：`--workers`（同 `--max-inflight`，預設跟 `--workers`）要等於 LLM server 嘅 `--max-concurrency`；本機 server 預設開 8 條 lane（200K context），所以用預設 `--workers 8` 就啱，唔好自己改細。睇 server 開咗幾多條：`ps -o args= -C ninfer-serve` 入面嘅 `--max-concurrency`。實測同一本書：2 條 lane 每鐘約 21 頁，8 條 lane 每鐘約 60 頁；benchmark 嘅 golden 評分全部喺 8 條 lane 跑。

   **round 4 嘅四個修正預設開**（round 4 基準之後用戶 2026-09-30 定）：阿拉伯數字照引擎 A 寫（`--keep-arabic-numerals`）、推理一字不差兜圈就收手（`--loop-detector`）、唔寫抄咗隔籬字嘅裁決答案（`--neighbour-guard`）、按位置學書眉（`--learned-heads`），點做同實測見 `references/long-book-workflow.md`。要關邊個就加 `--no-keep-arabic-numerals`、`--no-loop-detector`、`--no-neighbour-guard`、`--no-learned-heads`；舊嘅開關名照收（即係開，同預設一樣），舊 script 照跑。速度開關 C1（`--census-confirms-engine-a`）、C4（`--folio-furniture`）同 R2-C（`--top-rung-caps`）預設關（C1 實測過：快一成，但有頁排版出錯，所以唔開）。每頁 provenance 照封每個開關開定關，一本書由頭到尾用同一套：**改預設之前開咗頭、做咗一半嘅書**用而家嘅 code 續跑，runner 一開始就停（exit 2，一頁都唔做、唔問模型），`ERROR` 嗰行（`wait_for_run.py` 嗰行一樣）以 `resume with --no-keep-arabic-numerals …` 開頭：**唔好加 `--overwrite` 成本重做**，續跑嗰個 command 照佢講加齊嗰幾個 `--no-…`，已封存嘅頁照算 current，未做嘅頁用同一套舊做法做，成本書一致，唔會溝亂；之後每次跑呢本書（分段跑、`finish_book.py` exit 3 叫你補做嘅頁）都要加返呢幾個 `--no-…`；書眉、代字呢類缺陷交〈拼書之後修書〉。續跑都唔好重跑 `book_profile.py`（profile 改咗，已封存嘅頁一樣唔算 current）。新開嘅書唔使加任何嘢。

   **跨頁嘅表**：`proofread_pages.py` 逐頁封存晒之後，會喺同一個輸出目錄行一次 `scripts/stitch_tables.py`（唔問模型、唔使 GPU），睇晒目錄入面每一頁（唔止今次跑嗰啲），將印跨頁嘅表寫成一張，放喺表開始嗰頁：上一頁最後係表、下一頁第一樣都係表（書眉、頁碼唔計），而且有結構證據（重印同一個表頭、欄數一樣、或者格線對得上）先併；下一頁張表有自己標題、有自己嘅表頭，或者係一系列同表頭嘅編號表，就當兩張表。位置啱但結構講唔定就唔併，兩頁記 `table-continuation-undecided` 留畀人睇對照圖 `page-NNNN-stitch-01.png`；欄數唔同而格線對唔到每一格，就記 `table-continuation-unaligned`，唔會寫錯位嘅行。一格長字被頁切斷、後半印喺下一頁同一欄嘅頂（續表第一筆「紀錄」冇名、或者一段比框頂低嘅字），而引擎 B 嘅換行顯示嗰格最後一行係整行（即係被切斷，唔係喺本頁完結），就駁返落嗰格，記 `table-continuation-cell-joined`。續頁淨係得嗰截表嘅話文字會係空——**唔係空白頁**，佢嘅 sealed JSON `tableStitch` 記住原文同搬咗去邊；`finish_book.py` 拼書時照封存嘅（空）文字拼，唔好自己再手動拼。已經封存嘅舊目錄可以直接跑 `python3 scripts/stitch_tables.py OUTPUT_DIR --renders RENDER_DIR --drafts OCR_A_DIR --drafts2 OCR_B_DIR`（加 `--dry-run` 淨係睇佢會點判）。細節見 `references/long-book-workflow.md`〈跨頁表格〉。

## 做完之後：`finish_book.py`，然後交付

Phase 3 封存晒全書之後，一個 command 做晒拼書、修書、定稿同疑問清單（〈分三次交付〉嘅第三次）：

```bash
python3 scripts/finish_book.py BOOK > BOOK/finish.log 2>&1      # 放背景
python3 scripts/wait_for_run.py BOOK BOOK/finish.log             # 前景，timeout 600000，照〈安全並行〉等
```

`BOOK` 係本書目錄：放 phase 3 嘅封存頁、兩個引擎嘅底稿、render、`book-profile.json` 同 page manifest 嗰個。每樣佢自己搵（本書目錄嘅慣用名、profile 記住嘅路徑、或者本書目錄入面唯一一個）；搵唔到或者有兩個，佢會講明，就用 `--proofread`、`--renders`、`--ocr-a`、`--ocr-b`、`--profile`、`--page-manifest` 指明。佢按次序做四步：

1. 拼書：驗 page manifest 要嘅每頁都封存咗（封條啱、狀態 complete、對住 manifest 嘅 render 封），將封存頁原文加 page marker 寫入 `assembled/`（`segments/`、`ordered-segments.json`、`page-sources.json`、page manifest 副本），用 `assemble_ocr_segments.py` 砌 `combined-annotated.md`；
2. 修書：`repair_book.py`（寫 `repaired/`），連佢問模型嘅問題，同 phase 3 一樣用本機 Qwen、xhigh；
3. 定稿：`finalize_page_markers.py` 用修書寫嘅 `boundaries.json` 出 `BOOK/final.md`（檢查過冇 page marker），再跑 final audit；
4. 疑問清單：`BOOK/doubts.md`，按類同掃描頁碼列出流程定唔到嘅位：要查資料嘅專名（research queue）、phase 3 嘅疑點、修書嘅疑點、修書之後自動檢查仲見到嘅缺陷、final audit 嘅錯誤；最可能要改字嘅排先（開頭有每類幾多項嘅表），書眉、頁碼嘅雜訊摺埋喺最尾；全部細節喺 `BOOK/finish/doubts.json`。

修書要問模型好多條問題，要跑幾耐未量過（書長就可以好多個鐘），所以**一律放背景**、照〈安全並行〉用 `wait_for_run.py` 等（嗰行會講做到第幾步、修書收咗幾多個模型答案）；唔好前景跑，前景 call 一到 harness 時限就俾人殺咗。每步做完嘅嘢都留低：再跑同一個 command，已經係最新嘅步驟會跳過，修書由上次停低嗰度續（已經答咗嘅問題唔再問）；拼書之後有頁重新封存過，舊 `assembled/` 會搬去 `assembled.stale-…/`，唔會刪。同一本書淨係跑得一個：已經有一個跑緊，第二個乜都唔寫就 exit 2，用 `wait_for_run.py` 等返第一個，唔好再開。`final.md`、`doubts.md` 寫咗出嚟就係用戶嘅：再跑嗰陣，佢哋唔係 `finish_book.py` 上次寫嗰份（例如用戶改過字、剔過疑問），舊檔會搬去 `final.edited-<時間>.md`／`doubts.edited-<時間>.md`，唔會蓋咗，嗰行會講；照講畀用戶知，新 `final.md` 冇嗰啲改動。所以用戶叫你改完 `final.md` 之後，唔好為咗重跑檢查再跑 `finish_book.py`；要重跑 final audit 就淨係跑 `python3 scripts/audit_ocr_markdown.py BOOK/final.md --mode final --summary-only`。佢嘅 stdout 淨係一行 `[finish] RESULT exit=N …`，加 `final.md`、`doubts.md` 兩個路徑；每步嘅詳細輸出喺 `BOOK/finish/finish-book.log`。照 exit code 做（`wait_for_run.py` 嗰行一樣會講）：

- **exit 0**：做完，交付（見下面）；
- **exit 3**：有頁未封存（phase 3 未做完）：照嗰行講嘅頁跑 `proofread_pages.py`，做完再跑 `finish_book.py`；
- **exit 6**：問唔到模型（server 冇開）：已經答咗嘅留低，server 返嚟再跑同一個 command；一直都起唔到就加 `--no-model`（唔問模型，問題全部寫入 `doubts.md`）；
- **exit 4**：俾人停咗（SIGTERM、Ctrl-C）：再跑同一個 command；
- **exit 1**：有一步失敗（拼書或者修書驗唔過、finalize 拒絕、定稿仲有 page marker）：睇 `BOOK/finish/finish-book.log` 尾幾行（`tail -20`），照實話畀用戶知；唔好淨係重跑，亦唔好自己拼書、改封存頁、切裁圖或者手寫 `final.md` 嚟補；
- **exit 2**：參數錯、搵唔到輸入或者有兩個、輸入喺 `assembled/` 入面（嗰個 folder 過時會成個搬走）、封存頁俾人改過、或者同一本書有另一個 `finish_book.py` 跑緊（用 `wait_for_run.py` 等返佢）：照嗰行講嘅改好先再跑。

**唔好自己覆核。** 由開 phase 3 到交付之後，agent 都**唔准**：逐頁睇頁圖、用 `zoom_image` 放大或者用 `read_file` 讀頁圖同裁圖、自己切裁圖、自己裁定（adjudicate）字或者標點、讀 sealed `.md`／`.json` 或者 run report 嚟搵錯、自己手改 `final.md`（用戶核完圖叫你改先改，見〈核心流程〉），亦唔准叫 subagent 代你做以上任何一樣（佢一樣用緊同一個 server）。呢啲全部由流程做：phase 3 同修書步驟喺自己嘅 process 入面對住裁圖問模型，唔經對話；定唔到嘅寫入 `doubts.md` 交用戶。`doubts.md` 入面寫「要睇圖」「要對圖核」嘅位，係畀用戶做嘅，唔係畀 agent 做。本 skill 其他地方講嘅睇圖、核圖同覆核——〈先讀邊份規則〉同〈安全並行〉嘅 subagent 獨立核圖／visual audit、〈Markdown 結構〉嘅睇 PDF 字級同目錄 100% 圖像覆核、references 嘅 visual audit／visual closure——由開 phase 3 起都係流程或者用戶做，唔係 agent，亦唔係 subagent。點解：每張讀入對話嘅圖都塞入 Qwen Code 嘅 context，冇得清走。實測（Qwen Code 跑 30 頁）：新舊兩版 skill 都喺約 59 分鐘封存晒 30 頁，之後 agent 自己切裁圖、用 `zoom_image`／`read_file` 讀入對話、自己裁字（「All disputed glyphs have been adjudicated…」），新版做咗 1 個鐘、舊版 2 個鐘，最後 Qwen Code 以 `Context is too large to send safely after automatic compression … hard limit: 177000 … COMPRESSION_FAILED_OUTPUT_TRUNCATED` 退出（exit 1）：兩次都冇拼到書，冇 `final.md`。

**交付要短。** 幾句就夠：`final.md` 同 `doubts.md` 喺邊、入書幾多頁、幾多項疑問喺幾多頁（`finish_book.py` 嗰行有齊），同埋講明冇逐頁視覺核對、流程定唔到嘅位喺 `doubts.md` 要用戶對住原書核。唔好將 `final.md`、`doubts.md` 或者 log 成段讀入對話；`wait_for_run.py` 嗰行（或者 RESULT 行）講有 `WARNING` 就淨係 grep 嗰幾行（`grep -n WARNING BOOK/finish/finish-book.log`），照佢講嘅一齊話畀用戶知（例如引擎 A 嘅底稿唔係封存頁用嗰批、改過嘅 `final.md` 搬咗去邊）。

## 安全並行

- LLM subagent 只用嚟分段轉錄、版面重建同獨立核圖；raw OCR 唔計入 LLM slots，由主 agent 直接啟動 runner。兩個 OCR 引擎都用 GPU，各自一個常駐 worker（加 worker 只會同本機 LLM server 爭 VRAM），一次跑一個引擎。
- 本機 LLM server 同 PaddleOCR-VL 共用一張卡時，OCR 同 proofread 要分階段跑，唔好同時開；否則 OCR 會 OOM 或者令 LLM server 被逐出顯存。
- 就算 agent 本身係行喺嗰個 LLM server 上面，都照樣做得到：**前景**（foreground）shell tool call 執行期間 harness 冇 in-flight request，對話狀態亦喺 client 端，所以喺**同一個** command 入面停 server → 跑 OCR → 開返 server，對 harness 係透明嘅，代價只係下一輪 prefix cache 變凍（重新 prefill 一次）。用 `scripts/run_ocr_phase.py` 做呢件事，唔好自己手寫 stop／start，因為佢保證成功、失敗、SIGINT／SIGTERM／SIGHUP 都會 restore，restore 唔返會 exit 3 大聲報錯；佢仲會喺停 server 之前開一個獨立嘅 watchdog（唔喺同一個 process group），就算成個 command 俾 harness 殺咗（SIGKILL），watchdog 都會開返 server。實測（RTX 5090）：swap 成功 exit 0，OCR 失敗時 runner exit 2 照樣 restore 到 HTTP 200。
- **GPU 交接一定要喺前景行，唔准放背景**（Qwen Code 嘅 `is_background`、`&`、`nohup`、交接中途撳 Ctrl+B 轉背景，全部唔得）：server 停咗期間 agent 冇模型可以諗嘢。實測（2026-09-23，Qwen Code）：agent 因為成本書超過 shell 時限，將交接放咗背景，下一輪即刻撞正 server 停咗（`ECONNREFUSED`），重試兩次就退出，退出時仲殺埋交接（成個 process group 先 SIGTERM、200 毫秒後 SIGKILL），server 冇開返。所以長書要**分幾次前景 call** 做晒：
  - harness 嘅 shell 有時限（Qwen Code 預設 120 秒、最多 600 秒）：每個交接 call 都要將 tool call 嘅 timeout 設到 harness 容許嘅最大值（Qwen Code 係 `600000`）。
  - `run_ocr_phase.py` 嘅時間預算（機器設定 `env.sh` 嘅 `OCR_PHASE_MAX_SECONDS`，或者 `--max-seconds`）要**低過**嗰個時限，佢會留返一段時間 restore。要停 server 但冇預算，佢會拒絕開工（exit 2）；喺 harness 以外手動跑先用 `--max-seconds 0`。
  - **每個 tool call 淨係放一個 `run_ocr_phase.py`**：兩個引擎分開叫，先叫 `run_paddleocr_vl.py` 叫到 exit 0，再叫 `run_hunyuanocr.py` 叫到 exit 0。每次 `run_ocr_phase.py` 都由零開始計預算，用 `&&`／`;` 串埋兩個，總時間可以係預算兩倍，超過 harness 時限就會喺第二個中途被殺。
  - **唔好將輸出 pipe 去 `tail`／`head`**：`echo $?` 會變成 `tail` 嘅 exit code（實測 phase exit 75，印出嚟係 0），`head` 提早收 pipe 仲會令 runner 寫 log 時死咗。要截短就先寫落檔：`python3 scripts/run_ocr_phase.py -- … > ocr-phase.log 2>&1; echo "exit=$?"; tail -20 ocr-phase.log`。最後一行 `[ocr-phase] RESULT exit=N …` 一定會印，照佢做：
    - **exit 0**：做完；
    - **exit 75**：預算用完，runner 喺兩頁之間停、封存咗嘅頁照留、server 已經開返——照樣再叫**同一個** command，直到 exit 0（runner 自動跳過已封存嘅頁，上次失敗嘅頁會再試）；
    - **exit 1**：有頁失敗／被拒，或者預算連一頁都唔夠（模型載入食晒時間，或者某一頁卡死）——**唔好淨係再叫**，睇 runner 嗰行 `failed`／`blocked`／`deferred` 同 ERROR；
    - **exit 2**：設定錯，乜都冇跑；**exit 3**：server 冇開返（watchdog 會再試；一直冇就手動開）。
  - 萬一成個 command 俾 harness 殺咗（timeout、Qwen 退出），watchdog 會殺埋 OCR runner、等顯存放返、再開 server，所以 `OCR_PHASE_RESTORE_CMD` 一定要可以重複執行而唔會開多一個 server（`systemctl --user start` 得；`nohup server &` 唔得）。
  - 顯存夠、唔使停 server（`run_ocr_phase.py` 見到夠顯存就唔會停 server）：唔涉及交接，可以放背景。
  - 用住 server 嘅長步驟（`book_profile.py`、phase 3 `proofread_pages.py`、`finish_book.py`）唔涉及交接，行得耐過 harness 時限就放背景，輸出寫落一個新嘅 log 檔（例如 `python3 scripts/proofread_pages.py … > proofread.log 2>&1`），跟住照下一點靜靜哋等；但：(1) 背景跑緊嘅時候唔好開任何 `run_ocr_phase.py`——佢會停埋佢哋用緊嘅 server；(2) Qwen Code 退出會殺晒背景 shell（SIGTERM，200 毫秒後 SIGKILL），非互動模式要等 `wait_for_run.py` 報做完（exit 0 或 1）先好結束；兩個都係逐頁封存，被殺咗重跑會續。
- **背景長步驟跑緊嘅時候淨係等，唔好自己睇**：唔好 tail log、唔好讀已封存嘅頁、唔好喺度做其他要諗嘢嘅工夫（例如寫筆記；要做就等呢步做完先做；放大頁圖研究本書就幾時都唔做，見〈做完之後〉），淨係一次又一次叫：

  ```bash
  python3 scripts/wait_for_run.py OUTPUT LOG
  python3 scripts/wait_for_run.py BOOK/proofread LOG --progress BOOK   # phase 3
  ```

  前景行，tool call 嘅 timeout 設 `600000`。`OUTPUT` 係嗰步寫嘅嘢（`proofread_pages.py` 嘅輸出目錄、`book_profile.py` 嘅 `book-profile.json`、OCR runner 嘅輸出目錄、`finish_book.py` 嘅本書目錄 `BOOK`），`LOG` 係上面嗰個 log 檔。佢唔問模型、唔連 server，每隔十幾秒睇下檔案同 process；做完即刻返，未做完就等夠 570 秒（`--timeout`，一定要低過 harness 嘅時限；tool call 冇設 timeout 嘅話 Qwen Code 係 120 秒，就用 `--timeout 110`），最後淨係印**一行**：做完未、封咗幾多頁／總共幾多頁、每個鐘幾多頁、幾多頁失敗，做完仲有 run report 嘅路徑（book profile 就講做緊第幾步）。等 phase 3（`proofread_pages.py`）就加 `--progress BOOK`：佢每 5 分鐘同返嚟之前重整 `BOOK/proofreading.md`，嗰行最後講埋呢個檔同校對咗幾多頁（用戶問先講，最多每個鐘講一次，見〈分三次交付〉）；整唔到都唔改 exit code。照 exit code 做：
  - **exit 75**：仲跑緊——即刻再叫同一個 command，中間唔好做其他嘢；
  - **exit 0**：做完，去下一步——但嗰行講有 `WARNING`（exit 1、4 嗰行都可能有）就先睇晒嗰幾行（`grep -n WARNING LOG`，唔使睇成個 log）：佢哋講呢步做完之後要跟嘅嘢（例如 profile 同異體表對唔上要重建 profile、引擎偏好喺抽查頁唔再成立要重做嗰部分嘅 profile），照佢講嘅處理咗先去下一步；
  - **exit 1**：做完但有失敗（有頁失敗或者被拒、ERROR、Traceback、異體投票嘅 call 全部失敗）——睇 run report 同 log 尾，唔好淨係重跑；嗰行講 `did not start` 就係個步驟根本開唔到工（佢唔認啲參數、搵唔到 script、搵唔到 `python3`）——同一個 command 再開都係咁，照嗰行講嘅錯改好 command 先再開；
  - **exit 4**：個 process 冇咗但未做完（俾人殺咗、死咗、中斷咗，或者 OCR 用完時間預算）——重跑同一個 command，封咗嘅頁會留；
  - **exit 2**：`wait_for_run.py` 自己嘅參數錯，或者冇 process 又冇 `LOG` 呢個檔（路徑錯咗）——檢查兩個路徑，唔好因為咁就重跑。

  點解：agent 自己同呢啲步驟用緊同一個 server、同一張 GPU，agent 每行一輪都要將成個對話由頭再送一次畀 server。實測（Qwen Code，一本書）：99 分鐘嘅 book profile 期間 agent 行咗 84 輪（睇 log、放大頁圖、寫筆記），每輪大約 11 萬 prompt token，大半冇用到 prefix cache，加埋 930 萬 token，估計食咗 server 大約三成時間；phase 3 開 2 條 lane，agent 喺旁邊行咗 73 輪嗰次每個鐘得 7 頁，冇 agent 嗰次每個鐘 17–21 頁（server 嘅排隊冇記錄，所以差距係咪全部因為 agent 未證實，但時間對得上）。所以開長步驟之前亦要將對話保持短：要記住嘅嘢寫一兩句總結，唔好將 log、JSON 成段貼入對話。
- 同時運行嘅 LLM child 數量不得超過平台實際可用 slots，亦最多八個；agent tasks 多過 slots 時分 wave 執行。Worker／auditor 預設沿用主 session 嘅有效模型策略，唔喺通用技能鎖死平台 model ID。
- 多份獨立 Markdown/PDF pair 可以一檔一 agent 並行；每個 writer 嘅檔案範圍必須互斥。
- 單一長書亦可以按連續頁段分工，但每個 agent 只寫獨立暫存 segment，例如 `segments/p001-080.md`；最終 Markdown 由 `finish_book.py` 拼、修同定稿（見〈做完之後〉），唔好自己砌。
- 開工前列明 PDF 頁數、頁段、marker 範圍、表格／尾頁／缺頁風險同輸出檔。唔好畀多人同時改同一份最終檔。
- segment 交界、拼書驗證同 final audit 由 `finish_book.py` 做；主 agent 處理 writer 之間嘅衝突，唔逐段睇圖覆核。subagent 回報唔等於全文完成。
- 交付前收齊所有 writer 同 read-only auditor 嘅 final report，確認冇 active、未合併或可能再寫入嘅頁段 task。獨立覆核後再 patch，受影響 scan 要重新獨立覆核；啟用 `release` 時，亦可以建立 canonical sealed amendment ledger，再用 `validate_review_evidence.py` 驗 status、reviewer、coverage 同目前 hashes。
- Writer 封 candidate 後要停止寫入；independent verifier 只核 formal seals，唔採納未封存嘅 live bytes。Verifier open 0 先可轉 final；如果仍要 patch，重新指定唯一 writer、產生新 candidate，再由另一位 reviewer 重核，唔可以一邊覆核一邊繼續改同一份 artifact。
- `release` evidence 要分清目前生效嘅 `lifecycle: active`，同被排除嘅 `historical`／`superseded`；後者要標 `classification: exclude`，用非空 `exclusion_reason` 交代，`superseded` 仲必須有指向 active included evidence 嘅 `superseded_by`。任何 provisional、未驗證或 failing artifact 都唔可以進入 active release closure。

## 工作 profile

Profile 只控制證據封存重量。對圖核字一律由流程做（phase 3 同修書步驟對住裁圖問模型），定唔到嘅交用戶；邊個 profile 都唔會變成 agent 喺對話入面逐頁睇圖。先揀最低足夠 profile，再按實際素材疊加專項 gate；唔好按書名、固定頁數或上一冊做法自動升級。

- `basic`（預設）：單一文件、單一 writer，無複雜跨頁結構或可重播交付要求。`finish_book.py` 做晒拼書、修書、定稿、final audit 同疑問清單；唔強制建立 release plan、tool snapshot 或 receipt。
- `structured`：有 page markers、跨頁 join、缺頁／重複掃描、分段或多 agent。page list、segment assembly 同 boundary manifest 由 `finish_book.py` 寫（`assembled/`、`repaired/boundaries.json`），再按實際需要加專項 auditor；多 writer、重核 late patch 或外部復原本身唔會自動升級。
- `release`：只有用戶／目標 repo 明確要求可重播 evidence closure、跨 release 證據重用，或者決定要將現有多 writer／獨立覆核／外部復原證據封成 durable closure 時先啟用 sealed review ledger、release plan、tool snapshot、receipt 同 final audit。

來源校勘符號、星號題名註、長目錄、表格同外部復原係互相獨立嘅 feature gate；只喺來源實際出現時啟用，亦唔單憑其中一項自動揀 `release`。唔適用嘅 artifact 記做 `not-applicable`，唔為湊齊流程建立空 sidecar。

## 核心流程

1. 找出 PDF，確認 PDF scan page count；有凡例、編輯說明就先讀，定好交付範圍。
2. 保留檔首 `---` metadata；只有 PDF、既有 OCR 或可靠同版書目清楚提供時先補 metadata。
3. 照〈OCR 工具次序〉：render 同認版式、兩個引擎、book profile、phase 3。
4. 照〈做完之後〉：`finish_book.py` 拼書、修書、定稿、寫 `doubts.md`，然後交付；唔自己覆核。

以下係成品要守嘅規矩，由流程嘅 scripts 做（phase 3、`repair_book.py`、`finalize_page_markers.py`），用戶按 `doubts.md` 核書時亦照佢哋：

- 段落、heading、list、table、表單同圖說按〈Markdown 結構〉重建；頁面家具按〈頁面家具〉刪。
- 拼書稿保留 `<!-- page_... -->` 定位；逐個 marker 判斷刪除後應係正文 join、真正 paragraph break、新 list item，定同一 list item 續文（`repair_book.py` 寫 `boundaries.json`，`finalize_page_markers.py` 照佢刪），判斷時保留原始 leading whitespace。
- 若頁底註腳插斷跨頁正文，先接完整正文，再將註腳放到所屬完整段落後；核對註號順序。移動任何註腳／題注後重判相關 boundary。
- 用戶核圖之後叫你改一個錯字：搜尋全書同形／一字之差嘅人名、官名同固定語，將命中逐處列畀用戶核（唔做全域替換，唔自己睇圖定）；改完 `final.md` 就係最後一次改文，依賴舊 bytes 嘅檢查（例如 final audit）要重跑。

`structured` 文件先建立 page manifest，分開記 source/render、scan facts、重複／缺頁同 `marker_expected`；boundary、notation、TOC 同 review evidence 各自用專責 contract，唔靠一個 status 欄包辦。`release` 文件先收齊 review，以 `validate_review_evidence.py` 驗 late amendments、以 `plan_release_rebuild.py` 找 stale descendants、用 `assemble_ocr_segments.py` 重播，再驗 release plan、finalize receipt 同 final audit。完整次序見相關 references。

若來源明確用星號題名註，先由凡例／頁圖確認該 apparatus，先用 `audit_title_notes.py`；普通 Markdown `*` list／emphasis 同題注語法可能相撞，auditor 只係結構 gate，ownership 仍要由用戶逐 heading 核圖。所有 note→running-body 跨頁 transition 預設 actionable；只可由 project-local、綁定目前 target／boundary hash 同逐項視覺證據嘅 transition review 放行，唔可以靠來源句式、語言或詞頭猜。

## 完成狀態同 canonical output

- 分開報告四條軸：OCR／scan coverage、流程校對（phase 3 同修書；冇人逐頁睇過 PDF，唔可以報做逐頁視覺校對；未定案嘅喺 `doubts.md`）、deterministic release closure、repo／publish delivery。前三者 open 0 唔自動代表檔案已 tracked、committed 或發布；未追蹤／ignored／repo 外輸出要如實交代，亦唔自動 stage 或 commit。
- `release` profile 嘅 canonical final path 由 schema v2 receipt `output.path` 決定，唔預設一定有 `release/final.md`。直接 receipt-bound／final-audited public Markdown 可以係唯一 canonical output。
- 如果同時宣稱 internal 同 public 兩份 final，兩份 target bytes／SHA 必須一致，並各有 current receipt＋final audit；或者由 post-final bundle 明確封存 canonical target、secondary copy 同 parity。Output path 唔同時 receipt hash 可以唔同，唔可以誤當內容不一致。
- 回答既有 release「而家仲係咪完成」時做 read-only current-seal check（唔係另一個 profile，仍屬 `release` profile）：解析 receipt target、重算 target／receipt／plan／source hashes、驗 release plan、要求 rebuild planner direct／transitive stale 為零，並重跑 final audit（`audit_ocr_markdown.py` 冇 `--check-only` flag；唔加 `--json-report` 只睇 stdout 同 exit status，或者將 `--json-report` 寫去 discovery scope 以外嘅暫存路徑，唔好覆蓋已封存嘅 pass 報告）。舊 `pass` JSON 或 pre-final root summary 本身唔證明目前 bytes 仍然有效。

## 回歸測試（golden reference）

改咗任何 prompt、任何 threshold、任何 merge 規則之後，**一定要跑**：

```bash
python3 tests/run_regression.py OUTPUT_DIR            # 只睇結果目錄，唔使 GPU
python3 tests/run_regression.py OUTPUT_DIR --strict   # 連 machine 級都當失敗
```

`tests/cases/*.json` 每本書一個檔，入面係一條條 assertion。**Assertion 分三級，因為佢哋唔係同樣可信：**

| provenance | 意思 | 失敗會點 |
|---|---|---|
| `human` | 有人真係核過頁圖，講明頁上係乜 | 硬失敗 |
| `regression` | 曾經出過、已修好、唔准返嚟嘅 bug | 硬失敗 |
| `machine` | 模型讀出嚟、有 adversarial 覆核，但冇人確認 | 只報 warning |

**點解要有呢個嘢**：本技能所有準確率數字本來都係喺一本書上面臨時度出嚟，改動係「講道理」而唔係「量出嚟」。同一節課入面，有兩次改動睇落係乾淨嘅勝仗，其實唔係——一次改標點 prompt，「，」由 125 個跌到 0（睇落完美），但同一次跑，有一頁變成差唔多逐個字後面一個「。」（每百字 96.6），另一頁一個都冇；另一次 crop matcher 出咗 141 張圖，第一張畀人核嘅就係錯 block。呢兩次都會喺呢度紅。

**Assertion 類型**：`contains`／`absent` 只比對漢字（標點、空白唔計），啱用嚟守字；守標點要用 `contains_exact`（逐字逐符號比對，只忽略空白），否則 formatter 刪走頁上嘅圈都會通過。另有 `json_field`、`table_row`、`table_count`、`golden_table`、`golden_tree`、`no_repeat_run`、`all_pages_*` 同純記錄嘅 `note`。三種表格 assertion 都經 `scripts/_tables.py` 讀表（pipeline 寫表、auditor 查表用同一個 parser），Markdown 表同 HTML 表一樣計；合併格嘅字喺佢跨嘅每一行都算。`golden_table` 將成張表同 `tests/golden/` 入面人手轉錄嘅表比：形狀、合併格佈局同每格都啱先算過，未過都會報形狀、啱咗幾多格同 CER。直排印嘅表寫法係一筆紀錄一行，但評分一筆紀錄一行、一欄一行兩樣都收（用戶裁定，2026-09-27），所以每張表照寫法同轉置（行變欄）各比一次（`_tables.orientations`；表頂成行嘅標題、表腳成行嘅附註留喺原位，淨係轉佢哋中間嗰截），報告講明用咗邊樣。轉置要計分真係好過照寫法先用：啱嘅格唔少過、CER 唔高過，而且其中一樣好啲；淨係睇啲格喺唔喺原位唔得——輸出將 golden 表頂嘅標題行寫咗做表上面一行字，照寫法就冇一格喺原位，轉置反而可以碰啱幾格（實測一張冇錯嘅表因此由 CER 7% 評成 56%）。`golden_page`（成頁同人手轉錄比錯字）嘅 golden 有表嘅話，輸出嘅每張表都照寫法同轉置試，淨係轉置令成頁錯字少咗先轉（`tablesTurned` 記低）。其他轉法——紀錄倒轉次序、每筆紀錄嘅欄位倒轉、成張表倒轉、轉九十度——用戶未裁過，一律當錯表：收咗就會將 pipeline 定向、讀向轉錯嘅表當啱。跨頁嘅大表係一張表：`golden_table` 寫 `"pages": [首頁, 尾頁]`，golden 係合併咗嘅成張表，輸出要將合併好嘅成張表寫喺呢幾頁其中一頁先算啱——逐頁搵表（一頁未收尾嘅表唔會駁落下一頁），攞最啱嗰張嚟比，每頁各有一截就只計到一截，報告亦會講輸出寫咗幾多張表。表格入面嘅字用 `contains`、`contains_exact`、`absent` 守嘅話，都可以寫 `"pages": [首頁, 尾頁]`，幾頁連埋當一段字查，因為合併咗嘅表寫喺邊一頁都得。`golden_tree` 比印出嚟嘅分類圖、大括號樹狀圖、組織系統表：golden 係人手寫嘅巢狀清單（每個節點一項，節點嘅註寫喺括號入面），輸出用巢狀清單、檔案樹（├── └──）、打橫嘅括號圖（┌ ├ ┼ └，好似維基文庫咁）定 Mermaid 圖都得，每條上下級連線同每條註都要齊，而且唔可以多咗錯嘅連線（例如一個節點同時掛喺啱同錯嘅上級）先算過；註要喺讀出嚟嘅樹入面係括號註，喺頁上第二度出現唔計。未過會報啱咗幾多條連線、錯咗幾多條、當係邊種畫法讀、註啱咗幾多。golden 入面某個節點掛喺邊度喺頁上睇唔清，assertion 可以寫 `uncertainParents`（`{"節點": ["可能嘅上級", …]}`，要包 golden 自己嗰個），輸出掛喺其中任何一個都算啱，報告講明用咗邊個（用戶決定 D10；`run_regression.py --no-uncertain-parents` 就淨係認 golden 嗰個）；同時掛喺兩個上級照算一條錯。讀樹嘅 parser 係 `scripts/_trees.py`，pipeline 嘅圖表步驟收模型答案都用佢，所以評分讀得到嘅畫法，pipeline 都收。

**加 assertion 嘅時機**：每次有人核圖裁決一個字、每次修好一個 bug。裁決 → `human`，bug → `regression`。唔好等到「有時間先做」，因為 assertion 嘅來源就係當時嗰個判斷，過咗就冇。

**唔好 overfit 校準書。** 本技能將來要處理幾百本未見過嘅書；校準書淨係例子。凡係「書係咁樣嘅」嘅假設——邊個引擎好啲、句讀有幾密、書眉喺邊、一頁幾多葉——都唔准寫死成常數或者 prompt 規則，要由 book profile 喺每本書自己嘅頁面量度。Golden case 係用嚟**測機制**嘅（例如 profile 要喺每本書自己量度、揀返讀得啱嗰個引擎），唔係用嚟調參數嘅；一個改動要同時喺所有 case 書都唔退步先算數。如果你發覺自己加緊一條「呢本書係咁」嘅規則，嗰個就係 overfit。淨係防真正失效（幻覺空白頁、無限重複、漏成段）嘅護欄可以係常數，而且都要喺所有書上面都成立。

**每本新書要記低佢覆蓋咗乜、冇覆蓋乜**（`traits` / `notCovered`）。加多幾本同類型嘅書價值好低；要揀**打得爛現有假設**嘅書：橫排、簡體、多欄、爛掃描。現有 case 覆蓋咗乜、未覆蓋乜，睇各個 `tests/cases/*.json` 入面嘅 `traits`／`notCovered`，唔好喺呢度列書名。

## 經驗泛化同技能更新門檻

- 每份材料新見到嘅字形、題名、頁碼、人名、地名、來源句式、版式、頁面家具同編輯符號，先放入目標 project 嘅 correction ledger、notation／inventory profile、boundary contract、source exception 或 review sidecar，唔直接寫入核心 skill。
- 只喺以下情況更新核心 skill／bundled scripts：同一失效類型喺至少兩份互不相關嘅出版物或 OCR pipeline 重現；單一案例揭示與書種無關嘅資料遺失、fail-open、hash／provenance 或安全問題；或者公開 contract 同工具實際行為矛盾。
- 核心規則同程式唔可以 hard-code 書名、scan number、人名、地名、單一版次符號或特定來源措辭。新 acceptance 必須由結構、exact locator、目前內容 hash 同視覺 evidence 證明。
- Regression tests（`tests/run_regression.py` + `tests/cases/*.json`）係以實書做 golden reference：每本書一個 case 檔，記低 PDF 路徑、sha256、頁數、`traits`／`notCovered`，同埋 pin 住實頁碼嘅 `human`／`regression`／`machine` assertion（見上面「回歸測試」一節）。實書名、實頁碼喺 `tests/cases/` 入面係允許亦係必要嘅；唔可以寫入嘅係核心規則、`references/` 同 bundled scripts，嗰度只描述失效類型。新教訓寫入對應 case 嘅 assertion（人核裁決 → `human`，修好嘅 bug → `regression`，失效類型記喺 assertion 嘅 `note`），跨書嘅陷阱先加入 `references/common-ocr-traps.md`。本 repo 冇 CHANGELOG，README 只係概覽。
- 每本書完成後先將新發現記做 candidate lesson。若現有 project contract 已經可以表達，而且未達以上門檻，預設結論係毋須更新技能。

## `release` profile 完整流程

以下 11 步只喺 `release` profile 使用；`basic`／`structured` 只跑上面核心流程同適用 feature gates。呢度講嘅核圖、覆核、reviewer 同 verifier 係人（或者流程對住裁圖問模型），唔係 agent 喺對話入面讀頁圖（見〈做完之後〉）；初稿一樣由 `finish_book.py` 出。

1. 找出 PDF/Markdown pair，確認 PDF scan page count，同時辨認書內 printed page number；先讀凡例、編輯說明同交付範圍。
2. 建立或核對 page manifest：記錄 source/render、scan facts、重複／缺頁同 `marker_expected`。若來源有特殊 notation，另建 project-local notation／inventory profile；boundary、writer 同 independent review evidence 亦各存 sealed sidecar，唔好靠 page manifest 一個 status 欄代替。內容位置凍結後先產生適用 inventory；之後再移字／題注就重建。衍生 audit／inventory 要封 generator toolchain hash 同 invocation profile；要偵測 skill/tool 升級，release plan 亦要收錄 project-local tool snapshot，並由報告 typed-depend on 該 snapshot。
3. 保留檔首 `---` metadata；只有 PDF、既有 OCR 或可靠同版書目清楚提供時先補 metadata。
4. render 足夠解像度嘅頁圖或 crop；確認現有 render 數量同 PDF 頁數一致。
5. 改文前掃 `[]`、page marker、OCR notice、頁面家具、可疑拉丁／符號及已知高信心錯字；將命中分類成 OCR、來源內容或合法格式。
6. 按頁處理 reviewer 核圖之後提出嘅修改（`doubts.md` 係佢哋嘅起點）：先字、後段落、heading、list、table、表單同圖說。
7. reviewer 確認一個錯字之後，搜尋全書同形／一字之差嘅人名、官名同固定語，逐處交 reviewer 核；唔做全域替換。
8. 校對期間保留 `<!-- page_... -->` 定位。逐個 marker 判斷刪除後應係正文 join、真正 paragraph break、新 list item，定同一 list item 續文。產生 boundary manifest 時保留下一個非空行嘅原始 leading whitespace；唔可以先 `.strip()` 再判斷 `list-cont`／nested `list-new`，亦要保留經 PDF 確認嘅兩個獨立 lists 之間嘅真正 break。
9. 若頁底註腳插斷跨頁正文，先接完整正文，再將註腳放到所屬完整段落後；核對註號順序。若來源有星號題名註，題注要跟返所屬 heading，唔套用普通頁底註腳位置；用 `audit_title_notes.py` 核對 marker balance 同跨頁 hazard，再由人逐 heading 判 ownership；移動題注後重判相關 boundary。
10. 收齊所有 review；canonical amendment ledgers 要先通過 `validate_review_evidence.py`。由目前 segment bytes、boundary／page facts、heading／list／table 結構同 note ownership 等全部 normative channels 機械導出 final changed-scan union，分開記 text、facts-only、structure-only、restored-to-baseline、delta-review 同 neighbor/context sets，唔用手填總數或相加 counts 代替 set arithmetic。任何 late patch 先用舊 release plan 跑 `plan_release_rebuild.py` 找 direct／transitive stale descendants，再依 dependency-first order 重建。凍結 segments 後用 `assemble_ocr_segments.py` 按 sealed ordered manifest 重播；separator 只可係空字串或全由 LF newline characters 組成，segment ranges、每段同組裝後嘅實際 markers、sealed page manifest 嘅 `marker_expected` 必須 exact，combined annotated 要 byte-for-byte 相同。
11. 建立並用 `validate_release_evidence.py` 驗證 pre-final `release-plan.json` 嘅 discovery inventory、classification、full/subset dependency hash、active closure、DAG 同必要 reconciliation evidence binding；任何 active TOC evidence type 都強制要 `reconciliation_scope`，plan 唔包含待生成 final／receipt／audit。Finalizer 必須帶 `--release-plan` 寫 schema v2 receipt；output／receipt 唔可 alias plan／classified artifact 或新命中 pre-final discovery globs。再跑 final audit，重驗 plan 同 receipt exact active closure；legacy v1 receipt 必須重新 finalize。Post-final auditor 只可 read-only，發現任何內容或結構問題就返回第 10 步；要完整成品 inventory 就另建 post-final bundle plan，唔回餵 finalizer。

## 真正缺失嘅印刷頁

- 先證明頁面真係唔存在於 PDF，而唔係 OCR 漏頁、spread 次序錯、旋轉頁、重複頁或 render 漏檔。
- 先找本地舊版、raw OCR、完整 render 或同 repo 底稿。只有原 PDF 真缺頁時，先用外部同版資料復原正文。
- 外部資料必須可以確認為同一版本；優先完整同版頁圖。無完整頁圖時，以兩個獨立同版來源交叉核實字詞。
- 保存 evidence manifest，記錄 PDF hash、缺頁位置、來源、復原文字、證據強度同未能視覺核實嘅標點／行款。
- 在 metadata 同最終回覆透明披露；唔可以將非視覺復原講成逐頁圖像校對。

## Markdown 結構

- 全書題名用 `#`；大篇／主要文件用 `##`；章節、呈文、批答、箚覆等按父子關係使用 `###` 以下層級。
- heading 層級除咗按語義，亦要睇 PDF 字級、位置同副題關係。完成後檢查 heading 前後空行同有冇意外跳級。
- 同一語義段落寫成一個 Markdown 段落；唔保留 OCR 原始行寬。
- 目錄、條文、問題、辦法、證據同明顯枚舉可用 tight bullet list；保留原項號，項目之間唔加空行。
- 跨頁同一 list item 嘅續文縮入該 item；新項目另起 bullet。唔好因數字開頭就自動當新項。
- 長目錄先逐 scan 建立每項末端印刷參照 inventory，同 recovery ledger 記錄漏抽／誤併；再由獨立 reviewer 對全部參照做 100% 圖像覆核，唔只抽查差異。
- 目錄 item、分組 heading 同正文 TOC-eligible heading 要分開建 ledger／inventory；非 TOC-eligible heading 要逐項記 exclusion reason。正文同目錄係兩套來源文字，保留核圖確認嘅原參照、註號、題名同次序。
- 目錄跨卷、跨冊或跨交付範圍時，先定義 `reconciliation_scope` 同互斥 partitions；只喺同一 scope 內比較 count／mapping，scope 外每項亦要有明確 disposition，唔可以用全目錄同局部正文硬對數。
- Scope validator 只驗 partition arithmetic 同五項 sealed evidence binding；ledger row/status、reviewer coverage 同 challenge 語義仍要由專用 invariant／challenge 工具或人工逐項審核，否則唔可以聲稱對賬完成。
- 例行裝置省略可以獨立分類；涉及語義、人名、官職、日期、數字嘅高風險異文，以及每個頁碼差額或重排，都要經第二位 reviewer challenge。頁碼 mapping 另設細分類 disposition，唔可以改寫目錄印刷參照去迎合正文。
- PDF 明顯係表格就重建表格：冇合併格用 Markdown table；有合併格（一格跨幾行或者幾欄，例如一格附註管住幾行、一個標題蓋住幾欄）就用 HTML `<table>`，合併格用 `rowspan`／`colspan` 表示。Markdown table 表達唔到合併格：拆格補空白格等於話啲格係空，將同一段字抄入幾格等於話頁上印咗幾次，兩樣都唔忠實。直排表格按版面理解欄列，唔照 OCR 行序硬排。
- HTML 表淨係用嚟載合併格；冇合併格嘅表一律寫 Markdown table，純文字都睇得明。HTML 要乾淨：`<table>`、表頭行可用 `<thead>`／`<th>`、每個 `<tr>` 一行、`<td>`；`rowspan`／`colspan` 淨係大過 1 先寫，格內換行用 `<br>`，字照原書，唔加 style 或者其他 tag。
- 表格總數、條號、人名數、A–J 等結構 invariants 要另行計算驗證，唔好只靠閱讀語意。

## 頁面家具

- 刪除重複頁眉、頁腳、書脊、頁碼、承印資訊、卷冊／叢書邊欄、OCR 工具標題同空白頁 notice。
- 只刪明顯非正文。似家具但同正文黐住，或者課名／書名可能屬正文時，要對 PDF 先定：修書步驟問模型，定唔到就入 `doubts.md`。
- OCR 話空白嘅頁仍要睇全頁 render 先標空白（淡字、印章、表格、圖、尾頁小字同另一篇題名）；呢個係認版式嗰陣睇 survey 報嘅 candidate（〈OCR 工具次序〉第 1 步），唔放大逐字讀。
- 全書識別通常保留只出現一次嘅扉頁、英文題名、版權／CIP、凡例、照片圖說、贊助題記同來源說明；呢啲唔係重複頁面家具。先界定係全掃描本定正文-only，唔好見到出版資訊就機械刪。

## Deterministic 驗證

技能附帶：

- `scripts/survey_pdf.py`（phase 1，任何平台）：render 全書 + 封存 `page-manifest.json`（schema 同 `audit_ocr_markdown.py --page-manifest` 完全一致，已實測通過驗證）同 `survey-report.json`（render provenance、幾何統計、空白／跨頁／重複 candidates）。render 命名固定 `page-NNNN.png`，同兩個 OCR runner 對齊。已 render 嘅頁預設略過，`--overwrite` 先重做。
- `scripts/run_hunyuanocr.py`（phase 2，第二引擎）：同一套 sealed 契約嘅獨立 OCR 底稿。~2 秒／頁、~4.3 GB VRAM。**寫唔寫句讀、寫成咩形狀，要睇本書點印**（PaddleOCR-VL 一樣）：實測六本書，有書兩個引擎都寫咗幾千個符號，有書成本得十幾個；形狀亦會錯，例如將直排佔一格嘅逗號寫成「丶」、將 ▲ 寫成「厶」、將圈寫成「，」。所以引擎嘅符號唔當係頁上印咗乜嘅證明，句讀由 phase 3 對住裁圖讀；每頁 JSON 嘅 `sentenceMarks` 記住佢喺嗰頁寫咗幾多個句讀符號。佢嘅 grounding 框（成行得 `(x,y),(x,y)`）phase 3 讀底稿時會刪走，唔當括號。
- `scripts/proofread_pages.py`（phase 3，**merger 唔係 transcriber**）：兩個獨立引擎一致嘅字直接凍結；唔一致嘅位置由本書 profile 量度出嚟嘅引擎決定（`book-profile.json`；`--prefer-engine` 只用嚟人手蓋過 profile），唔交畀模型揀；profile 冇信心就全部裁圖。每第 N 頁（`--audit-every`，預設 20）係 audit 頁，嗰頁嘅分歧全部裁圖、數返邊個引擎啱，run report 嘅 `engineAudit` 見到另一個引擎明顯較好就報 drift，提示呢部分要重新量度。模型淨係做佢先做得到嘅嘢——加句讀、重建結構、刪頁面家具——分兩步：先**逐個版面 block 對住該 block 嘅裁圖加句讀**——每個 block 先問一次「圖上有幾多處印咗符號，其中幾多處係雙圈」（census；雙圈算一處，另外報），數到零就一個都唔加（實測唔問就會喺通篇冇標點嘅官報上憑空加圈加點），有就要求輸出接近嗰兩個數——按位置核對，所以寫「。。」唔會當多咗符號被拒，雙圈數差太遠就講明兩個數再問一次（本書 profile 冇見過雙圈就唔叫佢寫，淨係報 doubt；`--no-doubled-census` 用返舊 census）；項目符號（▲ ● ⦿ ◉ 等）照印寫（D5；「●」「⦿」「◉」單個或者疊住印（「⦿⦿」）用戶裁定係同一個項目符號嘅異體，寫邊個都得、評分當一樣，形狀唔會攞去問人；疊住印嘅當一處數；census 見到嘅形狀淨係封存做證據），導引點線同刪節號一律寫「……」（D4），點串數目另外由裁圖墨跡數（唔使模型），census 唔會少過佢；字序要一模一樣（大 block 分幾欄一組做，每組嘅字同裁圖頭尾可能差幾個字：答案啱啱係 block 入面頭尾一欄之內另一段字（異體字歸一），就當嗰段嘅讀法，符號擺返合併嘅字上面，記 `realigned`；要咁對位先得嘅重試淨係留佢同第一個答案都寫咗嘅符號），差一個字就重試，再唔得就淨係留返被拒答案同引擎 A 喺同一個位都印咗嘅符號（圈要一樣先算，印雙圈嘅書引擎 A 嘅單圈唔算），記 `punctuation-partial`，唔算 clean；兩邊冇一個位對得上先照用冇標點嘅字；頁上少數嘅「，」（印圈嘅頁入面零星幾個）逐個位對住細裁圖再問一次係圈、雙圈、點定冇嘢，淨係改嗰個位（`gapRechecks`）；每個 block 嘅 census、marks、結果記入 sealed JSON 嘅 `punctuationPasses`；加完之後，兩個引擎讀到嘅括號寫返入所屬 block（句讀步驟對住裁圖實測漏咗大部分括號；錯開一兩個字嘅當擺錯位搬返埋去，記 `engineBrackets`），再**成頁加結構**（heading／list／表格／刪家具），呢一步標點鎖死，加減搬一個符號都拒收（只准為 list 編號補括號）；表格唔靠模型照抄——引擎 A 嘅 `<table>` 由 `engine_table` 收返做 Markdown 表，但淨係收有證據撐住嘅：格仔對唔齊、得一行有字、格內有換行（分唔到係格入面啲字自己換行，定係引擎將幾欄塞入一格）、有合併格（引擎嘅 `rowspan`／`colspan` 冇第二個讀法證實，實測錯多過啱；交返 formatter 對住頁圖寫 HTML）、有一行係本書書眉（profile 量到嘅書眉，或者全書重複出現嘅字串），都會拒收。引擎 B 係證人：夠長嘅格引擎 B 一段都讀唔到（佢 loop 咗、讀少咗或者冇讀，冇反對唔等於證實）、格入面嘅字引擎 B 讀嘅次序唔同或者同一段用咗兩次（即係引擎拼接或者重複）、兩格用同一段引擎 B 淨係讀過一次嘅字（抄格），或者冇漢字嘅格有字母／數字而引擎 B 冇讀到，都會拒收。所有理由記入 `tablesRejected`。舊版有條「一格超過 60 字就當散文」嘅規則，係假設：真表嘅附註欄一格可以過百字，已經刪咗。逐 block 做得嘅頁，收返嘅表根本唔經 formatter：佢個 block 喺結構步嘅文本入面換成一行表格記號（`⟦T1⟧`），formatter 淨係要原封不動照抄嗰行，之後先將個表擺返入去；記號唔見咗或者重複就當結構步拒收（重試，再唔得就逐 block 砌），formatter 自己再寫一次嘅表（格仔同收返嘅表一樣）刪走（實測佢會將表轉返版面次序、將兩個表併埋一個、寫一頁數字用晒 token）。記號頂替嘅係成個 block 嘅合併文本，但係入面喺表第一格之前、或者最後一格之後嘅字，表冇一格有——例如淨係引擎 B 讀到、印喺表上面嘅標題（`block_spans` 將 block 交界一個引擎獨有嘅讀法交畀後面嗰個 block，即係個表），或者個表係成頁最後一個 block，引擎 B 喺佢最後一格之後讀到嘅字——以前就咁冇咗，冇 doubt（用砌出嚟嘅頁實測：兩個偏好同裁決都冇咗個標題，裁決仲話有印）；而家寫喺記號前後，連引擎喺嗰度讀到嘅符號（表格 block 冇句讀 pass；照引擎寫嘅次序擺，中間冇字嘅一對括號唔會倒轉，`marks_as_written`），記 `table-edge-text` doubt 同 `decisionChanges`（`decision: textLoss`，`rule: table-edge-text`，`--no-table-edge-text` 關；round 3 整合 review 搵到，用戶未裁）；邊字一半以上係頁上已經有、多過兩個引擎各自讀到嘅次數、而且喺頁上別處淨係引擎 A 讀到（合併寫引擎 A 嘅字，引擎 B 喺嗰度冇讀或者讀咗第二個字）嘅三字段（即係另一個引擎喺頁上別處讀過，例如引擎 B 將引擎 A 讀做 footer 嘅書腳、或者表自己嘅欄名再讀一次，D2 又冇放一次；引擎 B 喺別處讀錯一個字唔算，嗰度佢有讀），就唔寫，doubt 照講（`edge_copies`；逐段判，一段係引擎 B 一行或者一格讀到嘅字，淨係數字或者得一個字嘅段跟隔籬，`edge_verdicts`；一段啱啱係引擎 A 另一個、引擎 B 喺原位冇讀嘅 block 嘅全部字——例如葉碼——數字都唔寫，`block_copy`；成段喺表自己嘅格入面、引擎 B 讀多過引擎 A 嘅，係引擎 B 將表嘅格再讀一次，唔寫，`cells_copy`）。個表嘅字亦改為淨係喺佢自己 block 嘅合併文本入面搵，表頭尾一段長過表嗰一兩個字三個字或以上、又唔係數字嘅取代喺表邊切開（長一兩個字嘅係格自己嘅讀法，照留喺格入面）（以前喺成頁搵：表第一個字合併改咗、前面又有字，第一格會連前面成段正文食埋，寫兩次）；引擎 B 同第一格／最後一格喺同一行或者同一格讀到嘅字入返嗰格（引擎 A 漏讀格頭格尾，例如數字少讀一個位；`table_places`）；重建嘅表一樣，區域合併文本頭尾、個表冇用嘅字留喺表旁邊（睇字嘅位置，唔係淨係數次數；淨係引擎 A 讀到、重建冇用嘅字係引擎 A 對個表嘅讀法，唔當邊字；`rebuilt_edges`）。整頁一次過做嘅頁冇 block 位置放記號，先要 formatter 照抄（標籤格照引擎讀出嚟嘅原樣畀佢抄，因為刪字檢查對住合併文本；擺返收返嘅表嗰陣先倒轉）；佢將幾個收返嘅表併埋做一個（格仔啱啱係嗰幾個表加埋）就拆返做原本嗰幾個。輸出入面格仔內容相同嘅表（左右反轉咗嘅格照樣認得）會擺返 `recover_tables` 嗰個版面（sealed JSON 記 `tables`——每張表嘅 block、`format` 同內文——同 `tablesEnforced`），因為模型會將已經轉好閱讀次序嘅表再轉返做版面次序；formatter 加嘅 `<caption>` 照留，但佢反轉咗嘅格會擺返原樣——由右至左印嘅標籤格係 `fix_cell_direction` 喺定向之後，用純文字、甲乙兩個讀法、兩個次序各問一次決定，兩次都揀倒轉先倒轉，唔一致就照原樣留、記 `cell-direction-undecided`（詳見 `references/long-book-workflow.md`）。但 formatter 自己寫咗合併格，或者表入面有格外嘅字，就唔蓋過佢，記 `tablesDisputed`，嗰頁唔算 clean，交人判。收咗嘅表喺輸出入面搵唔返（寫成散文、刪走咗，或者包咗喺 code fence 入面）就記 `tablesMissing`，嗰頁唔算 clean。layout model 冇標做表、但引擎 B 讀佢次序唔同嘅長 block 會提名做可能係表（實測提名 11 個，4 個係表；引擎 B 將印出嚟嘅符號讀成字——例如全格逗號寫「丶」——會切斷做證據嘅一段字，所以亦用拎走咗本頁括號規則同符號規則當係符號嘅字形嘅引擎 B 讀法再睇一次，用戶決定 D21，`--no-mark-aware-witness` 關），佢入面搬咗位嘅字（引擎 B 嗰段成段喺引擎 A 嗰邊對得上）只寫一次，引擎 A 嘅字留喺原位，對唔上嘅照一般分歧處理；次序衝突頁上引擎 B 反駁咗嘅表格 block 改由引擎 B 嘅行加引擎 A 獨有嘅格嚟（引擎 B 嗰行讀埋落其他 block 嘅字就切走，已經有嘅格唔再寫，引擎 B loop 咗就唔做）；兩種都叫 formatter 對住裁圖、字鎖死咁重建成表（唔係表就答唔係；提名嘅 block 准用嘅字係兩個引擎喺 block 讀到嘅字，每個字取讀得多嗰邊嘅次數，唔止合併寫低嘅字——合併可以因為對齊將一格數字同另一格對埋而丟咗佢——用戶決定 D20，`--no-rebuild-both-readings` 關；同一個表被 layout model 拆開咗嘅 block——框重疊或者相距唔夠一個字位、頂邊或者底邊對齊、引擎 B 唔係照引擎 A 次序讀佢但又喺區域入面讀過佢大部分嘅字，例如自己一個 block 嘅表頭欄——連埋一齊重建，收咗就一齊由個表頂替（引擎 B 喺區域入面讀到嘅佢嘅字個表一定要有，唔係就當區域拒收）；自己被提名嘅 block 係自己一張表，唔收埋；成個區域拒收就淨係重建提名嗰個 block：用戶決定 D22，`--no-rebuild-region` 關；咁樣收咗嘅表，區域入面其他 block 留做表旁邊嘅文字，佢哋兩個引擎都讀到嘅字結構步一個都唔准刪——唔理刪字檢查嘅長度門檻——刪咗就當結構步拒收、重試，再唔得就逐 block 砌，頁面最後仲係冇就記入 `tableCharactersLost`：實測一頁課本表嘅表頭欄 20 個字咁樣冇咗，刪字檢查將佢對住表格入面同樣嘅字切碎，冇一段夠長，冇人知；所以有 block 位置嘅頁，刪字檢查淨係將散文同輸出嘅散文比，表格拎走先比），重建寫咗兩個引擎喺區域入面都冇讀到嘅字，最多兩個位（`UNREAD_TABLE_LIMIT`）可以留：每個位對住佢自己嘅裁圖問裁決（位置由格入面佢前後、引擎 A 淨係讀過一次嘅一段字定；喺 block 頭尾就將引擎 A 個框向外擴兩個字位先裁，因為引擎 A 冇讀到嘅字好多時喺佢個框外），裁決讀到同一個字（異體歸一）先收，一個唔係就照舊拒收，重試淨係講鎖字嘅原因、唔講裁決讀咗乜；收咗記 `table-unread-confirmed` 同 `decisionChanges`（用戶裁定 headerCharacters，2026-09-27，`--no-unread-table-characters` 關；實測一頁課本表嘅表頭格最後一個字兩個引擎都冇讀到，區域重建六次跑次次為咗佢拒收，而重建自己亦會讀錯字，所以唔靠重建一句話）；收咗嘅表同收返嘅表一樣問方向，轉法由引擎 B 嘅閱讀次序定，定唔到就問頁圖第一筆紀錄喺邊邊（用戶決定 D23，`--no-rebuilt-orientation` 關），引擎 A 喺嗰度讀到嘅括號逐格寫返（括號規則），收咗記 `table-rebuilt-unvouched`，引擎 B 反駁嘅表冇重建到就記 `table-marks-unread`（表格 block 冇句讀 pass、結構步又唔准加符號，冇一步讀過佢印咗嘅符號），sealed JSON 記 `tableNominations`、`tablesRebuilt`（詳見 `references/long-book-workflow.md`）。表格 block（連拒收咗嗰啲）入面兩個引擎都讀到嘅字，輸出少咗任何一個（書眉行除外）就記 `tableCharactersLost`，嗰頁唔算 clean——`droppedRuns` 唔睇表格 block，拒收咗嘅表要 formatter 重建，冇呢個檢查就冇人知佢有冇漏字；淨係一個引擎讀到嘅唔計，因為另一個引擎讀書眉、頁碼嘅字會對齊落表格 block 度。結構步失敗就退返逐 block 一段嘅純標點文本，表格 block 用收返嘅表頂上，表旁邊嘅字照寫喺表前後（表連佢旁邊嘅字要包齊 block 入面兩個引擎都讀到嘅字，唔係就用 block 自己嘅字，記入 `tablesMissing`；淨係引擎 B 讀到而表同表旁邊都冇嘅字記入報告），記 `STRUCTURE PASS REJECTED`（答案係空嘅、或者每級 effort 都截斷，都當失敗再問一次：截斷就由低啲嘅 effort 問；模型自己交咗個空答案（冇截斷）就用返原本嘅 effort 問；唔會當「characters preserved」收）；formatter 被拒而又冇 block 位置擺返啲表（`FORMATTER REJECTED`），全部收咗嘅表記 `tablesMissing`。全部用 `verify_characters` 機械驗證冇改過字。點解要分：實測整頁一次過做，同一頁同一設定跑三次，可以由「頁上每個圈都出齊」到「一個都冇」到「整頁被拒收」；block 短、裁圖對得準，就穩定。冇獨立 auditor pass；profile 有偏好時係確定性揀引擎，唔打裁決 call，profile 冇信心（或人手 `--prefer-engine adjudicate`）先會就每段引擎分歧裁圖問模型（上限 `--max-adjudications`）。兩類分歧例外，無論偏好邊個都會裁圖：**淨係數字／筆畫嘅分歧**（引擎會將直排括號、格線讀成「一」，而且兩個引擎可以一齊讀錯編號；相鄰嘅數字段會合併成一個爭議，整個數字一齊問；但一方讀到單獨一個〇、另一方冇字、隔籬唔係數字又唔喺表格 block 嘅，係頁上印嘅圈，唔入字亦唔裁決，留畀句讀步驟；一方喺嗰度讀到括號、另一方將同一個括號讀成「一」或者「八」嘅，係括號，唔入字亦唔裁決，對唔晒就淨係問剩低嘅字）同**一方用咗 Unicode 擴展區罕見碼位嘅分歧**（可能係忠實嘅異體字形，亦可能係亂配碼位，只有裁圖分得出）。一方多咗嘅字如果啱啱喺另一方印咗符號嘅位，而嗰個字形係**本書底稿**顯示呢個引擎寫嚟代符號嘅（例如直排佔一格嘅逗號寫成「丶」、▲ 寫成「厶」；全書底稿數出嚟，唔係固定清單），就當係嗰個符號讀錯，唔入字亦唔裁決（`mark-not-character`，用戶決定 D1，`--no-mark-rule` 關；但係當做符號嘅係「〇」而隔籬係數字或者另一個〇、或者喺表格入面，可能係零或者隱名，照舊交裁決，記 `markWithheld`）。對齊用異體歸一之後嘅字（寫出嚟仍然係兩個引擎自己嘅字），一個字嘅兩個寫法唔會移開錨點（`--no-folded-alignment` 關；實測一個標題字兩個引擎寫法唔同，對齊就將引擎 A 漏讀嘅一行黐埋呢個字做一段取代，偏好寫咗引擎 A 嗰一個字，成行 17 個字冇咗都冇 doubt）；不過有偏好嘅頁，歸一拆開嘅一段、長嗰邊係另一個引擎喺頁上別處讀過或者 loop 嘅，照原字對齊由偏好定，唔會變咗一段淨係一個引擎讀到嘅字寫多一次（實測一行讀咗兩次嘅署名因此寫咗兩次）。有偏好嘅書，一段取代入面偏好嗰個引擎讀少過另一個三個字或以上（通常係佢漏讀咗一行，黐埋隔籬讀法唔同嘅一兩個字；觸發唔一定係異體，實測仲有讀成「〇」嘅項目符號同葉碼），就拆開：同長嗰段照舊處理，多出嚟嗰段當另一個引擎讀到嘅字、照插入嘅規則，本書書眉連葉碼照舊拎走、唔會變正文（`lopsidedSplits`；`--no-lopsided-split` 關）；但係多出嚟嗰段自己不停重複（loop），或者嗰個引擎成頁讀法係 loop，或者一半以上偏好嗰個引擎喺頁上別處讀過（讀次序唔同，唔係漏讀，拆開會寫兩次），就照舊由偏好定。冇偏好嘅頁（裁決逐個問）唔拆：裁決睇到成段，D16 保住長嗰邊（benchmark 重跑喺呢啲頁拆開，反而將引擎 A 讀嘅摺縫書名當咗正文）。兩樣改字都記入 `decisionChanges`（`decision: textLoss`，`rule: folded-alignment`／`lopsided-split`）；次序測試因為歸一而結果唔同（合併定次序衝突）嘅頁，亦記一條 `folded-alignment`（`evidence.orderTest`）。合併完，一個引擎讀到嘅三個字或以上喺合併文本入面冇咗——逐個字計：合併文本有呢個字嘅次數少過嗰個引擎讀到嘅，而且連前後成三個字喺合併文本出現嘅次數少過喺嗰個引擎讀法入面（每個字都搵到、淨係少咗次數嘅，係引擎讀多咗嘅第二份，唔計）；搬咗位嘅字、另一個引擎用另一個次序讀嘅表頭、書眉同全書重複字串、括號規則同符號規則當係符號嘅字形、成頁讀法係 loop 嘅引擎都唔計——記 `reading-dropped`，嗰頁唔算 clean（`readingsDropped`；`--no-merge-loss-guard` 關）。三樣都係用戶 2026-09-27 裁定要修。兩個引擎喺唔同位置讀到同一段字（版權頁、標題、書眉），合併淨係喺引擎 A 嘅位置放一次，兩份唔同嘅地方當普通分歧，引擎 A 冇讀到嘅字留喺引擎 B 嘅位置（`moved-kept-once`，D2，`--no-move-once` 關；記 `moved-placed-once` doubt）。淨係引擎 A 讀到、冇分歧可以問嘅字（例如引擎 B 冇讀嘅表格標籤），如果同一頁嘅裁決喺每個問過嘅位都判引擎 A 嘅同一個字係讀錯、次次讀成同一個字，都對住裁圖問一次（用戶決定 D24，`--no-verdict-propagation` 關）。有偏好嘅書，淨係一個引擎讀到、一兩個字、符號規則同括號規則同書眉都解釋唔到嘅位置，唔再由偏好留低，交裁決對住裁圖問「有冇字」（D3，`--no-insertion-crop` 關；裁決話有字但寫少過嗰個引擎讀到嘅字數，唔收，照留引擎讀到嘅字，記 `insertion-partial`；預算用完就照舊留低，記 `insertion-unjudged`；`--no-adjudicate` 冇裁決可問，就照舊留低、唔記 doubt）。一段淨係一個引擎讀到、每個字都喺全書重複字串（家具 8 字串）入面、而且係引擎 A 成個 block 或者喺頁頭頁尾嘅字（翻印本頁邊嘅叢書名、書眉），問嘢之前就當家具拎走（用戶決定 D15，`--no-furniture-insertion` 關）。兩個引擎都將同一張表讀成格仔、但啲數企喺唔同行（一個引擎跳咗空格、將成欄嘅數向上搬，逐字對齊就會將兩格數字黐埋、漏咗或者留空——實測一張跨兩頁嘅年度數字表兩次跑都錯 11 格），合併之前先睇頁圖定跟邊個嘅格仔：由表嘅直線切欄，逐欄數印咗幾多行字，淨係喺兩個引擎嘅格數都啱啱對得上嘅欄入面比，邊個嘅行同印出嚟嘅行企得齊就跟邊個（一個引擎對得上、另一個對唔上嘅欄唔算證據：漏咗一格嘅引擎對唔上，搬晒位嘅反而對得上）；另一個引擎嘅讀法逐格擺入跟住嘅格仔，分歧留喺格入面照常處理；佢讀到而跟住嗰邊冇嘅格，擺入同一欄上下兩個對得上嘅格之間嗰個空格，當一個引擎獨有嘅讀法照常處理（問裁決，或者照偏好），擺唔落就成張表照舊合併——兩邊嘅字一個都唔會因為跟格仔而冇咗。頁圖定唔到（冇直線、冇兩邊都對得上嘅欄、或者打和）就照舊合併，記 `table-grids-misaligned`；跟咗就記 `table-grid-followed` 同 `decisionChanges`（建議決定 D26，用戶未裁，`--no-grid-follow` 關；淨係喺照讀法合併嘅頁做，次序衝突頁照舊成頁取一邊）。靠用戶決定或者建議決定先開嘅規則每改一處字，都記入 sealed JSON 嘅 `decisionChanges`（邊個決定、喺邊、改之前同之後、證據），用嚟對 golden 逐個決定數啱錯。裁決用嘅裁圖由該分歧喺引擎 A 字流嘅偏移直接定位（唔靠搵字），收窄到該欄、上下各伸八個字、包住兩個引擎之中較長嗰個讀法（跨欄腳就連下一欄，過咗 block 尾就向上移）、放大咗；裁決答嘅字（兩個引擎都唔係，或者「無」）會刪走一個引擎讀到嘅三個字或以上（唔係數字分歧、唔係本書書眉連葉碼），就唔收，照留嗰個讀法，記 `deletion-refused` 同 `decisionChanges`（D16，用戶 2026-09-27 裁定開，`--no-answer-deletion-guard` 關；舊裁圖 `--no-whole-run-crop`）——但係漏咗嗰啲字已經喺合併文本附近（前後 40 個字之內）照次序、密集咁出現（散喺佢字數兩倍之內），即係另一個引擎喺隔籬用另一個次序讀過，就收裁決嘅答案、唔留多一份，`decisionChanges` 記 `answer-accepted-reading-nearby`（用戶 2026-09-27 裁定；`--no-answer-nearby` 關），但答「無」而裁圖係字位裁圖嘅，照下面嘅盲讀檢查先收；全部係數字嘅唔算（兩份數字邊份先係多出嚟嗰份，頁面講唔到：實測收咗裁決嘅答案，刪咗擺啱格嗰份，留低黐錯格嗰份；而且表入面數字好易撞啱），照舊唔收；裁決答「無」、而裁圖係按估計位置切嘅直排字位裁圖（唔係成個 block、成個表或者兩段交界並排），就先盲讀嗰張裁圖，搵到爭議位前後嘅字、中間又冇嘢先刪，否則照留引擎讀法（盲讀喺個位讀到邊個引擎嘅字就留邊個），記 `nothing-unconfirmed`（`coverageRead`；用戶 2026-09-27 裁定，`--no-crop-coverage-check` 關）——實測兩張裁圖根本冇影到爭議位，裁決照答「無」，刪咗引擎 A 讀啱嘅字；表格 block 就整個表；淨係引擎 B 讀到、夾喺兩個版面 block 之間（或者喺頁尾）嘅字，對齊分唔出係上一段嘅尾定下一段嘅頭，兩段又可以喺頁上唔同位置，所以裁圖將上一段嘅尾（向閱讀方向伸出佢個框外）同下一段嘅頭並排拼成一張，提示講明點拼（`adjudications` 記 `boundaryCrop`，`--no-boundary-crop` 關；實測淨係影下一段頭嘅舊裁圖睇唔到印喺上一段腳嘅字，裁決會刪走佢）；會存做 `page-NNNN-adjudication-NN.png` 放喺 sealed JSON 隔籬，方便覆核。數字裁決答案必須係數字或者「無」，答咗其他嘢當無效（`adjudicator-invalid`）退返引擎偏好；合併咗嘅數字段入面兩個引擎一致嘅數字係鐵證，裁決漏咗就補返，補唔返就當無效。引擎 A 喺表格入面將零寫做「○」，對齊時當「〇」。裁決結果直接落入轉錄並記入 `adjudications`（`trigger`、`crop`、`resolved_from`、`needs_research`）。題名頁（有 doc_title 類 block、字少）會記入 `needsResearch`，唔會當已定案。印出嚟嘅**分類圖、系統圖**（用大括號或者連線將名目一層層分類）兩個引擎都讀唔到：引擎 A 嘅版面模型會將個圖連埋隔籬嘅正文當成一張表、辨字喺入面 loop；引擎 B 橫住逐行讀，將隔籬嘅註黐埋、漏成個名目，一個名目嘅字散落幾行，點合併都砌唔返棵樹。所以一個唔係正文嘅 block（版面標做表、chart、image、figure，或者喺一個冇字、標做圖嘅版面區域入面）讀出嚟係 loop 而引擎 B 冇同樣嘅重複，就喺合併之前行**圖表步驟**：裁嗰個區域，唔畀引擎嘅字（佢哋嘅讀法亂晒，會帶偏模型），淨係問讀圖模型（影印書兩葉之間嘅摺縫——位置由全書 layout 量出嚟，但要喺裁圖上見到摺縫兩邊嘅界線先剪，由界線剪到界線，見唔到就唔剪——喺裁圖入面剪走、兩邊接埋先問，摺縫上嘅書名唔會當咗名目，跨摺縫嘅註亦連得返：用戶決定 D25，`--no-fold-cut` 關）——冇圖答「非圖」；有就寫 Markdown 巢狀清單，名目嘅註寫「名目（註）」，有名目掛兩個上層就寫 Mermaid，睇唔清嘅另起一行「存疑：……」（記入 seal，唔寫入頁面）。答案用 regression 評分同一個 parser（`scripts/_trees.py`）解；冇樹、或者又自己重複又漏咗兩個引擎都讀到嘅字、或者被 token 上限截斷，就講明原因再問一次，再唔得就記 `chart-refused`，嗰個區域照舊做法（放埋一邊）。收咗嘅圖由兩個讀法入面剪走——引擎 B 係最符合個圖嘅一段連續行（引擎 A 喺其他 block 讀到嘅字、同埋留低做正文嘅格連住讀落去嘅字唔當係圖嘅；冇行計得分就唔剪，個圖放返引擎 A 個 block 嘅位置），引擎 A 嗰個 block 淨係留低引擎 B 喺圖以外讀到嘅格，當正文，裁圖用嗰幾欄正文自己嘅 box，唔係成個區域（引擎 B 一段字淨係擔保一格，loop 重複嘅格淨係留一格，其餘記入 `repeatedCells`）——其餘照常合併（次序測試唔計引擎 B 對個區域圖以外嘅讀法，同放埋一邊一樣；剪咗個圖變咗次序衝突、冇呢步又唔係，就收返個圖、照舊做法，記 `chart-withdrawn`），圖最後插返引擎 B 讀佢嘅位置（搵唔到就放頁尾，記 `chart-position-unknown`；唔會插入表格、標題行或者未閂嘅行內標記中間，會搬去嗰個結構之後，記 `outOf`；成頁淨係得個圖就唔格式化，個圖就係成頁）。檢查只係證據、唔拒收：冇引擎讀過嘅字（`chart-unwitnessed`）、引擎 A 喺嗰度讀到同引擎 B 喺頁上讀到、而個圖同引擎 A 其他讀法都冇嘅字（`chart-lost`）、模型自己寫嘅存疑（`chart-uncertain`）、個圖自己重複而冇漏字（冇拒收，照插，記 `chart-degenerate`）；圖寫咗一個頁上冇引擎讀過嘅字，而引擎喺嗰度讀到佢唯一一個異體，就改返引擎印嘅字形（`--no-chart-variants` 關）。用戶決定 D9：淨係有 doubt 嘅圖先交人覆核（`--no-chart-review-by-doubt` 就每個圖都交）。兩個引擎同模型一齊漏咗嘅名目冇任何訊號；邊個名目掛喺邊個之下亦冇第二個讀法可以核，要睇圖。sealed JSON 嘅 `charts` 記晒（裁圖 `page-NNNN-chart-NN.png`、樹、檢查、剪咗引擎 B 邊幾行、引擎 A 留低邊啲格、插喺邊），`decisionChanges` 記個圖同改咗嘅異體（`decision: chart`）；`--no-charts` 成個步驟關。兩個引擎一齊錯嗰陣佢哋係一致嘅（實測一個部件異體字就係咁），runner 對呢類位置冇任何訊號，要另外核圖。輸出係逐頁 sealed JSON + Markdown，可續跑。
- `scripts/book_profile.py`（phase 2.5）：量度一本書——書眉同每頁葉數、邊個引擎讀字讀得啱（淨係數真正換字分歧，每對一票，有 Wilson 下界先定偏好）、異體對清單（分類、次數、裁圖），最後由模型逐對按裁圖多數裁定印嘅字形（`variant_vote.py`，寫入 `variant-rulings.json`；`--no-variant-vote` 關）、本書印咗乜符號同幾密。每項都封住證據（逐個裁決、裁圖同 hash、計數），所以 profile 錯咗睇得出。`proofread_pages.py` 讀佢：引擎偏好、異體裁決、標點提示、按本書密度放寬嘅退化輸出門檻、按字級核對嘅書眉刪除；profile 嘅決定部分 hash 封入每頁 provenance。同時喺 server 嘅 request 最多 `--workers` 個（同 phase 3 嘅 `--max-inflight` 一樣，所以 `--workers` 要設做 server 嘅 `--max-concurrency`；agent 同佢共用 server，送多過 lane 數就係搶 agent 嘅）；`--no-inflight-cap` 關，即係舊做法：唔封頂，靠每步各自開 `--workers` 條 thread 限住。模型答「兩個字係咪同一個字嘅兩種寫法」（`classify_pair`）嘅答案存落磁碟，所有書、所有 run 共用（預設 `~/.cache/jyut-ocr/pair-class.jsonl`，`PAIR_CACHE_PATH` 改位置）：同一條問題（同一個 prompt、model、effort、token 上限、effort 階梯，同一個 server；phase 3 開咗 `--top-rung-caps` 又封咗 `pair-class` 嘅話，連個上限都要一樣）之前答過就用返，唔再問模型。一對字照舊兩個次序各問一次、唔一致先按頭一個次序再問，答案逐個次序逐次存，所以之後喺另一個次序遇到同一對，淨係要問佢自己嗰次重問；同一個 process 入面同一對同時問（兩個次序都算）淨係問一次。server 由本機聽住 endpoint 個 port 嘅 process 認：佢嘅 command line，同埋 executable 同 command line 提到嘅每個檔嘅 SHA-256（大檔每個版本淨係讀一次，hash 記喺 store 隔籬）。呢啲檔入面一定要有一個 64 MiB 或以上、當佢係模型權重：port 上面係轉發嘅 process（`ssh -L`、socat、container 嘅 proxy），或者 server 按個名、喺自己嘅設定搵模型，command line 就冇權重，睇唔出答嘅係邊個模型。冇權重（設咗 `PAIR_CACHE_MODEL_TAG` 都一樣）、權重檔喺 server 開咗之後改過、去權重嘅路徑喺 server 開咗之後可能指去第二個檔（路徑上面嘅 link 改咗指向，例如 `current` 指去新版本，或者目錄改名、換咗入嚟：server 記憶體入面仲係舊模型；路徑上面一個名所在嘅目錄同佢指住嘅嘢都喺之後改過都算，例如放模型嘅目錄入面加咗新模型，重開 server 就得返）、command line 提到嘅路徑（有 `/` 嘅字）而家搵唔到而佢斷開嗰個目錄喺 server 開咗之後改過（個檔可能搬走咗）、server 唔喺本機、或者 command line 有目錄，就認唔到，個 store 唔用（照舊問模型）。`PAIR_CACHE_MODEL_TAG` 會加入 key，server 改咗啲 key 睇唔到嘅嘢想由頭問過就設佢。淨係存完整嘅答案：四級 effort 都俾 token 上限截斷、冇答、冇「判定」嗰行、call 失敗、問緊嗰陣 server 轉咗都唔存。亦淨係存經 HTTP 由 endpoint 個 port 上面嗰個 server 答返嚟嘅答案：真正嘅 transport（`Client._send`，`urlopen` 返咗之後）將讀到嘅每個 response 同 connection 另一端係邊話畀 store 知，答案要係最後一個 response 嘅、沿途（effort 階梯每一級）讀到嘅 response 全部都係噉樣嚟、connection 係接去本機 endpoint 個 port，先存；stand-in client、換咗 `_send` 嘅 client（check 入面嘅 stand-in）、假嘅 `urlopen`、proxy 或者 redirect 去第二個 port，都係照舊問、乜都唔存（2026-09-29 喺本機個 store 搵到 20 個「判定：不同」，係一個 offline replay 嘅 stand-in 喺 ninfer 聽住 endpoint 個 port 嗰陣答嘅，記咗喺 ninfer 名下）。送出去嘅 request 同 key 記住嗰個唔同（hook 咗 transport 換咗 prompt、model 或者 sampling，答嘅係第二條問題）、答案讀完之後俾人改過、或者 key 記住嗰個 server process 已經唔係喺嗰個 port 聽緊嗰個（佢停咗聽但仲喺度、第二個 server 佔咗個 port，或者佢 exec 咗第二個程式），都唔存；本 process 自己都喺嗰個 port（另一個 loopback 位址）聽緊，就唔信個 server。舊 code 存嘅記錄（schema 1，冇上面呢啲證明，其他 checkout 仲跑緊舊 code 嘅 check 會寫落預設 store）一律唔讀。每條答案記埋 server 個 response 自己講嘅 model id（`servedModel`）。`tests/` 入面跑 script 嘅 check 全部用自己嘅臨時 store、endpoint 指去冇嘢聽嘅 port（`tests/offline.py`；`tests/stand_in.py` 嘅 `run()` 每次用本書目錄隔籬嘅 store），唔會讀寫本機個 store。profile 嘅 `pairClassCache` 記住 store 喺邊、答案屬邊個 server、每對模型分類嘅每一票係咪由 store 攞（連存入時間）。實測一本 488 頁嘅書，profile 99 分鐘入面大約 76 分鐘係問呢啲問題；corpus 七本書入面，新書大約 14–22% 嘅對之前嘅書問過，同一本書重跑 profile 就全部問過。`--no-pair-cache` 關，即係舊做法：每個 process 重新問，答案淨係留喺記憶體。
- `scripts/variant_vote.py`：模型逐對裁異體印嘅字形（每張裁圖問一次，按多數定，人裁嘅對唔郁），`book_profile.py` 最後自動跑；舊 profile 可以單獨跑，`--dry-run` 淨係數有幾多對、幾多個 call，`--output` 寫去另一個檔，`--compare` 同另一份裁決逐對比。
- `scripts/variant_sheet.py`（可選，冇嘢會等佢）：由 profile 出異體對嘅 contact sheet（`variant-sheet.png`，每對附模型嘅裁決同票數）同參考範本（`variant-rulings.todo.json`），人已裁嘅對唔再出。
- `scripts/run_ocr_phase.py`（單 GPU 主機）：包住 OCR runner，顯存夠就直接跑，唔夠就先執行 release command 騰顯存、跑完再 restore 同等 health endpoint。release／restore／health 由 `OCR_PHASE_RELEASE_CMD`／`OCR_PHASE_RESTORE_CMD`／`OCR_PHASE_HEALTH_URL` 設定，唔喺技能寫死任何 service 名。restore 失敗 exit 3。
- `scripts/wait_for_run.py`：背景長步驟（`book_profile.py`、`proofread_pages.py`、OCR runner，直接跑或者經 `run_ocr_phase.py`，同埋 `finish_book.py`）跑緊嘅時候靜靜哋等，唔問模型、唔連 server；一次最多等 570 秒，印一行進度或者結果（做完仲會講埋嗰步印過嘅 `WARNING`）。process 由佢自己嘅參數認（用返嗰個 script 自己嘅 parser），冇咗就由 log 尾講佢點完，俾人殺咗都會即刻講，唔會一直等。exit 0 做完、1 做完但有失敗或者開唔到工、4 停咗要重跑、75 仲跑緊、2 佢自己嘅參數或者路徑錯。`--progress BOOK` 就順手重整 `proofreading.md`。用法見〈安全並行〉。
- `scripts/build_draft.py`（第一次交付）：兩個引擎做完就寫 `BOOK/draft.md`，引擎 B 嘅字、按掃描次序、略過 manifest 標咗空白嘅頁、保守刪書眉頁碼、冇頁嘅地方寫一行空位、引擎 B 不停重複同一段字（loop）嘅地方淨係留一次再寫一行空位；幾秒做完，唔問模型，寫唔到都唔阻流程。見〈分三次交付〉。
- `scripts/build_progress.py`（第二次交付）：寫 `BOOK/proofreading.md`，封存齊嘅頁用校對稿、其他頁用草稿，檔頭講校對咗幾多頁；一本幾百頁嘅書大約一秒，經暫存檔再改名寫。`wait_for_run.py --progress` 自動叫佢。
- `scripts/detect_ocr_engine.py`（任何平台）：印出本機可用嘅 draft engine（JSON 或 `--brief`），順帶報 GPU free VRAM 同顯存不足警告。有 engine exit 0，冇 exit 1。揀 engine 前先跑呢個，唔好逐個 runner 試。
- `scripts/run_paddleocr_vl.py`＋`scripts/paddleocr_vl_worker.py`（phase 2，主引擎）：逐頁產生可續跑、可驗 hash、有 scan provenance 嘅 JSON／TXT pair（連 layout block 同表格），用單一常駐 GPU worker（pipeline 只載入一次）。版面模型搵到而冇字嘅區域（圖、image 之類）另外記喺 JSON 嘅 `regions`（label、box、閱讀次序），唔入 `lines`，所以 TXT 同以前一樣；舊 JSON 冇呢欄，phase 3 照舊行。用 `--python` 或 `PADDLEOCR_PYTHON` 指向裝咗 paddleocr 嘅 venv。輸出只係 draft，亦絕不 fallback 去 Tesseract／Tessdata。
- `scripts/finish_book.py`（phase 3 之後，任何 profile）：一個 command 做晒拼書（封存頁寫成 `assembled/` 嘅 segment、`ordered-segments.json`、`page-sources.json`，`assemble_ocr_segments.py` 砌 `combined-annotated.md`）、修書（`repair_book.py`，寫 `repaired/`）、定稿（`finalize_page_markers.py` 出 `final.md`，冇 page marker，再跑 final audit）同疑問清單（`doubts.md`、`finish/doubts.json`）。每步可以重跑：最新嘅步驟跳過，修書由停低嗰度續；`final.md`／`doubts.md` 唔係佢上次寫嗰份（用戶改過）就先搬去 `final.edited-<時間>.md`／`doubts.edited-<時間>.md`，唔會蓋咗。開關：`--proofread`、`--renders`、`--ocr-a`、`--ocr-b`、`--profile`、`--page-manifest`（輸入唔喺慣用位置先用）、`--no-model`、`--endpoint`、`--model`、`--max-inflight`、`--timeout`、`--workers`。stdout 淨係一行 `[finish] RESULT exit=N …` 同兩個路徑，詳細輸出喺 `finish/finish-book.log`；唔讀任何圖入 agent 睇到嘅嘢。exit 0 做完、1 有一步失敗、2 參數或者輸入錯、3 有頁未封存、4 俾人停咗、6 問唔到模型。用法見〈做完之後〉。
- `scripts/assemble_ocr_segments.py`（`structured`／`release`）：按 strict ordered manifest 驗 segment hashes／連續 scan ranges，並按 sealed page manifest 驗 marker coverage；重播 bytes 同現有 combined annotated 不一致就失敗。
- `scripts/repair_book.py`（拼書之後、finalize 之前；`finish_book.py` 會叫佢）：唔重跑頁面，淨係寫一個新嘅 `--output` folder 修書；唔寫任何輸入 folder，開始前驗每頁 seal、拼書檔同 render hash，完咗再驗輸入冇改。由本書自己量出書本模型（書眉、卷次、頁碼序列、分卷頁、目錄頁、engine B 代字、版心同段首縮格，逐項有 gate），每個改動記入 `repair-log.jsonl`，重播要 byte for byte 等於輸出。呢個版本行嘅機械規則：書眉（F1–F8）、標點同代字（K1–K14、K-seq）、標題內容（H-JOIN、S6、S7x、S8、S10、S15）、目錄同篇目（S9、S4、S16、S7、S11：目錄逐條對返正文，印出嚟嘅篇號由引擎讀數同目錄次序兩個來源一齊定）、題名頁（S13，由右至左印嘅頁）、全書一套標題級數（S5、S12：級數跟目錄深度，唔係逐頁揀）、頁內分段（P1、P2、P4、P6、P7、P5：段首縮格由本書量出）、分頁 boundary（S、T、H、L、J1–J4、P-1–P-3：寫 `boundaries.json` 同 `boundary-evidence.json`，過 finalize contract；量出嘅印刷證據就係 boundary ledger，唔一致先問，未定案寫 `paragraph`）；證據唔夠嘅位寫做問題，唔估；問題由問 Qwen 階段（`questions`）問：一條問題一張由 render 切嘅裁圖（遮住書眉帶，紅線紅框標位），同第三階段一樣用本機 Qwen、xhigh、同一條 effort ladder、16000 token、server 嘅 lanes；Q-G 字、Q-P 兩個錨之間印咗乜、Q-L 抄一行、Q-Y 版面、Q-B 分頁。答案要過 G1–G7 檢查先寫（格式、太長或者有推理、抄鄰字、書眉字、無根據嘅新字、數字次序矛盾、兩個答案撞位），過唔到就記疑點，唔會寫入；每條答案一返嚟就寫入 `answers.jsonl`，`--resume` 唔再問。開關：`--plan-only`、`--no-model`、`--resume`、`--pages`、`--verify-sample`、`--endpoint`、`--model`、`--reasoning-effort`、`--max-tokens`、`--max-inflight`、`--timeout`、`--no-furniture`、`--no-marks`、`--no-headings`、`--no-contents`、`--no-title-page`、`--no-levels`、`--no-paragraphs`、`--no-joins`。問唔到模型就 exit 6，加 `--resume` 再跑。`scripts/_book_lint.py` 係佢嘅自動缺陷計數，可以單獨跑。詳情、疑點種類同計數見 `references/long-book-workflow.md`〈拼書之後修書〉。
- `scripts/audit_title_notes.py`（星號題名註 feature）：按主 item 核對 heading 尾端 `*`／`**` 同題注 marker，列 missing／orphan 同 note-shaped 跨頁 hazard。任何 note→running-body transition 預設 fail closed；只有 strict `--transition-reviews` exact match 目前 target、boundary、前後文字、reviewer 同 visual evidence 先接受。報告唔自動證明題注 ownership；普通 Markdown star syntax 必須由人分辨。
- `scripts/build_notation_inventory.py`（來源 notation feature）：逐頁 inventory 通用 residual symbols；`--inventory-profile` 可以用 project-local literal tokens 擴展，`--include-starred-title-notes` 只喺來源確有該 apparatus 時啟用。工具避開 metadata、code、單行 HTML comments 同 Markdown links，並封 target／authority／profile、toolchain hash 同 invocation profile；佢唔取代凡例判讀。
- `scripts/validate_review_evidence.py`（`release`）：驗 canonical late-amendment ledger 嘅 exact schema、安全相對路徑、current content／render／evidence hashes、非空而相異嘅 before／after rows、writer／verifier 獨立性、changed＋neighbor scan coverage 同零 unresolved；before／after 是否對應 baseline／目前字串仍由 reviewer 同 evidence 證明。
- `scripts/plan_release_rebuild.py`（`release`）：重算 active artifact hashes，將 direct stale 沿 reverse dependencies 傳播，輸出 dependency-first rebuild order；clean／stale／invalid 分別用不同 exit status。缺失 active path 若唔可能由 discovery globs 命中就係 invalid，唔係可重建 stale；JSON report 唔准 alias plan、任何 declared artifact 或工具。佢只理解 plan graph，未列入 plan 嘅 generator 升級唔會自動變 stale。
- `scripts/validate_release_evidence.py`：按 canonical discovery globs 驗全部 artifact classification、SHA-256、typed dependency contracts、active closure、dependency／supersession DAG，同 optional reconciliation arithmetic／sealed evidence binding。
- `scripts/audit_ocr_markdown.py`：審核 annotated/final Markdown、marker inventory、顯式 boundary contract、OCR residue、soft break、tight-list continuation、table 欄數、HTML 表（淨係准用嚟載合併格：冇合併格嘅 HTML 表、格仔對唔齊、`rowspan` 跨出表尾或者 `<thead>`／`<tbody>`、`<table>` 冇收尾都會報錯；CommonMark 要成張表係一個 HTML block，所以 `<table>` 唔喺行頭、表入面有空行、`</table>` 後面冇空行就接住文字都報錯；表包咗喺 code fence 入面會變成 code，報錯；表外嘅其他 HTML 報 warning）、成對標點、完整 EOF whitespace、來源 notation／exception、PDF／render provenance、marker coverage 同 assembly proof。`structured` final 可用 `--annotated-source` 加 boundary manifest 即場 exact 重建；`release` receipt gate 則重驗 schema v2 plan 同 ordered active closure。Notation policy 只喺 final mode exact accept；legacy v1 receipt 只可診斷，唔會放行。
- `scripts/finalize_page_markers.py`：先 dry-run，逐個核對 marker 左右 context、boundary manifest 同預期移除數；`--write` 必須提供完整 `--boundary-manifest` 同另一個 `--output`。長書寫 `--receipt` 時亦必須提供已驗證嘅 `--release-plan`；腳本唔覆寫 annotated 底稿，並自動用 schema v2 唯一 `release-plan` role 封存 plan 嘅 active closure，唔再靠手寫重複 `--upstream` 清單。Output／receipt 唔可以 alias plan 或任何 classified artifact，亦唔可以變成 pre-final discovery 新命中。
- 第一次 boundary／issue review 保留預設 verbose 輸出；全數位置已核實後，長書重跑可加 `--summary-only` 壓縮終端輸出。呢個選項只隱藏逐項 context，唔改檢查、deterministic issue counts 或 exit code；任何非零 issue 要除去選項重跑定位。

`finish_book.py` 已經跑 final audit 同修書嘅自動缺陷計數，命中寫入 `doubts.md`。想再手動查殘留（淨係文字搜尋，唔睇圖；命中多就淨係數行數，唔好成段貼入對話）：

```bash
rg -n "\[|\]|<!--|gjcool|此頁OCR|[A-Za-z]" TARGET.md || true
rg -n "[[:blank:]]+$" TARGET.md || true
test ! -s project-suspects.txt || rg -n -f project-suspects.txt TARGET.md || true
git status --short -- TARGET.md
git diff --check -- TARGET.md
```

`project-suspects.txt` 由目前文件嘅重複頁面家具、correction ledger、OCR disagreement 同已核實錯形產生；書名、專名同單一材料先入呢份 project-local 清單，唔回寫核心 skill。

`git diff --check -- TARGET.md` 對 untracked 新檔可能實際無檢查內容；遇到新檔要另跑 trailing-whitespace audit，或者用 `git diff --no-index --check /dev/null TARGET.md`，並留意 exit 1 可以只代表檔案有差異，判斷以有冇 whitespace error 輸出為準。

完成回覆要短（見〈做完之後〉）：`final.md` 同 `doubts.md` 喺邊、PDF scan 頁數同入書頁數、幾多項疑問喺幾多頁（`finish_book.py` 嗰行有齊）、冇逐頁視覺核對（唔可以話有）、有冇缺頁或者外部復原。只有啟用相應 feature／profile 時，先再交代 source/render manifest hashes、text／facts／structure changed-set arithmetic、notation inventory、題名註、獨立 auditor／late amendment、release plan、canonical receipt target、final audit、internal/public parity 同 tracked／untracked／ignored／repo 外交付狀態；唔適用就直接寫 `not-applicable`。
