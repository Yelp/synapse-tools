FROM ubuntu:bionic

RUN apt-get update && apt-get -y install \
    debhelper \
    dh-virtualenv \
    dpkg-dev \
    libyaml-dev \
    libcurl4-openssl-dev \
    python3.6-dev \
    python-tox \
    python-setuptools \
    libffi-dev \
    libssl-dev \
    libzookeeper-mt-dev \
    build-essential \
    protobuf-compiler \
    gdebi-core \
    wget

WORKDIR /work
