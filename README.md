# ASA recurring withdrawal dApp

The solution architecture relies on Algorand Standard Asset ([ASA](https://developer.algorand.org/docs/features/asa/)), Atomic Transfers ([AT](https://developer.algorand.org/docs/features/atomic_transfers/)) and Stateful & Stateless Smart Contracts ([ASC1](https://developer.algorand.org/docs/features/asc1/)), whose source code is provided both in [TEAL](https://developer.algorand.org/docs/features/asc1/teal/) and [PyTeal](https://developer.algorand.org/docs/features/asc1/teal/pyteal/).

[Check out the whole solution](https://developer.algorand.org/solutions/asa-recurring-withdrawal-dapp/).

## ASA Staking CLI

### 1. Setup

1. Download the [`asa_staking.py`](https://github.com/cusma/asa_withdrawal_dapp/blob/main/asa_staking.py) script
2. Install the following dependencies:

```shell
$ pip3 install docopt --upgrade
$ pip3 install py-algorand-sdk --upgrade
$ pip3 install pyteal --upgrade
```

3. Create an account on PureStake and [get your API token](https://developer.purestake.io/login)

### 2. CLI usage

Using the **ASA Staking dApp** from your CLI is pretty easy, just ask for help:

```shell
$ python3 asa_staking.py -h
```

```shell
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
```

**NOTE:** keep your `<mnemonic>` safe! Although you will only use it on you local machine, is it strongly recommended to make use of a dedicated account just to interact with the ASA Staking dApp!

### 3. Create your own ASA Staking dApp

Want to provide an ASA Staking dApp for your community? Let's use the `create` 
command:

1. Choose the `<asset-id>`
2. Define the `<locking-blocks>`: users will lock their ASA for this period
3. Define the `<funding-amount>`: as creator you will fund the ASA Staking dApp

⚠️ Note that the `<funding-amount>` must be expressed in **ASA minimal units**, 
taking into accunt **ASA decimals** positions.

⚠️ Example: if ASA Decimals = 3, then to fund the dApp with 100 ASA units you 
must enter `<funding-amount>=100000` (as result of 100 * 10^3).

```shell
$ python3 asa_staking.py create <purestake-api-token> <mnemonic> <asset-id> <locking-blocks> <funding-amount>
```

**NOTE:** enter the the `<mnemonic>` formatting it as: `"word_1 word_2 word_3 ... word_25"` and keep it safe!

### 4. ASA Staking dApp info

The given an `<app-id>` you can display ASA Staking dApp `info`:

```shell
$ python3 asa_staking.py info <purestake-api-token> <app-id>
```

### 5. Join the ASA Staking dApp

As a user you can `join` the ASA Staking dApp identified by its `<app-id>`:

```shell
$ python3 asa_staking.py join <purestake-api-token> <mnemonic> <app-id>
```

**NOTE:** enter the the `<mnemonic>` formatting it as: `"word_1 word_2 word_3 ... word_25"` and keep it safe!

### 6. Stake your ASA

As a user you can stake your ASA depositing a `<booking-amount>` of ASA in the 
ASA Staking dApp identified by its `<app-id>`, wait the locking blocks and 
withdraw the doubled staked amount!

⚠️ Note that the `<booking-amount>` must be expressed in **ASA minimal units**, 
taking into accunt **ASA decimals** positions.

⚠️ Example: if ASA Decimals = 3, then to stake 50 ASA units you must ener 
`<booking-amount>=50000` (as result of 50 * 10^3).

```shell
$ python3 asa_staking.py booking <purestake-api-token> <mnemonic> <app-id> <booking-amount>
```

**NOTE:** enter the the `<mnemonic>` formatting it as: `"word_1 word_2 word_3 ... word_25"` and keep it safe!

### 7. Check your staking status

Monitor the `status` of your `<account>` in the ASA Staking dApp identified by 
its `<app-id>`:

```shell
$ python3 asa_staking.py status <purestake-api-token> <account> <app-id>
```

### 8. Withdraw your staked ASA

As a user you can `withdraw` your staked ASA from the ASA Staking dApp 
identified by its `<app-id>` once the locking period expires:

```shell
$ python3 asa_staking.py withdraw <purestake-api-token> <mnemonic> <app-id>
```

**NOTE:** enter the the `<mnemonic>` formatting it as: `"word_1 word_2 word_3 ... word_25"` and keep it safe!

## Tip the Dev

If you find this solution useful as free and open source learning example, consider tipping the Dev:

`XODGWLOMKUPTGL3ZV53H3GZZWMCTJVQ5B2BZICFD3STSLA2LPSH6V6RW3I`
