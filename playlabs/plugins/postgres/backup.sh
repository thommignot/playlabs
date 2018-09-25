docker start {{ project_postgres_host }}
docker exec {{ project_postgres_host }} pg_dumpall -U {{ project_postgres_user }} -c -f /run/postgres/data.dump
docker logs {{ project_postgres_host }} &> postgres.log
