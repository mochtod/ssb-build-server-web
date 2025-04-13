FROM python:3.11-slim

WORKDIR /app

# Install Git and curl only
RUN apt-get update && \
    apt-get install -y git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files from the current directory
COPY . /app

# Create directories for persistent storage if they don't exist
RUN mkdir -p /app/configs /app/terraform /app/.vsphere_cache

# Run as non-root user for better security
RUN useradd -m appuser && \
    chown -R appuser:appuser /app /app/configs /app/terraform /app/.vsphere_cache && \
    chmod 755 /app/.vsphere_cache

# Switch to the non-root user
USER appuser

# # Configure Git for the non-root user
# RUN git config --global user.name "VM Provision Bot" && \
#     git config --global user.email "vm-provision@chrobinson.com"

# # Expose the application port
EXPOSE 5150

# Start the application with longer worker timeout
CMD ["gunicorn", "--bind", "0.0.0.0:5150", "--timeout", "300", "--workers", "4", "app:app"]
