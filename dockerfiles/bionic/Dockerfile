FROM ubuntu:bionic

ARG PIP_INDEX_URL=https://pypi.yelpcorp.com/simple
ENV PIP_INDEX_URL=$PIP_INDEX_URL

RUN apt-get update && apt-get -y install \
    debhelper \
    dh-virtualenv \
    dpkg-dev \
    libyaml-dev \
    libcurl4-openssl-dev \
    python3.6-dev \
    python-tox \
    python3-pip \
    python-setuptools \
    libffi-dev \
    libssl-dev \
    build-essential \
    protobuf-compiler \
    gdebi-core \
    wget

# When using internal pypi on older virtualenvs they
# fail looking for pkg-resources?!
RUN pip3 install virtualenv==16.0.0

WORKDIR /work
