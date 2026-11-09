FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/agent_ops/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_ops/requirements.txt
COPY . /app/agent_ops
ENV AGENT_OPS_HOST=0.0.0.0
ENV AGENT_OPS_PORT=8001
EXPOSE 8001
CMD ["uvicorn", "agent_ops.main:app", "--host", "0.0.0.0", "--port", "8001"]