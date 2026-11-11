FROM python:3.12-slim
WORKDIR /app
COPY server.py .
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"
USER nobody
CMD ["python", "-u", "server.py"]
