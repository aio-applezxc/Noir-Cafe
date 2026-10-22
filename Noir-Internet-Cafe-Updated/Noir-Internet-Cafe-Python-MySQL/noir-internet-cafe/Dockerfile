FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 noir
COPY --chown=noir:noir . .
USER noir
EXPOSE 8000
CMD ["sh", "-c", "python -m flask --app app init-db && python app.py"]
