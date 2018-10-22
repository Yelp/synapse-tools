FROM ubuntu:14.04
MAINTAINER John Billings <billings@yelp.com>

RUN rm -f /etc/apt/sources.list.d/proposed.list

# Older versions of dh-virtualenv are buggy and don't.. work
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 88ADA4A042F8DD13 && \
    echo 'deb http://ppa.launchpad.net/dh-virtualenv/daily/ubuntu trusty main\ndeb-src http://ppa.launchpad.net/dh-virtualenv/daily/ubuntu trusty main' >> /etc/apt/sources.list

# Need Python 3.6
RUN apt-get update > /dev/null && \
    apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa

RUN apt-get update && apt-get -y install \
    debhelper \
    dpkg-dev \
    libyaml-dev \
    libcurl4-openssl-dev \
    python3.6-dev \
    python-tox \
    python-setuptools \
    libffi-dev \
    libssl-dev \
    build-essential \
    gdebi-core \
    wget \
    protobuf-compiler

RUN apt-get update && cd /tmp && \
    wget http://mirrors.kernel.org/ubuntu/pool/universe/d/dh-virtualenv/dh-virtualenv_1.0-1_all.deb && \
    gdebi -n dh-virtualenv*.deb && \
    rm dh-virtualenv_*.deb

RUN pip install virtualenv==15.1.0 tox-pip-extensions==1.2.1 tox==3.1.3

WORKDIR /work
