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
    max_tokens = int(os.environ.get("POPO_OPENAI_MAX_TOKENS", "1024"))
    if not url:
        raise RuntimeError("POPO_OPENAI_BASE_URL is required for Popo API inference")
    print(
        f"### MINERU-WEB-POPO ### request model={base_model} base_url={url} "
        f"has_image={bool(base64_image)} prompt_chars={len(prompt)} max_tokens={max_tokens}",
        flush=True,
    )
'''
if old not in text:
    raise SystemExit("MinerU-Popo model_utils.py patch target not found")
text = text.replace(old, new, 1)

old_success = '''            res = response.choices[0].message.content

            return res
'''
new_success = '''            res = response.choices[0].message.content
            print(
                f"### MINERU-WEB-POPO ### response model={base_model} "
                f"response_chars={len(res or '')}",
                flush=True,
            )

            return res
'''
if old_success not in text:
    raise SystemExit("MinerU-Popo model_utils.py success patch target not found")
text = text.replace(old_success, new_success, 1)

old_max_tokens = '''                max_tokens=50000,
'''
new_max_tokens = '''                max_tokens=max_tokens,
'''
if old_max_tokens not in text:
    raise SystemExit("MinerU-Popo model_utils.py max_tokens patch target not found")
text = text.replace(old_max_tokens, new_max_tokens, 1)

old_failure = '''        except Exception as e:
            cnt += 1
            print(e)
'''
new_failure = '''        except Exception as e:
            cnt += 1
            print(
                f"### MINERU-WEB-POPO ### error model={base_model} "
                f"attempt={cnt} error={e}",
                flush=True,
            )
'''
if old_failure not in text:
    raise SystemExit("MinerU-Popo model_utils.py failure patch target not found")
path.write_text(text.replace(old_failure, new_failure, 1), encoding="utf-8")
PY

RUN python3 - <<'PY'
from pathlib import Path

path = Path("/opt/MinerU-Popo/post_processing/inference.py")
text = path.read_text(encoding="utf-8")
old = '''    return ranges, chunks
'''
new = '''    if not chunks and sorted_items:
        chunks.append(sorted_items)
        ranges.append([unique_pages[0], unique_pages[-1]])

    return ranges, chunks
'''
if old not in text:
    raise SystemExit("MinerU-Popo inference.py adaptive_chunk patch target not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
PY

COPY app ./app

ENV POPO_REPO_DIR=/opt/MinerU-Popo
ENV POPO_WORKSPACE=/workspace

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
