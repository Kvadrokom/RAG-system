from pydantic import BaseModel


class KnowledgeSchema(BaseModel):
    title: str
    desc: str
    text: str


# Models
class User(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class Query(BaseModel):
    query: str
