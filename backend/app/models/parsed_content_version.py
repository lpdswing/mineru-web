from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint, ForeignKey, func
from app.models.base import Base


class ParsedContentVersion(Base):
    """识别结果 Markdown 的编辑历史版本快照。

    - parsed_contents.content 始终等于最新一条版本的内容；
    - 每次保存/恢复都会新增一条版本记录，保证任意历史状态可恢复。
    """

    __tablename__ = 'parsed_content_versions'
    __table_args__ = (
        UniqueConstraint('file_id', 'version', name='uq_parsed_content_version_file_version'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey('files.id', ondelete='CASCADE'), nullable=False, index=True)
    version = Column(Integer, nullable=False)  # 文件内版本号，从 1 递增
    content = Column(Text, nullable=False)     # 该版本的 markdown 快照
    note = Column(String(255), nullable=True)  # 可选编辑备注
    source = Column(String(16), nullable=False, default='parse')  # parse / save / restore
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self):
        """列表展示用（不含 content）。"""
        return {
            'id': self.id,
            'version': self.version,
            'note': self.note,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def to_detail(self):
        """详情用（含 content）。"""
        data = self.to_dict()
        data['content'] = self.content
        return data
