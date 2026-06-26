"""NLLB-200-3.3B 即時翻譯服務（host, :8001）— stt-translate S-06 即時翻譯後端。

NLLB 是純模型、無內建 server、非 OpenAI 相容（FLORES-200 語言碼＋forced_bos_token_id）。
本服務掛 :8001，回應外型對齊專案 `{data, error?}`。

- 來源固定中文（zho_Hans/zho_Hant），一對多扇出由 app 端對每個目標各打一次（D-03，不串接）。
- 精度：先 fp16（~6.6GB）跑通；之後可轉 CTranslate2 int8（~3.4GB）降 VRAM、改 Translator 載入。
- 啟動：~/.venvs/nllb/bin/uvicorn nllb_server:app --host 0.0.0.0 --port 8001
- app 端：LIVE_TR_ENDPOINT=http://host.docker.internal:8001（無 /v1）。

FLORES-200 語言碼：中(簡)zho_Hans、中(繁)zho_Hant、英 eng_Latn、泰 tha_Thai。
"""
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

MODEL = "facebook/nllb-200-3.3B"
# 允許的 FLORES-200 碼（白名單，擋未知碼造成的奇怪輸出）。
ALLOWED_LANGS = {"zho_Hans", "zho_Hant", "eng_Latn", "tha_Thai"}

_tok = None
_model = None


def _load():
    """惰性載入：服務起來即載一次（systemd 按需起、閒置由 app 端 idle.tracker 釋放整個 unit）。"""
    global _tok, _model
    if _model is None:
        _tok = AutoTokenizer.from_pretrained(MODEL)
        _model = (
            AutoModelForSeq2SeqLM.from_pretrained(MODEL, torch_dtype=torch.float16)
            .to("cuda")
            .eval()
        )
    return _tok, _model


app = FastAPI(title="stt-translate NLLB live-tr", version="1")


class Req(BaseModel):
    text: str
    src_lang: str = "zho_Hans"  # 來源固定中文（扇出由 app 端負責）
    tgt_lang: str               # tha_Thai / eng_Latn ...


@app.on_event("startup")
def _startup():
    _load()


@app.get("/health")
def health():
    """就緒檢查：模型已載入回 ready。app 端 live-readiness／WS 連線前可探。"""
    return {"data": {"ready": _model is not None, "model": MODEL}}


@app.post("/translate")
def translate(r: Req):
    if r.tgt_lang not in ALLOWED_LANGS:
        return {"data": None, "error": "tgt_lang_not_allowed"}
    if r.src_lang not in ALLOWED_LANGS:
        return {"data": None, "error": "src_lang_not_allowed"}
    text = (r.text or "").strip()
    if not text:
        return {"data": {"translation": ""}}
    tok, model = _load()
    tok.src_lang = r.src_lang
    enc = tok(text, return_tensors="pt").to("cuda")
    bos = tok.convert_tokens_to_ids(r.tgt_lang)
    with torch.inference_mode():
        out = model.generate(**enc, forced_bos_token_id=bos, max_new_tokens=512)
    translation = tok.batch_decode(out, skip_special_tokens=True)[0]
    return {"data": {"translation": translation, "src_lang": r.src_lang, "tgt_lang": r.tgt_lang}}
