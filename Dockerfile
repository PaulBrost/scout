FROM python:3.12-slim

# Install system deps + Node.js (for Playwright script execution)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    libpq-dev \
    gcc \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files (whitenoise serves them)
RUN python manage.py collectstatic --noinput || true

# Non-root user for security
RUN useradd -m scout && chown -R scout:scout /app
USER scout

EXPOSE 8000

CMD ["gunicorn", "scout.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
