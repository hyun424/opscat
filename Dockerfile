FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .
COPY app ./app
COPY scripts ./scripts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
