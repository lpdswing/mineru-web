from sqlalchemy import Column, Integer, String, Text, ForeignKey
from app.models.base import Base

class ParsedContent(Base):
    __tablename__ = 'parsed_contents'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey('files.id'), nullable=False, index=True)
    content = Column(Text, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'file_id': self.file_id,
            'content': self.content
        } 