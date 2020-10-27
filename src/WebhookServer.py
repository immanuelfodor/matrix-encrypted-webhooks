import asyncio
import json
import logging
import os

import yaml
from aiohttp import web

from E2EEClient import E2EEClient


class WebhookServer:
    def __init__(self):
        self.matrix_client: E2EEClient = None
        self.WEBHOOK_PORT = int(os.environ.get('WEBHOOK_PORT', 8000))
        self.KNOWN_TOKENS = self._parse_known_tokens(
            os.environ['KNOWN_TOKENS'])

    def _parse_known_tokens(self, rooms: str) -> dict:
        known_tokens = {}

        for pairs in rooms.split(' '):
            token, room, app_name = pairs.split(',')
            known_tokens[token] = {'room': room, 'app_name': app_name}

        return known_tokens

    def get_known_rooms(self) -> set:
        known_rooms = set()

        known_rooms.add(os.environ['MATRIX_ADMIN_ROOM'])
        for token in self.KNOWN_TOKENS:
            known_rooms.add(self.KNOWN_TOKENS[token]['room'])

        return known_rooms

    def _format_message(self, msg_format: str, allow_unicode: bool, data) -> str:
        if msg_format == 'json':
            return json.dumps(data, indent=2, ensure_ascii=(not allow_unicode))
        if msg_format == 'yaml':
            return yaml.dump(data, indent=2, allow_unicode=allow_unicode)

    async def _get_index(self, request: web.Request) -> web.Response:
        return web.json_response({'success': True})

    async def _post_hook(self, request: web.Request) -> web.Response:
        message_format = os.environ['MESSAGE_FORMAT']
        allow_unicode = os.environ['ALLOW_UNICODE'] == 'True'

        token = request.match_info.get('token', '')
        logging.debug(f"Login token: {token}")
        logging.debug(f"Headers: {request.headers}")

        payload = await request.read()
        data = payload.decode()
        logging.info(f"Received raw data: {data}")

        if token not in self.KNOWN_TOKENS.keys():
            logging.error(
                f"Login token '{token}' is not recognized as known token.")
            return web.json_response({'error': 'Token mismatch'}, status=404)

        if message_format not in ['raw', 'json', 'yaml']:
            logging.error(
                f"Message format '{message_format}' is not allowed, please check the config.")
            return web.json_response({'error': 'Gateway configured with unknown message format'}, status=415)

        if message_format != 'raw':
            data = dict(await request.post())

            try:
                data = await request.json()
            except:
                logging.error('Error decoding data as JSON.')
            finally:
                logging.debug(f"Decoded data: {data}")

            data = self._format_message(message_format, allow_unicode, data)

        logging.debug(f"{message_format.upper()} formatted data: {data}")
        await self.matrix_client.send_message(
            data,
            self.KNOWN_TOKENS[token]['room'],
            self.KNOWN_TOKENS[token]['app_name']
        )

        return web.json_response({'success': True})

    async def run(self, matrix_client: E2EEClient) -> None:
        self.matrix_client = matrix_client
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
