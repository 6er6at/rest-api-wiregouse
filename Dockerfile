FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY server1.py .

EXPOSE 5000

CMD ["uvicorn", "server1:app", "--host", "0.0.0.0", "--port", "5000"]
