# Docker Setup for Integration Tests

This directory contains Docker configuration for running integration tests with MariaDB.

## Quick Start

```bash
# Start MariaDB container
make docker-up

# Run integration tests
make integration

# Stop MariaDB container
make docker-down
```

## Docker Compose Configuration

The `docker-compose.yml` file defines a MariaDB 10.5 service with the following configuration:

- **Container name**: `mariadb_10_5`
- **Port**: 3306 (mapped to host)
- **Database**: `flask_restless`
- **User**: `db_user`
- **Password**: `password`
- **Root password**: `rootpassword`

## Available Commands

### Start MariaDB
```bash
make docker-up
# or
docker-compose up -d
```

### Stop MariaDB
```bash
make docker-down
# or
docker-compose down
```

### View Logs
```bash
make docker-logs
# or
docker-compose logs -f mariadb_10_5
```

### Check Status
```bash
make docker-ps
# or
docker-compose ps
```

### Run Integration Tests
```bash
# Automatically starts/stops MariaDB
make integration

# Or manually
make docker-up
pytest -m integration
make docker-down
```

## Manual Docker Commands

If you prefer to use Docker directly:

```bash
# Start the container
docker-compose up -d mariadb_10_5

# Check if it's running
docker ps

# View logs
docker logs mariadb_10_5

# Connect to the database
docker exec -it mariadb_10_5 mysql -u db_user -p flask_restless
# Password: password

# Stop the container
docker-compose down
```

## Database Connection String

The integration tests use this connection string:
```
mysql+pymysql://db_user:password@localhost/flask_restless
```

## Health Check

The container includes a health check that verifies MariaDB is ready:
- Interval: 10 seconds
- Timeout: 5 seconds
- Retries: 5
- Start period: 30 seconds

Wait for the container to be healthy before running tests:
```bash
docker-compose ps
# Look for "(healthy)" status
```

## Persistent Data

Database data is stored in a Docker volume named `mariadb_data`. To remove all data:

```bash
docker-compose down -v
```

## Troubleshooting

### Port 3306 already in use
If you have another MySQL/MariaDB instance running:
```bash
# Find what's using the port
sudo lsof -i :3306

# Either stop that service or change the port in docker-compose.yml
```

### Container won't start
```bash
# Check logs
make docker-logs

# Remove and recreate
docker-compose down -v
make docker-up
```

### Connection refused
```bash
# Wait a few seconds for MariaDB to initialize
sleep 10

# Check if the container is healthy
docker-compose ps

# Verify the container is listening
docker exec mariadb_10_5 mysqladmin ping -h localhost -u root -prootpassword
```

## Requirements

- Docker Engine 20.10+
- Docker Compose 1.29+ (or Docker Compose v2)
- Python package: `pymysql` (installed with test dependencies)
