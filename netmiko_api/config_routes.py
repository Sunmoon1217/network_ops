import logging
from fastapi import APIRouter, HTTPException
from .netmiko_service import NetmikoService
from .device_models import DeviceInfo, ConfigResponse

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
console_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(console_handler)

router = APIRouter()

@router.post("/get-device-config", response_model=ConfigResponse)
async def get_device_config(device: DeviceInfo) -> ConfigResponse:
    """
    Get the running configuration from a network device
    """
    logger.info(f"Received request to get config for device: {device.hostname} ({device.address})")
    logger.debug(f"Device info: {device.dict()}")
    
    try:
        # Convert Pydantic model to dictionary
        device_dict = device.dict()
        
        # Get configuration using Netmiko service
        logger.info(f"Calling NetmikoService.get_device_config for {device.hostname}")
        config = NetmikoService.get_device_config(device_dict)
        logger.debug(f"Successfully got config for {device.hostname}")
        
        response = ConfigResponse(
            success=True,
            hostname=device.hostname,
            address=device.address,
            config=config or ""
        )
        logger.info(f"Returning config for {device.hostname}")
        return response
    except Exception as e:
        logger.error(f"Failed to get config for {device.hostname}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")
