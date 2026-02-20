#!/bin/bash

# ElementX Quick Start Script
# This script helps you start the application

echo "🚀 ElementX Startup Script"
echo "=========================="
echo ""

# Check if Docker is installed
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo "✅ Docker found!"
    echo ""
    echo "Starting with Docker Compose..."
    docker-compose up -d
    echo ""
    echo "✅ Services started!"
    echo "Frontend: http://localhost:3000"
    echo "Backend: http://localhost:8000"
    echo ""
    echo "To view logs: docker-compose logs -f"
    echo "To stop: docker-compose down"
elif command -v pm2 &> /dev/null; then
    echo "✅ PM2 found!"
    echo ""
    echo "Starting with PM2..."
    pm2 start ecosystem.config.js
    pm2 save
    echo ""
    echo "✅ Services started!"
    echo "Frontend: http://localhost:3000"
    echo "Backend: http://localhost:8000"
    echo ""
    echo "To view logs: pm2 logs"
    echo "To stop: pm2 stop all"
else
    echo "⚠️  Docker or PM2 not found. Starting manually..."
    echo ""
    
    # Check if .env exists
    if [ ! -f .env ]; then
        echo "Creating .env file..."
        echo "MONGODB_URI=mongodb://localhost:27017/elementx" > .env
        echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env
        echo "REACT_APP_API_URL=http://localhost:8000" >> .env
        echo "✅ .env file created!"
    fi
    
    echo "Starting backend..."
    cd backend
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -r requirements.txt > /dev/null 2>&1
    uvicorn main:app --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
    cd ..
    
    echo "Starting frontend..."
    cd frontend
    if [ ! -d "node_modules" ]; then
        npm install > /dev/null 2>&1
    fi
    npm start &
    FRONTEND_PID=$!
    cd ..
    
    echo ""
    echo "✅ Services started!"
    echo "Frontend: http://localhost:3000 (PID: $FRONTEND_PID)"
    echo "Backend: http://localhost:8000 (PID: $BACKEND_PID)"
    echo ""
    echo "To stop: kill $BACKEND_PID $FRONTEND_PID"
fi
