FROM python:3.12-alpine

RUN addgroup -S opscat && adduser -S -G opscat -u 65532 opscat
WORKDIR /app
COPY p174_workload.py /app/p174_workload.py
USER 65532:65532

ENTRYPOINT ["python", "/app/p174_workload.py"]
