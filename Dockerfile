# General arguments
ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.9.30
ARG DD_SERVERLESS_INIT_VERSION=1

############################### stage ###############################
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

############################### stage ###############################
FROM datadog/serverless-init:${DD_SERVERLESS_INIT_VERSION} AS dd_init


############################### stage ###############################
# To enable ssh & remote debugging on app service change the base image to the one below
# FROM mcr.microsoft.com/azure-functions/python:4-python3.12-appservice
FROM mcr.microsoft.com/azure-functions/python:4-python${PYTHON_VERSION} AS runtime
ARG INSTALL_IADB_CA=false
ARG IADB_ROOT_CA_FILE=.docker/empty-iadb-root-ca.crt

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    AzureFunctionsJobHost__Logging__Console__DisableColors=true

# Install Datadog serverless-init
COPY --from=dd_init /datadog-init /app/datadog-init
COPY .docker/start-functions.sh /app/start-functions.sh
RUN chmod +x /app/start-functions.sh

# Install uv
COPY --from=uv /uv /bin/uv

# Optionally trust the corporate TLS inspection root used on the IADB network.
# This avoids BuildKit-only secret mounts so Azure ACR server-side builds work.
COPY ${IADB_ROOT_CA_FILE} /tmp/iadb-root-ca.crt
RUN set -eux; \
    if [ "$INSTALL_IADB_CA" = "true" ]; then \
      test -s /tmp/iadb-root-ca.crt; \
      grep -q "BEGIN CERTIFICATE" /tmp/iadb-root-ca.crt; \
      cp /tmp/iadb-root-ca.crt /usr/local/share/ca-certificates/iadb-root-ca.crt; \
      update-ca-certificates; \
    else \
      echo "Skipping corporate root CA; using base image CA bundle."; \
    fi; \
    rm -f /tmp/iadb-root-ca.crt

# Install Microsoft ODBC Driver 18 for SQL Server (required by aioodbc/pyodbc)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl gnupg ca-certificates apt-transport-https; \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor --batch --yes -o /usr/share/keyrings/microsoft-prod.gpg; \
    chmod 644 /usr/share/keyrings/microsoft-prod.gpg; \
    curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list \
      -o /etc/apt/sources.list.d/mssql-release.list; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev; \
    rm -rf /var/lib/apt/lists/*


# Install python dependencies (no dev)
WORKDIR /home/site/wwwroot
COPY ./pyproject.toml ./uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/python/3
RUN uv --native-tls sync --no-dev --locked

COPY . /home/site/wwwroot
RUN rm -rf /home/site/wwwroot/.docker /home/site/wwwroot/iadb-root-ca.crt

ENTRYPOINT ["/app/datadog-init"]
CMD ["/app/start-functions.sh"]
