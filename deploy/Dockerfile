FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt requirements-email.txt ./
RUN python -m pip install -r requirements-email.txt \
    && python -m playwright install --with-deps chrome \
    && groupadd --gid 1000 agent \
    && useradd --uid 1000 --gid agent --create-home agent \
    && mkdir /data /oauth \
    && chown agent:agent /data /oauth

COPY senpilot ./senpilot
COPY deploy/container.json /etc/senpilot/agent.json
USER agent
ENTRYPOINT ["python", "-m", "senpilot.service", "--config", "/etc/senpilot/agent.json"]
