FROM debian:trixie-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends tar gzip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY src/ src/
COPY deploy/ deploy/
COPY deploy/image/assemble.sh /usr/local/bin/assemble-petcam
RUN chmod 0755 /usr/local/bin/assemble-petcam
ENTRYPOINT ["/usr/local/bin/assemble-petcam"]
