"""
ASA staking CLI (by cusma)
Stake your ASA depositing an amount in the Staking dApp, wait the locking
blocks and withdraw the doubled staked amount!

Usage:
  asa_staking.py create <purestake-api-token> <mnemonic> <asset-id> <locking-blocks> <funding-amount>
  asa_staking.py info <purestake-api-token> <app-id>
  asa_staking.py join <purestake-api-token> <mnemonic> <app-id>
  asa_staking.py booking <purestake-api-token> <mnemonic> <app-id> <booking-amount>
  asa_staking.py status <purestake-api-token> <account> <app-id>
  asa_staking.py withdraw <purestake-api-token> <mnemonic> <app-id>
  asa_staking.py [--help]

Commands:
  create      Create new decentalized ASA staking application.
  info        Decentalized ASA staking application info.
  join        Join a decentalized ASA staking application.
  booking     Book and deposit a staking amount.
  status      Check your staking status.
  withdraw    Withdraw staked amount with rewards.

Options:
  -h --help
"""


import json
import sys
import base64
import dataclasses

from docopt import docopt

from algosdk import encoding, mnemonic, account, util, kmd
from algosdk.v2client import algod, indexer
from algosdk.error import AlgodHTTPError, IndexerHTTPError
from algosdk.future.transaction import (
    AssetTransferTxn,
    ApplicationCreateTxn,
    ApplicationOptInTxn,
    ApplicationNoOpTxn,
    LogicSig,
    LogicSigTransaction,
    OnComplete,
    PaymentTxn,
    StateSchema,
    Transaction,
    calculate_group_id,
    wait_for_confirmation,
    write_to_file,
)
from pyteal import (
    And,
    App,
    Assert,
    Btoi,
    Bytes,
    Cond,
    Ge,
    Global,
    Gtxn,
    If,
    Int,
    Mode,
    Mul,
    OnComplete as PyTealOnComplete,
    Return,
    Seq,
    Txn,
    TxnType,
    compileTeal
)

# --- Config
MAX_CONNECTION_ATTEMPTS = 10
CONNECTION_ATTEMPT_DELAY_SEC = 2
FUND_ACCOUNT_ALGOS = 100_000

# --- PyTEAL
TEAL_VERSION = 2

# GLOBAL SCHEMA
GLOBAL_INTS = 3
GLOBAL_BYTES = 2

# LOCAL SCHEMA
LOCAL_INTS = 2
LOCAL_BYTES = 0


def withdrawal_approval():

    on_creation = Seq([
        App.globalPut(Bytes("Creator"), Txn.sender()),
        Return(Int(1))
    ])

    handle_optin = Return(Int(1))

    handle_closeout = Return(Int(1))

    handle_updateapp = Return(Int(0))

    handle_deleteapp = If(
        # Condition
        App.globalGet(Bytes("Creator")) == Txn.sender(),
        # Then
        Return(Int(1)),
        # Else
        Return(Int(0))
    )

    withdrawal_setup = If(
        # Condition
        And(
            Gtxn[0].application_args.length() == Int(2),
            Gtxn[1].type_enum() == TxnType.AssetTransfer,
            Gtxn[1].asset_receiver() == Gtxn[0].application_args[0],
            Gtxn[1].asset_amount() > Int(0)
        ),
        # Then
        Seq([
            App.globalPut(Bytes("AssetEscrow"),
                          Gtxn[0].application_args[0]),
            App.globalPut(Bytes("WithdrawalProcessingRounds"),
                          Btoi(Gtxn[0].application_args[1])),
            App.globalPut(Bytes("AssetID"),
                          Gtxn[1].xfer_asset()),
            App.globalPut(Bytes("WithdrawalBookableAmount"),
                          Gtxn[1].asset_amount()),
            Return(Int(1))
        ]),
        # Else
        Return(Int(0))
    )

    withdrawal_booking_round = App.localGetEx(
        Int(0), Gtxn[0].application_id(), Bytes("WithdrawalBookingRound")
    )

    booking = Seq([
        withdrawal_booking_round,
        If(
            # Condition
            And(
                withdrawal_booking_round.hasValue(),
                withdrawal_booking_round.value() > Int(0)
            ),
            # Then
            Return(Int(0)),
            # Else
            Seq([
                Assert(
                    And(
                        Gtxn[1].type_enum() == TxnType.AssetTransfer,
                        Gtxn[1].xfer_asset() == App.globalGet(
                            Bytes("AssetID")),
                        Gtxn[1].sender() == Gtxn[0].sender(),
                        Gtxn[1].asset_receiver() == App.globalGet(
                            Bytes("AssetEscrow")),
                        Gtxn[1].asset_amount() <= App.globalGet(
                            Bytes("WithdrawalBookableAmount"))
                    )
                ),
                App.localPut(Int(0), Bytes("WithdrawalBookingRound"),
                             Global.round()),
                App.localPut(Int(0), Bytes("WithdrawalBookedAmount"),
                             Gtxn[1].asset_amount()),
                App.globalPut(Bytes("WithdrawalBookableAmount"),
                              App.globalGet(Bytes("WithdrawalBookableAmount"))
                              - Gtxn[1].asset_amount()),
                Return(Int(1))
            ])
        ),
        Return(Int(1))
    ])

    withdrawal_approval_round = Ge(
        Global.round(),
        App.localGet(Int(0), Bytes("WithdrawalBookingRound")) +
        App.globalGet(Bytes("WithdrawalProcessingRounds"))
    )

    withdrawal_booked_amount = App.localGetEx(
        Int(0), Gtxn[0].application_id(), Bytes("WithdrawalBookedAmount")
    )

    withdrawal = Seq([
        withdrawal_booking_round,
        withdrawal_booked_amount,
        Assert(
            And(
                App.optedIn(Int(0), Gtxn[0].application_id()),
                withdrawal_booking_round.value() > Int(0),
                withdrawal_booked_amount.value() > Int(0),
                withdrawal_approval_round,
                Gtxn[1].xfer_asset() == App.globalGet(Bytes("AssetID")),
                Gtxn[1].sender() == App.globalGet(Bytes("AssetEscrow")),
                Gtxn[1].asset_amount() == Mul(
                    withdrawal_booked_amount.value(), Int(2)
                )
            )
        ),
        App.localPut(Int(0), Bytes("WithdrawalBookingRound"), Int(0)),
        App.localPut(Int(0), Bytes("WithdrawalBookedAmount"), Int(0)),
        Return(Int(1))
    ])

    handle_noop = Cond(
        [And(
            Global.group_size() == Int(2),
            App.globalGet(Bytes("Creator")) == Gtxn[0].sender()
        ), withdrawal_setup],
        [And(
            Global.group_size() == Int(2),
            Gtxn[0].application_args[0] == Bytes("Booking")
        ), booking],
        [And(
            Global.group_size() == Int(2),
            Gtxn[0].application_args[0] == Bytes("Withdrawal")
        ), withdrawal]
    )

    program = Cond(
        [Txn.application_id() == Int(0), on_creation],
        [Txn.on_completion() == PyTealOnComplete.OptIn, handle_optin],
        [Txn.on_completion() == PyTealOnComplete.CloseOut, handle_closeout],
        [Txn.on_completion() == PyTealOnComplete.UpdateApplication,
         handle_updateapp],
        [Txn.on_completion() == PyTealOnComplete.DeleteApplication,
         handle_deleteapp],
        [Txn.on_completion() == PyTealOnComplete.NoOp, handle_noop]
    )
    return compileTeal(program, Mode.Application, version=TEAL_VERSION)


def withdrawal_clear():
    return compileTeal(Int(1), Mode.Application, version=2)

def withdrawal_escrow(app_id: int, asa_id: int):

    fee = Int(1000)

    asa_opt_in = And(
        Txn.type_enum() == TxnType.AssetTransfer,
        Txn.xfer_asset() == Int(asa_id),
        Txn.asset_amount() == Int(0),
        Txn.fee() <= fee,
        Txn.rekey_to() == Global.zero_address(),
        Txn.asset_close_to() == Global.zero_address(),
    )

    asa_withdraw = And(
        Gtxn[0].type_enum() == TxnType.ApplicationCall,
        Gtxn[0].application_id() == Int(app_id),
        Gtxn[0].on_completion() == PyTealOnComplete.NoOp,
        Gtxn[1].type_enum() == TxnType.AssetTransfer,
        Gtxn[1].xfer_asset() == Int(asa_id),
        Gtxn[1].fee() <= fee,
        Gtxn[1].asset_close_to() == Global.zero_address(),
        Gtxn[1].rekey_to() == Global.zero_address()
    )

    program = Cond(
        [Global.group_size() == Int(1), asa_opt_in],
        [Global.group_size() == Int(2), asa_withdraw]
    )

    return compileTeal(program, Mode.Signature, version=TEAL_VERSION)


@dataclasses.dataclass
class Account:
    address: str
    private_key: str
    lsig: LogicSig = None

    def mnemonic(self) -> str:
        return mnemonic.from_private_key(self.private_key)

    def is_lsig(self):
        return not self.private_key and self.lsig

    @classmethod
    def create_account(cls):
        private_key, address = account.generate_account()
        return cls(private_key=private_key, address=address)


def sign(signer: Account, txn: Transaction):
    """Sign a transaction with an Account."""
    if signer.is_lsig():
        return LogicSigTransaction(txn, signer.lsig)
    else:
        assert signer.private_key
        return txn.sign(signer.private_key)


def sign_send_wait(algod_client: algod.AlgodClient, signer: Account,
                   txn: Transaction, debug=False):
    """Sign a transaction, submit it, and wait for its confirmation."""
    signed_txn = sign(signer, txn)
    tx_id = signed_txn.transaction.get_txid()

    if debug:
        write_to_file([signed_txn], "/tmp/txn.signed", overwrite=True)

    algod_client.send_transactions([signed_txn])
    wait_for_confirmation(algod_client, tx_id)
    return algod_client.pending_transaction_info(tx_id)


def group_and_sign(signers: list[Account], txns: list[Transaction], debug=False):
    assert len(signers) == len(txns)

    signed_group = []
    gid = calculate_group_id(txns)

    for signer, t in zip(signers, txns):
        t.group = gid
        signed_group.append(sign(signer, t))

    if debug:
        write_to_file(signed_group, "/tmp/txn.signed", overwrite=True)

    return signed_group


def fund(algod_client: algod.AlgodClient, faucet: Account, receiver: Account, amount=FUND_ACCOUNT_ALGOS):
    params = algod_client.suggested_params()
    txn = PaymentTxn(faucet.address, params, receiver.address, amount)
    return sign_send_wait(algod_client, faucet, txn)


def get_last_round(algod_client: algod.AlgodClient) -> int:
    return algod_client.status()["last-round"]


def wait_until_round(algod_client: algod.AlgodClient, admin: Account, r: int):
    print(f" --- Waiting until round: {r}.")
    while get_last_round(algod_client) < r:
        fund(algod_client, admin, admin, amount=0)


def to_lsig(algod_client: algod.AlgodClient, teal, debug=False):
    if debug:  
        with open('/tmp/program.teal', 'w') as f:
            f.write(teal)

    compiled = algod_client.compile(teal)
    lsig = LogicSig(base64.decodebytes(compiled["result"].encode()))
    return Account(address=lsig.address(), lsig=lsig, private_key=None)


def generate_blocks(algod_client: algod.AlgodClient, num_blocks: int, account: Account):
    for i in range(num_blocks):
        txn = PaymentTxn(
            sender=account.address,
            sp=algod_client.suggested_params(),
            receiver=account.address,
            amt=0,
        )
        sign_send_wait(algod_client, account, txn)


def compile_program(algod_client: algod.AlgodClient, source_code):
    compile_response = algod_client.compile(source_code)
    return base64.b64decode(compile_response["result"])


def create_application(algod_client: algod.AlgodClient, creator: Account, debug=False):

    global_schema = StateSchema(GLOBAL_INTS, GLOBAL_BYTES)
    local_schema = StateSchema(LOCAL_INTS, LOCAL_BYTES)

    approval_program_teal = withdrawal_approval()
    approval_program = compile_program(algod_client, approval_program_teal)
    if debug:
        with open('/tmp/approval_program.teal', 'w') as f:
            f.write(approval_program_teal)

    clear_program_teal = withdrawal_clear()
    clear_program = compile_program(algod_client, clear_program_teal)
    if debug:
        with open('/tmp/clear_program.teal', 'w') as f:
            f.write(clear_program_teal)

    on_complete = OnComplete.NoOpOC
    params = algod_client.suggested_params()

    app_create_txn = ApplicationCreateTxn(
        sender=creator.address,
        sp=params,
        on_complete=on_complete,
        approval_program=approval_program,
        clear_program=clear_program,
        global_schema=global_schema,
        local_schema=local_schema,
    )

    transaction_response = sign_send_wait(algod_client, creator, app_create_txn)
    return transaction_response["application-index"]


def optin_to_asset(algod_client: algod.AlgodClient, account: Account, asa_id: int, note=None):
    params = algod_client.suggested_params()
    optin_txn = AssetTransferTxn(
        sender=account.address,
        sp=params,
        receiver=account.address,
        amt=0,
        index=asa_id,
        note=note
    )
    return sign_send_wait(algod_client, account, optin_txn)


def optin_to_application(algod_client: algod.AlgodClient, account: Account, app_id: int):
    params = algod_client.suggested_params()
    optin_txn = ApplicationOptInTxn(
        sender=account.address,
        sp=params,
        index=app_id,
    )
    return sign_send_wait(algod_client, account, optin_txn)


def info(algod_client: algod.AlgodClient, app_id: int):

    global_state = algod_client.application_info(app_id)['params']['global-state']

    settings = {
        'asa_id': next(item['value']['uint']
        for item in global_state if item['key'] == 'QXNzZXRJRA=='),
        'escrow': next(encoding.encode_address(base64.b64decode(item['value']['bytes']))
        for item in global_state if item['key'] == 'QXNzZXRFc2Nyb3c='),
        'locking_blocks': next(item['value']['uint']
        for item in global_state if item['key'] == 'V2l0aGRyYXdhbFByb2Nlc3NpbmdSb3VuZHM='),
        'bookable_funds': next(item['value']['uint']
        for item in global_state if item['key'] == 'V2l0aGRyYXdhbEJvb2thYmxlQW1vdW50'),
    }

    summary = f"""
    * ======================== STAKING dAPP SUMMARY ======================== *

       APP ID:\t{app_id}
       ASA ID:\t{settings['asa_id']}
       ESCROW:\t{settings['escrow']}

       LOCKING BLOCKS:\t⏳ {settings['locking_blocks']}
       BOOKABLE FUNDS:\t💰 {settings['bookable_funds']}

    * ====================================================================== *
    """
    return settings, summary


def status(algod_client: algod.AlgodClient, address: str, app_id: int):

    local_state = algod_client.account_info(address)['apps-local-state']

    settings, summary = info(algod_client, app_id)

    booking_status = {}
    for app in local_state:
        if app['id'] == app_id:
            booking_status = {
                'amount': next(item['value']['uint']
                    for item in app['key-value'] if item['key'] == 'V2l0aGRyYXdhbEJvb2tlZEFtb3VudA=='),
                'round': next(item['value']['uint']
                    for item in app['key-value'] if item['key'] == 'V2l0aGRyYXdhbEJvb2tpbmdSb3VuZA=='),
            }
    if booking_status:
        remaning_rounds = settings['locking_blocks'] \
            - (get_last_round(algod_client) - booking_status['round'])

        if remaning_rounds > 0:
            withdrawal_status = str(remaning_rounds) + ' BLOCKS 🔒⏳'
        elif booking_status['amount'] > 0:
            withdrawal_status = "Withdrawal ready! ️🔐⌛"
        else:
            withdrawal_status = "Withdrawal already executed! 🔓💸"

        booking_summary = f"""
        * ======================= BOOKED STAKING SUMMARY ======================= *

           APP ID:\t{app_id}
           ASA ID:\t{settings['asa_id']}

           BOOKED AMOUNT:\t{booking_status['amount']}
           REMANING LOCK:\t{withdrawal_status}

        * ====================================================================== *
        """

        return booking_status, booking_summary

    else:
        quit(f"\n⚠️  Account {address} not booked for App ID: {app_id}")


def asa_staking_init(
    algod_client: algod.AlgodClient,
    creator: Account,
    asa_id: int,
    locking_blocks: int,
    asa_funding_amount: int
) -> int:

    app_id = create_application(algod_client, creator)
    escrow = to_lsig(algod_client, withdrawal_escrow(app_id, asa_id))
    print(f"[2/4] 🔐 Creating staking escrow {escrow.address}...")
    fund(algod_client, creator, escrow, amount=300_000)
    print(f"[3/4] 🗳  Staking escrow opt-in ASA {asa_id}...")
    optin_to_asset(algod_client, escrow, asa_id)

    params = algod_client.suggested_params()
    set_escrow_txn = ApplicationNoOpTxn(
        sender=creator.address,
        sp=params,
        index=app_id,
        app_args=[encoding.decode_address(escrow.address), locking_blocks],
    )

    fund_escrow_txn = AssetTransferTxn(
        sender=creator.address,
        sp=params,
        receiver=escrow.address,
        amt=asa_funding_amount,
        index=asa_id,
    )

    signed_group = group_and_sign(
        [creator, creator],
        [set_escrow_txn, fund_escrow_txn],
    )

    print(f"[4/4] 💰 Funding staking escrow with {asa_funding_amount} of ASA {asa_id}...")
    gtxn_id = algod_client.send_transactions(signed_group)
    wait_for_confirmation(algod_client, gtxn_id)
    return app_id


def asa_stake_booking(
    algod_client: algod.AlgodClient,
    user: Account,
    app_id: int,
    booking_amount: int,
):
    settings, summary = info(algod_client, app_id)
    params = algod_client.suggested_params()

    booking_call_txn = ApplicationNoOpTxn(
        sender=user.address,
        sp=params,
        index=app_id,
        app_args=[b'Booking'],
    )

    deposit_txn = AssetTransferTxn(
        sender=user.address,
        sp=params,
        receiver=settings['escrow'],
        amt=booking_amount,
        index=settings['asa_id'],
    )

    signed_group = group_and_sign(
        [user, user],
        [booking_call_txn, deposit_txn],
    )

    gtxn_id = algod_client.send_transactions(signed_group)
    wait_for_confirmation(algod_client, gtxn_id)


def asa_stake_withdrawal(
    algod_client: algod.AlgodClient,
    indexer_client: indexer.IndexerClient,
    user: Account,
    app_id: int,
):
    settings, summary = info(algod_client, app_id)
    bookink_status, booking_summary = status(algod_client, user.address, app_id)

    attempts = 1
    escrow_txns = None
    while attempts <= MAX_CONNECTION_ATTEMPTS:
        try:
            escrow_txns = indexer_client.search_transactions_by_address(
                address=settings['escrow'],
                asset_id=settings['asa_id'],
            )['transactions']
            break
        except IndexerHTTPError:
            print(f'Indexer Client connection attempt '
                  f'{attempts}/{MAX_CONNECTION_ATTEMPTS}')
            print('Trying to contact Indexer Client again...')
            time.sleep(CONNECTION_ATTEMPT_DELAY_SEC)
        finally:
            attempts += 1
    if not escrow_txns:
        quit("❌ Unable to connect to Indexer Client. Check your API token!")

    lsig = (next(txn['signature']['logicsig']['logic']
               for txn in escrow_txns if txn['sender'] == settings['escrow']))

    escrow = Account(
        address=settings['escrow'],
        private_key=None,
        lsig=LogicSig(base64.decodebytes(lsig.encode()))
    )

    params = algod_client.suggested_params()

    withdrawal_call_txn = ApplicationNoOpTxn(
        sender=user.address,
        sp=params,
        index=app_id,
        app_args=[b'Withdrawal'],
    )

    withdrawal_txn = AssetTransferTxn(
        sender=settings['escrow'],
        sp=params,
        receiver=user.address,
        amt=int(bookink_status['amount'] * 2),
        index=settings['asa_id'],
    )

    signed_group = group_and_sign(
        [user, escrow],
        [withdrawal_call_txn, withdrawal_txn],
    )

    try:
        gtxn_id = algod_client.send_transactions(signed_group)
        wait_for_confirmation(algod_client, gtxn_id)
        quit(f"\n🎉  Withdrawal completed: {int(bookink_status['amount'] * 2)}"
              f" units of ASA ID: {settings['asa_id']}\n")
    except AlgodHTTPError:
        quit("\n⚠️  Withdrawal denied! Check your withdrawl status (--help).\n")


def main():
    if len(sys.argv) == 1:
        # Display help if no arguments, see:
        # https://github.com/docopt/docopt/issues/420#issuecomment-405018014
        sys.argv.append('--help')

    args = docopt(__doc__)

    # Clients
    if args['<purestake-api-token>']:
        algod_address = 'https://mainnet-algorand.api.purestake.io/ps2'
        indexer_address = 'https://mainnet-algorand.api.purestake.io/idx2'
        token = args['<purestake-api-token>']
        header = {'X-Api-key': token}
    else:
        algod_address = 'http://localhost:4001'
        indexer_address = 'http://localhost:8980'
        token = 64 * 'a'
        header = {'X-Api-key': token}

    _algod_client = algod.AlgodClient(
        algod_token=token,
        algod_address=algod_address,
        headers=header
    )

    _indexer_client = indexer.IndexerClient(
        indexer_token=token,
        indexer_address=indexer_address,
        headers=header
    )

    if args['info']:
        settings, summary = info(_algod_client, args['<app-id>'])
        return print(summary)

    if args['status']:
        booking_status, booking_summary = status(_algod_client, args['<account>'], int(args['<app-id>']))
        return print(booking_summary)

    # Checking mnemonic format
    try:
        assert len(args['<mnemonic>'].split()) == 25
    except AssertionError:
        quit('\n⚠️\tThe mnemonic phrase must contain 25 words, '
             'formatted as: "word_1 word_2 ... word_25"\n')

    private_key = mnemonic.to_private_key(args['<mnemonic>'])

    user = Account(
        account.address_from_private_key(private_key),
        private_key
    )

    if args['create']:
        print(f"\n[1/4] 💰 Creating new staking dApp for ASA {args['<asset-id>']}...")
        app_id = asa_staking_init(
            algod_client=_algod_client,
            creator=user,
            asa_id=int(args['<asset-id>']),
            locking_blocks=int(args['<locking-blocks>']),
            asa_funding_amount=int(args['<funding-amount>'])
        )
        settings, summary = info(_algod_client, app_id)
        return print(summary)

    if args['join']:
        print(f"\n📝 Joining staking dApp {args['<app-id>']}...\n")
        optin_to_application(
            algod_client=_algod_client,
            account=user,
            app_id=int(args['<app-id>']),
        )
        settings, summary = info(_algod_client, int(args['<app-id>']))
        return print(summary)

    if args['booking']:
        print(f"\n🔐 Staking {args['<booking-amount>']} units in dApp {args['<app-id>']}...\n")
        asa_stake_booking(
            algod_client=_algod_client,
            user=user,
            app_id=int(args['<app-id>']),
            booking_amount=int(args['<booking-amount>'])
        )
        booking_status, booking_summary = status(_algod_client, user.address, int(args['<app-id>']))
        return print(booking_summary)

    if args['withdraw']:
        print(f"\n🤑 Withdrawal request...\n")
        asa_stake_withdrawal(
            algod_client=_algod_client,
            indexer_client=_indexer_client,
            user=user,
            app_id=int(args['<app-id>'])
        )

    else:
        quit("\nError: read '--help'!\n")


if __name__ == "__main__":
    main()
