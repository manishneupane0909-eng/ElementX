# Deployment Guide for ElementX

This guide covers multiple ways to deploy your ElementX application so it runs automatically.

## Option 1: Docker Compose (Recommended for Local/Server)

### Prerequisites
- Docker and Docker Compose installed

### Steps
1. Create a `.env` file in the root directory:
```bash
MONGODB_URI=your_mongodb_connection_string
JWT_SECRET=your_secret_key_here
```

2. Start both services:
```bash
docker-compose up -d
```

3. Your app will be available at:
   - Frontend: http://localhost:3000
   - Backend: http://localhost:8000

4. To stop:
```bash
docker-compose down
```

5. To view logs:
```bash
docker-compose logs -f
```

## Option 2: Render (Free Cloud Hosting)

### Backend Deployment
1. Go to [render.com](https://render.com) and sign up
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: elementx-backend
   - **Environment**: Python 3
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Root Directory**: `backend`
5. Add environment variables:
   - `MONGODB_URI`: Your MongoDB connection string
   - `JWT_SECRET`: A random secret key
6. Deploy!

### Frontend Deployment
1. Click "New +" → "Static Site"
2. Connect your GitHub repository
3. Configure:
   - **Name**: elementx-frontend
   - **Build Command**: `cd frontend && npm install && npm run build`
   - **Publish Directory**: `frontend/build`
   - **Root Directory**: `frontend`
4. Add environment variable:
   - `REACT_APP_API_URL`: Your backend URL (e.g., `https://elementx-backend.onrender.com`)
5. Deploy!

## Option 3: Railway (Simple Cloud Hosting)

### Backend
1. Go to [railway.app](https://railway.app)
2. New Project → Deploy from GitHub
3. Select your repo
4. Add service → Backend folder
5. Set environment variables
6. Railway auto-detects Python and runs it

### Frontend
1. Add another service → Frontend folder
2. Set build command: `npm install && npm run build`
3. Set start command: `npx serve -s build`
4. Add `REACT_APP_API_URL` environment variable

## Option 4: PM2 (Process Manager - Local Server)

### Prerequisites
```bash
npm install -g pm2
pip install uvicorn[standard]
```

### Steps
1. Create logs directory:
```bash
mkdir -p logs
```

2. Start both services:
```bash
pm2 start ecosystem.config.js
```

3. Save PM2 configuration:
```bash
pm2 save
pm2 startup
```

4. Your app will be available at:
   - Frontend: http://localhost:3000
   - Backend: http://localhost:8000

5. Useful PM2 commands:
```bash
pm2 list              # View running processes
pm2 logs              # View logs
pm2 restart all       # Restart all
pm2 stop all          # Stop all
pm2 delete all        # Remove all
```

## Option 5: Vercel (Frontend) + Render/Railway (Backend)

### Frontend on Vercel
1. Go to [vercel.com](https://vercel.com)
2. Import your GitHub repository
3. Set root directory to `frontend`
4. Build command: `npm run build`
5. Output directory: `build`
6. Add environment variable: `REACT_APP_API_URL`

### Backend
Use Render or Railway as described above.

## Environment Variables

Create a `.env` file in the root directory:

```env
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/elementx
JWT_SECRET=your-super-secret-key-change-this-in-production
REACT_APP_API_URL=http://localhost:8000  # Change to your backend URL in production
```

## Quick Start (Docker)

```bash
# Clone and navigate
cd ElementX

# Create .env file with your variables
cp .env.example .env  # Edit with your values

# Start everything
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## Troubleshooting

### Backend won't start
- Check if port 8000 is available
- Verify MongoDB connection string
- Check logs: `docker-compose logs backend` or `pm2 logs elementx-backend`

### Frontend won't connect to backend
- Verify `REACT_APP_API_URL` is set correctly
- Check CORS settings in backend
- Ensure backend is running and accessible

### Port conflicts
- Change ports in `docker-compose.yml` or `ecosystem.config.js`
- Update frontend API URL accordingly
