FROM mcr.microsoft.com/playwright/python:v1.41.2-jammy

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Kyiv

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    tzdata \
  && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
  && echo $TZ > /etc/timezone \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "run.py"]
