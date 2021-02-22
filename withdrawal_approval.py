from pyteal import *


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
        [Txn.on_completion() == OnComplete.OptIn, handle_optin],
        [Txn.on_completion() == OnComplete.CloseOut, handle_closeout],
        [Txn.on_completion() == OnComplete.UpdateApplication,
         handle_updateapp],
        [Txn.on_completion() == OnComplete.DeleteApplication,
         handle_deleteapp],
        [Txn.on_completion() == OnComplete.NoOp, handle_noop]
    )
    return compileTeal(program, Mode.Application)


if __name__ == "__main__":
    with open('withdrawal_approval.teal', 'w') as f:
        compiled = withdrawal_approval()
        f.write(compiled)
