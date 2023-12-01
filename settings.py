from datetime import timedelta

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ServerSettings(BaseModel):
    HOST: str = Field(default='127.0.0.1')
    PORT: int = Field(default=8000)
    # Имя файла для сохранения истории общего чата
    BACKUP_FILE: str = Field(default='messages.json')


class Settings(BaseSettings):
    # Параметры сервера
    SERVER: ServerSettings = ServerSettings()
    # Кол-во последних выводимых сообщений (при подключении в общий чат)
    LAST_MESSAGES_CNT: int = Field(default=3)
    # Лимит отправляемых одним пользоватеелм сообщений в час (в общий чат)
    LIMIT_MESSAGES_CNT: int = Field(default=5)
    # Время жизни сообщения в секундах
    TTL_MESSAGES_SEC: timedelta = Field(default=timedelta(seconds=3600))
