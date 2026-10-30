FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/generate_data.py
EXPOSE 8501
# Truyền key lúc chạy, KHÔNG nhét vào image:  docker run --env-file .env -p 8501:8501 vidata-agent
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
