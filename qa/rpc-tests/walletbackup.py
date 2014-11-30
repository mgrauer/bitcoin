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

    def initialize_wallet_paths(self):
        self.wallet_paths = []
        self.wallet_dumps = []
        self.wallet_backups = []
        for i, node in enumerate(self.nodes[0:3]):
            datadir = os.path.join(self.options.tmpdir, "node"+str(i))
            self.wallet_paths.append(os.path.join(datadir, "regtest", "wallet.dat"))
            self.wallet_dumps.append(os.path.join(datadir, "wallet.dump"))
            self.wallet_backups.append(os.path.join(datadir, "wallet.bak"))

    def erase_spender_wallets(self):
        for i in range(3):
            os.remove(self.wallet_paths[i])

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

    def one_send(self, from_node, to_node, addresses):
        if (randint(1,2) == 1):
            amount = Decimal(randint(1,10)) / Decimal(10)
            to_address = addresses[to_node]
            txnid = self.nodes[from_node].sendtoaddress(to_address, amount)
            return (from_node, to_node, amount, self.nodes[from_node].gettransaction(txnid)['fee'])
        else:
            return (from_node, to_node, 0, 0)

    def do_one_round(self):
        addresses = [node.getnewaddress() for node in self.nodes[0:3]]
        # each spender node gets a chance to send BTC to the other two nodes
        txns = [self.one_send(from_ind, to_ind, addresses) for from_ind in range(3) for to_ind in range(3) if from_ind != to_ind]

        # Have the miner mine a block, it will get fees from the txns upon maturity
        self.nodes[3].setgenerate(True, 1)
        return txns

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

        self.initialize_wallet_paths()

        # Five rounds of the spenders sending each other transactions.
        print "Creating first set of 5 rounds of transactions..."

        txn_fees = []
        for i in range(5):
            txn_fees.extend(self.do_one_round())

        # add up the txn amounts and fees from the first round
        from_amounts, to_amounts, fees = [0] * 3, [0] * 3, [0] * 3
        for from_ind, to_ind, amount, fee in txn_fees:
            from_amounts[from_ind] += Decimal(amount)
            to_amounts[to_ind] += Decimal(amount)
            fees[from_ind] += fee

        print "Balances after first set of txns...note that mempools have not been synced"
        self.print_balances()

        # node 4 has 250 BTC from mining the 5 blocks from the 5 rounds of txns
        assert_balances(self.nodes[3:], [250])

        print "Creating second set of 5 rounds of transactions..."

        # Then another set of 5 rounds of transactions.
        txn_fees_2 = []
        for i in range(5):
            txn_fees_2.extend(self.do_one_round())

        # accumulate the txn amounts and fees from the second round
        for from_ind, to_ind, amount, fee in txn_fees_2:
            from_amounts[from_ind] += Decimal(amount)
            to_amounts[to_ind] += Decimal(amount)
            fees[from_ind] += fee

        print "Balances after second set of txns...note that mempools have not been synced"
        self.print_balances()

        # Dump/backup wallets after all txns.  After the txns are complete,
        # the wallets have all addresses associated with the txns.  Even
        # though the wallets do not have the mature balances at the point and
        # have not had their mempools synced before we are backing them up,
        # when we restore the wallets, they will be able
        # to get their mature balances from the blockchain.
        #
        # Spender wallets are backed up using dumpwallet/backupwallet.
        for i, node in enumerate(self.nodes[0:3]):
            node.backupwallet(self.wallet_backups[i])
            node.dumpwallet(self.wallet_dumps[i])

        # ensure same transactions in all mempools so that all txn fees mature
        sync_mempools(self.nodes)

        ## Generate 101 more blocks, so fees paid from all txns mature
        self.nodes[3].setgenerate(True, 101)
        self.sync_all()

        print "Balances after all txn fees have matured"

        self.print_balances()
        mature_balances = [node.getbalance() for node in self.nodes]
        spender_balance_sum = sum(mature_balances[0:3])
        print "fees: ", spender_balance_sum - 150

        fee_total = sum(fees)
        assert(spender_balance_sum > 149.0)
        assert(spender_balance_sum < 150.0)
        # subtract 150 from spender_balance_sum because fees are negative
        assert_equal(fee_total, spender_balance_sum - 150)

        # miner has mined 100 + (2*5) + 101 = 211 blocks
        # 111 of these are mature, yielding 5550 BTC + fees as the fees have now matured
        assert_equal(Decimal(self.nodes[3].getbalance()), Decimal(111 * 50 + -1 * fee_total))

        ##
        # Test restoring spender wallets from backups
        ##

        self.stop_all()
        self.erase_spender_wallets()
        # erasing node3's blockchain to ensure that when a node is recovered it
        # will correctly get the blockchain from the network if needed.
        self.remove_node3_chain()

        # restore wallets from backup
        for i in range(3):
            shutil.copyfile(self.wallet_backups[i], self.wallet_paths[i])

        self.setup_network()
        print "Balances after restoration of spender wallets from backups and restart"
        self.print_balances()

        # assert restored balances are correct
        assert_balances(self.nodes, mature_balances)

        ##
        # Test restoring spender wallets via importing dumps
        ##

        self.stop_all()
        self.erase_spender_wallets()
        self.remove_node3_chain()
        self.setup_network()

        print "Balances after erasure of spender wallets and restart"
        self.print_balances()

        # assert erased and restarted balances are correct
        # spenders should have 0 balances because they do not have their addresses
        # and miner should have the mature value
        erased_balances = [0] * 3 + mature_balances[3:]
        assert_balances(self.nodes, erased_balances)

        # import spender wallets from dumps
        for i, node in enumerate(self.nodes[0:3]):
            node.importwallet(self.wallet_dumps[i])

        print "Balances after importing spender wallets"
        self.print_balances()

        # all nodes should now have their mature balances
        assert_balances(self.nodes, mature_balances)


if __name__ == '__main__':
    WalletBackupTest().main()
