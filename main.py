import time

import rich
import typer
import uvloop
from dotenv import load_dotenv
from loguru import logger

load_dotenv()
uvloop.install()
logger.add(f"output/{time.strftime('%Y-%m-%d')}/log.txt", rotation="10 MB")


def main(name: str = typer.Option("World", help="Name to greet")) -> None:
    rich.print(f"Hello {name}!")


if __name__ == "__main__":
    typer.run(main)
