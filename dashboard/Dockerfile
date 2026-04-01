# Stage 1: Build frontend
# Build context must be the project root (docker-compose sets context: .)
FROM node:22-slim AS frontend
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci
COPY dashboard/ .
RUN npm run build

# Stage 2: Python API + static files
FROM python:3.13-slim
WORKDIR /app

# Copy built frontend to the path the app expects: <repo_root>/dashboard/dist
COPY --from=frontend /app/dist /app/dashboard/dist

# Copy Python source and project config
COPY src /app/src
COPY pyproject.toml README.md /app/

# Install package with dashboard extras
RUN pip install --no-cache-dir -e ".[dashboard]"

EXPOSE 8080

CMD ["python", "-m", "reagent.api", "--host", "0.0.0.0", "--port", "8080"]
