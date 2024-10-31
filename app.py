from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from exit_prediction import model_call

app = FastAPI()

class InputData(BaseModel):
    layout: List[List[str]]

@app.post("/model-call/")
def model(state_space : InputData):
    try:
        updated_state_space = model_call({"layout":state_space.layout})
        return {"updated_space": updated_state_space, "status": "successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
