"""Generic CRUD repository base class (Repository pattern).

Concrete repositories subclass this for a specific ORM model, keeping
raw SQLAlchemy usage out of the service layer entirely.
"""
from typing import Generic, Optional, Type, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, id_: str) -> Optional[ModelT]:
        return self.db.get(self.model, id_)

    def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        self.db.delete(entity)
        self.db.commit()
