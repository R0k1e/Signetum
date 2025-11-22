import time

import typer
import uvloop
import yaml
from dotenv import load_dotenv
from loguru import logger
from rich import print

load_dotenv()
uvloop.install()
logger.add(f"output/{time.strftime('%Y-%m-%d_%H:%M:%S')}/log.txt", rotation="10 MB")


def main(name: str = typer.Option("World", help="Name to greet")) -> None:
    print(f"Hello {name}!")
    with open("config/config.yml") as f:
        config = yaml.safe_load(f)
        logger.info(f"Hello {config['name']}!")


if __name__ == "__main__":
    typer.run(main)
