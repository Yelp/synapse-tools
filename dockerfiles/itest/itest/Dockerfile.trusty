FROM ubuntu:14.04
MAINTAINER John Billings <billings@yelp.com>

# Need Python 3.6
RUN apt-get update > /dev/null && \
    apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa

RUN apt-get update && apt-get -y install \
    libcurl3 \
    iptables \
    python3.6 \
    python-setuptools \
    python-pytest \
    python-pycurl \
    python-kazoo \
    python-zope.interface \
    ruby1.9.1 \
    ruby1.9.1-dev \
    rubygems1.9.1 \
    libxml2 \
    libxml2-dev \
    libxslt-dev \
    libssl-dev \
    build-essential \
    zlib1g-dev

# Lua 5.3 for scripting with HAProxy
WORKDIR /
ADD http://www.lua.org/ftp/lua-5.3.1.tar.gz /lua-5.3.1.tar.gz
RUN tar -axvf /lua-5.3.1.tar.gz
WORKDIR /lua-5.3.1
RUN pwd
RUN make generic
RUN make install INSTALL_TOP=/usr/bin/lua

# Ubuntu trusty nginx and haproxy are ancient, grab newer ones
WORKDIR /
ADD http://www.haproxy.org/download/1.7/src/haproxy-1.7.8.tar.gz /haproxy.tar.gz
RUN tar -axvf /haproxy.tar.gz
WORKDIR /haproxy-1.7.8
RUN pwd
RUN make TARGET=linux26 -j 4 \
    USE_LUA=1 \
    LUA_LIB=/usr/bin/lua/lib \
    LUA_INC=/usr/bin/lua/include \
    && mv haproxy /usr/bin/haproxy-synapse

# Nginx
WORKDIR /
ADD https://nginx.org/download/nginx-1.11.10.tar.gz /nginx.tar.gz
RUN tar -axvf /nginx.tar.gz
WORKDIR /nginx-1.11.10
RUN ./configure \
    --prefix=/etc/nginx \
    --sbin-path=/usr/sbin/nginx \
    --conf-path=/etc/nginx/nginx.conf \
    --error-log-path=/var/log/nginx/error.log \
    --http-log-path=/var/log/nginx/access.log \
    --pid-path=/var/run/nginx.pid \
    --lock-path=/var/run/nginx.lock \
    --user=nobody \
    --group=nogroup \
    --with-http_ssl_module \
    --with-stream \
    --without-http_rewrite_module \
    --without-http_gzip_module


RUN make -j 4
RUN make install

# Pin for test reproducibility
RUN gem install --no-ri --no-rdoc nokogiri -v 1.6.7.2
RUN gem install --no-ri --no-rdoc synapse -v 0.14.1
RUN gem install --no-ri --no-rdoc synapse-nginx -v 0.2.2

ADD synapse.conf /etc/init/synapse.conf
ADD synapse.conf.json /etc/synapse/synapse.conf.json
ADD synapse-tools.conf.json /etc/synapse/synapse-tools.conf.json
ADD synapse-tools-both.conf.json /etc/synapse/synapse-tools-both.conf.json
ADD synapse-tools-nginx.conf.json /etc/synapse/synapse-tools-nginx.conf.json

# Zookeeper discovery
RUN mkdir -p /nail/etc/zookeeper_discovery/infrastructure
ADD zookeeper_discovery/infrastructure/local.yaml.trusty /nail/etc/zookeeper_discovery/infrastructure/local.yaml

ADD yelpsoa-configs /nail/etc/services
ADD habitat /nail/etc/habitat
ADD ecosystem /nail/etc/ecosystem
ADD region /nail/etc/region
ADD itest.py /itest.py
ADD run_itest.sh /run_itest.sh
ADD rsyslog-configs/49-haproxy.conf /etc/rsyslog.d/49-haproxy.conf
ADD maps/ip_to_service.map /var/run/synapse/maps/ip_to_service.map

# configure_synapse tries to restart synapse.
# make it think it succeeded.
RUN ln -sf /bin/true /usr/sbin/service

CMD /bin/bash /run_itest.sh
