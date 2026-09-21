FROM confluentinc/cp-kafka-connect:7.9.1

USER root

RUN confluent-hub install \
    --no-prompt \
    confluentinc/kafka-connect-jdbc:10.8.4

USER appuser