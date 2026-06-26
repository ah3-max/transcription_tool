"""應用設定：一律由環境變數讀入（容器以 env_file 注入）。

對應規格的環境變數表（開發執行手冊 §5.2）。預設值對齊 .env.example，
端點預設指向 host.docker.internal（模型在 host 原生、app 在容器內 — D-14）。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 本機開發可放 .env；容器內由 compose env_file 注入真實環境變數
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 路徑與綁定
    data_dir: str = "/data"
    db_path: str = "/data/index.db"
    web_dir: str = "/web"
    app_port: int = 3600
    bind_host: str = "0.0.0.0"

    # 模型端點（OpenAI 相容；host 原生服務，經 host.docker.internal 連出）
    llm_endpoint: str = "http://host.docker.internal:1234/v1"   # LM Studio：gemma-4-31b
    asr_endpoint: str = "http://host.docker.internal:8000/v1"   # vLLM：Qwen3-ASR（待建）
    live_tr_endpoint: str = "http://host.docker.internal:8001"  # NLLB（待建）
    gpu_stat_endpoint: str = "http://host.docker.internal:3601"  # host gpu_stat（VRAM 查詢，D-17）

    # 政策與資源
    retention_days: int = 7
    max_file_min: int = 120
    res_cap: float = 0.8
    idle_release_min: int = 10


settings = Settings()
