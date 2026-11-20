FROM swipl:stable
WORKDIR /app
COPY connect4_ai.pl server.pl ./
ENV PORT=8090
EXPOSE 8090
# Comprobación de salud: el puerto TCP responde (la imagen no trae curl).
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD bash -c 'exec 3<>/dev/tcp/127.0.0.1/8090' || exit 1
CMD ["swipl", "-g", "main", "server.pl"]
