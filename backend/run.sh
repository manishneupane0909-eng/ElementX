#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
# Uncomment next line only if a broken shell MONGODB_URI blocks backend/.env
# unset MONGODB_URI
uvicorn main:app --reload --host 0.0.0.0 --port 8000 --reload-exclude 'venv/*'
