FROM python:3.12-slim

WORKDIR /app

ARG PORT=2001

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=app.py \
    FLASK_RUN_HOST=0.0.0.0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE ${PORT}

CMD ["sh", "-c", "flask run --host=${FLASK_RUN_HOST:-0.0.0.0} --port=${PORT:-5000}"]
