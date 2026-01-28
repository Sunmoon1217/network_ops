from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from netmiko_api.config_routes import router as config_router

# Create FastAPI app instance
app = FastAPI(title="Network Device Config API", description="API for getting device configurations using Netmiko")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(config_router)

# Root endpoint
@app.get("/")
async def root():
    """
    Root endpoint for the Network Device Config API
    """
    return {
        "message": "Network Device Config API",
        "version": "1.0.0",
        "description": "API for getting device configurations using Netmiko",
        "endpoints": {
            "get_device_config": "/get-device-config"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)


