FROM python:3.10-slim

WORKDIR /service

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN git clone --depth 1 https://github.com/opendatalab/MinerU-Popo.git /opt/MinerU-Popo
RUN python3 - <<'PY'
from pathlib import Path

path = Path("/opt/MinerU-Popo/post_processing/model_utils.py")
text = path.read_text(encoding="utf-8")
old = '''    url = ""
    key = ""
    base_model = "Popo"
'''
new = '''    url = os.environ.get("POPO_OPENAI_BASE_URL", "")
    key = os.environ.get("POPO_OPENAI_API_KEY", "dummy")
    base_model = os.environ.get("POPO_OPENAI_MODEL", "Popo")
    if not url:
        raise RuntimeError("POPO_OPENAI_BASE_URL is required for Popo API inference")
'''
if old not in text:
    raise SystemExit("MinerU-Popo model_utils.py patch target not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
PY

COPY app ./app

ENV POPO_REPO_DIR=/opt/MinerU-Popo
ENV POPO_WORKSPACE=/workspace

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
