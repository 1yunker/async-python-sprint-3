import asyncio
from codecs import StreamReader, StreamWriter
from http import client
import logging
from aioconsole import ainput
from server import (
    HOST,
    PORT,
    Message,
    message_object_to_str,
    message_str_to_object,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
# logger.addHandler(logging.StreamHandler(stream=sys.stdout))


class Client:
    def __init__(self, username, server_host=HOST, server_port=PORT):
        self.server_host = server_host
        self.server_port = server_port
        self.reader = None
        self.writer = None
        self.username = username

    async def start(self) -> None:
        """
        Подключаемся к серверу и посылаем стартовое сообщение
        """
        logger.info(f'Запускаем клиента под именем {self.username}')
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.server_host, self.server_port
            )
            print(f'Подключились к {self.server_host}:{self.server_port}')

            # Отправляем стартовое сообщение с именем пользователя
            message_obj = Message(username=self.username)
            message_bytes = message_object_to_str(message_obj).encode()
            self.writer.write(message_bytes)
            await self.writer.drain()
            await asyncio.gather(self.listen(), self.send())

        except Exception as error:
            logger.error(f'Произошла ошибка: {error}')
            self.writer.close()

    async def listen(self) -> None:
        try:
            while True:
                message_bytes = await self.reader.readline()
                if not message_bytes:
                    break
                message_str = message_bytes.decode().strip()
                message_obj = message_str_to_object(message_str)
                print(str(message_obj))

        except OSError as error:
            logger.error(f'Произошла ошибка: {error}')

    async def send(self) -> None:
        while True:
            user_input = await ainput('')
            if not user_input:  # просто нажали Enter
                break

            message_obj = Message(username=self.username, text=user_input)
            message_bytes = message_object_to_str(message_obj).encode()
            self.writer.write(message_bytes)
            await self.writer.drain()


async def main() -> None:
    user_input = str(input('Введите свой username: '))
    client = Client(username=user_input)
    await client.start()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Клиент завершил свою работу.')
