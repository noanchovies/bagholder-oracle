# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code (app.py and templates folder)
# DO NOT copy portfolio.csv
COPY app.py .
COPY templates ./templates

# Inform Docker container listens on port 8000 (Gunicorn default)
EXPOSE 8000

# Placeholder for database URL (set by Render/docker run)
ENV DATABASE_URL=""

# Command to run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "app:app"]
