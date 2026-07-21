from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_vehicle():
    return {"message": "Vehicle router"}
