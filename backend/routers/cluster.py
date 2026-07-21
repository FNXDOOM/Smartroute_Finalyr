from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_cluster():
    return {"message": "Cluster router"}
