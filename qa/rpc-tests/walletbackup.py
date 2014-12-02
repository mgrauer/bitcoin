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
from shutil import rmtree, copyfile

class WalletBackupTest (BitcoinTestFramework):

    def setup_chain(self):
        print("Initializing test directory "+self.options.tmpdir)
        initialize_chain_clean(self.options.tmpdir, 4)

    def setup_network(self, split=False):
        self.nodes = start_nodes(4, self.options.tmpdir)
        connect_nodes_bi(self.nodes,0,1)
        connect_nodes_bi(self.nodes,1,2)
        connect_nodes_bi(self.nodes,2,3)
        self.is_network_split=False
        self.sync_all()

    def stop_all(self):
        stop_nodes(self.nodes[0:4])
        wait_bitcoinds()

    def remove_node3_chain(self):
        # set node 3 (2 with zero indexing) to have no chain
        regtestdir = os.path.join(self.options.tmpdir, "node"+str(2), "regtest")
        shutil.rmtree(os.path.join(regtestdir, "blocks"))
        shutil.rmtree(os.path.join(regtestdir, "chainstate"))

    def print_balances(self):
        print "node0: ", self.nodes[0].getbalance()
        print "node1: ", self.nodes[1].getbalance()
        print "node2: ", self.nodes[2].getbalance()
        print "node3: ", self.nodes[3].getbalance()

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
        # Must sync mempools so that the miner knows about the transactions.
        sync_mempools(self.nodes)
        self.nodes[3].setgenerate(True, 1)

    def run_test (self):
        # Test case involves 4 nodes.
        # 1 2 3 and send transactions between each other,
        # 4 is a miner.

        # 1 2 3 and each mine a block to start, then
        # miner creates 100 blocks so 1 2 3 each have 50 mature
        # coins to spend.
        self.nodes[0].setgenerate(True, 1)
        self.sync_all()
        self.nodes[1].setgenerate(True, 1)
        self.sync_all()
        self.nodes[2].setgenerate(True, 1)
        self.sync_all()
        self.nodes[3].setgenerate(True, 100)
        self.sync_all()

        def assert_balances(nodes, balances):
            for i, node in enumerate(nodes):
                assert_equal(node.getbalance(), balances[i])

        assert_balances(self.nodes, [50]*3 + [0])
        print "Balances after initialization"
        self.print_balances()

        # Five rounds of the spenders sending each other transactions.
        print "Creating first set of 5 rounds of transactions..."
        for i in range(5):
            self.do_one_round()
        print "Balances after first set of txns..."
        self.print_balances()

        #Backing up..."
        tmpdir = self.options.tmpdir
        self.nodes[0].backupwallet(tmpdir + "/node0/wallet.bak")
        self.nodes[0].dumpwallet(tmpdir + "/node0/wallet.dump")
        self.nodes[1].backupwallet(tmpdir + "/node1/wallet.bak")
        self.nodes[1].dumpwallet(tmpdir + "/node1/wallet.dump")
        self.nodes[2].backupwallet(tmpdir + "/node2/wallet.bak")
        self.nodes[2].dumpwallet(tmpdir + "/node2/wallet.dump")

        # Then another set of 5 rounds of transactions.
        print "Creating second set of 5 rounds of transactions..."
        for i in range(5):
            self.do_one_round()
        print "Balances after second set of txns..."
        self.print_balances()


        # Generate 101 more blocks, so any fees paid mature
        self.nodes[3].setgenerate(True, 101)

        balance0 = self.nodes[0].getbalance()
        balance1 = self.nodes[1].getbalance()
        balance2 = self.nodes[2].getbalance()
        balance3 = self.nodes[3].getbalance()
        total = balance0 + balance1 + balance2 + balance3
        print "Total: ", total
        self.print_balances()

        ##
        # Test restoring spender wallets from backups
        ##

        self.stop_all()
        os.remove(tmpdir + "/node0/regtest/wallet.dat")
        os.remove(tmpdir + "/node1/regtest/wallet.dat")
        os.remove(tmpdir + "/node2/regtest/wallet.dat")
        # erasing node3's blockchain to ensure that when a node is recovered it
        # will correctly get the blockchain from the network if needed.
        self.remove_node3_chain()

        # restore wallets from backup
        for i in range(3):
            backup = tmpdir + "/node" + str(i) + "/wallet.bak"
            wallet = tmpdir + "/node" + str(i) + "/regtest/wallet.dat"
            print "copying", backup, wallet
            shutil.copyfile(backup, wallet)

        self.setup_network()
        sync_blocks(self.nodes)
        print "Balances after restoration of spender wallets from backups and restart"
        self.print_balances()

        ##
        # Test restoring spender wallets via importing dumps
        ##

        self.stop_all()
        for i in range(3):
            wallet = tmpdir + "/node" + str(i) + "/regtest/wallet.dat"
            os.remove(wallet)
        self.remove_node3_chain()
        self.setup_network()
        sync_blocks(self.nodes)

        print "Balances after erasure of spender wallets and restart"
        self.print_balances()

        # import spender wallets from dumps
        for i, node in enumerate(self.nodes[0:3]):
            dump = tmpdir + "/node" + str(i) + "/wallet.dump"
            print dump
            node.importwallet(dump)
        sync_blocks(self.nodes)

        print "Balances after importing spender wallets"
        self.print_balances()

        assert_equal(5700, sum([node.getbalance() for node in self.nodes]))


if __name__ == '__main__':
    WalletBackupTest().main()
