from pyteal import *


def withdrawal_escrow(app_id, asa_id):

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
        Gtxn[0].on_completion() == OnComplete.NoOp,
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

    return compileTeal(program, Mode.Signature)


# Use your TMPL_ASA_ID
asa_id = 0

# Use your TMPL_APP_ID
app_id = 0


if __name__ == "__main__":

    with open('withdrawal_escrow.teal', 'w') as f:
        compiled = withdrawal_escrow(app_id, asa_id)
        f.write(compiled)
