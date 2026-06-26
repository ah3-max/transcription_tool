# app 本體映像：純 CPU（不需 nvidia-container-toolkit）。
# 所有 GPU 推論走 host 原生端點（vLLM / NLLB / LM Studio），見 D-14。
# build context = 倉庫根（compose 指定），故可同時複製 server/ 與 web/。
FROM python:3.12-slim

WORKDIR /app

# 系統相依：curl 供 healthcheck；ffmpeg(含 ffprobe) 供上傳深度驗證(SEC-2/G4：解碼＋時長)
# 以 https 取套件：預設 http 鏡像對部分 .deb 會回 403，https 來源正常且更安全。
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 程式碼與內建一份前端（compose 會以 bind-mount 覆蓋 /web 供開發即時更新）
COPY server/ /app/
COPY web/ /web/

EXPOSE 3600
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3600"]
