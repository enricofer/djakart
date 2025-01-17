#!/usr/bin/env sh
if [ -e /etc/nginx/conf.d/default.conf.template ]
then
    set -eu
    # ${HOST_EXTERNAL} ${WEBAPP_PORT_EXTERNAL} ${WEBAPP_EXTERNAL} ${QGIS_SERVER_EXTERNAL}
    #envsubst '${SITE_SUBPATH}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

    cat /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

    cat /etc/nginx/conf.d/default.conf

    exec "$@"

else
    echo "no template!"
fi