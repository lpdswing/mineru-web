from sqlalchemy import Column, Integer, String, Boolean
from app.models.base import Base
from app.models.enums import DEFAULT_MINERU_BACKEND, normalize_backend_value

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    ocr_lang = Column(String(32), default='ch')  # lang背后对应的是ocr模型的选择
    force_ocr = Column(Boolean, default=False)
    # 默认值必须与 api/settings.py GET 兜底一致：True。曾因默认 False，
    # 首次部分 PUT /settings 建行时静默关闭表格/公式识别，导致发票表格整块丢失。
    table_recognition = Column(Boolean, default=True)
    formula_recognition = Column(Boolean, default=True)
    backend = Column(String(64), default=DEFAULT_MINERU_BACKEND)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'ocr_lang': self.ocr_lang,
            'force_ocr': self.force_ocr,
            'table_recognition': self.table_recognition,
            'formula_recognition': self.formula_recognition,
            'backend': normalize_backend_value(self.backend)
        }
