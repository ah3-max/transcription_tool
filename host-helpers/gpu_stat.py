#!/usr/bin/env python3
"""host 端極小 GPU 用量服務（S-03 / D-17）。

app 在純 CPU 容器內量不到 VRAM；此服務跑在 host、讀 `nvidia-smi`，
以 JSON 暴露 GPU 記憶體用量，供 app（經 host.docker.internal）查詢、
顯示右上資源用量（FR-24）。純標準函式庫、無第三方相依。

執行（host 上，python 3.12/3.14 皆可）：
    python3 host-helpers/gpu_stat.py                       # 預設綁 docker0 閘道(安全)
    GPU_STAT_HOST=0.0.0.0 python3 host-helpers/gpu_stat.py # 強制對 LAN 外露(不建議)

安全（G2 / NFR-4・SEC-9）：模型/輔助端點不對 LAN 外露。
- 預設**自動綁 docker 預設 bridge（docker0）的閘道 IP**（本機 172.17.0.1）。
  該 IP 只在 docker0 介面、不在 LAN NIC(eth0)，故 **LAN 連不到**；而容器以
  `host.docker.internal` 連 host＝走 `host-gateway`＝**docker0 閘道**，仍連得到。
- ⚠️ 不要綁 compose 專案網路（br-xxxx，如 172.25.0.1）的閘道：容器經
  host-gateway(172.17.0.1) 連出、不是經專案網路閘道，綁那個容器會連不到。
- 偵測不到 docker0 時退回 0.0.0.0 並印 SECURITY 警告（此時請改用防火牆限制 :3601）。
僅暴露 GPU 記憶體數字、無任何控制能力。埠 3601 在本專案保留範圍內。
"""
import fcntl
import json
import os
import socket
import struct
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

_SIOCGIFADDR = 0x8915  # Linux ioctl：取介面 IPv4


def _iface_ipv4(ifname: str = "docker0") -> str | None:
    """回 host 在指定介面上的 IPv4（docker0 閘道即 host-gateway）；取不到回 None。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("256s", ifname.encode()[:15])
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(), _SIOCGIFADDR, packed)[20:24])
    except OSError:
        return None
    finally:
        s.close()


# 綁定優先序：GPU_STAT_HOST 明設 > 自動偵測 docker0 閘道 > 退回 0.0.0.0(警告)
HOST = os.environ.get("GPU_STAT_HOST") or _iface_ipv4("docker0") or "0.0.0.0"
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
    if HOST == "0.0.0.0":
        print("⚠️ SECURITY：gpu_stat 綁 0.0.0.0＝對 LAN 外露(NFR-4/SEC-9)；"
              "請設 GPU_STAT_HOST=<docker0 閘道> 或以防火牆限制 :3601")
    print(f"gpu_stat 服務啟動於 http://{HOST}:{PORT}/gpu")
    HTTPServer((HOST, PORT), Handler).serve_forever()
