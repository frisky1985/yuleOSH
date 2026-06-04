FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir pytest coverage
EXPOSE 8080
ENTRYPOINT ["python3", "src/ui/server.py"]
