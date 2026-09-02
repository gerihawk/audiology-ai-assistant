# Base con pg_dump ya incluido (misma familia de versión que el Postgres
# de Railway). `age` y `aws` desde los repos de Alpine. Sin dependencias
# del backend.
FROM postgres:17-alpine
RUN apk add --no-cache python3 age aws-cli
COPY backup.py /backup.py
ENTRYPOINT []
CMD ["python3", "/backup.py"]
