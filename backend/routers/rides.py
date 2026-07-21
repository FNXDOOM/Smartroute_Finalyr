from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_rides():
    return {"message": "Rides router"}
