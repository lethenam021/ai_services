#!/bin/bash

# Kill existing processes
pkill -f "uvicorn" 2>/dev/null || true
pkill -f "gradio" 2>/dev/null || true

echo "🚀 Starting Bình Dân Học AI Services..."

# Start API
echo "📡 Starting API on port 8000..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for API to be ready
sleep 5

# Start Gradio
echo "🎨 Starting Gradio Test UI on port 7860..."
python gradio_app.py &
GRADIO_PID=$!

echo ""
echo "✅ All services running:"
echo "   📚 API Docs:      http://localhost:8000/docs"
echo "   🧪 Gradio UI:     http://localhost:7860"
echo "   ❤️  Health Check:  http://localhost:8000/api/v1/health"
echo ""
echo "Press Ctrl+C to stop all services"

# Graceful shutdown
trap "echo '🛑 Stopping services...'; kill $API_PID $GRADIO_PID 2>/dev/null; exit" INT

wait