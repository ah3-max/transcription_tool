#!/usr/bin/env python3
"""host 端極小 GPU 用量服務（S-03 / D-17）。

app 在純 CPU 容器內量不到 VRAM；此服務跑在 host、讀 `nvidia-smi`，
以 JSON 暴露 GPU 記憶體用量，供 app（經 host.docker.internal）查詢、
顯示右上資源用量（FR-24）。純標準函式庫、無第三方相依。

執行（host 上，python 3.12/3.14 皆可）：
    python3 host-helpers/gpu_stat.py
    GPU_STAT_PORT=3601 GPU_STAT_HOST=0.0.0.0 python3 host-helpers/gpu_stat.py

安全：預設綁 0.0.0.0:3601（讓容器經 host.docker.internal 連得到）。
僅暴露 GPU 記憶體數字、無任何控制能力；Stage 2 建議以防火牆限制 :3601
僅 docker 橋接網段可達（呼應 NFR-4/SEC-9）。埠 3601 在本專案保留範圍內。
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = os.environ.get("GPU_STAT_HOST", "0.0.0.0")
PORT = int(os.environ.get("GPU_STAT_PORT", "3601"))


def query_gpu() -> list:
    out = subprocess.run(
        ["nvidia-smi",
         "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5, check=True,
    )
    gpus = []
    for line in out.stdout.strip().splitlines():
        idx, name, total, used, free, util = [c.strip() for c in line.split(",")]
        total_i, used_i = int(total), int(used)
        gpus.append({
            "index": int(idx),
            "name": name,
            "mem_total_mib": total_i,
            "mem_used_mib": used_i,
            "mem_free_mib": int(free),
            "mem_used_pct": round(used_i / total_i * 100, 1) if total_i else None,
            "util_gpu_pct": int(util) if util.isdigit() else None,
        })
    return gpus


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") not in ("/gpu", ""):
            self.send_error(404)
            return
        try:
            payload = {"data": {"gpus": query_gpu()}}
            code = 200
        except Exception:
            payload = {"data": None, "error": "gpu_unavailable", "message": "讀取 GPU 失敗"}
            code = 503
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 靜音 access log
        pass


if __name__ == "__main__":
    print(f"gpu_stat 服務啟動於 http://{HOST}:{PORT}/gpu")
    HTTPServer((HOST, PORT), Handler).serve_forever()
