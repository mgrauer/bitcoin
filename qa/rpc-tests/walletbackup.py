#!/usr/bin/env python
# Copyright (c) 2014 The Bitcoin Core developers
# Distributed under the MIT/X11 software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

#
# Exercise the wallet backup code.  Ported from walletbackup.sh.
#
#

from test_framework import BitcoinTestFramework
from util import *
from random import randint
import time

class WalletBackupTest (BitcoinTestFramework):

    def setup_chain(self):
        print("Initializing test directory "+self.options.tmpdir)
        initialize_chain_clean(self.options.tmpdir, 4)

    def setup_network(self, split=False):
        # nodes 1, 2,3 are spenders, let's give them a keypool=100
        # node 3 is the miner, give him keypool=1 (hard-coded into the utility function)
        extra_args = [["-keypool=100"], ["-keypool=100"], ["-keypool=100"], []]
        self.nodes = start_nodes(4, self.options.tmpdir, extra_args)
        connect_nodes(self.nodes[0], 3)
        connect_nodes(self.nodes[1], 3)
        connect_nodes(self.nodes[2], 0)
        self.is_network_split=False
        self.sync_all()

    def stop_all(self):
        stop_nodes(self.nodes[0:4])
        wait_bitcoinds()

    def one_send(self, from_node, to_address):
        if (randint(1,2) == 1):
            amount = Decimal(randint(1,10)) / Decimal(10)
            self.nodes[from_node].sendtoaddress(to_address, amount)

    def do_one_round(self):
        a0 = self.nodes[0].getnewaddress()
        a1 = self.nodes[1].getnewaddress()
        a2 = self.nodes[2].getnewaddress()

        self.one_send(0, a1)
        self.one_send(0, a2)
        self.one_send(1, a0)
        self.one_send(1, a2)
        self.one_send(2, a0)
        self.one_send(2, a1)

        # Have the miner (node3) mine a block.
        # Must sync mempools before mining.
        sync_mempools(self.nodes)
        self.nodes[3].setgenerate(True, 1)

    def start_three(self):
        self.nodes[0] = start_node(0, self.options.tmpdir)
        self.nodes[1] = start_node(1, self.options.tmpdir)
        self.nodes[2] = start_node(2, self.options.tmpdir)
        connect_nodes(self.nodes[0], 3)
        connect_nodes(self.nodes[1], 3)
        connect_nodes(self.nodes[2], 0)

    def stop_three(self):
        stop_node(self.nodes[0], 0)
        stop_node(self.nodes[1], 1)
        stop_node(self.nodes[2], 2)

    def erase_three(self):
        os.remove(self.options.tmpdir + "/node0/regtest/wallet.dat")
        os.remove(self.options.tmpdir + "/node1/regtest/wallet.dat")
        os.remove(self.options.tmpdir + "/node2/regtest/wallet.dat")

    def run_test (self):

        print "Generating initial blockchain..."
        self.nodes[0].setgenerate(True, 1)
        self.sync_all()
        self.nodes[1].setgenerate(True, 1)
        self.sync_all()
        self.nodes[2].setgenerate(True, 1)
        self.sync_all()
        self.nodes[3].setgenerate(True, 100)
        self.sync_all()

        assert_equal(self.nodes[0].getbalance(), 50)
        assert_equal(self.nodes[1].getbalance(), 50)
        assert_equal(self.nodes[2].getbalance(), 50)
        assert_equal(self.nodes[3].getbalance(), 0)

        print "Creating transactions..."
        # Five rounds of sending each other transactions.
        for i in range(5):
            self.do_one_round()

        print "Backing up..."
        tmpdir = self.options.tmpdir
        self.nodes[0].backupwallet(tmpdir + "/node0/wallet.bak")
        self.nodes[0].dumpwallet(tmpdir + "/node0/wallet.dump")
        self.nodes[1].backupwallet(tmpdir + "/node1/wallet.bak")
        self.nodes[1].dumpwallet(tmpdir + "/node1/wallet.dump")
        self.nodes[2].backupwallet(tmpdir + "/node2/wallet.bak")
        self.nodes[2].dumpwallet(tmpdir + "/node2/wallet.dump")

        print "More transactions..."
        for i in range(5):
            self.do_one_round()

        # Generate 101 more blocks, so any fees paid mature
        self.nodes[3].setgenerate(True, 101)
        self.sync_all()

        balance0 = self.nodes[0].getbalance()
        balance1 = self.nodes[1].getbalance()
        balance2 = self.nodes[2].getbalance()
        balance3 = self.nodes[3].getbalance()
        total = balance0 + balance1 + balance2 + balance3

        # At this point, there are 214 blocks (103 for setup, then 10 rounds, then 101.)
        # 114 are mature, so the sum of all wallets should be 114 * 50 = 5700.
        assert_equal(total, 5700)

        ##
        # Test restoring spender wallets from backups
        ##
        print "Restoring using wallet.dat.."

        self.stop_three()
        self.erase_three()

        # Start node2 with no chain
        shutil.rmtree(self.options.tmpdir + "/node2/regtest/blocks")
        shutil.rmtree(self.options.tmpdir + "/node2/regtest/chainstate")

        # Restore wallets from backup
        shutil.copyfile(tmpdir + "/node0/wallet.bak", tmpdir + "/node0/regtest/wallet.dat")
        shutil.copyfile(tmpdir + "/node1/wallet.bak", tmpdir + "/node1/regtest/wallet.dat")
        shutil.copyfile(tmpdir + "/node2/wallet.bak", tmpdir + "/node2/regtest/wallet.dat")

        print "Re-starting nodes.."
        self.start_three()
        sync_blocks(self.nodes)

        assert_equal(self.nodes[0].getbalance(), balance0)
        assert_equal(self.nodes[1].getbalance(), balance1)
        assert_equal(self.nodes[2].getbalance(), balance2)

        print "Restoring using dumped wallet.."
        self.stop_three()
        self.erase_three()

        #start node2 with no chain
        shutil.rmtree(self.options.tmpdir + "/node2/regtest/blocks")
        shutil.rmtree(self.options.tmpdir + "/node2/regtest/chainstate")

        self.start_three()

        assert_equal(self.nodes[0].getbalance(), 0)
        assert_equal(self.nodes[1].getbalance(), 0)
        assert_equal(self.nodes[2].getbalance(), 0)

        self.nodes[0].importwallet(tmpdir + "/node0/wallet.dump")
        self.nodes[1].importwallet(tmpdir + "/node1/wallet.dump")
        self.nodes[2].importwallet(tmpdir + "/node2/wallet.dump")

        sync_blocks(self.nodes)

        assert_equal(self.nodes[0].getbalance(), balance0)
        assert_equal(self.nodes[1].getbalance(), balance1)
        assert_equal(self.nodes[2].getbalance(), balance2)



if __name__ == '__main__':
    WalletBackupTest().main()
