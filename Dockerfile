FROM python:3.11-slim

WORKDIR /app

# Remove Git and curl installation as they are not needed
RUN apt-get update && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files from the current directory
COPY . /app

# Update volume mapping to ensure configs are written to the host
RUN mkdir -p /app/configs && \
    useradd -m appuser && \
    chown -R appuser:appuser /app /app/configs && \
    chmod -R 775 /app/configs

# Switch to the non-root user
USER appuser

# Expose the application port
EXPOSE 5001  # Updated exposed port to 5001

# Start the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]