"""模型路由端點 CRUD（S-03，API-11）。

function ∈ asr / batch_tr / live_tr / post；active 旗標可停用。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from models_db.db import db
from responses import envelope
from storage.paths import new_id

router = APIRouter(prefix="/api/endpoints", tags=["endpoints"])

FUNCTIONS = {"asr", "batch_tr", "live_tr", "post"}


class EndpointIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=1)
    model: str = Field(min_length=1, max_length=100)
    function: str
    active: bool = True


def _to_dict(r) -> dict:
    return {
        "id": r["id"], "name": r["name"], "url": r["url"],
        "model": r["model"], "function": r["function"], "active": bool(r["active"]),
    }


@router.get("")
def list_endpoints():
    with db() as conn:
        rows = [_to_dict(r) for r in
                conn.execute("SELECT * FROM endpoints ORDER BY function, name")]
    return envelope(rows)


@router.post("", status_code=201)
def create_endpoint(body: EndpointIn):
    if body.function not in FUNCTIONS:
        raise HTTPException(status_code=400, detail=f"function 須為 {sorted(FUNCTIONS)}")
    eid = new_id("e_")
    with db() as conn:
        conn.execute(
            "INSERT INTO endpoints(id,name,url,model,function,active) VALUES(?,?,?,?,?,?)",
            (eid, body.name, body.url, body.model, body.function, int(body.active)),
        )
    return envelope({"id": eid, **body.model_dump()})


@router.patch("/{eid}")
def set_active(eid: str, active: bool):
    with db() as conn:
        cur = conn.execute("UPDATE endpoints SET active=? WHERE id=?", (int(active), eid))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="端點不存在")
    return envelope({"id": eid, "active": active})


@router.delete("/{eid}")
def delete_endpoint(eid: str):
    with db() as conn:
        cur = conn.execute("DELETE FROM endpoints WHERE id=?", (eid,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="端點不存在")
    return envelope({"deleted": eid})
