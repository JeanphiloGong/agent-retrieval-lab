from database import connect as open_database

# connect is mentioned here, but this is not a function definition.


def main() -> str:
    return open_database("sqlite://local")


def wrapper():
    def connect():
        return "nested connector"
    return connect()


def call_unknown(obj):
    return obj.connect()
