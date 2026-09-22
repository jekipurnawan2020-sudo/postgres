FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y \
       curl \
       gnupg2 \
       ca-certificates \
       unixodbc \
       unixodbc-dev \
       gcc \
       g++ \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL \
    https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor \
    > /usr/share/keyrings/microsoft-prod.gpg

RUN curl -fsSL \
    https://packages.microsoft.com/config/debian/12/prod.list \
    > /etc/apt/sources.list.d/mssql-release.list

RUN apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY cdc/requirements.txt .

RUN pip install \
    --no-cache-dir \
    -r requirements.txt

COPY cdc/app ./app
COPY scripts ./scripts

CMD ["python", "-u", "app/main.py"]