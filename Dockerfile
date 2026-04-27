FROM python:3.13-slim

# Install ODBC dependencies
RUN apt-get update && apt-get install -y \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set the start command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
