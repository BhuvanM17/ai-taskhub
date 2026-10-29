import argparse

from app.config import settings
from app.store import Store


def main():
    parser = argparse.ArgumentParser(description="AI TaskHub administration")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    key = sub.add_parser("create-key")
    key.add_argument("--name", required=True)
    args = parser.parse_args()
    store = Store(settings().database_url)
    if args.command == "init-db":
        store.initialize()
        print("Database initialized")
    else:
        print(store.create_key(args.name))


if __name__ == "__main__":
    main()
