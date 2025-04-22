FROM python:3.9-slim

WORKDIR /app

# Install Git, curl, and system dependencies
RUN apt-get update && \
    apt-get install -y git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install all Python dependencies as root
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Ensure pyVim is installed properly
    pip install --no-cache-dir pyVim && \
    # Make sure the installation works
    python -c "import sys; from pyVim import connect; from pyVmomi import vim; print('VMware modules imported successfully'); print(f'Python path: {sys.path}')"

# Copy the application files
COPY . /app

# Create directories for persistent storage if they don't exist
RUN mkdir -p /app/configs /app/terraform /app/vm-workspace /app/logs

# Create non-root user and set permissions
RUN useradd -m appuser && \
    chown -R appuser:appuser /app /app/configs /app/terraform /app/vm-workspace /app/logs && \
    # Make Python packages accessible to non-root user
    chmod -R 755 /usr/local/lib/python3.9/site-packages /usr/local/bin

# Switch to the non-root user
USER appuser

# Expose the application port
EXPOSE 5150

# Start the application
CMD ["gunicorn", "--bind", "0.0.0.0:5150", "app:app"]
