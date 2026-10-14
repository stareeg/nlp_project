FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY law_aliases.json .
COPY detector ./detector

# индекс собираем при сборке образа, чтобы сервис стартовал за доли секунды
RUN python -c "from detector import LawReferenceDetector; LawReferenceDetector.cached('law_aliases.json')"

EXPOSE 8978

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8978", "--workers", "1"]
