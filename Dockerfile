FROM python:3.11-slim
WORKDIR /app
COPY api api
COPY db db
COPY data data
COPY demo demo
EXPOSE 8090
ENV HOST=0.0.0.0
ENV PORT=8090
CMD ["python", "api/server.py"]
