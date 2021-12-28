from pyteal import *


def withdrawal_clear():
    return compileTeal(Int(1), Mode.Application, version=2)


if __name__ == "__main__":
    with open('withdrawal_approval.teal', 'w') as f:
        compiled = withdrawal_clear()
        f.write(compiled)