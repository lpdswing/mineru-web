FROM python:3.10-slim

WORKDIR /service

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN git clone --depth 1 https://github.com/opendatalab/MinerU-Popo.git /opt/MinerU-Popo
RUN sed -i 's/^click==8\.3\.1$/click==8.2.1/' /opt/MinerU-Popo/requirements.txt \
    && pip install --no-cache-dir --use-deprecated=legacy-resolver -r /opt/MinerU-Popo/requirements.txt

COPY app ./app

ENV POPO_REPO_DIR=/opt/MinerU-Popo
ENV POPO_WORKSPACE=/workspace

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
