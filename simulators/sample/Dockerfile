FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "pymodbus>=3.9.2"
COPY tf03_sim.py /app/tf03_sim.py

CMD ["python", "tf03_sim.py"]
