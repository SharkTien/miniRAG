from pydantic import BaseModel

class DocumentResponse(BaseModel):
    """Provide the documentresponse application component."""
    id: str
    filename: str
    status: str
    message: str

class ErrorResponse(BaseModel):
    """Provide the errorresponse application component."""
    detail: str
