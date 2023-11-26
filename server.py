import asyncio
import logging
import sys
from asyncio.streams import StreamReader, StreamWriter
from datetime import datetime
from tkinter import S

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


class Message:
    def __init__(self, username: str, text='', created_at=datetime.now()):
        self.author = username
        self.text = text
        self.datetime = created_at

    def __str__(self) -> str:
        return f'{self.datetime};{self.author};{self.text}\n'


class Chat:
    def __init__(self, name: str, clients: set[str],
                 messages: list[Message], last_msg_cnt=LAST_MESSAGES_CNT):
        self.name = name
        self.clients = clients if clients else set()
        self.messages = messages or []
        self.last_msg_cnt = last_msg_cnt


class Server:

    BACKUP_FILE = 'Chat_messages.json'

    def __init__(self, host=HOST, port=PORT):
        self.clients = {}
        self.server = None
        self.host = host
        self.port = port
        self.messages_store = []
        self.public_chat = Chat(PUBLIC_CHAT_NAME, clients=set(), messages=[])
        self.chats = {'Public': self.public_chat}

        # self.restore_server_history()

    @staticmethod
    def message_str_to_message_obj(message: str):
        message_list = message.split(sep=';', maxsplit=2)
        created_at = datetime.strptime(message_list[0], '%Y-%m-%d %H:%M:%S.%f')
        username = message_list[1]  # [:-1]
        text = message_list[2]
        return Message(created_at=created_at, username=username, text=text)

    async def send_last_messages(self, writer: StreamWriter) -> None:
        """
        Посылает клиенту последние LAST_MESSAGES_CNT сообщений
        """
        for message in self.messages_store[-LAST_MESSAGES_CNT:]:
            writer.write(f'{message}\n'.encode())
            await writer.drain()

    async def send_everyone_exept_me(self, message: str, write_username: str) -> None:
        """
        Отправляет сообщения всем клиентам в чате кроме себя
        """
        # for user, client_writer in self.clients.items():
        #     for chat_name, chat in self.chats.items():
        #         if (user in chat.clients and write_username in chat.clients
        #             and user != write_username):
        #             client_writer.write(f'{message}\n'.encode())
        #             await client_writer.drain()

    async def client_connected(
            self, reader: StreamReader, writer: StreamWriter):

        # Принятый байткод переводим в строку и десереализуем в объект Message
        message_bytes = await reader.readline()
        message_str = message_bytes.decode().strip()
        message_obj = self.message_str_to_message_obj(message_str)

        # username_bytes: bytes = await reader.readline()
        # username: str = username_bytes.decode().strip()
        # self.public_chat.clients.add(username)

        if message_obj.author in self.clients.keys():
            self.clients[message_obj.author] = writer
            await self.send_last_messages(writer)
        else:
            self.public_chat.clients.add(message_obj.author)
            new_client_message = f'{message_obj.author} вошел в чат'
            print(new_client_message)
            self.messages_store.append(message_obj)
            await self.send_everyone_exept_me(
                new_client_message, message_obj.author)

        try:
            while True:
                message_bytes: bytes = await reader.readline()
                if not message_bytes:
                    break

                if message_bytes.decode().startswith('/quit'):
                    break

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

                message_str = message_bytes.decode().strip()
                message_obj = self.message_str_to_message_obj(message_str)
                self.messages_store.append(message_obj)
                print(message_str)
                await self.send_everyone_exept_me(
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

    # async def stop(self):
    #     self.server.close()
    #     await self.server.wait_closed()
    #     # write the chat history to a file
    #     with open(self.BACKUP_FILE, 'w') as f:
    #         # pickle.dump(self.chats, f)
    #     logger.info('Server stopped')


async def main() -> None:
    server = Server()
    await server.listen()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Сервер завершил свою работу.')
