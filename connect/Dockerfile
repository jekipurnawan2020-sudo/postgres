FROM confluentinc/cp-kafka-connect:7.9.1

USER root

RUN confluent-hub install \
    --no-prompt \
    confluentinc/kafka-connect-jdbc:10.8.4

RUN curl -fsSL \
    https://jdbc.postgresql.org/download/postgresql-42.7.4.jar \
    -o /usr/share/java/kafka-connect-jdbc/postgresql-42.7.4.jar

USER appuser