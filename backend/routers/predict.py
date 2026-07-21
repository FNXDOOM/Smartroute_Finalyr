from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_predict():
    return {"message": "Predict router"}
