FROM python:3.11-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Ngăn Python ghi file .pyc và bật log unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Cloud Run tự động inject biến PORT (mặc định 8080)
ENV PORT=8080
EXPOSE 8080

# Chạy ứng dụng (chỉnh lại lệnh phù hợp với app của nhóm):
# Ví dụ Streamlit:
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0

# Hoặc nếu là Flask / FastAPI:
# CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
