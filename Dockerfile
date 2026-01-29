FROM python:3.11-slim

WORKDIR /code

# Install dependencies
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy application
COPY ./app /code/app
COPY ./main.py /code/main.py

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
