#!/usr/bin/env python3
"""host 端模型控制小服務（S-03 / G5 / D-06）。

app 在純 CPU 容器內無法卸載 GPU；「釋放 VRAM」＝停掉 host 上的模型服務程序、
下次使用前再起。本服務讓 app（經 host.docker.internal）對本專案的 vLLM/NLLB
user systemd unit 下 start/stop/status。純標準函式庫、無第三方相依（仿 gpu_stat）。

安全（同 G2 / NFR-4・SEC-9）：預設自動綁 docker0 閘道（host-gateway，本機
172.17.0.1）：LAN 連不到、容器經 host.docker.internal 連得到。偵測不到退回
0.0.0.0 並印 SECURITY 警告。**只允許控制白名單內的本專案 unit**，不得碰別人服務。

執行（host 上）：
    python3 host-helpers/model_ctl.py                 # 預設綁 docker0 閘道、:3602
API：
    GET  /status?unit=stt-nllb     → {"data":{"unit":...,"active":bool,"state":"active|inactive|..."}}
    POST /start  {"unit":"stt-nllb"}
    POST /stop   {"unit":"stt-nllb"}
    （unit 不在白名單 → 403；未知路徑 → 404）

⚠️ 屬 host 端控制：部署、enable 與實機 start/stop 牽涉 GPU 與 host 程序，
   上線前須取得使用者同意；vLLM(ASR) unit 由 PoC 端建立後再納入白名單。
"""
import fcntl
import json
import os
import socket
import struct
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# 只允許控制這些本專案 unit（嚴禁波及他人服務）。asr 的 vLLM unit 待 S-06/PoC 建立後加入。
ALLOWED_UNITS = {"stt-nllb", "stt-vllm-asr"}
CTL_TIMEOUT = 10  # systemctl 子程序逾時（秒）

_SIOCGIFADDR = 0x8915


def _iface_ipv4(ifname: str = "docker0") -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("256s", ifname.encode()[:15])
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(), _SIOCGIFADDR, packed)[20:24])
    except OSError:
        return None
    finally:
        s.close()


HOST = os.environ.get("MODEL_CTL_HOST") or _iface_ipv4("docker0") or "0.0.0.0"
PORT = int(os.environ.get("MODEL_CTL_PORT", "3602"))


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args],
                          capture_output=True, text=True, timeout=CTL_TIMEOUT)


def unit_status(unit: str) -> dict:
    try:
        out = _systemctl("is-active", unit)
        state = (out.stdout or out.stderr or "unknown").strip()
    except Exception:
        state = "unknown"
    return {"unit": unit, "active": state == "active", "state": state}


def unit_action(unit: str, action: str) -> dict:
    """action ∈ start|stop。回最終狀態；systemctl 失敗也回狀態（不丟例外給 HTTP 層）。"""
    try:
        _systemctl(action, unit)
    except Exception:
        pass
    return unit_status(unit)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unit_from_body(self) -> str | None:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return (json.loads(raw or b"{}") or {}).get("unit")
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != "/status":
            self._send(404, {"data": None, "error": "not_found"})
            return
        unit = (parse_qs(parsed.query).get("unit") or [None])[0]
        if unit not in ALLOWED_UNITS:
            self._send(403, {"data": None, "error": "unit_not_allowed"})
            return
        self._send(200, {"data": unit_status(unit)})

    def do_POST(self):
        action = self.path.rstrip("/").lstrip("/")
        if action not in ("start", "stop"):
            self._send(404, {"data": None, "error": "not_found"})
            return
        unit = self._unit_from_body()
        if unit not in ALLOWED_UNITS:
            self._send(403, {"data": None, "error": "unit_not_allowed"})
            return
        self._send(200, {"data": unit_action(unit, action)})

    def log_message(self, *args):  # 靜音 access log
        pass


if __name__ == "__main__":
    if HOST == "0.0.0.0":
        print("⚠️ SECURITY：model_ctl 綁 0.0.0.0＝對 LAN 外露(NFR-4/SEC-9)；"
              "請設 MODEL_CTL_HOST=<docker0 閘道> 或以防火牆限制 :3602")
    print(f"model_ctl 服務啟動於 http://{HOST}:{PORT}（白名單 unit：{sorted(ALLOWED_UNITS)}）")
    HTTPServer((HOST, PORT), Handler).serve_forever()
