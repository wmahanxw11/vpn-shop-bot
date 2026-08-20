FROM python:3.11-slim

WORKDIR /app

# کپی فایل requirements و نصب
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی همه فایل‌ها
COPY . .

# اجرا با gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]