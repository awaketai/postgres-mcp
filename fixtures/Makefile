# =============================================================================
# Test Fixture Database Manager
#
# Usage:
#   make all          # Create & seed all three databases
#   make small        # Create & seed small (bookshelf)
#   make medium       # Create & seed medium (ecommerce)
#   make large        # Create & seed large (enterprise)
#   make drop-all     # Drop all three databases
#   make reset-all    # Drop then recreate all
#   make refresh-all  # Re-seed all (drop data + re-init + re-seed)
# =============================================================================

# PostgreSQL connection (override via environment)
PGHOST     ?= localhost
PGPORT     ?= 5432
PGUSER     ?= root
PGPASSWORD ?= admin123

export PGPASSWORD

PSQL      = psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) -d postgres -q
PSQL_VARS = psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) -v ON_ERROR_STOP=1

SMALL_DB  = pg_mcp_test_small
MEDIUM_DB = pg_mcp_test_medium
LARGE_DB  = pg_mcp_test_large
ALL_DBS   = $(SMALL_DB) $(MEDIUM_DB) $(LARGE_DB)

# ---------------------------------------------------------------------------
# Phony targets
# ---------------------------------------------------------------------------
.PHONY: all small medium large drop-all reset-all refresh-all \
        $(SMALL_DB) $(MEDIUM_DB) $(LARGE_DB) \
        drop-$(SMALL_DB) drop-$(MEDIUM_DB) drop-$(LARGE_DB) \
        refresh-$(SMALL_DB) refresh-$(MEDIUM_DB) refresh-$(LARGE_DB) \
        deps check-psql

# ---------------------------------------------------------------------------
# Aggregate targets
# ---------------------------------------------------------------------------
all: $(SMALL_DB) $(MEDIUM_DB) $(LARGE_DB)

drop-all: drop-$(SMALL_DB) drop-$(MEDIUM_DB) drop-$(LARGE_DB)

reset-all: drop-all all

refresh-all: refresh-$(SMALL_DB) refresh-$(MEDIUM_DB) refresh-$(LARGE_DB)

# ---------------------------------------------------------------------------
# Per-database targets
# ---------------------------------------------------------------------------
# small
$(SMALL_DB): deps
	@echo "==> Creating database: $(SMALL_DB)"
	$(PSQL) -c "CREATE DATABASE $(SMALL_DB)"
	$(PSQL_VARS) -d $(SMALL_DB) -f small/init.sql
	PG_FIXTURE_URL="postgresql://$(PGUSER)@$(PGHOST):$(PGPORT)/$(SMALL_DB)" \
		python3 small/seed.py
	@echo "==> $(SMALL_DB) ready"

drop-$(SMALL_DB):
	@echo "==> Dropping database: $(SMALL_DB)"
	$(PSQL) -c "DROP DATABASE IF EXISTS $(SMALL_DB)"

refresh-$(SMALL_DB): drop-$(SMALL_DB) $(SMALL_DB)

# medium
$(MEDIUM_DB): deps
	@echo "==> Creating database: $(MEDIUM_DB)"
	$(PSQL) -c "CREATE DATABASE $(MEDIUM_DB)"
	$(PSQL_VARS) -d $(MEDIUM_DB) -f medium/init.sql
	PG_FIXTURE_URL="postgresql://$(PGUSER)@$(PGHOST):$(PGPORT)/$(MEDIUM_DB)" \
		python3 medium/seed.py
	@echo "==> $(MEDIUM_DB) ready"

drop-$(MEDIUM_DB):
	@echo "==> Dropping database: $(MEDIUM_DB)"
	$(PSQL) -c "DROP DATABASE IF EXISTS $(MEDIUM_DB)"

refresh-$(MEDIUM_DB): drop-$(MEDIUM_DB) $(MEDIUM_DB)

# large
$(LARGE_DB): deps
	@echo "==> Creating database: $(LARGE_DB)"
	$(PSQL) -c "CREATE DATABASE $(LARGE_DB)"
	$(PSQL_VARS) -d $(LARGE_DB) -f large/init.sql
	PG_FIXTURE_URL="postgresql://$(PGUSER)@$(PGHOST):$(PGPORT)/$(LARGE_DB)" \
		python3 large/seed.py
	@echo "==> $(LARGE_DB) ready"

drop-$(LARGE_DB):
	@echo "==> Dropping database: $(LARGE_DB)"
	$(PSQL) -c "DROP DATABASE IF EXISTS $(LARGE_DB)"

refresh-$(LARGE_DB): drop-$(LARGE_DB) $(LARGE_DB)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
deps: check-psql
	@pip3 install -q faker psycopg2-binary 2>/dev/null || \
		pip install -q faker psycopg2-binary 2>/dev/null || true

check-psql:
	@command -v psql >/dev/null 2>&1 || \
		(echo "ERROR: psql not found. Install PostgreSQL client."; exit 1)
	@$(PSQL) -c "SELECT 1" >/dev/null 2>&1 || \
		(echo "ERROR: Cannot connect to PostgreSQL at $(PGHOST):$(PGPORT) as $(PGUSER)."; exit 1)
