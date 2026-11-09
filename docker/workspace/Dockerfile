FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    bash \
    curl \
    wget \
    git \
    nano \
    vim \
    iproute2 \
    iputils-ping \
    dnsutils \
    net-tools \
    procps \
    ca-certificates \
    sudo \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash devops \
    && mkdir -p /home/devops/workspace \
    && chown -R devops:devops /home/devops

WORKDIR /home/devops/workspace

USER devops

CMD ["sleep", "infinity"]
