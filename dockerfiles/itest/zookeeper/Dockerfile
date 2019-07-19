FROM ubuntu:14.04

RUN apt-get update
RUN apt-get -y install zookeeper

EXPOSE 2181
CMD /usr/share/zookeeper/bin/zkServer.sh start-foreground
