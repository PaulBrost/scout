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

# Install Playwright Chromium browser + OS dependencies
RUN npx playwright install --with-deps chromium

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files (whitenoise serves them)
RUN SECRET_KEY=build-placeholder python manage.py collectstatic --noinput

# Create mount point for Playwright project
RUN mkdir -p /playwright-project

EXPOSE 8000

CMD ["gunicorn", "scout.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
