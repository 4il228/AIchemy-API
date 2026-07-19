from pydantic import BaseModel


class CraftRequest(BaseModel):
    element_1: str
    element_2: str


class CraftResponse(BaseModel):
    result: str
    description: str
    image_url: str
    creator_id: int
    creator_nickname: str
