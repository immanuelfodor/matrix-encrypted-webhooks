# End-to-end encrypted (E2EE) Matrix Webhook Gateway <!-- omit in toc -->

A microservice that forwards form data or JSON objects received in an HTTP POST request to an end-to-end-encrypted (E2EE) Matrix room. There is no schema restriction on the posted data, so you can throw at it _anyting_! Supports multiple rooms and sender aliases with different associated webhook URLs, e.g, one for Grafana, another for `curl`, and so on. Can convert the received payload to JSON or YAML for better message readability, and can apply Markdown formatting to messages. Easy installation with `docker-compose`.

## Table of contents <!-- omit in toc -->

- [Usage](#usage)
- [Configuration](#configuration)
  - [Available customizations of posted messages](#available-customizations-of-posted-messages)
  - [Matrix connection parameters](#matrix-connection-parameters)
  - [The notification channels](#the-notification-channels)
- [Dependencies](#dependencies)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Improvement ideas](#improvement-ideas)
- [Disclaimer](#disclaimer)
- [Contact](#contact)

## Usage

- Create a new Matrix account on your homeserver for receiving webhooks
- Add this account to a new E2EE room with yourself then login with the new account and accept the invite
- Clone this repo, create a copy of the provided `.env.example` file as `.env`, and fill in all the required info
- Start up the gateway. It logs in, sends a greeting message, and listens to webhook events
- Send data with `curl` or any HTTP POST capable client to the gateway
- Enjoy the messages in your chat!

```bash
cp .env{.example,}
# edit the .env with your preferred editor

mkdir -p store
chown 1000:1000 store
sudo docker-compose up -d --build

# post form data
curl -d 'hello="world"' http://localhost:8000/post/YOURSECRETTOKEN

# post a JSON
curl -H 'Content-Type: application/json' -d '{"hello":"world"}' http://localhost:8000/post/YOURSECRETTOKEN

# post a text file by converting it to a valid JSON array
cat /etc/resolv.conf | jq -R -s -c 'split("\n")' | curl -H 'Content-Type: application/json' -d @- http://localhost:8000/post/YOURSECRETTOKEN

# make posts cleaner by adding all parameters to a curl config file
printf '# @see: https://ec.haxx.se/cmdline-configfile.html
url = "http://localhost:8000/post/YOURSECRETTOKEN"
header = "Content-Type: application/json"
output = /dev/null
silent
' > ~/.matrix.curlrc
/any/command | curl -K ~/.matrix.curlrc -d @-
```

## Configuration

The gateway tries to join all of the specified rooms in the `.env` file on start. However, you must make sure to invite the webhook user and accept the invite on behalf of them from any client before you start up the gateway!

### Available customizations of posted messages

- Message formatting via `MESSAGE_FORMAT`: `raw` | `json` | `yaml` (default)
- Markdown formatting turned on or off via `USE_MARKDOWN`: `True` | `False` (default)
- ASCII (e.g., `\u1234`) or Unicode characters (e.g., `ű`) in JSON or YAML content via `ALLOW_UNICODE`: `True` (default) | `False`

### Matrix connection parameters

- The URL of the Matrix server via `MATRIX_SERVER`: a string like `https://matrix.example.org`
- SSL cert checking turned on or off via `MATRIX_SSLVERIFY`: `True` (default) | `False`
- The webhook user ID via `MATRIX_USERID`: a string like `@myhook:matrix.example.org`
- The webhook user password via `MATRIX_PASSWORD`: a string like `mypass+*!word` 
  - Put the string in quotes if your password contains likely sell-unsafe characters
- A device name that the webhook user will use via `MATRIX_DEVICE`: a string like `docker`
- The room where the webhook user will send its greeting upon (re)start via `MATRIX_ADMIN_ROOM`: a string like `!privatechatwiththebotuser:matrix.example.org`
  - You must use the room ID (with `!`) at all times even if the room has an alias like `#alias:matrix.example.org`!
  - You can invite the webhook user to a private chat with yourself to get a different room than the ones you're using for notification, it's up to you. Later, we can add some basic commands for the webhook service as it can read messages in joined rooms, so I made the admin room a private chat with the bot to be future-proof.

### The notification channels

- The list of `token,roomid,name` triplets separated by spaces via `KNOWN_TOKENS`: a string like  
  `YOURSECRETTOKEN,!myroomid:matrix.example.org,Curl anOTheRToKen99,!myroomid2:matrix.example.org,Grafana`
  - Put the string in quotes if you have more than one triplet ie. you have at least one space on the line
  - The `token` and `name` parts should match the following regexp: `[a-zA-Z0-9]+`
  - You must use the room ID (with `!`) at all times even if the room has an alias like `#alias:matrix.example.org`!
  - You can use different room IDs for different notifications, and these can be different from the admin room as well. But you can use the same room for everything, it depends on your use case.

### "Hidden" parameters that need no change most of the time <!-- omit in toc -->

- The Python log level via `PYTHON_LOG_LEVEL`: `debug` | `info` (default) | `warn` | `error` | `critical`
- The store path of the saved login session via `LOGIN_STORE_PATH`: a path-string without trailing slash like `/config` (default)
  - If you want to make login sessions persist to avoid device IDs stacking up on the webhook user, you can put this path on a docker volume with read-write permissions to the `1000:1000` user:group.

## Dependencies

- [Docker](https://www.docker.com/)
- [Docker Compose](https://github.com/docker/compose)

Installation on Manjaro Linux:

```bash
sudo pacman -S docker docker-compose

sudo systemctl enable --now docker
```

Of course, you'll also need a [Matrix server](https://matrix.org/discover/) up and running with at least one E2EE room and two users joined in the same room (the webhook user and probably _you_). Explaining setting these up is way beyond the scope of this document, so please see the online docs for proper instructions, or use a hosted Matrix server.

## Development

Install global dependencies, install dev dependencies, create a new virtual environment, install package dependencies, then start the project:

```bash
# Manjaro
sudo pacman -S libolm
sudo pip install virtualenv

virtualenv venv

# Fish
source venv/bin/activate.fish

pip install -r requirements.txt

./docker-entrypoint.sh
```

## Troubleshooting

- You might need to turn off SSL cert verification (with `False` in the environment file) if your certs are self-signed or you experience any problem with the cert verification even if you have a valid cert.
- Depending on the content of your messages, you might need to experiment with the available formatting combinations that suits your use case and eyes. We are different, I like plain YAML best with Unicode characters.

## Improvement ideas

- Execute predefined commands from the admin room for a set of predefined admin users. Maubot seems to be more flexible in this case but we could implement simple controls for the webhok gateway itself.

## Disclaimer

**This is an experimental project. I do not take responsibility for anything regarding the use or misuse of the contents of this repository.**

- Tested with Grafana webhooks and Synapse as a Matrix server, but in theory, it should work with any source capable of sending HTTP POST requests with valid form data or JSON objects (e.g., `curl`).
- Tested in rooms only with E2EE enabled as the main goal of this project is to receive arbitrary data in encrypted rooms.
- JSON and YAML formatting is indented by 2 spaces, no further processing is being made. The padded object's size is limited by your server's maximum message size.
- If you expose this service to the net, malicious actors could only send spam notifications if they knew any of your long and random tokens, as the token acts as auth. Otherwise, the messages are not routed to a Matrix room, so you're safe. However, if you host your message source and this gateway on the same network, you can use local hostnames, DNS or IP addresses to set the webhook up in the source. This way the message gateway won't be accessible from the outside, and your message data won't leave the internal network without encryption.
- If you use RocketChat, there is a similar project for that service here: [immanuelfodor/rocketchat-push-gateway](https://github.com/immanuelfodor/rocketchat-push-gateway)
- If you use XMPP, there is a similar project for that service here: [immanuelfodor/xmpp-muc-message-gateway](https://github.com/immanuelfodor/xmpp-muc-message-gateway)

## Contact

Immánuel Fodor    
[fodor.it](https://fodor.it/matrixmsgwit) | [Linkedin](https://fodor.it/matrixmsgwin)
