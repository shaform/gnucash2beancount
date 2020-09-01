"""
gnucash_utils.py
===================================
Utils to access GnuCash objects.
"""
import gnucash
from gnucash import gnucash_business


def get_all_transactions(book):
    """get_all_transactions.
    Get all transactions from a GnuCash book.

    :param book:
    """
    query = gnucash.Query()
    query.search_for('Trans')
    query.set_book(book)

    txns = []

    for txn in query.run():
        txns.append(gnucash_business.Transaction(instance=txn))

    query.destroy()

    return txns


def get_all_accounts(book):
    """get_all_accounts.
    Get all accounts from a GnuCash book.

    :param book:
    """
    acct = book.get_root_account()
    accts = acct.get_descendants_sorted()
    # remove placeholder accounts
    # keep only if has splits or is leaf account
    accts = [
        acct for acct in accts
        if len(acct.get_children()) == 0 or len(acct.GetSplitList()) > 0
    ]
    return accts


def get_main_account(txn):
    """get_main_account.

    :param txn:
    """
    main_split = txn.GetSplitList()[0]
    return main_split.GetAccount()
