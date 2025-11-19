Repo to the FastAPI of the OpenTaberna Project. See [Wiki](https://wiki.opentaberna.de) for more information.


# Dev Setup

For code development use `uv` package manager. After installation go into the root directory of this repository and run:

```bash
uv sync
```

To start the API locally:
```bash
source .venv/bin/activate
python3 src/app/main.py
```

To test the Setup:

Take a look at the `docker-compose.dev.yml` file. It provides a dev docker setup for local development. Run:

```bash
docker compose up -f docker-compose.dev.yml -d
```
