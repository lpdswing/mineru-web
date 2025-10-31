from sqlalchemy import Column, Integer, String, Boolean, Enum
from app.models.base import Base
from app.models.enums import SettingsBackendType

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    ocr_lang = Column(String(32), default='ch')  # lang背后对应的是ocr模型的选择
    force_ocr = Column(Boolean, default=False)
    table_recognition = Column(Boolean, default=False)
    formula_recognition = Column(Boolean, default=False)
    backend = Column(Enum(SettingsBackendType), default=SettingsBackendType.PIPELINE)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'ocr_lang': self.ocr_lang,
            'force_ocr': self.force_ocr,
            'table_recognition': self.table_recognition,
            'formula_recognition': self.formula_recognition,
            'backend': self.backend.value if self.backend else SettingsBackendType.PIPELINE.value
        }