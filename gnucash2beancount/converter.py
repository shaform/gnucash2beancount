import re
import decimal

import gnucash
from beancount.core.account_types import DEFAULT_ACCOUNT_TYPES
from beancount.core import data

from . import gnucash_utils as gnc_utils
from .printer import CostBasedPosting

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
            is_currency = gnc_acct.GetCommodity().get_namespace() == 'CURRENCY'
            gnc_amount = split.GetAmount()
            acct = acct_map[gnc_acct.GetGUID().to_string()]
            amount = Converter.normalize_numeric(gnc_amount)
            units = data.Amount(amount, acct.currencies[0])
            split_flag = None
            if acct.currencies[0] != base_currency:
                total_cost = data.Amount(
                    abs(Converter.normalize_numeric(split.GetValue())),
                    base_currency)
                num_units = abs(gnc_amount.to_double())
                if num_units == 0.:
                    cost = price = None
                else:
                    price = data.Amount(
                        decimal.Decimal(
                            float(split.GetValue().to_double()) /
                            float(gnc_amount.to_double())), base_currency)
                    if amount > 0 and not is_currency:
                        cost = data.Cost(price, base_currency,
                                         txn.GetDate().date(), None)
                    elif amount < 0 and not is_currency:
                        cost = data.Cost(price, base_currency,
                                         None, None)
                    else:
                        cost = None
                postings.append(
                    CostBasedPosting(acct.account, units, cost, price,
                                     total_cost, split_flag, split_meta))
            else:
                cost = price = None
                postings.append(
                    data.Posting(acct.account, units, cost, price, split_flag,
                                 split_meta))
        return data.Transaction(meta, date, flag, payee, narration, None, None,
                                postings)

    @staticmethod
    def convert_price(name, currency, gnc_price):
        meta = {}
        v = gnc_price.get_value()
        gv = gnucash.gnucash_business.GncNumeric(instance=v)
        price = Converter.normalize_numeric(gv)
        amount = data.Amount(price, currency)
        date = gnc_price.get_time64().strftime('%Y-%m-%d')
        return data.Price(meta, date, Converter.normalize_commodity(name),
                          amount)

    @staticmethod
    def normalize_commodity(name):
        assert len(name) >= 1
        if len(name) == 1:
            name = "X" + name
        if name[0] >= "0" and name[0] <= "9":
            name = "X" + name
        if name[-1] >= "0" and name[-1] <= "9":
            name = name + "X"
        return name

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
        gnc_commodities = {}
        for acct in gnc_accts:
            gnc_commodity = acct.GetCommodity()
            ns = gnc_commodity.get_namespace()
            name = gnc_commodity.get_mnemonic()
            if (ns, name) not in used_commodities:
                used_commodities.add((ns, name))
                gnc_commodities[name] = gnc_commodity

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
        return commodities, gnc_commodities

    def convert(self, currency):
        book = self.book
        entries = [
            'option "operating_currency" "%s"' % currency,
            'option "inferred_tolerance_default" "*:0.000001"',
            'option "booking_method" "FIFO"',
        ]

        txns = gnc_utils.get_all_transactions(book)
        first_date = txns[0].GetDate().strftime('%Y-%m-%d')

        # convert accounts
        gnc_accts = gnc_utils.get_all_accounts(book)
        accts = [Converter.convert_account(gnc_acct) for gnc_acct in gnc_accts]

        # convert commodities
        commodities, gnc_commodities = Converter.collect_commodities(
            book, gnc_accts, first_date)

        # add commodities
        entries.append('* Commodities')
        entries.extend(commodities)
        # add accounts
        entries.append('* Accounts')
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
            entries.append('** %s' % acct_name)
            entries.extend(postings)

        # convert prices
        entries.append('* Prices')
        gnc_currency = gnc_commodities[currency]
        price_db = book.get_price_db()
        for name, gnc_commodity in sorted(gnc_commodities.items(),
                                          key=lambda x: x[0]):
            if gnc_commodity is gnc_currency:
                continue
            gnc_prices = price_db.get_prices(gnc_commodity, gnc_currency)
            if not gnc_prices:
                continue
            entries.append('** %s' % name)
            for gnc_price in sorted(gnc_prices, key=lambda x: x.get_time64()):
                price = Converter.convert_price(name, currency, gnc_price)
                entries.append(price)

        return entries
