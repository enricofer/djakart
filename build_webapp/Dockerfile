# docker build --build-context root=./webapp -t djakart:latest ./build_webapp
FROM debian:bookworm-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# ENV HTTPS_PROXY=http://172.20.0.252:3128
# ENV HTTP_PROXY=http://172.20.0.252:3128
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && apt-get install -y tzdata && apt-get install -y git

# RUN git config --global http.proxy http://172.20.0.252:3128
# RUN git config --global https.proxy http://172.20.0.252:3128

RUN apt-get update &&\
    apt-get install -y python3 python3-pip   && \
    apt-get install -y binutils libproj-dev gdal-bin python3-gdal

RUN apt-get install -y wget

RUN wget https://github.com/koordinates/kart/releases/download/v0.15.1/kart_0.15.1_amd64.deb
RUN dpkg -i kart_0.15.1_amd64.deb

RUN kart config --global user.email "you@example.com"
RUN kart config --global user.name "Your Name"

COPY --from=root requirements.txt /requirements.txt

RUN python3 -m pip config --global set global.break-system-packages true

RUN pip install -r requirements.txt

RUN apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
