FROM nginx:latest
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HTTPS_PROXY=http://172.20.0.252:3128
ENV HTTP_PROXY=http://172.20.0.252:3128

RUN apt-get update
#RUN apt-get install -y openssl

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get -y install tzdata
RUN apt-get install -y iputils-ping 
RUN apt-get install -y wget 

COPY --chmod=755 docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]