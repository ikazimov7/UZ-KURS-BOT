FROM python:3.11-alpine

WORKDIR /app

# Install build dependencies (needed for some packages), then remove them
RUN apk add --no-cache build-base libffi-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]

