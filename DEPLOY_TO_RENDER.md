# Deploy ElementX to Render.com (Step-by-Step Guide)

Since your code is already on GitHub, follow these steps to make your app live!

## Prerequisites
- GitHub repository with your ElementX code
- MongoDB connection string (from MongoDB Atlas or your MongoDB instance)
- Render.com account (free tier available)

## Step 1: Deploy Backend

1. **Go to Render.com**
   - Visit [render.com](https://render.com)
   - Sign up/login (you can use GitHub to sign in)

2. **Create New Web Service**
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select your ElementX repository

3. **Configure Backend Service**
   - **Name**: `elementx-backend`
   - **Environment**: `Python 3`
   - **Region**: Choose closest to you
   - **Branch**: `main` (or your default branch)
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

4. **Add Environment Variables**
   Click "Advanced" → "Add Environment Variable":
   - `MONGODB_URI`: Your MongoDB connection string
     - Example: `mongodb+srv://username:password@cluster.mongodb.net/elementx`
   - `JWT_SECRET`: A random secret key (you can generate one or Render will auto-generate)
     - Generate one: `openssl rand -hex 32` or use any long random string

5. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment (takes 2-5 minutes)
   - Copy your backend URL (e.g., `https://elementx-backend.onrender.com`)

## Step 2: Deploy Frontend

1. **Create New Static Site**
   - Click "New +" → "Static Site"
   - Connect the same GitHub repository

2. **Configure Frontend Service**
   - **Name**: `elementx-frontend`
   - **Branch**: `main` (or your default branch)
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `build`

3. **Add Environment Variable**
   - `REACT_APP_API_URL`: Your backend URL from Step 1
     - Example: `https://elementx-backend.onrender.com`

4. **Deploy**
   - Click "Create Static Site"
   - Wait for deployment (takes 2-5 minutes)
   - Your frontend will be live! (e.g., `https://elementx-frontend.onrender.com`)

## Step 3: Update CORS (if needed)

If you get CORS errors, update your backend `main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://elementx-frontend.onrender.com",  # Your frontend URL
        "http://localhost:3000",  # For local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Then redeploy the backend.

## Alternative: Use Single render.yaml (Easier!)

If you prefer, you can deploy both services at once:

1. **Create Blueprint**
   - Click "New +" → "Blueprint"
   - Connect your GitHub repository
   - Render will detect `render.yaml` in the root
   - It will create both services automatically!

2. **Set Environment Variables**
   - Go to each service and add:
     - Backend: `MONGODB_URI` and `JWT_SECRET`
     - Frontend: `REACT_APP_API_URL` (pointing to backend URL)

## Your App is Now Live! 🎉

- **Frontend**: `https://elementx-frontend.onrender.com`
- **Backend**: `https://elementx-backend.onrender.com`

## Free Tier Notes

- Render free tier spins down after 15 minutes of inactivity
- First request after spin-down takes ~30 seconds (cold start)
- For always-on, upgrade to paid plan ($7/month per service)

## Troubleshooting

### Backend won't start
- Check logs in Render dashboard
- Verify `MONGODB_URI` is correct
- Ensure all dependencies are in `requirements.txt`

### Frontend can't connect to backend
- Verify `REACT_APP_API_URL` matches your backend URL exactly
- Check CORS settings in backend
- Rebuild frontend after changing environment variables

### 502 Bad Gateway
- Backend might be spinning up (wait 30 seconds)
- Check backend logs for errors
- Verify health check endpoint works: `https://your-backend.onrender.com/health`

## Next Steps

1. **Custom Domain** (optional): Add your own domain in Render settings
2. **Environment Variables**: Keep sensitive data in Render's environment variables
3. **Monitoring**: Check Render dashboard for logs and metrics
4. **Auto-Deploy**: Every push to main branch auto-deploys!

## Quick Commands

```bash
# View backend logs
# Go to Render dashboard → elementx-backend → Logs

# View frontend logs  
# Go to Render dashboard → elementx-frontend → Logs

# Manual redeploy
# Go to service → Manual Deploy → Deploy latest commit
```

Your app is now live and will automatically deploy on every GitHub push! 🚀
