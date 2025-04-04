FROM python:3.11-slim

WORKDIR /app

# Remove Git and curl installation as they are not needed
RUN apt-get update && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify gunicorn installation
RUN pip show gunicorn || (echo "gunicorn not installed" && exit 1)

# Copy the application files from the current directory
COPY . /app

# Remove the appuser and permission changes
# Update volume mapping to ensure configs are written to the host
RUN mkdir -p /app/configs

# Expose the application port
# Corrected to match the port used in CMD
EXPOSE 5000

# Start the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]  # Updated to bind to port 5150 for create VM app