# Build context is the parent `resumes/` directory — resume_builder.py imports
# resume.py from one level above resume_service/, so both must ship together.
FROM python:3.10-slim

WORKDIR /app

COPY resume_service/requirements.txt resume_service/requirements.txt
RUN pip install --no-cache-dir -r resume_service/requirements.txt

COPY resume.py .
COPY resume_service/ resume_service/

WORKDIR /app/resume_service

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
