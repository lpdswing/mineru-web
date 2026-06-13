import os
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import AUTH_COOKIE_NAME, decode_session_token


def _legacy_header_enabled() -> bool:
    return os.getenv("AUTH_ALLOW_USER_HEADER", "false").lower() == "true"


async def get_current_user(
    session_token: Optional[str] = Cookie(None, alias=AUTH_COOKIE_NAME),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录，请先登录")

    payload = decode_session_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="登录状态无效")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="登录状态无效")
    return user


async def get_user_id(
    x_user_id: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=AUTH_COOKIE_NAME),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> str:
    if x_user_id and _legacy_header_enabled():
        return x_user_id

    current_user = await get_current_user(
        session_token=session_token,
        authorization=authorization,
        db=db,
    )
    return str(current_user.id)
