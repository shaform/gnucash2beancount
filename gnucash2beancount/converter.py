import re
import decimal

import gnucash
from beancount.core.account_types import DEFAULT_ACCOUNT_TYPES
from beancount.core import data

from . import gnucash_utils as gnc_utils

ACCOUNT_TYPES_MAP = {
    gnucash.ACCT_TYPE_ASSET: DEFAULT_ACCOUNT_TYPES.assets,
    gnucash.ACCT_TYPE_BANK: DEFAULT_ACCOUNT_TYPES.assets,
    gnucash.ACCT_TYPE_CASH: DEFAULT_ACCOUNT_TYPES.assets,
    gnucash.ACCT_TYPE_CHECKING: DEFAULT_ACCOUNT_TYPES.assets,
    gnucash.ACCT_TYPE_CREDIT: DEFAULT_ACCOUNT_TYPES.liabilities,
    gnucash.ACCT_TYPE_EQUITY: DEFAULT_ACCOUNT_TYPES.equity,
    gnucash.ACCT_TYPE_EXPENSE: DEFAULT_ACCOUNT_TYPES.expenses,
    gnucash.ACCT_TYPE_INCOME: DEFAULT_ACCOUNT_TYPES.income,
    gnucash.ACCT_TYPE_LIABILITY: DEFAULT_ACCOUNT_TYPES.liabilities,
    gnucash.ACCT_TYPE_MUTUAL: DEFAULT_ACCOUNT_TYPES.assets,
    gnucash.ACCT_TYPE_PAYABLE: DEFAULT_ACCOUNT_TYPES.liabilities,
    gnucash.ACCT_TYPE_RECEIVABLE: DEFAULT_ACCOUNT_TYPES.assets,
    gnucash.ACCT_TYPE_STOCK: DEFAULT_ACCOUNT_TYPES.assets,
    gnucash.ACCT_TYPE_TRADING: DEFAULT_ACCOUNT_TYPES.assets,
}


class Converter(object):
    def __init__(self, book):
        self.book = book

    @staticmethod
    def convert_full_name(account):
        """convert_full_name.

        :param name:
        """
        name = account.get_full_name()
        full_name = name.replace('.', ':')
        full_name = re.sub(' +', '-', full_name)
        full_name = re.sub('-*/-*', '-', full_name)
        full_name = re.sub('-*@-*', '-at-', full_name)

        # shouldn't have invalid types
        acct_type = ACCOUNT_TYPES_MAP[account.GetType()]
        top_name = full_name.split(':', 1)[0]
        if top_name != acct_type:
            full_name = acct_type + ':' + full_name

        return full_name

    @staticmethod
    def convert_account(account):
        meta = {'description': account.GetDescription()}
        gnc_commodity = account.GetCommodity()
        if gnc_commodity is None:
            commodity = None
        else:
            commodity = [
                Converter.normalize_commodity(gnc_commodity.get_mnemonic())
            ]
        splits = account.GetSplitList()
        if len(splits) == 0:
            import datetime
            date = datetime.datetime.today().strftime('%Y-%m-%d')
        else:
            date = splits[0].GetParent().GetDate().strftime('%Y-%m-%d')
        name = Converter.convert_full_name(account)
        return data.Open(meta, date, name, commodity, None)

    @staticmethod
    def convert_transaction(txn, acct_map):
        meta = {}
        date = txn.GetDate().strftime('%Y-%m-%d')
        flag = '*'
        payee = ''
        narration = txn.GetDescription()
        base_currency = txn.GetCurrency().get_mnemonic()

        postings = []
        for split in txn.GetSplitList():
            split_meta = {}
            memo = split.GetMemo()
            if memo:
                split_meta['memo'] = memo
            gnc_acct = split.GetAccount()
            gnc_amount = split.GetAmount()
            acct = acct_map[gnc_acct.GetGUID().to_string()]
            units = data.Amount(Converter.normalize_numeric(gnc_amount),
                                acct.currencies[0])
            cost = price = split_flag = None
            if acct.currencies[0] != base_currency:
                price = data.Amount(
                    Converter.normalize_numeric(split.GetSharePrice()),
                    base_currency)
            postings.append(
                data.Posting(acct.account, units, cost, price, split_flag,
                             split_meta))
        return data.Transaction(meta, date, flag, payee, narration, None, None,
                                postings)

    @staticmethod
    def normalize_commodity(name):
        return re.sub('[0-9]', 'X', name)

    @staticmethod
    def normalize_numeric(num):
        s = num.to_string()
        if s.startswith('-'):
            s = s[1:]
            neg = True
        else:
            neg = False

        if '/' in s:
            a, b = s.split('/')
            dec = decimal.Decimal(a) / decimal.Decimal(b)
        else:
            dec = decimal.Decimal(s)

        if neg:
            dec = -dec
        return dec

    @staticmethod
    def collect_commodities(book, gnc_accts, date):

        used_commodities = set()
        for acct in gnc_accts:
            gnc_commodity = acct.GetCommodity()
            ns = gnc_commodity.get_namespace()
            name = gnc_commodity.get_mnemonic()
            used_commodities.add((ns, name))

        tbl = book.get_table()
        commodities = []
        for ns in tbl.get_namespaces():
            for gnc_commodity in tbl.get_commodities(ns):
                name = gnc_commodity.get_mnemonic()
                if (ns, name) in used_commodities:
                    name = Converter.normalize_commodity(name)
                    meta = {
                        'export': '%s:%s' % (ns, name),
                        'name': gnc_commodity.get_fullname(),
                        'price': 'USD:yahoo/%s' % name
                    }
                    commodities.append(data.Commodity(meta, date, name))
        return commodities

    def convert(self, currency):
        book = self.book
        entries = ['option "operating_currency" "%s"\n' % currency]

        txns = gnc_utils.get_all_transactions(book)
        first_date = txns[0].GetDate().strftime('%Y-%m-%d')

        # convert accounts
        gnc_accts = gnc_utils.get_all_accounts(book)
        accts = [Converter.convert_account(gnc_acct) for gnc_acct in gnc_accts]

        # convert commodities
        commodities = Converter.collect_commodities(book, gnc_accts,
                                                    first_date)

        # add commodities
        entries.append('* Commodities\n\n')
        entries.extend(commodities)
        # add accounts
        entries.append('* Accounts\n\n')
        entries.extend(accts)

        # convert transactions
        acct_map = {
            gnc_acct.GetGUID().to_string(): acct
            for gnc_acct, acct in zip(gnc_accts, accts)
        }
        acct_txns = {acct.account: [] for acct in accts}
        for txn in txns:
            main_acct = gnc_utils.get_main_account(txn)
            acct = acct_map[main_acct.GetGUID().to_string()]
            acct_txns[acct.account].append(
                Converter.convert_transaction(txn, acct_map))

        for acct_name, postings in sorted(acct_txns.items(),
                                          key=lambda x: x[0]):
            entries.append('** %s\n' % acct_name)
            entries.extend(postings)

        # TODO: handle prices

        return entries
