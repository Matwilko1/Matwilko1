ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache tzdata

WORKDIR /app
COPY coffee_reminders /app/coffee_reminders
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
