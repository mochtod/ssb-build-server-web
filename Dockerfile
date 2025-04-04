FROM python:3.11-slim

WORKDIR /app

# Install Git, curl and other dependencies
RUN apt-get update && \
    apt-get install -y git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files from the current directory
COPY . /app

# Create directories for persistent storage if they don't exist
RUN mkdir -p /app/configs /app/terraform

# Run as non-root user for better security
RUN useradd -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# Configure Git for the non-root user
RUN git config --global user.name "VM Provision Bot" && \
    git config --global user.email "vm-provision@chrobinson.com"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
