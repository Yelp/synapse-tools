FROM ubuntu:14.04
RUN apt-get update && apt-get install -y git python python-setuptools python-pip
RUN git clone --branch yelp https://github.com/Yelp/hacheck
RUN cd /hacheck && python setup.py install

RUN apt-get -y install socat

# Hacheck
EXPOSE 6666

# Run hacheck in background and dummy service in foreground
EXPOSE 1025
CMD /usr/local/bin/hacheck -p 6666 & socat TCP4-LISTEN:1025,fork SYSTEM:date
