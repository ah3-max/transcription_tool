"""模型路由解析（S-03，FR-21）：依 function 取目前 active 的端點。

S-04（ASR）／S-05（翻譯）／S-06（即時）處理時，用此決定要打哪個 OpenAI 相容端點。
"""
from models_db.db import db


def resolve_endpoint(function: str) -> dict | None:
    """回該 function（asr/batch_tr/live_tr/post）目前 active 的端點；無則 None。

    多筆 active 時取最後新增者（rowid 最大）。
    """
    with db() as conn:
        r = conn.execute(
            "SELECT * FROM endpoints WHERE function=? AND active=1 ORDER BY rowid DESC LIMIT 1",
            (function,),
        ).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "name": r["name"], "url": r["url"],
            "model": r["model"], "function": r["function"]}
