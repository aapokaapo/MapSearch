from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    tag_id: Optional[int] = Field(default=None, primary_key=True)
    map_id: int = Field(foreign_key="maps.map_id")
    tag_name: str

    map: Optional["Map"] = Relationship(back_populates="tags")


class Map(SQLModel, table=True):
    __tablename__ = "maps"

    map_id: Optional[int] = Field(default=None, primary_key=True)
    map_name: str
    map_path: str
    message: Optional[str] = None

    tags: List[Tag] = Relationship(back_populates="map")
