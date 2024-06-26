ARG CLICKHOUSE_VERSION
FROM clickhouse/clickhouse-server:${CLICKHOUSE_VERSION}

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y supervisor python3-pip && \
    rm -rf /var/lib/apt/lists/* /var/cache/debconf && \
    apt-get clean

COPY images/clickhouse/config/monitor-ch-backup /etc/sudoers.d/monitor-ch-backup
COPY images/clickhouse/config/regions_names_ru.txt /opt/geo/regions_names_ru.txt
COPY images/clickhouse/config/regions_hierarchy.txt /opt/geo/regions_hierarchy.txt

RUN rm -rf /etc/supervisor && \
    ln -s /config/supervisor /etc/supervisor && \
    mkdir /var/log/monrun && \
    ln -s /config/dbaas.conf /etc/dbaas.conf && \
    mkdir -p /etc/yandex/ch-backup && \
    ln -s /config/ch-backup.conf /etc/yandex/ch-backup/ch-backup.conf && \
    ln -s /config/config.xml /etc/clickhouse-server/config.d/ && \
    rm /etc/clickhouse-server/users.xml && \
    ln -s /config/users.xml /etc/clickhouse-server/ && \
    \
    mkdir -p /etc/clickhouse-server/ssl && \
    openssl rand -writerand /root/.rnd && \
    openssl req -subj "/CN=localhost" -new -newkey rsa:2048 -days 365 -nodes -x509 \
        -keyout /etc/clickhouse-server/ssl/server.key \
        -addext "subjectAltName=DNS:clickhouse01,DNS:clickhouse02,DNS:clickhouse01.ch_tools_test,DNS:clickhouse02.ch_tools_test" \
        -out /etc/clickhouse-server/ssl/server.crt && \
    ln -s /etc/clickhouse-server/ssl/server.crt /etc/clickhouse-server/ssl/allCAs.pem && \
    \
    groupadd monitor && useradd -g monitor -G monitor,clickhouse monitor && \
    mkdir /var/log/clickhouse-monitoring && \
    chown monitor:monitor -R /var/log/clickhouse-monitoring && \
    mkdir /var/log/keeper-monitoring && \
    chown monitor:monitor -R /var/log/keeper-monitoring && \
    chmod 755 /var/lib/clickhouse && \
    chmod 777 /etc && \
    chmod 755 /etc/clickhouse-server && \
    chmod 750 /etc/clickhouse-server/ssl && \
    chmod 640 /etc/clickhouse-server/ssl/server.crt && \
    chmod 640 /etc/clickhouse-server/ssl/allCAs.pem && \
    chown -R clickhouse:clickhouse /etc/clickhouse-server/ /usr/bin/clickhouse

ENTRYPOINT ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
