FROM nginx:latest

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apache2-utils \
        dos2unix \
        bash && \
    rm -rf /var/lib/apt/lists/*

COPY ./commands/set_nginx_basic_auth.sh /commands/set_nginx_basic_auth.sh

RUN dos2unix /commands/*.sh

RUN chmod +x /commands/*.sh

ENTRYPOINT ["/commands/set_nginx_basic_auth.sh"]

CMD ["nginx", "-g", "daemon off;"]
