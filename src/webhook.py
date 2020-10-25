import asyncio
import json
import logging
import os
import sys
import traceback

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
            ssl=bool(os.environ['MATRIX_SSLVERIFY']),
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

    async def message_callback(self, room: MatrixRoom, event: RoomMessageText) -> None:
        logging.info(colored(
            f"@{room.user_name(event.sender)} in {room.display_name} | {event.body}",
            'green'
        ))

    async def sync_callback(self, response: SyncResponse) -> None:
        logging.info(f"We synced, token: {response.next_batch}")

        if not self.greeting_sent:
            self.greeting_sent = True

            greeting = f"Hi, I'm up and runnig from **{os.environ['MATRIX_DEVICE']}**, waiting for webhooks!"
            await self.client.room_send(
                room_id=os.environ['MATRIX_ROOMID'],
                message_type="m.room.message",
                content={
                    'msgtype': 'm.text',
                    'body': greeting,
                    'format': 'org.matrix.custom.html',
                    'formatted_body': markdown(greeting, extensions=['extra']),
                },
                ignore_unverified_devices=True
            )

    async def run(self) -> None:
        await self.login()

        self.client.add_event_callback(self.message_callback, RoomMessageText)
        self.client.add_response_callback(self.sync_callback, SyncResponse)

        if self.client.should_upload_keys:
            await self.client.keys_upload()

        await self.client.join(os.environ['MATRIX_ROOMID'])
        await self.client.joined_rooms()

        logging.info('Ready and waiting for events.')

        await self.client.sync_forever(timeout=300000, full_state=True)


async def main() -> None:
    logging.basicConfig(
        level=logging.getLevelName(
            os.environ['PYTHON_LOG_LEVEL'].upper()),
        format='%(asctime)s | %(levelname)s | module:%(name)s | %(message)s'
    )

    e2ee_client = E2EEClient()
    await e2ee_client.run()


try:
    asyncio.get_event_loop().run_until_complete(main())
except Exception:
    logging.critical(traceback.format_exc())
    sys.exit(1)
except KeyboardInterrupt:
    logging.critical('Received keyboard interrupt.')
    sys.exit(0)
