FROM python:3.13.5-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files into /app (not /app/app)
COPY . .

# Expose Hugging Face default port
EXPOSE 7860

# Run Flask with Gunicorn (module:app)
# If your file is app.py and Flask instance = app, this works
CMD ["gunicorn", "-b", "0.0.0.0:7860", "app:app"]
