"""統一回應外型 {data, error?, message?}（清單另含 pagination）。

main 與各路由共用，避免循環匯入。
"""


def envelope(data=None, error: str | None = None, message: str | None = None) -> dict:
    body: dict = {"data": data}
    if error is not None:
        body["error"] = error
    if message is not None:
        body["message"] = message
    return body
