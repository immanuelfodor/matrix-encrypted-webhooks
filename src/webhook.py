import asyncio
import json
import logging
import os
import sys
import traceback
from typing import Optional

import yaml
from aiohttp import web
from markdown import markdown
from nio import (AsyncClient, AsyncClientConfig, LoginResponse, MatrixRoom,
                 RoomMessageText, SyncResponse)
from termcolor import colored


class E2EEClient:
    def __init__(self):
        self.STORE_PATH = os.environ['LOGIN_STORE_PATH']
        self.CONFIG_FILE = f"{self.STORE_PATH}/credentials.json"

        self.client: AsyncClient = None
        self.client_config = AsyncClientConfig(
            max_limit_exceeded=0,
            max_timeouts=0,
            store_sync_tokens=True,
            encryption_enabled=True,
        )

        self.greeting_sent = False

    def _write_details_to_disk(self, resp: LoginResponse, homeserver) -> None:
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(
                {
                    'homeserver': homeserver,  # e.g. "https://matrix.example.org"
                    'user_id': resp.user_id,  # e.g. "@user:example.org"
                    'device_id': resp.device_id,  # device ID, 10 uppercase letters
                    'access_token': resp.access_token  # cryptogr. access token
                },
                f
            )

    async def _login_first_time(self) -> None:
        homeserver = os.environ['MATRIX_SERVER']
        user_id = os.environ['MATRIX_USERID']
        pw = os.environ['MATRIX_PASSWORD']
        device_name = os.environ['MATRIX_DEVICE']

        if not os.path.exists(self.STORE_PATH):
            os.makedirs(self.STORE_PATH)

        self.client = AsyncClient(
            homeserver,
            user_id,
            store_path=self.STORE_PATH,
            config=self.client_config,
            ssl=(os.environ['MATRIX_SSLVERIFY'] == 'True'),
        )

        resp = await self.client.login(password=pw, device_name=device_name)

        if (isinstance(resp, LoginResponse)):
            self._write_details_to_disk(resp, homeserver)
        else:
            logging.info(
                f"homeserver = \"{homeserver}\"; user = \"{user_id}\"")
            logging.critical(f"Failed to log in: {resp}")
            sys.exit(1)

    async def _login_with_stored_config(self) -> None:
        if self.client:
            return

        with open(self.CONFIG_FILE, "r") as f:
            config = json.load(f)

            self.client = AsyncClient(
                config['homeserver'],
                config['user_id'],
                device_id=config['device_id'],
                store_path=self.STORE_PATH,
                config=self.client_config,
                ssl=bool(os.environ['MATRIX_SSLVERIFY']),
            )

            self.client.restore_login(
                user_id=config['user_id'],
                device_id=config['device_id'],
                access_token=config['access_token']
            )

    async def login(self) -> None:
        if os.path.exists(self.CONFIG_FILE):
            logging.info('Logging in using stored credentials.')
        else:
            logging.info('First time use, did not find credential file.')
            await self._login_first_time()
            logging.info(
                f"Logged in, credentials are stored under '{self.STORE_PATH}'.")

        await self._login_with_stored_config()

    async def _message_callback(self, room: MatrixRoom, event: RoomMessageText) -> None:
        logging.info(colored(
            f"@{room.user_name(event.sender)} in {room.display_name} | {event.body}",
            'green'
        ))

    async def _sync_callback(self, response: SyncResponse) -> None:
        logging.info(f"We synced, token: {response.next_batch}")

        if not self.greeting_sent:
            self.greeting_sent = True

            greeting = f"Hi, I'm up and runnig from **{os.environ['MATRIX_DEVICE']}**, waiting for webhooks!"
            await self.send_message(greeting)

    async def send_message(
        self,
        message: str,
        sync: Optional[bool] = False
    ) -> None:
        if sync:
            await self.client.sync(timeout=3000, full_state=True)

        content = {
            'msgtype': 'm.text',
            'body': message,
        }
        if os.environ['USE_MARKDOWN'] == 'True':
            # Markdown formatting removes YAML newlines, and can also mess up posted data like system logs
            logging.debug('Markdown formatting is turned on.')

            content['format'] = 'org.matrix.custom.html'
            content['formatted_body'] = markdown(message, extensions=['extra'])

        await self.client.room_send(
            room_id=os.environ['MATRIX_ROOMID'],
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=True
        )

    async def run(self) -> None:
        await self.login()

        self.client.add_event_callback(self._message_callback, RoomMessageText)
        self.client.add_response_callback(self._sync_callback, SyncResponse)

        if self.client.should_upload_keys:
            await self.client.keys_upload()

        await self.client.join(os.environ['MATRIX_ROOMID'])
        await self.client.joined_rooms()

        logging.info('The Matrix client is waiting for events.')

        await self.client.sync_forever(timeout=300000, full_state=True)


class WebhookServer:
    def __init__(self, matrix_client: E2EEClient):
        self.matrix_client = matrix_client
        self.WEBHOOK_PORT = int(os.environ.get('WEBHOOK_PORT', 8000))

    def _format_message(self, msg_format: str, allow_unicode: bool, data) -> str:
        if msg_format == 'json':
            return json.dumps(data, indent=2, ensure_ascii=(not allow_unicode))
        if msg_format == 'yaml':
            return yaml.dump(data, indent=2, allow_unicode=allow_unicode)

    async def _get_index(self, request: web.Request) -> web.Response:
        return web.json_response({'message': 'OK'})

    async def _post_hook(self, request: web.Request) -> web.Response:
        message_format = os.environ['MESSAGE_FORMAT']
        allow_unicode = os.environ['ALLOW_UNICODE'] == 'True'

        logging.debug(f"Headers: {request.headers}")

        token = request.match_info.get('token', '')
        logging.debug(f"Login token: {token}")

        payload = await request.read()
        data = payload.decode()
        logging.info(f"Received raw data: {data}")

        if message_format != 'raw':
            data = dict(await request.post())

            try:
                data = await request.json()
                logging.debug(f"JSON data: {data}")
            except:
                logging.error('Error decoding data as JSON.')
            finally:
                logging.debug(f"Decoded data: {data}")

            data = self._format_message(message_format, allow_unicode, data)

        logging.debug(f"{message_format.upper()} formatted data: {data}")
        await self.matrix_client.send_message(data)

        return web.json_response({'message': 'OK'})

    async def run(self) -> None:
        app = web.Application()

        app.router.add_get('/', self._get_index)
        app.router.add_post('/post/{token:[a-zA-Z0-9]+}', self._post_hook)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(
            runner,
            host='0.0.0.0',
            port=self.WEBHOOK_PORT
        )

        logging.info('The web server is waiting for events.')
        await site.start()


async def main() -> None:
    logging.basicConfig(
        level=logging.getLevelName(
            os.environ.get('PYTHON_LOG_LEVEL', 'info').upper()),
        format='%(asctime)s | %(levelname)s | module:%(name)s | %(message)s'
    )

    matrix_client = E2EEClient()
    webhook_server = WebhookServer(matrix_client)
    processes = [matrix_client.run(), webhook_server.run()]

    await asyncio.gather(*processes, return_exceptions=True)


try:
    asyncio.get_event_loop().run_until_complete(main())
except Exception:
    logging.critical(traceback.format_exc())
    sys.exit(1)
except KeyboardInterrupt:
    logging.critical('Received keyboard interrupt.')
    sys.exit(0)
