from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import firebase_admin
from firebase_admin import credentials, firestore
import threading
import json
import time
from exit_prediction import model_call
import logging
from datetime import datetime
from google.cloud.firestore import SERVER_TIMESTAMP
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List
import json


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('google.api_core.bidi').setLevel(logging.WARNING)

app = FastAPI()

# Initialize Firebase
cred = credentials.Certificate("exitmatrix.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

class InputData(BaseModel):
    layout: List[List[str]]

def serialize_firebase_data(data):
    """Convert Firebase data to JSON serializable format"""
    if isinstance(data, dict):
        return {k: serialize_firebase_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_firebase_data(x) for x in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, (firestore.DocumentReference)):
        return str(data)
    elif data == SERVER_TIMESTAMP:
        return "SERVER_TIMESTAMP"
    else:
        return data

class FirebaseManager:
    def __init__(self):
        self.is_updating = False

    def map_to_string(self, layout):
        """Convert 2D array layout to string format"""
        return '|'.join([''.join(row) for row in layout])

    def update_layout(self, doc_ref, new_layout, is_model_output=True):
        """Update the layout in Firebase with proper metadata"""
        try:
            self.is_updating = True
            
            update_data = {
                'layout': new_layout,
                'timestamp': SERVER_TIMESTAMP,
                'processed': True if is_model_output else False,
                'is_model_output': is_model_output
            }
            
            doc_ref.set(update_data, merge=True)
            logger.info(f"Firebase layout updated successfully - is_model_output: {is_model_output}")
            
        except Exception as e:
            logger.error(f"Error updating Firebase: {str(e)}")
        finally:
            self.is_updating = False

    def should_process_update(self, data):
        """Determine if this update should be processed"""
        # Skip if we're currently updating
        if self.is_updating:
            return False
            
        # If there's no processed flag or it's False, we should process
        return not data.get('processed', False)

firebase_mgr = FirebaseManager()

@app.post("/model-call/")
def model(state_space: InputData):
    try:
        updated_state_space = model_call({"layout": state_space.layout})
        return {"updated_space": updated_state_space, "status": "successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class LayoutResponse(BaseModel):
    layout: List[List[str]]
    status: str
    building_name: str | None = None
    floor_number: int | None = None

@app.get("/current-layout/", response_model=LayoutResponse)
async def get_current_layout():
    """Get the current layout from Firebase in 2D array format"""
    try:
        # Get the current layout from Firebase
        doc_ref = db.collection('current_map').document('info')
        doc = doc_ref.get()
        
        if not doc.exists:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "No layout found"}
            )
            
        data = doc.to_dict()
        layout_str = data.get('layout')
        
        if not layout_str:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Layout data is missing"}
            )
        
        # Convert string layout to 2D array if it's in string format
        if isinstance(layout_str, str):
            layout_2d = [list(row) for row in layout_str.split('|')]
        elif isinstance(layout_str, list):
            layout_2d = layout_str
        else:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid layout format"}
            )
            
        response_data = {
            "layout": layout_2d,
            "status": "success",
            "building_name": data.get('buildingName'),
            "floor_number": data.get('floorNumber')
        }
        
        return JSONResponse(content=jsonable_encoder(response_data))
        
    except Exception as e:
        logger.error(f"Error getting current layout: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/convert-layout/raw/")
async def convert_layout_raw(data: dict = Body(...)):
    """
    Alternative endpoint that accepts raw JSON data
    Useful for clients that can't easily structure the JSON
    """
    try:
        # Extract and validate layout from raw data
        layout = data.get('layout')
        if not layout:
            raise HTTPException(
                status_code=400,
                detail="Missing layout in input data"
            )
            
        # Convert to string format
        layout_string = '|'.join([''.join(row) for row in layout])
        
        return {
            "layout": layout_string,
            "status": "success"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error converting raw layout: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error converting layout: {str(e)}"
        )
    
def on_snapshot(doc_snapshot, changes, read_time):
    """Callback function for Firebase document changes"""
    try:
        for change in changes:
            if change.type.name in ['ADDED', 'MODIFIED']:
                doc = change.document
                data = doc.to_dict()
                
                if not data or 'layout' not in data:
                    logger.info("Skipping update - no layout data")
                    continue

                # Log raw data without serialization for debugging
                logger.info(f"Raw update data - processed: {data.get('processed', False)}, "
                          f"is_model_output: {data.get('is_model_output', False)}")

                # Check if we should process this update
                if not firebase_mgr.should_process_update(data):
                    logger.info("Skipping update - already processed or in progress")
                    continue

                logger.info("Processing new layout change")
                
                # Convert layout to list format if it's a string
                layout = data['layout']
                if isinstance(layout, str):
                    layout = [list(row) for row in layout.split('|')]

                # Process through model
                try:
                    result = model_call({"layout": layout})
                    logger.info("Model call successful")
                    
                    # Convert result to string format
                    result_string = firebase_mgr.map_to_string(result)
                    
                    # Update Firebase with result
                    doc_ref = db.collection('current_map').document('info')
                    firebase_mgr.update_layout(doc_ref, result_string, is_model_output=True)
                    
                except Exception as e:
                    logger.error(f"Error in model processing: {str(e)}")

    except Exception as e:
        logger.error(f"Error in snapshot listener: {str(e)}", exc_info=True)

class FirebaseListener:
    def __init__(self):
        self.watch = None
        self.is_running = False

    def start(self):
        if self.is_running:
            return

        try:
            doc_ref = db.collection('current_map').document('info')
            self.watch = doc_ref.on_snapshot(on_snapshot)
            self.is_running = True
            logger.info("Firebase listener started successfully")
        except Exception as e:
            logger.error(f"Failed to start Firebase listener: {str(e)}")
            self.is_running = False

    def stop(self):
        if self.watch:
            self.watch.unsubscribe()
            self.is_running = False
            logger.info("Firebase listener stopped")

firebase_listener = FirebaseListener()

@app.on_event("startup")
async def startup_event():
    def run_listener():
        firebase_listener.start()
        while firebase_listener.is_running:
            time.sleep(1)

    thread = threading.Thread(target=run_listener, daemon=True)
    thread.start()
    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    firebase_listener.stop()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="192.168.1.7", port=8001)