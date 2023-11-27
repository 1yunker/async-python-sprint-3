import asyncio
import json
import logging
import sys
from asyncio.streams import StreamReader, StreamWriter
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(stream=sys.stdout))

HOST = '127.0.0.1'
PORT = 8000

# Название общего чата
PUBLIC_CHAT_NAME = 'Public'
# Кол-во последних выводимых сообщений (при подключении в общий чат)
LAST_MESSAGES_CNT = 20
# Лимит отправляемых одним пользоватеелм сообщений в час (в общий чат)
LIMIT_MESSAGES_CNT = 20
# Время жизни сообщения в секундах
TTL_MESSAGES_SEC = timedelta(seconds=3600)


class Message:
    def __init__(self, username: str, text='', created_at=datetime.now()):
        self.author = username
        self.text = text
        self.datetime = created_at

    def __str__(self) -> str:
        return f'{self.author}: {self.text}'


def message_obj_to_message_str(message: Message) -> str:
    """
    Сериализует объект Message в строку
    """
    return f'{message.datetime};{message.author};{message.text}\n'


def message_str_to_message_obj(message: str) -> Message:
    """
    Десериализует строку message в объект Message
    """
    message_list = message.split(sep=';', maxsplit=2)
    created_at = datetime.strptime(message_list[0], '%Y-%m-%d %H:%M:%S.%f')
    username = message_list[1]  # [:-1]
    text = message_list[2]
    return Message(created_at=created_at, username=username, text=text)


class Chat:
    def __init__(self, name: str, clients: set[str],
                 messages: list[Message], last_msg_cnt=LAST_MESSAGES_CNT):
        self.name = name
        self.clients = clients if clients else set()
        self.messages = messages or []
        self.last_msg_cnt = last_msg_cnt


class Server:
    # Имя файла для сохранения истории общего чата
    BACKUP_FILE = 'messages.json'

    def __init__(self, host=HOST, port=PORT):
        self.clients = {}
        self.server = None
        self.host = host
        self.port = port
        self.message_store = []
        self.public_chat = Chat(PUBLIC_CHAT_NAME, clients=set(), messages=[])
        self.chats = {'Public': self.public_chat}

        self.restore_chat_history(self.BACKUP_FILE)

    def backup_chat_history(self, backup_file: str) -> None:
        """
        Сохраняет историю общего чата в JSON-файл (BACKUP_FILE)
        """
        messages_json = []
        for message in self.message_store:
            message_dict = dict(message.__dict__)
            message_dict['datetime'] = str(message.datetime)
            messages_json.append(message_dict)

        with open(backup_file, 'w') as f:
            json.dump(messages_json, f, indent=4)
        logger.info(
            f'История общего чата успешно сохранена в {backup_file}.'
        )

    def restore_chat_history(self, backup_file: str) -> None:
        """
        Восстанавливает историю общего чата из JSON-файла (BACKUP_FILE)
        """
        try:
            with open(backup_file, 'r') as f:
                messages = json.load(f)

            for message in messages:
                message_obj = Message(
                    username=message.get('author'),
                    text=message.get('text'),
                    created_at=datetime.strptime(
                        message.get('datetime'), '%Y-%m-%d %H:%M:%S.%f'
                    ),
                )

                if message_obj.datetime - datetime.now() < TTL_MESSAGES_SEC:
                    self.message_store.append(message_obj)
            logger.info(
                f'История общего чата успешно восстановлена из {backup_file}.'
            )
        except Exception as err:
            logger.error(
                f'При чтении файла {backup_file} произошла ошибка: {err}.'
            )

    async def send_last_messages(self, writer: StreamWriter) -> None:
        """
        Посылает клиенту последние LAST_MESSAGES_CNT сообщений
        """
        for message_obj in self.message_store[-LAST_MESSAGES_CNT:]:
            message_bytes = message_obj_to_message_str(message_obj).encode()
            writer.write(message_bytes)
            await writer.drain()
        # await asyncio.sleep(0.1)

    async def send_all_exсept_me(
            self, message: str, write_username: str) -> None:
        """
        Отправляет сообщения всем клиентам в чате кроме себя
        """
        await asyncio.sleep(0.1)
        # for user, client_writer in self.clients.items():
        #     for chat_name, chat in self.chats.items():
        #         if (user in chat.clients and write_username in chat.clients
        #             and user != write_username):
        #             client_writer.write(f'{message}\n'.encode())
        #             await client_writer.drain()

    async def client_connected(
            self, reader: StreamReader, writer: StreamWriter):

        # Принятый байткод переводим в строку и десереализуем в объект Message
        intro_bytes: bytes = await reader.readline()
        message_str = intro_bytes.decode().strip()
        message_obj = message_str_to_message_obj(message_str)

        if message_obj.author not in self.clients.keys():
            self.clients[message_obj.author] = writer
            await self.send_last_messages(writer)
        else:
            self.public_chat.clients.add(message_obj.author)
            new_client_message = f'{message_obj.author} добавился в чат'
            print(new_client_message)
            await self.send_all_exсept_me(
                new_client_message, message_obj.author)

        try:
            while True:
                message_bytes = await reader.readline()
                if not message_bytes:
                    break

                message_str = message_bytes.decode().strip()
                message_obj = message_str_to_message_obj(message_str)

                if message_obj.text.startswith('/quit'):
                    break

                if message_obj.text.startswith('/stop'):
                    await self.stop()

                # if message_bytes.decode().startswith('/chats'):
                #     """Метод получения списка чатов"""
                #     await self.get_chats(message_bytes, writer)
                #     continue

                # if message_bytes.decode().startswith('/get_chat'):
                #     """Метод создания чата или переход в существующий"""
                #     await self.create_chat(message_bytes, username, writer)
                #     continue

                # if message_bytes.decode().startswith('/send'):
                #     """Метод отправки сообщения определенному клиенту"""
                #     await self.send_to_one_client(message_bytes, username)
                #     continue

                self.message_store.append(message_obj)
                print(message_obj)

                await self.send_all_exсept_me(
                    message_str, message_obj.author)

        except asyncio.IncompleteReadError as error:
            logger.error(f'Server catch IncompleteReadError: {error}')
        finally:
            self.clients[message_obj.author] = None
            logger.info(f'{message_obj.author} вышел из чата')
            writer.close()

    async def listen(self):
        self.server = await asyncio.start_server(
            self.client_connected, self.host, self.port
        )
        logger.info(f'Запущен сервер http://{self.host}:{self.port}/')

        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()
        self.backup_chat_history(self.BACKUP_FILE)
        logger.info('Сервер остановлен.')


async def main() -> None:
    try:
        server = Server()
        await server.listen()
    except asyncio.CancelledError:
        print('Сервер остановлен по требованию клиента.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Сервер завершил свою работу.')
