from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_route():
    return {"message": "Route router"}
