#!/usr/bin/env python3
# Copyright (c) 2021 The Logos Foundation
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the BIP341 sighash."""

import re
import hashlib

from test_framework import cashaddr
from test_framework.key import ECKey
from test_framework.messages import (
    COutPoint,
    CTransaction,
    CTxIn,
    CTxOut,
)
from test_framework.mininode import (
    P2PDataStore,
)
from test_framework.script import (
    hash160,
    CScript,
    OP_0,
    OP_1,
    OP_CHECKSIG,
    OP_CODESEPARATOR,
    OP_DUP,
    OP_DROP,
    OP_ELSE,
    OP_ENDIF,
    OP_EQUAL,
    OP_EQUALVERIFY,
    OP_HASH160,
    OP_IF,
    OP_NOP,
    SIGHASH_ALL,
    SIGHASH_ANYONECANPAY,
    SIGHASH_BIP341,
    SIGHASH_NONE,
    SIGHASH_SINGLE,
    SIGHASH_FORKID,
    SignatureHashBIP341,
)
from test_framework.test_framework import BitcoinTestFramework


TESTCASES = [
    dict(outputs=1, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341]),
    dict(outputs=10, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341]),
    dict(outputs=2, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY]),
    dict(outputs=3, sig_hash_types=[SIGHASH_NONE | SIGHASH_BIP341]),
    dict(outputs=4, sig_hash_types=[SIGHASH_NONE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY]),
    dict(outputs=5, sig_hash_types=[SIGHASH_SINGLE | SIGHASH_BIP341]),
    dict(outputs=6, sig_hash_types=[SIGHASH_SINGLE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY]),
    dict(outputs=10, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341,
                                     SIGHASH_ALL | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_NONE | SIGHASH_BIP341,
                                     SIGHASH_NONE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_SINGLE | SIGHASH_BIP341,
                                     SIGHASH_SINGLE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY]),
    dict(outputs=1, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341], is_p2pk=True),
    dict(outputs=10, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341,
                                     SIGHASH_ALL | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_NONE | SIGHASH_BIP341,
                                     SIGHASH_NONE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_SINGLE | SIGHASH_BIP341,
                                     SIGHASH_SINGLE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY], is_p2pk=True),
    dict(outputs=1, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341],
         codesep=30, opcodes=[OP_NOP]*30 + [OP_CODESEPARATOR]),
    dict(outputs=1, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341],
         codesep=29, opcodes=[OP_NOP]*30 + [OP_CODESEPARATOR], error='Signature must be zero for failed CHECK(MULTI)SIG operation'),
    dict(outputs=3, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341],
         codesep=300, opcodes=[OP_NOP]*300 + [OP_CODESEPARATOR]),
    dict(outputs=10, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341,
                                     SIGHASH_ALL | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_NONE | SIGHASH_BIP341,
                                     SIGHASH_NONE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_SINGLE | SIGHASH_BIP341,
                                     SIGHASH_SINGLE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY],
         codesep=14, opcodes=[OP_NOP]*14 + [OP_CODESEPARATOR]),
    dict(outputs=13, sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341,
                                     SIGHASH_ALL | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_NONE | SIGHASH_BIP341,
                                     SIGHASH_NONE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY,
                                     SIGHASH_SINGLE | SIGHASH_BIP341,
                                     SIGHASH_SINGLE | SIGHASH_BIP341 | SIGHASH_ANYONECANPAY],
         codesep=9, opcodes=[
            OP_0, OP_IF,
                OP_CODESEPARATOR,
            OP_ELSE,
                OP_CODESEPARATOR,
                bytes(120),
                OP_DROP,
                OP_1, OP_IF,
                    OP_CODESEPARATOR, # <- last executed codeseparator, at pos 9
                OP_ELSE,
                    OP_1, OP_CODESEPARATOR,
                OP_ENDIF,
            OP_ENDIF]),
    dict(outputs=13,
         sig_hash_types=[SIGHASH_ALL | SIGHASH_BIP341 | SIGHASH_FORKID],
         codesep=9,
         opcodes=[
            OP_1, OP_IF,
                OP_CODESEPARATOR, # <- last executed codeseparator, at pos 3, but we sign 9, therefore invalid
            OP_ELSE,
                OP_CODESEPARATOR,
                bytes(120),
                OP_DROP,
                OP_1, OP_IF,
                    OP_CODESEPARATOR,
                OP_ELSE,
                    OP_1, OP_CODESEPARATOR,
                OP_ENDIF,
            OP_ENDIF],
         error='Signature must be zero for failed CHECK(MULTI)SIG operation'),
    dict(outputs=4, sig_hash_types=[SIGHASH_BIP341], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x20, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x21, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x22, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x23, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x24, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x25, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x26, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x27, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x28, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x29, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x2a, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x2b, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x2c, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x2d, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x2e, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x2f, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x60, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=1, sig_hash_types=[0x63, 0x61, 0x61]),
    dict(outputs=3, sig_hash_types=[0x61, 0x61, 0x63]),
    dict(outputs=3, sig_hash_types=[0x61, 0x62, 0x63]),
    dict(outputs=3, sig_hash_types=[0x61, 0x63, 0x63]),
    dict(outputs=3, sig_hash_types=[0x61, 0x64, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x65, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x66, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x67, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x68, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x69, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x6a, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x6b, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x6c, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x6d, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x6e, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x6f, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0x71, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xe0, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xe1, 0x63]),
    dict(outputs=3, sig_hash_types=[0x61, 0xe2, 0x63]),
    dict(outputs=3, sig_hash_types=[0x61, 0xe3, 0x63]),
    dict(outputs=3, sig_hash_types=[0x61, 0xe4, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xe5, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xe6, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xe7, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xe8, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xe9, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xea, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xeb, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xec, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xed, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xee, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xef, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0x61, 0xf1, 0x63], error='Signature hash type missing or not understood'),
    dict(outputs=5, sig_hash_types=[SIGHASH_FORKID], error='Signature hash type missing or not understood'),
    dict(outputs=4, sig_hash_types=[SIGHASH_ALL], error='Signature must use SIGHASH_FORKID or SIGHASH_BIP341'),
    dict(outputs=3, sig_hash_types=[SIGHASH_NONE], error='Signature must use SIGHASH_FORKID or SIGHASH_BIP341'),
    dict(outputs=2, sig_hash_types=[SIGHASH_SINGLE], error='Signature must use SIGHASH_FORKID or SIGHASH_BIP341'),
    dict(outputs=6, sig_hash_types=[SIGHASH_ALL | SIGHASH_FORKID],
         error='Signature must be zero for failed CHECK(MULTI)SIG operation'), # Valid sighash type but wrong sighash algorithm
    dict(outputs=3, sig_hash_types=[0x21], error='Signature must be zero for failed CHECK(MULTI)SIG operation', suffix=0x61),
    dict(outputs=3, sig_hash_types=[0x81], error='Signature must be zero for failed CHECK(MULTI)SIG operation', suffix=0xe1),
    'ENABLE_REPLAY_PROTECTION',
    dict(outputs=3, sig_hash_types=[0xffdead60], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0xffdead61]),
    dict(outputs=3, sig_hash_types=[0xffdead62]),
    dict(outputs=3, sig_hash_types=[0xffdead63]),
    dict(outputs=3, sig_hash_types=[0xffdead64], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0xffdead6f], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0xffdead71], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0xffdeade0], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0xffdeade1]),
    dict(outputs=3, sig_hash_types=[0xffdeade2]),
    dict(outputs=3, sig_hash_types=[0xffdeade3]),
    dict(outputs=3, sig_hash_types=[0xffdeade4], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0xffdeadef], error='Signature hash type missing or not understood'),
    dict(outputs=3, sig_hash_types=[0xffdeadf1], error='Signature hash type missing or not understood'),
]

ACTIVATION_TIME = 2000000000

class Bip341Sighash(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True
        self.extra_args = [['-whitelist=noban@127.0.0.1',
                            f'-replayprotectionactivationtime={ACTIVATION_TIME}']]

    def run_test(self):
        node = self.nodes[0]
        node.add_p2p_connection(P2PDataStore())
        num_utxos = sum(len(test_case['sig_hash_types'])
                        for test_case in TESTCASES
                        if isinstance(test_case, dict))

        value = 50 * 100_000_000
        fee = 10_000

        max_utxo_value = (value - fee) // num_utxos
        private_keys = []
        public_keys = []
        spendable_outputs = []
        executed_scripts = []
        utxo_idx = 0
        for test_case in TESTCASES:
            if test_case == 'ENABLE_REPLAY_PROTECTION':
                continue
            for _ in test_case['sig_hash_types']:
                private_key = ECKey()
                private_key.generate()
                private_keys.append(private_key)
                public_key = private_key.get_pubkey()
                public_keys.append(public_key)
                utxo_value = max_utxo_value - utxo_idx * 100  # deduct 100*i coins for unique amounts
                if test_case.get('opcodes', False):
                    opcodes = test_case['opcodes']
                    redeem_script = CScript(opcodes + [public_key.get_bytes(), OP_CHECKSIG])
                    executed_scripts.append(redeem_script)
                    utxo_script = CScript([OP_HASH160, hash160(redeem_script), OP_EQUAL])
                elif test_case.get('is_p2pk', False):
                    utxo_script = CScript([public_key.get_bytes(), OP_CHECKSIG])
                    executed_scripts.append(utxo_script)
                else:
                    utxo_script = CScript([OP_DUP, OP_HASH160, hash160(public_key.get_bytes()), OP_EQUALVERIFY, OP_CHECKSIG])
                    executed_scripts.append(utxo_script)
                spendable_outputs.append(
                    CTxOut(utxo_value, utxo_script)
                )
                utxo_idx += 1

        anyonecanspend_address = node.decodescript('51')['p2sh']
        burn_address = node.decodescript('00')['p2sh']
        p2sh_script = CScript([OP_HASH160, bytes(20), OP_EQUAL])
        node.generatetoaddress(1, anyonecanspend_address)
        node.generatetoaddress(100, burn_address)

        block_hash = node.getblockhash(1)
        coin = int(node.getblock(block_hash)['tx'][0], 16)
        tx_fan_out = CTransaction()
        tx_fan_out.vin.append(CTxIn(COutPoint(coin, 0), CScript([b'\x51'])))
        tx_fan_out.vout = spendable_outputs
        tx_fan_out.rehash()

        node.p2p.send_txs_and_test([tx_fan_out], node)

        utxo_idx = 0
        key_idx = 0
        for test_case in TESTCASES:
            if test_case == 'ENABLE_REPLAY_PROTECTION':
                node.setmocktime(ACTIVATION_TIME)
                node.generatetoaddress(11, burn_address)
                continue
            tx = CTransaction()
            num_inputs = len(test_case['sig_hash_types'])
            spent_outputs = spendable_outputs[:num_inputs]
            del spendable_outputs[:num_inputs]
            assert spent_outputs
            total_input_amount = sum(output.nValue for output in spent_outputs)
            max_output_amount = (total_input_amount - fee) // test_case['outputs']
            for i in range(test_case['outputs']):
                output_amount = max_output_amount - i * 77
                output_script = CScript([OP_HASH160, i.to_bytes(20, 'big'), OP_EQUAL])
                tx.vout.append(CTxOut(output_amount, output_script))
            for _ in test_case['sig_hash_types']:
                tx.vin.append(CTxIn(COutPoint(int(tx_fan_out.hash, 16), utxo_idx), CScript()))
                utxo_idx += 1
            for i, sig_hash_type in enumerate(test_case['sig_hash_types']):
                sighash = SignatureHashBIP341(
                    tx_to=tx,
                    spent_utxos=spent_outputs,
                    sig_hash_type=sig_hash_type,
                    input_index=i,
                    executed_script_hash=hashlib.sha256(executed_scripts[key_idx]).digest(),
                    codeseparator_pos=test_case.get('codesep', 0xffff_ffff),
                )
                signature = private_keys[key_idx].sign_ecdsa(sighash)
                signature += bytes([test_case.get('suffix', sig_hash_type & 0xff)])
                if test_case.get('opcodes'):
                    tx.vin[i].scriptSig = CScript([signature, executed_scripts[key_idx]])
                elif test_case.get('is_p2pk'):
                    tx.vin[i].scriptSig = CScript([signature])
                else:
                    tx.vin[i].scriptSig = CScript([signature, public_keys[key_idx].get_bytes()])
                key_idx += 1
            tx.rehash()
            if 'error' not in test_case:
                node.p2p.send_txs_and_test([tx], node)
            else:
                node.p2p.send_txs_and_test([tx], node, success=False, reject_reason=test_case['error'])


if __name__ == '__main__':
    Bip341Sighash().main()
