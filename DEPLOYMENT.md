# Study Helper Backend API - Deployment Guide

This guide provides comprehensive instructions for deploying the Study Helper Backend API in different environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Configuration](#environment-configuration)
3. [Local Development Setup](#local-development-setup)
4. [Production Deployment](#production-deployment)
5. [Database Setup](#database-setup)
6. [Security Considerations](#security-considerations)
7. [Monitoring and Maintenance](#monitoring-and-maintenance)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Docker**: Version 20.10 or higher
- **Docker Compose**: Version 1.29 or higher
- **Python**: 3.11 or higher (for local development)
- **PostgreSQL**: 15 or higher
- **Redis**: 7 or higher (optional, for caching)

### API Keys Required

- **Google Gemini API Key**: Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
- **OpenAI API Key**: Get from [OpenAI Platform](https://platform.openai.com/api-keys)

## Environment Configuration

### 1. Copy Environment Files

```bash
# For development
cp .env.example .env

# For production
cp .env.production .env.prod
```

### 2. Configure Environment Variables

Edit the `.env` file with your specific values:

```bash
# Database configuration
DB_HOST=localhost
DB_USER=studyhelper_user
DB_PASSWORD=your_secure_password
DB_NAME=studyhelper_db

# Security
SECURITY_JWT_SECRET_KEY=your-super-secret-jwt-key-256-bits-minimum

# AI Provider Keys
AI_GEMINI_API_KEY=your_gemini_api_key_here
AI_OPENAI_API_KEY=your_openai_api_key_here
```

## Local Development Setup

### Option 1: Docker Compose (Recommended)

1. **Start all services**:

   ```bash
   docker-compose up -d
   ```

2. **View logs**:

   ```bash
   docker-compose logs -f api
   ```

3. **Access the API**:
   - API: <http://localhost:8000>
   - API Documentation: <http://localhost:8000/docs>
   - pgAdmin: <http://localhost:8080>
   - Redis Commander: <http://localhost:8081>

4. **Run database migrations**:

   ```bash
   docker-compose exec api alembic upgrade head
   ```

5. **Create default users** (optional):

   ```bash
   docker-compose exec api python scripts/create_default_users.py
   ```

### Option 2: Local Python Setup

1. **Create virtual environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up database** (PostgreSQL required):

   ```bash
   # Create database
   createdb studyhelper_db
   
   # Run migrations
   alembic upgrade head
   ```

4. **Start the application**:

   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

## Production Deployment

### 1. Prepare Production Environment

```bash
# Create production directory
mkdir -p /opt/studyhelper
cd /opt/studyhelper

# Clone repository
git clone <repository-url> .

# Copy production configuration
cp .env.production .env
```

### 2. Configure Production Environment

Edit `.env` with production values:

```bash
# Use strong, unique values for production
ENVIRONMENT=production
DEBUG=false
SECURITY_JWT_SECRET_KEY=<generate-secure-256-bit-key>

# Database (use managed database service recommended)
DB_HOST=your-production-db-host
DB_USER=your-production-db-user
DB_PASSWORD=<strong-password>
DB_NAME=studyhelper_prod

# Redis (use managed Redis service recommended)
REDIS_HOST=your-redis-host
REDIS_PASSWORD=<strong-password>
```

### 3. SSL Certificate Setup

```bash
# Create SSL directory
mkdir -p nginx/ssl

# Option 1: Use Let's Encrypt (recommended)
certbot certonly --standalone -d api.yourdomain.com

# Copy certificates
cp /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem nginx/ssl/cert.pem
cp /etc/letsencrypt/live/api.yourdomain.com/privkey.pem nginx/ssl/key.pem

# Option 2: Use self-signed certificates (development only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem \
  -out nginx/ssl/cert.pem
```

### 4. Deploy with Docker Compose

```bash
# Build and start production services
docker-compose -f docker-compose.prod.yml up -d

# Check service status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

### 5. Database Migration

```bash
# Run database migrations
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head

# Create default users and data
docker-compose -f docker-compose.prod.yml exec api python scripts/create_default_users.py
```

## Database Setup

### Initial Migration

```bash
# Initialize Alembic (only for new deployments)
alembic init alembic

# Create initial migration
alembic revision -m "Initial database schema"

# Apply migrations
alembic upgrade head
```

### Database Backup

```bash
# Create backup
docker-compose exec database pg_dump -U studyhelper_user studyhelper_db > backup.sql

# Restore backup
docker-compose exec -T database psql -U studyhelper_user studyhelper_db < backup.sql
```

### Database Maintenance

```bash
# Connect to database
docker-compose exec database psql -U studyhelper_user studyhelper_db

# Analyze database performance
ANALYZE;

# Vacuum database
VACUUM ANALYZE;
```

## Security Considerations

### 1. Environment Security

- **Never commit `.env` files to version control**
- **Use strong, unique passwords** for all services
- **Rotate API keys and secrets** regularly
- **Enable firewall** and restrict access to necessary ports only

### 2. Database Security

- **Use managed database services** in production
- **Enable SSL/TLS** for database connections
- **Implement regular backups** with encryption
- **Monitor database access logs**

### 3. Application Security

- **Use HTTPS only** in production
- **Implement rate limiting** (handled by Nginx)
- **Monitor authentication attempts**
- **Keep dependencies updated**

### 4. Network Security

```bash
# Configure firewall (example for Ubuntu)
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP (redirects to HTTPS)
ufw allow 443/tcp     # HTTPS
ufw enable
```

## Monitoring and Maintenance

### Health Checks

```bash
# Check API health
curl -f http://localhost:8000/health

# Check detailed system health
curl -f http://localhost:8000/health/detailed
```

### Log Management

```bash
# View application logs
docker-compose logs -f api

# View Nginx logs
docker-compose logs -f nginx

# View database logs
docker-compose logs -f database
```

### Performance Monitoring

```bash
# Monitor container resources
docker stats

# Monitor database performance
docker-compose exec database pg_stat_activity
```

### Updates and Maintenance

```bash
# Update application
git pull origin main
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Update dependencies
pip-compile requirements.in
docker-compose -f docker-compose.prod.yml build api

# Database maintenance
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Issues

```bash
# Check database status
docker-compose ps database

# Check database logs
docker-compose logs database

# Test database connection
docker-compose exec database pg_isready -U studyhelper_user
```

#### 2. API Startup Issues

```bash
# Check API logs
docker-compose logs api

# Check environment variables
docker-compose exec api env | grep -E "(DB_|AI_|SECURITY_)"

# Restart API service
docker-compose restart api
```

#### 3. Permission Issues

```bash
# Fix file permissions
sudo chown -R 1000:1000 cache/
sudo chown -R 1000:1000 logs/

# Check Docker permissions
sudo usermod -aG docker $USER
```

#### 4. Memory Issues

```bash
# Check memory usage
docker stats

# Increase memory limits in docker-compose.yml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G
```

### Performance Optimization

#### 1. Database Optimization

```sql
-- Add indexes for frequently queried columns
CREATE INDEX CONCURRENTLY idx_user_email ON "user"(email);
CREATE INDEX CONCURRENTLY idx_content_analytics ON content_analytics(content_type, content_id);

-- Monitor slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
```

#### 2. Application Optimization

```bash
# Use production WSGI server
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker

# Enable Redis caching
REDIS_HOST=redis
REDIS_PORT=6379
```

### Support and Documentation

- **API Documentation**: <http://localhost:8000/docs>
- **ReDoc Documentation**: <http://localhost:8000/redoc>
- **Health Check**: <http://localhost:8000/health>

For additional support, please refer to the project documentation or contact the development team.
