import asyncio
import json
import logging
import sys
from asyncio.streams import StreamReader, StreamWriter
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

HOST = '127.0.0.1'
PORT = 8000

# Кол-во последних выводимых сообщений (при подключении в общий чат)
LAST_MESSAGES_CNT = 3
# Лимит отправляемых одним пользоватеелм сообщений в час (в общий чат)
LIMIT_MESSAGES_CNT = 5
# Время жизни сообщения в секундах
TTL_MESSAGES_SEC = timedelta(seconds=3600)


class Message:
    def __init__(self, username: str, text='', created_at=datetime.now(),
                 sep=':', to='', send_after=0):
        self.author = username
        self.text = text
        self.datetime = created_at
        self.sep = sep
        self.to_username = to
        self.send_after = send_after

    def __str__(self) -> str:
        return f'{self.author}{self.sep} {self.text}'


def message_object_to_str(message: Message) -> str:
    """
    Сериализует объект Message в строку
    """
    return (f'{message.datetime};{message.author};'
            f'{message.text};{message.sep};{message.to_username}\n')


def message_str_to_object(message: str) -> Message:
    """
    Десериализует строку message в объект Message
    """
    message_list = message.split(sep=';', maxsplit=4)
    username = message_list[1]
    text = message_list[2]
    created_at = datetime.strptime(message_list[0], '%Y-%m-%d %H:%M:%S.%f')
    sep = message_list[3]
    to_username = message_list[4]
    return Message(username=username, text=text, created_at=created_at,
                   sep=sep, to=to_username)


class Server:
    # Имя файла для сохранения истории общего чата
    BACKUP_FILE = 'messages.json'

    def __init__(self, host=HOST, port=PORT):
        self.clients: dict[str, StreamWriter | datetime] = {}
        self.server = None
        self.host: str = host
        self.port: int = port
        self.message_store: list[Message] = []
        self.message_to_send: list[Message] = []

        self.restore_chat_history(self.BACKUP_FILE)

    def backup_chat_history(self, backup_file: str) -> None:
        """
        Сохраняет историю общего чата в JSON-файл (BACKUP_FILE).
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
        Восстанавливает историю общего чата из JSON-файла (BACKUP_FILE).
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
                    sep=message.get('sep'),
                    to=message.get('to_username'),
                )

                if datetime.now() - message_obj.datetime < TTL_MESSAGES_SEC:
                    self.message_store.append(message_obj)
            logger.info(
                f'История общего чата успешно восстановлена из {backup_file}.'
            )
        except Exception as err:
            logger.error(
                f'При чтении файла {backup_file} произошла ошибка: {err}.'
            )

    async def send_start_messages(
            self, username: str, writer: StreamWriter) -> None:
        """
        Посылает новому клиенту стартовое сообщение.
        """
        messages = []
        messages.append(Message(
            'ǁ', '==================================================', sep=''))
        messages.append(Message(
            'ǁ     ', f'{username}, добро пожаловать в общий чат!', sep=''))
        messages.append(Message(
            'ǁ', '--------------------------------------------------', sep=''))
        messages.append(Message(
            'ǁ', '/private username text :отправка личного сообщения', sep=''))
        messages.append(Message(
            'ǁ', '/delay seconds text :отложенная отправка сообщения', sep=''))
        messages.append(Message(
            'ǁ', '/clear_unsent :стереть все неотправленые сообщения', sep=''))
        messages.append(Message(
            'ǁ', '/stop :остановить сервер и сделать бэкап сообщений', sep=''))
        messages.append(Message(
            'ǁ', '==================================================', sep=''))

        for message_obj in messages:
            message_bytes = message_object_to_str(message_obj).encode()
            writer.write(message_bytes)
            await writer.drain()

    async def send_last_messages(self, writer: StreamWriter) -> None:
        """
        Посылает новому клиенту последние LAST_MESSAGES_CNT
        сообщений из общего чата.
        """
        msg_counter = LAST_MESSAGES_CNT
        for message_obj in reversed(self.message_store):
            if message_obj.to_username == '':
                msg_counter -= 1
                if msg_counter < 0:
                    break
                message_bytes = message_object_to_str(message_obj).encode()
                writer.write(message_bytes)
                await writer.drain()

    async def send_unread_messages(
            self, writer: StreamWriter, username: str,
            exit_datetime: datetime) -> None:
        """
        Посылает повторно подключенному клиенту непрочитанные
        личные сообщения и сообщения из общего чата.
        """
        for message_obj in reversed(self.message_store):
            if message_obj.datetime > exit_datetime:
                if message_obj.to_username in ('', username):
                    message_bytes = message_object_to_str(message_obj).encode()
                    writer.write(message_bytes)
                    await writer.drain()
            else:
                break

    async def send_all_except_me(
            self, message: str, write_username: str) -> None:
        """
        Отправляет сообщение всем клиентам в общем чате кроме себя.
        """
        for username, writer in self.clients.items():
            if username != write_username and isinstance(writer, StreamWriter):
                message_obj = Message(write_username, message)
                message_bytes = message_object_to_str(message_obj).encode()
                writer.write(message_bytes)
                await writer.drain()

    async def send_private_message(
            self, message: str, target_username: str) -> None:
        """
        Отправляет личное сообщение указанному пользователю.
        """
        writer = self.clients[target_username]
        message = ' '.join(['[private]', message])
        message_obj = Message(target_username, message)
        message_bytes = message_object_to_str(message_obj).encode()
        writer.write(message_bytes)
        await writer.drain()

    async def client_connected(
            self, reader: StreamReader, writer: StreamWriter):

        # Фиксируем счетчик лимита сообщений и время соединения
        msg_counter = LIMIT_MESSAGES_CNT
        connected_at = datetime.now()

        # Принимаем от клиента стартовое сообщение с именем пользователя
        intro_bytes = await reader.readline()
        # Принятый байткод переводим в строку и десереализуем в объект Message
        message_str = intro_bytes.decode().strip()
        message_obj = message_str_to_object(message_str)

        # Смотрим не подключался ли пользователь ранее
        if message_obj.author not in self.clients.keys():
            self.clients[message_obj.author] = writer
            await self.send_start_messages(message_obj.author, writer)
            await self.send_last_messages(writer)

            new_client_message = f'== {message_obj.author} вошел в чат =='
            print(new_client_message)
            await self.send_all_except_me(
                new_client_message, message_obj.author)
        else:
            exit_datetime = self.clients[message_obj.author]
            self.clients[message_obj.author] = writer
            await self.send_unread_messages(
                writer, message_obj.author, exit_datetime)

        try:
            while True:
                message_bytes = await reader.readline()
                if not message_bytes:
                    break

                message_str = message_bytes.decode().strip()
                message_obj = message_str_to_object(message_str)

                if message_obj.text.startswith('/stop'):
                    await self.stop()

                if message_obj.text.startswith('/delay'):
                    """
                    Отправить сообщение c заданной в секундах задержкой.
                    """
                    # Парсим текст сообщения и записываем данные в Message
                    [_, delay, text] = message_obj.text.split(maxsplit=2)
                    message_obj.send_after = delay
                    message_obj.text = text
                    self.message_to_send.append(message_obj)

                elif message_obj.text.startswith('/clear_unsent'):
                    """
                    Стереть из списка все неотправленные сообщения.
                    """
                    self.message_to_send.clear()

                elif message_obj.text.startswith('/private'):
                    """
                    Отрпавить личное сообщение указанному пользователю.
                    """
                    # Парсим текст сообщения и записываем данные в Message
                    [_, username, text] = message_obj.text.split(maxsplit=2)
                    message_obj.to_username = username
                    message_obj.text = text
                    self.message_store.append(message_obj)

                    await self.send_private_message(text, username)
                else:
                    # Обновляем лимит сообщений раз в час
                    if (datetime.now() - connected_at).seconds > 3600:
                        msg_counter = LIMIT_MESSAGES_CNT
                        connected_at = datetime.now()

                    msg_counter -= 1
                    if msg_counter < 0:
                        # Посылаем пользователю информацию о превышении
                        # лимита сообщений в общем чате
                        message_obj = Message(
                            '!', 'Вы исчерпали лимит сообщений в общем чате !',
                            sep='')
                        message_bytes = message_object_to_str(
                            message_obj).encode()
                        writer.write(message_bytes)
                    else:
                        self.message_store.append(message_obj)
                        print(message_obj)

                        await self.send_all_except_me(
                            message_obj.text, message_obj.author)

        except asyncio.CancelledError as error:
            logger.error(f'Во время работы возникла ошибка: {error}')
        finally:
            # Сохраняем дату выхода пользователя из чата
            self.clients[message_obj.author] = datetime.now()
            # Информируем клиентов о выходе пользователя из чата
            message_str = f'== {message_obj.author} вышел из чата =='
            await self.send_all_except_me(message_str, message_obj.author)

            logger.info(message_str)
            writer.close()

    async def listen(self):
        self.server = await asyncio.start_server(
            self.client_connected, self.host, self.port
        )
        logger.info(f'Запущен сервер http://{self.host}:{self.port}/')

        async with self.server:
            await self.server.serve_forever()

    async def send_with_delay(self):
        """
        Отправляет сообщения из списка на отправку при наступлении времени.
        """
        while True:
            for message_obj in self.message_to_send:
                if (
                    message_obj.datetime
                    + timedelta(seconds=int(message_obj.send_after))
                    < datetime.now()
                ):

                    # Переносим сообщение из списка на отправку
                    # в список отправленных и отправляем в общий чат
                    self.message_to_send.remove(message_obj)
                    self.message_store.append(message_obj)
                    print(message_obj)
                    await self.send_all_except_me(
                        message_obj.text, message_obj.author)
            await asyncio.sleep(1)

    async def stop(self):
        """
        Штатно останавливает сервер и сохраняет историю сообщений.
        """
        self.server.close()
        await self.server.wait_closed()
        self.backup_chat_history(self.BACKUP_FILE)
        logger.info('Сервер штатно остановлен.')


async def main() -> None:
    try:
        server = Server()
        await asyncio.gather(server.listen(), server.send_with_delay())
    except asyncio.CancelledError:
        logger.info('Сервер остановлен по требованию клиента.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Сервер нештатно завершил свою работу.')
