FROM ubuntu:14.04
ARG PIP_INDEX_URL=https://pypi.yelpcorp.com/simple
ENV PIP_INDEX_URL=$PIP_INDEX_URL
RUN apt-get update && apt-get install -y git python python-setuptools python-pip
RUN git clone --branch yelp https://github.com/Yelp/hacheck
RUN cd /hacheck && pip install .

# Hacheck
EXPOSE 6666

# Create a dummy service running on port 1024 and serving up /my_healthcheck_endpoint
EXPOSE 1999
WORKDIR /tmp
ADD test-server.py /tmp/test-server.py
ADD hacheck.conf.yaml /tmp/hacheck.conf.yaml
RUN echo 'OK' > lil_brudder

CMD /usr/local/bin/hacheck -p 6666 -c /tmp/hacheck.conf.yaml & python /tmp/test-server.py
